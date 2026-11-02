#!/usr/bin/env python3
"""v8 Foundation contract C2 (DESIGN §5): ace_cli.run_search / run_learn.

- run_search = exactly ONE `ace-cli search --stdin --json [--pin-session X] [--top-k N]`
  spawn, default timeout 15 s, returns (result_dict_or_None, duration_ms).
- No `--version` probe (check_session_pinning_available is deleted), no `whoami`
  on the success path (auth check only inside the failure branch).
- Failures are logged with the CALLER's hook_event_name (v7 hard-coded
  "UserPromptSubmit" for SubagentStart/PostToolUse failures too).
- run_learn = single `ace-cli learn` spawn, subprocess timeout 300 s, --timeout 300000 (P-18).
- round 2: run_search default timeout 25 (A2); recall_session deleted; ACE_CLIENT_ID (P-8).
subprocess is mocked everywhere: the real ace-cli is never executed.
"""
import importlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))

RESP = {"similar_patterns": [{"id": "ctx-1234567890-abcd", "content": "x"}], "count": 1}


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # relevance log lands in tmp .claude/data/logs
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import ace_cli
    mod = importlib.reload(ace_cli)
    try:
        import ace_relevance_logger
        ace_relevance_logger._logger = None
    except Exception:
        pass
    return mod


def _ok(payload=RESP):
    r = MagicMock()
    r.returncode = 0
    r.stdout = json.dumps(payload).encode()
    r.stderr = b""
    return r


def _fail(stdout=b"", stderr=b"boom"):
    r = MagicMock()
    r.returncode = 1
    r.stdout = stdout
    r.stderr = stderr
    return r


def _relevance(tmp_path):
    p = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def test_check_session_pinning_available_removed(cli):
    assert not hasattr(cli, "check_session_pinning_available")


def test_run_search_single_spawn_minimal_argv(cli):
    with patch("subprocess.run", return_value=_ok()) as run:
        result, ms = cli.run_search("fix auth bug", hook_event_name="UserPromptSubmit")
    assert run.call_count == 1, "exactly one spawn; no --version / whoami probes"
    assert run.call_args.args[0] == ["ace-cli", "search", "--stdin", "--json"]
    assert run.call_args.kwargs["timeout"] == 25, "DESIGN §11 A2: run_search default timeout 25 s"
    assert run.call_args.kwargs["input"] == "fix auth bug".encode()
    assert result == RESP
    assert isinstance(ms, int) and ms >= 0


def test_run_search_pin_session_and_top_k(cli):
    with patch("subprocess.run", return_value=_ok()) as run:
        cli.run_search("q", session_id="tsid-1", top_k=8, hook_event_name="PostToolUse")
    assert run.call_args.args[0] == [
        "ace-cli", "search", "--stdin", "--json", "--pin-session", "tsid-1", "--top-k", "8"]


def test_run_search_top_k_only(cli):
    with patch("subprocess.run", return_value=_ok()) as run:
        cli.run_search("q", top_k=8, hook_event_name="PostToolUse")
    assert run.call_args.args[0] == ["ace-cli", "search", "--stdin", "--json", "--top-k", "8"]


def test_run_search_custom_timeout(cli):
    with patch("subprocess.run", return_value=_ok()) as run:
        cli.run_search("q", timeout=7, hook_event_name="SubagentStart")
    assert run.call_args.kwargs["timeout"] == 7


def test_run_search_no_whoami_or_version_on_success(cli):
    with patch("subprocess.run", return_value=_ok()) as run:
        cli.run_search("q", session_id="s", hook_event_name="UserPromptSubmit")
    for c in run.call_args_list:
        argv = c.args[0]
        assert "whoami" not in argv and "--version" not in argv


def test_run_search_invalid_json_returns_none_and_logs_hook(cli, tmp_path):
    bad = MagicMock(returncode=0, stdout=b"{ nope", stderr=b"")
    with patch("subprocess.run", return_value=bad):
        result, ms = cli.run_search("q", hook_event_name="SubagentStart")
    assert result is None and isinstance(ms, int)
    errs = [e for e in _relevance(tmp_path) if e.get("event") == "error"]
    assert errs and errs[-1]["hook"] == "SubagentStart"


def test_run_search_nonzero_exit_logs_passed_hook(cli, tmp_path):
    with patch("subprocess.run", return_value=_fail()):
        result, _ = cli.run_search("q", hook_event_name="PostToolUse")
    assert result is None
    errs = [e for e in _relevance(tmp_path) if e.get("event") == "error"]
    assert errs, "non-zero exit must be logged"
    assert errs[-1]["hook"] == "PostToolUse", "must not hard-code UserPromptSubmit"
    assert errs[-1]["timestamp"].endswith("Z")


def test_run_search_timeout_logs_passed_hook(cli, tmp_path):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ace-cli", 15)):
        result, ms = cli.run_search("q", hook_event_name="SubagentStart")
    assert isinstance(result, dict) and result.get("error") == "timeout"
    assert isinstance(ms, int)
    errs = [e for e in _relevance(tmp_path) if e.get("event") == "error"]
    assert errs and errs[-1]["hook"] == "SubagentStart"


def test_run_search_auth_failure_structured(cli):
    with patch("subprocess.run", return_value=_fail(stdout=b'{"error":"Not logged in"}', stderr=b"")):
        result, _ = cli.run_search("q", hook_event_name="UserPromptSubmit")
    assert result == {"error": "not_authenticated",
                      "message": "Not logged in. Run /ace-login first."}


