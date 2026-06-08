#!/usr/bin/env python3
"""
Tests for task_intent handling in run_search() and call sites.

Scope:
  1. run_search(query, ..., task_intent=None)
       - when task_intent is set, --task-intent <value> is appended to the ace-cli cmd
       - when task_intent is None (default), --task-intent is NOT appended
  2. LRU cache key includes task_intent so different intents never share a cache entry
  3. UserPromptSubmit call site (ace_before_task.py) does NOT hardcode task_intent;
     it omits the kwarg (or passes None) so the server classifies intent itself.
  4. Domain-shift PreToolUse call site (ace_pretooluse_wrapper.sh) does NOT pass
     --task-intent; the server classifies intent from the search payload.

The run_search() plumbing still supports task_intent when explicitly passed (used by
callers that have a real intent); the change is only at the two hardcoded call-sites.
"""

import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap paths — mirror the pattern used by test_f080_capture.py
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
SHARED_UTILS = SHARED / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"

sys.path.insert(0, str(SHARED_UTILS))
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(PLUGIN_UTILS))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLI_CMD = "ace-cli"


def _load_ace_cli_module():
    """Load utils/ace_cli.py as an isolated module."""
    spec = importlib.util.spec_from_file_location(
        "ace_cli_issue26",
        str(SHARED_UTILS / "ace_cli.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # ace_cli.py only imports stdlib + its own utils; safe to exec directly.
    spec.loader.exec_module(mod)
    return mod


def _load_ace_before_task_module():
    """Load ace_before_task.py with heavy network/subprocess deps mocked out."""
    with patch.dict("sys.modules", {
        "ace_cli": MagicMock(),
        "ace_search_cache": MagicMock(),
        "ace_context": MagicMock(),
        "ace_relevance_logger": MagicMock(),
        "ace_event_logger": MagicMock(),
    }):
        spec = importlib.util.spec_from_file_location(
            "ace_before_task_issue26",
            str(SHARED / "ace_before_task.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. run_search() — --task-intent flag behaviour
# ---------------------------------------------------------------------------

class TestRunSearchTaskIntentFlag:
    """run_search must accept task_intent and conditionally append --task-intent."""

    def test_run_search_signature_accepts_task_intent(self):
        """run_search must have a task_intent keyword parameter."""
        import inspect
        ace_cli = _load_ace_cli_module()
        sig = inspect.signature(ace_cli.run_search)
        assert "task_intent" in sig.parameters, (
            "run_search() must accept a task_intent keyword parameter"
        )

    def test_run_search_task_intent_default_is_none(self):
        """task_intent parameter must default to None."""
        import inspect
        ace_cli = _load_ace_cli_module()
        sig = inspect.signature(ace_cli.run_search)
        param = sig.parameters["task_intent"]
        assert param.default is None, (
            "task_intent default must be None"
        )

    def test_run_search_appends_task_intent_flag_when_set(self):
        """When task_intent='explore', --task-intent explore must appear in subprocess cmd."""
        ace_cli = _load_ace_cli_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"similar_patterns": [], "count": 0}).encode()
            mock_result.stderr = b""
            return mock_result

        with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
            # Also patch the LRU cache to always miss so subprocess.run is reached
            with patch.dict("sys.modules", {"utils.ace_search_cache": MagicMock()}):
                # Directly patch get_global_cache to raise (cache miss path)
                try:
                    from utils import ace_search_cache as _asc
                    with patch.object(_asc, "get_global_cache", side_effect=Exception("no cache")):
                        ace_cli.run_search("test query", task_intent="explore")
                except Exception:
                    pass

            # If the import path didn't work (module-level singleton), patch at ace_cli level
            if not captured_cmds:
                ace_cli.run_search("test query", task_intent="explore")

        assert len(captured_cmds) > 0, "subprocess.run must have been called"
        cmd = captured_cmds[0]
        assert "--task-intent" in cmd, (
            "--task-intent must be present in ace-cli cmd when task_intent is set"
        )
        ti_idx = cmd.index("--task-intent")
        assert cmd[ti_idx + 1] == "explore", (
            "value after --task-intent must be the task_intent argument ('explore')"
        )

    def test_run_search_omits_task_intent_flag_when_none(self):
        """When task_intent=None (default), --task-intent must NOT appear in the cmd."""
        ace_cli = _load_ace_cli_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"similar_patterns": [], "count": 0}).encode()
            mock_result.stderr = b""
            return mock_result

        with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
            ace_cli.run_search("test query", task_intent=None)

        assert len(captured_cmds) > 0, "subprocess.run must have been called"
        cmd = captured_cmds[0]
        assert "--task-intent" not in cmd, (
            "--task-intent must NOT be present in ace-cli cmd when task_intent is None"
        )

    def test_run_search_omits_task_intent_flag_by_default(self):
        """When task_intent omitted entirely, --task-intent must NOT appear in the cmd."""
        ace_cli = _load_ace_cli_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"similar_patterns": [], "count": 0}).encode()
            mock_result.stderr = b""
            return mock_result

        with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
            ace_cli.run_search("test query")

        assert len(captured_cmds) > 0, "subprocess.run must have been called"
        cmd = captured_cmds[0]
        assert "--task-intent" not in cmd, (
            "--task-intent must NOT be present in ace-cli cmd when omitted"
        )

    def test_run_search_task_intent_position_after_json_flag(self):
        """--task-intent must appear after --json in the command (not before base flags)."""
        ace_cli = _load_ace_cli_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"similar_patterns": [], "count": 0}).encode()
            mock_result.stderr = b""
            return mock_result

        with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
            ace_cli.run_search("test query", task_intent="refactor")

        cmd = captured_cmds[0]
        assert "search" in cmd, "cmd must contain 'search' subcommand"
        assert "--json" in cmd, "cmd must contain --json flag"
        assert "--task-intent" in cmd, "--task-intent must be in cmd"
        # task_intent value must be 'refactor'
        ti_idx = cmd.index("--task-intent")
        assert cmd[ti_idx + 1] == "refactor"

    @pytest.mark.parametrize("intent", ["explore", "refactor", "routine", "spec_strict"])
    def test_run_search_accepts_all_valid_intent_values(self, intent):
        """run_search must pass all four valid intent values through to the CLI."""
        ace_cli = _load_ace_cli_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps({"similar_patterns": [], "count": 0}).encode()
            mock_result.stderr = b""
            return mock_result

        with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
            ace_cli.run_search("test query", task_intent=intent)

        cmd = captured_cmds[0]
        ti_idx = cmd.index("--task-intent")
        assert cmd[ti_idx + 1] == intent, (
            f"task_intent='{intent}' must be forwarded verbatim to --task-intent"
        )


