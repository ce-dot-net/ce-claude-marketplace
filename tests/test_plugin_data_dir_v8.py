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


REAL_DIR = "ace-ce-dot-net-marketplace"  # CC's data dir name for this plugin (p3, DESIGN §10 P-19)


def _reload_no_env(monkeypatch, tmp_path, xdg=None):
    for var in ("CLAUDE_PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT", "XDG_DATA_HOME"):
        monkeypatch.delenv(var, raising=False)
    if xdg:
        monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    monkeypatch.setenv("HOME", str(tmp_path))
    import plugin_data_dir
    return importlib.reload(plugin_data_dir)


def test_root_default_is_real_cc_data_dir(monkeypatch, tmp_path):
    """DESIGN §10 P-19: CLAUDE_PLUGIN_DATA unset -> the real CC dir
    ~/.claude/plugins/data/ace-ce-dot-net-marketplace (not a made-up '.../ace')."""
    mod = _reload_no_env(monkeypatch, tmp_path)
    assert mod.data_root() == tmp_path / ".claude" / "plugins" / "data" / REAL_DIR


def test_root_falls_back_to_xdg_for_dev_runs(monkeypatch, tmp_path):
    """DESIGN §10 P-19: no CLAUDE_PLUGIN_DATA and no installed data dir -> $XDG_DATA_HOME/ace."""
    mod = _reload_no_env(monkeypatch, tmp_path, xdg=tmp_path / "xdg")
    assert mod.data_root() == tmp_path / "xdg" / "ace"


def test_root_prefers_existing_real_dir_over_xdg(monkeypatch, tmp_path):
    """DESIGN §10 P-19 order: the real CC dir first (when it exists), then XDG."""
    real = tmp_path / ".claude" / "plugins" / "data" / REAL_DIR
    real.mkdir(parents=True)
    mod = _reload_no_env(monkeypatch, tmp_path, xdg=tmp_path / "xdg")
    assert mod.data_root() == real


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


# ── round 2 (DESIGN §9 G1, §10 P-19/P-26, §11 A1) ─────────────────────────

def test_v65_project_hash_scheme_removed(pdd):
    """DESIGN §10 P-19: ONLY the prj_ id from ace_context; the v6.5 hash scheme and
    its migration helpers are gone (two schemes = two dirs per project)."""
    for name in ("get_project_hash", "get_project_id", "get_project_data_dir",
                 "get_session_data_dir", "get_plugin_data_base", "lazy_migrate",
                 "archive_on_id_change", "write_metadata"):
        assert not hasattr(pdd, name), "%s must be removed (P-19)" % name


def test_no_v65_scheme_consumers_left():
    """DESIGN §10 P-19: no production module imports the removed helpers (insights
    _resolve_relevance_path reads the project log only); no ACE_MIGRATE_DATA path."""
    plugin = REPO / "plugins" / "ace"
    hits = []
    for f in list(plugin.rglob("*.py")) + list(plugin.rglob("*.sh")):
        if "/tests/" in str(f):
            continue
        t = f.read_text(errors="replace")
        for name in ("get_project_data_dir", "get_project_hash", "ACE_MIGRATE_DATA"):
            if name in t:
                hits.append((str(f.relative_to(plugin)), name))
    assert not hits, hits


def test_pin_backoff_file_at_root(pdd, tmp_path):
    """DESIGN §11 A1: <root>/pin-backoff marks a recent sessions.db lock."""
    p = pdd.pin_backoff_file()
    assert p == tmp_path / "pd" / "pin-backoff"
    assert p.parent.is_dir()


def test_agent_prompt_stash_paths(pdd, tmp_path):
    """DESIGN §9 G1: <session>/agent-prompts/<prompt_id>-<subagent_type>.json."""
    sd = tmp_path / "pd" / "projects" / "prj_1" / "sessions" / "s1"
    assert pdd.agent_prompts_dir("prj_1", "s1") == sd / "agent-prompts"
    f = pdd.agent_prompt_file("prj_1", "s1", "550e8400-e29b", "Explore")
    assert f == sd / "agent-prompts" / "550e8400-e29b-Explore.json"
    assert f.parent.is_dir(), "parent created on demand"


def test_agent_prompt_file_sanitizes_plugin_scoped_type(pdd, tmp_path):
    """Plugin agent types are 'plugin:name' (cc_hooks_reference.md:2551); untrusted ids
    never leave the agent-prompts dir. Writer and reader map the same input identically."""
    f = pdd.agent_prompt_file("prj_1", "s1", "../p", "my-plugin:reviewer")
    root = (tmp_path / "pd" / "projects" / "prj_1" / "sessions" / "s1" / "agent-prompts").resolve()
    assert f.resolve().parent == root
    assert f == pdd.agent_prompt_file("prj_1", "s1", "../p", "my-plugin:reviewer")


def test_project_disabled_flag_path(pdd, tmp_path):
    """DESIGN §10 P-26: <project>/disabled.flag disables ACE for every session of the project."""
    assert pdd.project_disabled_flag("prj_1") == tmp_path / "pd" / "projects" / "prj_1" / "disabled.flag"


def test_is_disabled_checks_session_and_project_flags(pdd):
    """DESIGN §10 P-26: one predicate every hook uses."""
    assert pdd.is_disabled("prj_d", "s1") is False
    pdd.disabled_flag("prj_d", "s1").write_text("x")
    assert pdd.is_disabled("prj_d", "s1") is True
    assert pdd.is_disabled("prj_d", "s2") is False
    f = pdd.project_disabled_flag("prj_d")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x")
    assert pdd.is_disabled("prj_d", "s2") is True


def test_no_tmp_hook_debug_log_anywhere():
    """DESIGN §10 ACE_DEBUG_HOOKS: no /tmp/ace_hook_debug.log in production code; debug
    lines go to <root>/logs/ace-hook-errors.log (grep: 0 hits). Regression guard."""
    plugin = REPO / "plugins" / "ace"
    hits = [str(f.relative_to(plugin)) for ext in ("*.py", "*.sh", "*.json")
            for f in plugin.rglob(ext)
            if "/tests/" not in str(f) and "ace_hook_debug" in f.read_text(errors="replace")]
    assert not hits, hits


def test_live_server_session_pinning_script_deleted():
    """DESIGN §10: shared-hooks/test_session_pinning.py imported the deleted --version
    probe. Regression guard."""
    assert not (REPO / "plugins" / "ace" / "shared-hooks" / "test_session_pinning.py").exists()