def test_run_search_cli_missing(cli):
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result, _ = cli.run_search("q", hook_event_name="UserPromptSubmit")
    assert result.get("error") == "cli_not_found"


def test_run_search_keyword_only_options(cli):
    """C2 signature: everything after `query` is keyword-only."""
    with patch("subprocess.run", return_value=_ok()):
        with pytest.raises(TypeError):
            cli.run_search("q", "org", "prj", "sess")


# ── run_learn ──

def test_run_learn_single_spawn_timeout_300(cli):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        path = cmd[cmd.index("--transcript") + 1]
        seen["path"] = path
        seen["trace"] = json.loads(Path(path).read_text())
        return MagicMock(returncode=0, stdout='{"learning_statistics": {}}', stderr="")

    with patch("subprocess.run", side_effect=fake_run) as run:
        result, ms = cli.run_learn({"task": "t"}, retrieval_id="r-1",
                                   applied_log_ids=[3, 4], hook_event_name="Stop")
    assert run.call_count == 1
    assert seen["cmd"][:2] == ["ace-cli", "learn"]
    assert "--json" in seen["cmd"]
    assert seen["kw"]["timeout"] == 300, "DESIGN §10 P-18: run_learn(timeout=300)"
    k = seen["cmd"].index("--timeout")
    assert seen["cmd"][k + 1] == "300000", "DESIGN §10 P-18: ace-cli --timeout 300000 (one source of truth)"
    assert "--pin-session" not in seen["cmd"], "DESIGN §11 A1: run_learn never pins"
    i = seen["cmd"].index("--retrieval-id")
    assert seen["cmd"][i + 1] == "r-1"
    j = seen["cmd"].index("--applied-log-ids")
    assert seen["cmd"][j + 1] == "3,4"
    assert seen["trace"] == {"task": "t"}
    assert not Path(seen["path"]).exists(), "temp trace file removed after the spawn"
    assert result == {"learning_statistics": {}}
    assert isinstance(ms, int)


def test_run_learn_omits_f080_flags_when_absent(cli):
    with patch("subprocess.run",
               return_value=MagicMock(returncode=0, stdout="{}", stderr="")) as run:
        cli.run_learn({"task": "t"}, hook_event_name="SubagentStop")
    cmd = run.call_args.args[0]
    assert "--retrieval-id" not in cmd and "--applied-log-ids" not in cmd


def test_run_learn_failure_logs_passed_hook(cli, tmp_path):
    with patch("subprocess.run",
               return_value=MagicMock(returncode=1, stdout="", stderr="x")):
        result, _ = cli.run_learn({"task": "t"}, hook_event_name="SubagentStop")
    assert result is None
    errs = [e for e in _relevance(tmp_path) if e.get("event") == "error"]
    assert errs and errs[-1]["hook"] == "SubagentStop"


# ── round 2 (DESIGN §10/§11) ──

def test_recall_session_deleted(cli):
    """DESIGN §10: dead `recall_session` / `ace-cli cache recall` export removed."""
    assert not hasattr(cli, "recall_session")
    src = (REPO / "plugins" / "ace" / "shared-hooks" / "utils" / "ace_cli.py").read_text()
    assert "'cache', 'recall'" not in src and '"cache", "recall"' not in src


def test_run_learn_timeout_flag_matches_python_timeout_for_custom_value(cli):
    """DESIGN §10 P-18: the --timeout passed to ace-cli equals the Python timeout (ms)."""
    with patch("subprocess.run",
               return_value=MagicMock(returncode=0, stdout="{}", stderr="")) as run:
        cli.run_learn({"task": "t"}, timeout=300, hook_event_name="Stop")
    cmd = run.call_args.args[0]
    assert cmd[cmd.index("--timeout") + 1] == str(run.call_args.kwargs["timeout"] * 1000)


def _plugin_version():
    return json.loads((REPO / "plugins" / "ace" / ".claude-plugin" / "plugin.json").read_text())["version"]


@pytest.mark.parametrize("call", ["search", "learn"])
def test_client_id_env_on_every_spawn(cli, monkeypatch, call):
    """DESIGN §10 P-8: shims no longer source _ace_env.sh, so ace_cli._env() sets
    ACE_CLIENT_ID=claude-code-plugin/<plugin.json version> on every spawn when unset."""
    monkeypatch.delenv("ACE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    with patch("subprocess.run", return_value=_ok() if call == "search" else
               MagicMock(returncode=0, stdout="{}", stderr="")) as run:
        if call == "search":
            cli.run_search("q", session_id="s", hook_event_name="UserPromptSubmit")
        else:
            cli.run_learn({"task": "t"}, hook_event_name="Stop")
    for c in run.call_args_list:
        assert c.kwargs["env"]["ACE_CLIENT_ID"] == "claude-code-plugin/%s" % _plugin_version()


def test_client_id_user_override_kept(cli, monkeypatch):
    """P-8: a user-set ACE_CLIENT_ID is not overwritten."""
    monkeypatch.setenv("ACE_CLIENT_ID", "custom/1")
    with patch("subprocess.run", return_value=_ok()) as run:
        cli.run_search("q", hook_event_name="UserPromptSubmit")
    assert run.call_args.kwargs["env"]["ACE_CLIENT_ID"] == "custom/1"