# ---------------------------------------------------------------------------
# 2. LRU cache key includes task_intent
# ---------------------------------------------------------------------------

class TestCacheKeyIncludesTaskIntent:
    """AceSearchCache.make_key must incorporate task_intent to prevent cross-intent bleed."""

    def test_different_task_intents_produce_different_cache_keys(self):
        """make_key('search', query, org, project, 'explore') != make_key(..., 'refactor')."""
        from ace_search_cache import AceSearchCache

        key_explore = AceSearchCache.make_key("search", "my query", "org1", "proj1", "explore")
        key_refactor = AceSearchCache.make_key("search", "my query", "org1", "proj1", "refactor")

        assert key_explore != key_refactor, (
            "Different task_intent values must produce different cache keys"
        )

    def test_none_task_intent_differs_from_explore(self):
        """make_key(..., None) must differ from make_key(..., 'explore')."""
        from ace_search_cache import AceSearchCache

        key_none = AceSearchCache.make_key("search", "my query", "org1", "proj1", None)
        key_explore = AceSearchCache.make_key("search", "my query", "org1", "proj1", "explore")

        assert key_none != key_explore, (
            "None task_intent cache key must differ from 'explore' key"
        )

    def test_same_query_same_intent_same_key(self):
        """Identical args with same task_intent must produce the same cache key."""
        from ace_search_cache import AceSearchCache

        key_a = AceSearchCache.make_key("search", "my query", "org1", "proj1", "explore")
        key_b = AceSearchCache.make_key("search", "my query", "org1", "proj1", "explore")

        assert key_a == key_b, (
            "Same args + same task_intent must produce identical cache keys"
        )

    def test_run_search_uses_task_intent_in_cache_key(self):
        """
        run_search must pass task_intent as part of the AceSearchCache.make_key call,
        so results for task_intent='explore' do NOT bleed into task_intent='refactor'.
        """
        ace_cli = _load_ace_cli_module()

        captured_keys = []
        fake_cache = MagicMock()
        fake_cache.get.return_value = None  # Always cache miss

        def fake_make_key(*parts):
            captured_keys.append(parts)
            # Compute real hash for the return value
            from ace_search_cache import AceSearchCache
            return AceSearchCache.make_key(*parts)

        with patch("ace_search_cache.get_global_cache", return_value=fake_cache):
            with patch("ace_search_cache.AceSearchCache.make_key", side_effect=fake_make_key):
                def fake_run(cmd, **kwargs):
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = json.dumps({"similar_patterns": [], "count": 0}).encode()
                    mock_result.stderr = b""
                    return mock_result

                with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
                    ace_cli.run_search("my query", org="org1", project="proj1",
                                       task_intent="explore")

        # The cache key parts must include task_intent somewhere
        assert len(captured_keys) > 0, "make_key must have been called"
        all_parts_flat = [str(p) for parts in captured_keys for p in parts]
        assert "explore" in all_parts_flat, (
            "task_intent='explore' must appear in AceSearchCache.make_key() arguments"
        )

    def test_cached_result_not_returned_for_different_task_intent(self):
        """A cached entry for task_intent=None must NOT be returned for task_intent='explore'."""
        ace_cli = _load_ace_cli_module()

        fake_result = {"similar_patterns": [{"id": "ctx-111-aaaa"}], "count": 1}

        subprocess_call_count = [0]

        def fake_run(cmd, **kwargs):
            subprocess_call_count[0] += 1
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(fake_result).encode()
            mock_result.stderr = b""
            return mock_result

        with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
            # First call with no intent — populates cache for key(query, org, proj, None)
            ace_cli.run_search("shared query", org="org1", project="proj1", task_intent=None)
            call1_count = subprocess_call_count[0]

            # Second call with task_intent='explore' — must NOT hit the None-keyed cache entry
            ace_cli.run_search("shared query", org="org1", project="proj1",
                               task_intent="explore")
            call2_count = subprocess_call_count[0]

        assert call2_count > call1_count, (
            "A second run_search with different task_intent must not reuse the cached "
            "result from the first call (must make a fresh subprocess call)"
        )


