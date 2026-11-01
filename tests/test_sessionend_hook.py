#!/usr/bin/env python3
"""SessionEnd (v8, WP-A): delete THIS session's dir under plugin data — nothing else.

DESIGN §4: "SessionEnd deletes <root>/projects/<project_id>/sessions/<session_id>/ only."
Hard 1.5 s budget for plugin hooks; plugin `timeout` does not raise it
(cc_hooks_reference.md:3578-3586, critic V9/C4). Output is discarded (doc :3574).
v7 swept /tmp/ace-* and .claude/data/logs/ace-patterns-used-* with a jq-parsed
SESSION_ID (critic T21) — replaced by the §4 session dir.

Rewritten from the v6 static-grep tests (which pinned the /tmp file names and an ERR
trap the §3.1 shim no longer has).
"""
import json
import time

from wpa_harness import Env, PROJECT_ID, SCRIPTS

SCRIPT = "ace_sessionend_wrapper.sh"


def _ev(env, sid, cwd=None):
    return {"session_id": sid, "hook_event_name": "SessionEnd", "reason": "other",
            "cwd": str(cwd or env.project), "transcript_path": ""}


def _seed(env, sid):
    d = env.session_dir(sid)
    d.mkdir(parents=True)
    (d / "patterns-used-main.json").write_text("{}")
    (d / "domain-last-main.txt").write_text("python")
    (d / "disabled.flag").write_text("x")
    return d


def test_sessionend_deletes_own_session_dir(tmp_path):
    """DESIGN §4: the session's dir (and everything in it) is removed."""
    env = Env(tmp_path)
    d = _seed(env, "s-end")
    r = env.run(SCRIPT, _ev(env, "s-end"))
    assert r.returncode == 0, r.stderr
    assert not d.exists(), "own session dir must be deleted"


def test_sessionend_keeps_other_sessions_and_project_state(tmp_path):
    """Only <sid>/ goes: sibling sessions, domains.json and the project's relevance log stay."""
    env = Env(tmp_path)
    _seed(env, "s-end")
    other = _seed(env, "s-other")
    domains = env.data / "projects" / PROJECT_ID / "domains.json"
    domains.write_text("[]")
    rel = env.project / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    rel.parent.mkdir(parents=True)
    rel.write_text("{}\n")
    env.run(SCRIPT, _ev(env, "s-end"))
    assert other.exists() and domains.exists() and rel.exists()


def test_sessionend_resolves_project_from_hook_cwd(tmp_path):
    """DESIGN §3.1: no `cd` in shims, Python uses the hook JSON `cwd` (CC may run the
    hook from another dir, doc :402)."""
    env = Env(tmp_path)
    d = _seed(env, "s-cwd")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    r = env.run(SCRIPT, _ev(env, "s-cwd"), cwd=elsewhere)
    assert r.returncode == 0, r.stderr
    assert not d.exists(), "project must be resolved from event cwd, not process cwd"


def test_sessionend_unsafe_session_id_cannot_escape(tmp_path):
    """Hook-supplied ids are untrusted: '../s-victim' must not delete a sibling session."""
    env = Env(tmp_path)
    victim = _seed(env, "s-victim")
    r = env.run(SCRIPT, _ev(env, "../s-victim"))
    assert r.returncode == 0
    assert victim.exists()


def test_sessionend_missing_session_id_is_noop(tmp_path):
    env = Env(tmp_path)
    d = _seed(env, "default")
    r = env.run(SCRIPT, {"hook_event_name": "SessionEnd", "cwd": str(env.project)})
    assert r.returncode == 0
    assert d.exists(), "no session_id -> nothing deleted (never fall back to 'default')"


def test_sessionend_fits_plugin_budget(tmp_path):
    """cc_hooks_reference.md:3578-3586: plugin SessionEnd hooks have a hard 1.5 s budget."""
    env = Env(tmp_path)
    _seed(env, "s-fast")
    t0 = time.monotonic()
    env.run(SCRIPT, _ev(env, "s-fast"))
    assert time.monotonic() - t0 < 1.5


def test_sessionend_hooks_json_timeout_is_5s():
    """DESIGN §3: SessionEnd sync, timeout 5 (seconds)."""
    hooks = json.loads((SCRIPTS.parent / "hooks" / "hooks.json").read_text())["hooks"]
    timeouts = [h.get("timeout") for g in hooks["SessionEnd"] for h in g["hooks"]]
    assert timeouts == [5]
