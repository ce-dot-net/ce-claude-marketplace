"""Foundation review fixes: learn never retries, retry stays in deadline, data-root fallback, helpers."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))
import ace_cli  # noqa: E402
import plugin_data_dir as pdd  # noqa: E402


def _locked(*a, **k):
    return subprocess.CompletedProcess(a[0], 1, b"", b"database is locked")


def test_learn_does_not_retry_on_lock(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(1) or _locked(*a))
    monkeypatch.setattr(ace_cli, "_log_cli_error", lambda *a, **k: None)
    assert ace_cli.run_learn({"x": 1})[0] is None
    assert len(calls) == 1


def test_search_lock_retry_policy(monkeypatch):
    """DESIGN §11 A1: no same-command retry. Unpinned lock -> 1 spawn; pinned lock -> a
    second spawn WITHOUT --pin-session (inside the deadline)."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a[0], k.get("timeout"))) or _locked(*a))
    monkeypatch.setattr(ace_cli, "_log_cli_error", lambda *a, **k: None)
    monkeypatch.setattr(ace_cli, "_log_pin", lambda *a, **k: None)
    monkeypatch.setattr(ace_cli, "_pin_backoff_active", lambda: False)
    monkeypatch.setattr(ace_cli, "_plugin_dir", lambda: None)
    ace_cli.run_search("q", timeout=15)
    assert len(calls) == 1
    calls.clear()
    ace_cli.run_search("q", session_id="t1", timeout=15)
    assert len(calls) == 2 and "--pin-session" in calls[0][0] and "--pin-session" not in calls[1][0]
    assert calls[1][1] <= 15


def test_fallback_root_from_plugin_root(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/h/.claude/plugins/cache/ce-dot-net-marketplace/ace/8.0.0")
    assert pdd.data_root() == tmp_path / ".claude/plugins/data/ace-ce-dot-net-marketplace"
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert pdd.data_root() == tmp_path / ".claude/plugins/data/ace-ce-dot-net-marketplace"


def test_extra_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    assert pdd.domain_last_file("p", "s", "a").name == "domain-last-a.txt"
    assert pdd.tools_db("p", "s").name == "tools.db"
    assert pdd.patterns_used_file("p", "s", None).name == "patterns-used-main.json"
    monkeypatch.setattr(pdd, "ERRORS_LOG_MAX", 10)
    pdd.append_error("x" * 20)
    pdd.append_error("y")
    assert Path(str(pdd.errors_log()) + ".1").exists()
