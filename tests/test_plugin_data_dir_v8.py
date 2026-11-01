#!/usr/bin/env python3
"""v8 Foundation (DESIGN §4, contract C3): plugin_data_dir helpers are the ONLY
way to compute ACE state paths. Root = $CLAUDE_PLUGIN_DATA (exported to every
hook process, cc_hooks_reference.md:480) else ~/.claude/plugins/data/ace
(cc_plugins_reference.md:559). Replaces /tmp/ace-* and .claude/data/logs state.
"""
import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))


@pytest.fixture
def pdd(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "pd"))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    import plugin_data_dir
    return importlib.reload(plugin_data_dir)


def test_root_from_env(pdd, tmp_path):
    assert pdd.data_root() == tmp_path / "pd"


def test_root_default_is_claude_plugins_data_ace(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    import plugin_data_dir
    mod = importlib.reload(plugin_data_dir)
    assert mod.data_root() == tmp_path / ".claude" / "plugins" / "data" / "ace"


def test_all_helpers_return_paths(pdd):
    for p in (
        pdd.data_root(), pdd.project_dir("prj_1"), pdd.session_dir("prj_1", "s1"),
        pdd.domains_file("prj_1"), pdd.python_path_file(), pdd.cli_version_file(),
        pdd.search_cache_dir(), pdd.disabled_flag("prj_1", "s1"),
        pdd.learn_lock("prj_1", "s1", "main"), pdd.errors_log(),
    ):
        assert isinstance(p, Path)


def test_layout(pdd, tmp_path):
    r = tmp_path / "pd"
    assert pdd.python_path_file() == r / "python_path"
    assert pdd.cli_version_file() == r / "cli_version.json"
    assert pdd.errors_log() == r / "logs" / "ace-hook-errors.log"
    assert pdd.search_cache_dir() == r / "cache" / "search"
    assert pdd.project_dir("prj_1") == r / "projects" / "prj_1"
    assert pdd.domains_file("prj_1") == r / "projects" / "prj_1" / "domains.json"
    sd = r / "projects" / "prj_1" / "sessions" / "s1"
    assert pdd.session_dir("prj_1", "s1") == sd
    assert pdd.disabled_flag("prj_1", "s1") == sd / "disabled.flag"
    assert pdd.learn_lock("prj_1", "s1", "main") == sd / "learn-inflight-main.lock"
    assert pdd.learn_lock("prj_1", "s1", "agent-x") == sd / "learn-inflight-agent-x.lock"


def test_learn_lock_defaults_agent_to_main(pdd):
    assert pdd.learn_lock("prj_1", "s1", None).name == "learn-inflight-main.lock"
    assert pdd.learn_lock("prj_1", "s1", "").name == "learn-inflight-main.lock"


def test_session_dir_create_flag(pdd):
    p = pdd.session_dir("prj_1", "s-nocreate", create=False)
    assert not p.exists()
    p2 = pdd.session_dir("prj_1", "s-create", create=True)
    assert p2.is_dir()


def test_file_helpers_create_parent_dirs(pdd):
    for f in (pdd.domains_file("prj_2"), pdd.errors_log(), pdd.cli_version_file(),
              pdd.disabled_flag("prj_2", "s2"), pdd.learn_lock("prj_2", "s2", "a")):
        assert f.parent.is_dir(), f"parent of {f} must exist on demand"
    assert pdd.search_cache_dir().is_dir()


def test_nothing_under_tmp_or_claude_logs(pdd):
    for p in (pdd.session_dir("prj_1", "s1"), pdd.errors_log(), pdd.search_cache_dir(),
              pdd.domains_file("prj_1")):
        s = str(p)
        assert not s.startswith("/tmp/ace-") and "/.claude/logs/" not in s


@pytest.mark.parametrize("bad", ["../escape", "a/b", ""])
def test_ids_cannot_escape_root(pdd, tmp_path, bad):
    """Path components from hook JSON are untrusted: they must not escape root."""
    root = (tmp_path / "pd").resolve()
    p = pdd.session_dir("prj_1", bad, create=False).resolve()
    assert root in p.parents
    assert p.parent.name == "sessions"


# ── session-id resolution: hook JSON → CLAUDE_CODE_SESSION_ID → "default" ──

def test_session_id_from_hook_json_wins(pdd, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "env-sess")
    assert pdd.resolve_session_id({"session_id": "json-sess"}) == "json-sess"


def test_session_id_from_env_when_json_missing(pdd, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "env-sess")
    assert pdd.resolve_session_id({}) == "env-sess"
    assert pdd.resolve_session_id({"session_id": ""}) == "env-sess"
    assert pdd.resolve_session_id(None) == "env-sess"


def test_session_id_default(pdd):
    assert pdd.resolve_session_id({}) == "default"
    assert pdd.resolve_session_id(None) == "default"
