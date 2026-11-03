#!/usr/bin/env python3
"""WP-G RED — DESIGN §11 A1: run_search pin-drop + backoff (replaces the §8 pinned retry).

p2 (SYNTHESIS §0.1): `ace-cli search --pin-session X` exits 1 with EMPTY stdout and
`SqliteError: database is locked` while the no-pin search succeeds; the lock is held
for hours, so re-running the PINNED command can never succeed. Required:
- pinned spawn + (rc != 0 with 'database is locked' in stderr OR empty stdout)
  -> immediately ONE re-spawn WITHOUT --pin-session; relevance row `pin_failed: true`;
  touch <root>/pin-backoff.
- pin-backoff younger than ACE_PIN_BACKOFF_MIN (default 30) min -> no --pin-session up
  front, relevance row `pin_skipped: "backoff"`.
- --pin-session stays primary when healthy; run_learn never pins.

A real fake `ace-cli` executable (first on PATH) logs argv per call; nothing hits the network.
"""
import importlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

from wpd_harness import HookEnv, flag_value

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))

PATTERN = {"id": "ctx-1234567890-abcd", "content": "use jq -n --arg for hook JSON",
           "section": "strategies", "confidence": 0.9, "helpful": 3, "harmful": 0,
           "cumulative_v15_reward": 1.0, "isAtRisk": False,
           "match_factors": {"bandit_rank": 1, "retrieval_log_id": 7}}
RESPONSE = {"count": 1, "similar_patterns": [PATTERN], "retrieval_id": "ret-pin-1"}