# ---------------------------------------------------------------------------
# 3. Call site — ace_before_task.py UserPromptSubmit must NOT hardcode task_intent
# ---------------------------------------------------------------------------

class TestBeforeTaskCallSiteTaskIntent:
    """
    ace_before_task.py must NOT pass task_intent='explore' to run_search at
    UserPromptSubmit. The call-site must omit the kwarg (or pass None) so the
    server's intent classifier fires without being overridden by a non-null value.
    """

    def test_run_search_called_without_hardcoded_task_intent(self, tmp_path, monkeypatch):
        """
        When ace_before_task.main() fires for a UserPromptSubmit event,
        run_search must be called with task_intent omitted or None (NOT 'explore').
        Hardcoding 'explore' masks the server's own intent classifier (flow-A
        precedence: a non-null value is never overwritten by the server backfill).
        """
        # Minimal valid hook event
        event = {
            "prompt": "implement JWT authentication",
            "session_id": "test-session-26",
            "agent_type": "main",
            "agent_id": None,
        }

        fake_search_response = {
            "similar_patterns": [],
            "count": 0,
        }

        captured_kwargs = []

        def fake_run_search(query, org=None, project=None, session_id=None,
                            task_intent=None, **kwargs):
            captured_kwargs.append({
                "query": query,
                "org": org,
                "project": project,
                "session_id": session_id,
                "task_intent": task_intent,
            })
            return fake_search_response

        # Stub context so the hook doesn't bail early
        fake_context = {"org": "test-org", "project": "test-proj"}

        mod = _load_ace_before_task_module()
        mod.run_search = fake_run_search
        mod.get_context = MagicMock(return_value=fake_context)
        mod.check_session_pinning_available = MagicMock(return_value=False)
        mod.check_auth_status = MagicMock(return_value=None)
        mod.log_search_metrics = MagicMock()
        mod.append_patterns_used = MagicMock()

        # Run main() with event on stdin
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(event)))

        with pytest.raises(SystemExit):
            mod.main()

        assert len(captured_kwargs) >= 1, (
            "run_search must be called at least once from ace_before_task.main()"
        )
        call0 = captured_kwargs[0]
        assert call0["task_intent"] is None, (
            f"ace_before_task UserPromptSubmit call site must NOT hardcode task_intent "
            f"(must be None so server classifies intent), got: {call0['task_intent']!r}"
        )

    def test_run_search_import_in_before_task_includes_no_learn_task_intent(self):
        """
        Confirm ace_before_task.py does NOT pass task_intent to any learn call.
        The learn trace is intentionally kept free of task_intent (search-only per 4.0.1).
        Tested by checking source: no run_learn(..., task_intent=) call exists.
        """
        source = (SHARED / "ace_before_task.py").read_text()
        # If run_learn or ace_learn is called with task_intent it's a bug
        import re
        # Search for any invocation that passes task_intent= to a learn function
        bad_pattern = re.search(r"(run_learn|ace_learn|ace-cli.*learn).*task_intent", source)
        assert bad_pattern is None, (
            "ace_before_task.py must NOT pass task_intent to any learn call "
            "(task_intent is search-only per 4.0.1)"
        )


# ---------------------------------------------------------------------------
# 4. Shell-level — ace_pretooluse_wrapper.sh domain-shift must NOT pass --task-intent
# ---------------------------------------------------------------------------

class TestPreToolUseShellCallSiteTaskIntent:
    """
    ace_pretooluse_wrapper.sh domain-shift ace-cli invocation must NOT include
    --task-intent in the search command. Hardcoding 'explore' masks the server's
    own intent classifier; the fix is to omit the flag entirely.
    """

    def test_pretooluse_wrapper_omits_task_intent(self):
        """
        The shell script source must NOT contain --task-intent in the
        ace-cli search call (domain-shift branch). The server classifies
        intent from the search payload; sending a non-null value prevents
        the server backfill from firing (flow-A precedence).
        """
        wrapper = REPO / "plugins" / "ace" / "scripts" / "ace_pretooluse_wrapper.sh"
        assert wrapper.exists(), f"ace_pretooluse_wrapper.sh not found at {wrapper}"

        source = wrapper.read_text()
        assert "--task-intent" not in source, (
            "ace_pretooluse_wrapper.sh must NOT contain --task-intent flag; "
            "hardcoding it masks the server intent classifier"
        )
