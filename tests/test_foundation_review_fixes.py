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


def test_search_retry_respects_deadline(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(k.get("timeout")) or _locked(*a))
    monkeypatch.setattr(ace_cli, "_log_cli_error", lambda *a, **k: None)
    monkeypatch.setattr(ace_cli.time, "sleep", lambda s: None)
    ace_cli.run_search("q", timeout=15)
    assert len(calls) == 2 and calls[1] <= 15
    calls.clear()
    ace_cli.run_search("q", timeout=0.5)  # < 1 s left -> no retry
    assert len(calls) == 1


def test_fallback_root_from_plugin_root(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/h/.claude/plugins/cache/ce-dot-net-marketplace/ace/8.0.0")
    assert pdd.data_root() == tmp_path / ".claude/plugins/data/ace-ce-dot-net-marketplace"
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")
    assert pdd.data_root() == tmp_path / ".claude/plugins/data/ace"


def test_extra_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    assert pdd.domain_last_file("p", "s", "a").name == "domain-last-a.txt"
    assert pdd.tools_db("p", "s").name == "tools.db"
    assert pdd.patterns_used_file("p", "s", None).name == "patterns-used-main.json"
    monkeypatch.setattr(pdd, "ERRORS_LOG_MAX", 10)
    pdd.append_error("x" * 20)
    pdd.append_error("y")
    assert Path(str(pdd.errors_log()) + ".1").exists()