# mode via env ACE_FAKE_PIN_MODE: locked | empty | auth | ok
_FAKE = r'''#!%(py)s
import json, os, sys
argv = sys.argv[1:]
data = sys.stdin.read() if "--stdin" in argv else ""
with open(os.environ["ACE_FAKE_CLI_LOG"], "a") as f:
    f.write(json.dumps({"argv": argv, "stdin": data,
                        "client_id": os.environ.get("ACE_CLIENT_ID")}) + "\n")
mode = os.environ.get("ACE_FAKE_PIN_MODE", "ok")
if argv[:1] == ["search"] and "--pin-session" in argv:
    if mode == "slowlock":
        import time; time.sleep(2.5)
        sys.stderr.write("SqliteError: database is locked\n")
        sys.exit(1)
    if mode == "hang":
        import time; time.sleep(6)
    if mode == "locked":
        sys.stderr.write("SqliteError: database is locked\n    at SessionStorage.cleanupExpiredSessions\n")
        sys.exit(1)
    if mode == "empty":
        sys.exit(0)
    if mode == "auth":
        sys.stderr.write("Error: Not logged in\n")
        sys.exit(1)
if argv[:1] == ["search"]:
    sys.stdout.write(%(resp)r)
else:
    sys.stdout.write("{}")
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    b = tmp_path / "bin"
    b.mkdir()
    cli = b / "ace-cli"
    cli.write_text(_FAKE % {"py": sys.executable, "resp": json.dumps(RESPONSE)})
    cli.chmod(0o755)
    monkeypatch.setenv("PATH", str(b) + os.pathsep + os.environ["PATH"])
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("ACE_FAKE_CLI_LOG", str(log))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.delenv("ACE_PIN_BACKOFF_MIN", raising=False)
    monkeypatch.chdir(tmp_path)
    import plugin_data_dir
    importlib.reload(plugin_data_dir)
    import ace_relevance_logger
    ace_relevance_logger._logger = None
    import ace_cli
    mod = importlib.reload(ace_cli)

    class F:
        cli = mod
        pdd = plugin_data_dir

        @staticmethod
        def calls():
            if not log.exists():
                return []
            return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]

        @staticmethod
        def rows():
            p = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
            return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    return F


def _search(f):
    return [c for c in f.calls() if c["argv"][:1] == ["search"]]


@pytest.mark.parametrize("mode", ["locked", "empty"])
def test_pin_failure_drops_pin_once(fake, monkeypatch, mode):
    """A1: locked stderr / empty stdout on the pinned spawn -> exactly 2 spawns, the
    second WITHOUT --pin-session; patterns are not lost."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", mode)
    result, ms = fake.cli.run_search("fix the hook", session_id="tsid-1",
                                     hook_event_name="UserPromptSubmit")
    calls = _search(fake)
    assert len(calls) == 2, [c["argv"] for c in calls]
    assert flag_value(calls[0]["argv"], "--pin-session") == "tsid-1"
    assert "--pin-session" not in calls[1]["argv"], "fallback must drop --pin-session"
    assert calls[1]["stdin"] == "fix the hook"
    assert isinstance(result, dict) and result.get("similar_patterns"), result
    assert isinstance(ms, int)


def test_pinned_command_is_never_rerun(fake, monkeypatch):
    """A1: the lock is held for hours (p2) -> the §8 'retry the same pinned command'
    must be gone: at most ONE spawn carries --pin-session."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "locked")
    fake.cli.run_search("q", session_id="tsid-1", hook_event_name="UserPromptSubmit")
    pinned = [c for c in _search(fake) if "--pin-session" in c["argv"]]
    assert len(pinned) == 1


def test_pin_failure_logs_pin_failed_and_touches_backoff(fake, monkeypatch):
    """A1: relevance row carries pin_failed: true; <root>/pin-backoff is touched."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "locked")
    fake.cli.run_search("q", session_id="tsid-1", hook_event_name="SubagentStart")
    assert any(r.get("pin_failed") is True for r in fake.rows()), fake.rows()
    assert fake.pdd.pin_backoff_file().exists()


def test_fresh_backoff_skips_pin_up_front(fake, monkeypatch):
    """A1: pin-backoff younger than 30 min -> 1 spawn, no --pin-session, pin_skipped='backoff'."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "locked")
    fake.pdd.pin_backoff_file().touch()
    result, _ = fake.cli.run_search("q", session_id="tsid-2", hook_event_name="UserPromptSubmit")
    calls = _search(fake)
    assert len(calls) == 1 and "--pin-session" not in calls[0]["argv"], [c["argv"] for c in calls]
    assert result and result.get("similar_patterns")
    assert any(r.get("pin_skipped") == "backoff" for r in fake.rows()), fake.rows()


def test_expired_backoff_pins_again(fake):
    """A1: an old backoff (> 5 min, default since SDK 4.3.0) no longer suppresses the pin (healthy path primary)."""
    b = fake.pdd.pin_backoff_file()
    b.touch()
    old = time.time() - 6 * 60
    os.utime(str(b), (old, old))
    fake.cli.run_search("q", session_id="tsid-3", hook_event_name="UserPromptSubmit")
    calls = _search(fake)
    assert len(calls) == 1 and flag_value(calls[0]["argv"], "--pin-session") == "tsid-3"


def test_backoff_window_env_override(fake, monkeypatch):
    """A1: ACE_PIN_BACKOFF_MIN sets the window (10-min-old file, window 5 -> pin again)."""
    monkeypatch.setenv("ACE_PIN_BACKOFF_MIN", "5")
    b = fake.pdd.pin_backoff_file()
    b.touch()
    old = time.time() - 10 * 60
    os.utime(str(b), (old, old))
    fake.cli.run_search("q", session_id="tsid-4", hook_event_name="UserPromptSubmit")
    assert flag_value(_search(fake)[0]["argv"], "--pin-session") == "tsid-4"


def test_healthy_pin_is_single_pinned_spawn(fake):
    """A1: healthy -> exactly one spawn, pinned (task_session_id semantics unchanged); no backoff file."""
    result, _ = fake.cli.run_search("q", session_id="tsid-5", hook_event_name="UserPromptSubmit")
    calls = _search(fake)
    assert len(calls) == 1 and flag_value(calls[0]["argv"], "--pin-session") == "tsid-5"
    assert result.get("similar_patterns")
    assert not fake.pdd.pin_backoff_file().exists()


def test_auth_failure_with_pin_is_not_retried(fake, monkeypatch):
    """A1 applies only to the lock/empty signature: an auth failure is reported, not re-spawned."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "auth")
    result, _ = fake.cli.run_search("q", session_id="tsid-6", hook_event_name="UserPromptSubmit")
    assert len(_search(fake)) == 1
    assert result.get("error") == "not_authenticated"


def test_unpinned_search_never_creates_backoff(fake, monkeypatch):
    """No pin requested -> one spawn, no pin-backoff side effect."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "locked")
    fake.cli.run_search("q", top_k=8, hook_event_name="PostToolUse")
    assert len(_search(fake)) == 1
    assert not fake.pdd.pin_backoff_file().exists()


# ── end to end through the UPS shim (fake ace-cli on PATH, hermetic tmp dirs) ──

def test_ups_injects_patterns_when_pin_store_is_locked(tmp_path):
    """A1 + §9: 'Patterns must never be lost to the pin store' — a locked sessions.db
    still yields additionalContext on the human prompt, and the run logs pin_failed."""
    env = HookEnv(tmp_path, project_id="prj_pin_e2e")
    (env.bin / "ace-cli").write_text(_FAKE % {"py": sys.executable, "resp": json.dumps(RESPONSE)})
    ev = {"session_id": "cc-pin-1", "prompt_id": "pid-pin-1", "cwd": str(env.proj),
          "transcript_path": str(env.tmp / "t.jsonl"), "hook_event_name": "UserPromptSubmit",
          "prompt": "refactor the authentication middleware to use JSON web tokens"}
    proc = env.run("ace_before_task_wrapper.sh", ev, extra_env={"ACE_FAKE_PIN_MODE": "locked"})
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert PATTERN["id"] in out["hookSpecificOutput"]["additionalContext"]
    assert any(r.get("pin_failed") is True for r in env.relevance_rows()), env.relevance_rows()


def test_empty_stdout_retries_but_does_not_touch_backoff(fake, monkeypatch):
    """Empty stdout without lock text (network/5xx/crash): re-run unpinned, but do NOT
    suspend pinning globally for 30 min."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "empty")
    result, _ = fake.cli.run_search("q", session_id="tsid-7", hook_event_name="UserPromptSubmit")
    assert len(_search(fake)) == 2 and result.get("similar_patterns")
    assert not fake.pdd.pin_backoff_file().exists()


def test_retry_skipped_when_under_two_seconds_remain(fake, monkeypatch):
    """A2: lock failure after 2.5 s of a 3 s budget -> no floored retry; backoff still set."""
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "slowlock")
    fake.cli.run_search("q", session_id="tsid-8", timeout=3, hook_event_name="PostToolUse")
    assert len(_search(fake)) == 1
    assert fake.pdd.pin_backoff_file().exists()


def test_pinned_timeout_touches_backoff(fake, monkeypatch):
    monkeypatch.setenv("ACE_FAKE_PIN_MODE", "hang")
    result, _ = fake.cli.run_search("q", session_id="tsid-9", timeout=1, hook_event_name="UserPromptSubmit")
    assert result.get("error") == "timeout"
    assert fake.pdd.pin_backoff_file().exists()


def test_ups_disabled_writes_nothing_before_check(tmp_path):
    """UPS disabled flag is checked before any relevance row / review state is written."""
    env = HookEnv(tmp_path, project_id="prj_dis_ups")
    (env.bin / "ace-cli").write_text(_FAKE % {"py": sys.executable, "resp": json.dumps(RESPONSE)})
    import plugin_data_dir  # noqa
    sd = env.session_dir("cc-dis-1")
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "disabled.flag").write_text("1")
    ev = {"session_id": "cc-dis-1", "prompt_id": "p", "cwd": str(env.proj),
          "transcript_path": str(env.tmp / "t.jsonl"), "hook_event_name": "UserPromptSubmit",
          "prompt": "ok"}  # too-short prompt would normally log a skipped row
    proc = env.run("ace_before_task_wrapper.sh", ev)
    assert proc.returncode == 0 and proc.stdout == ""
    assert env.relevance_rows() == []
