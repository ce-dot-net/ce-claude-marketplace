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
  4. Domain-shift call site (v8: ace_domain_shift.py) does NOT pass
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
# 1+2. v8 (DESIGN §5 C2): run_search has NO task_intent plumbing and no
# in-process cache; argv is exactly [ace-cli, search, --stdin, --json,
# (--pin-session X)?, (--top-k N)?]. The disk cache key lives in
# tests/test_search_cache_v8.py.
# ---------------------------------------------------------------------------

class TestRunSearchNoTaskIntent:
    def test_run_search_has_no_task_intent_param(self):
        import inspect
        ace_cli = _load_ace_cli_module()
        assert "task_intent" not in inspect.signature(ace_cli.run_search).parameters

    def test_run_search_never_sends_task_intent(self):
        ace_cli = _load_ace_cli_module()
        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            r = MagicMock()
            r.returncode = 0
            r.stdout = json.dumps({"similar_patterns": [], "count": 0}).encode()
            r.stderr = b""
            return r

        with patch.object(ace_cli.subprocess, "run", side_effect=fake_run):
            ace_cli.run_search("test query", hook_event_name="UserPromptSubmit")
        assert captured_cmds and "--task-intent" not in captured_cmds[0]


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
            return fake_search_response, 0

        # Stub context so the hook doesn't bail early
        fake_context = {"org": "test-org", "project": "test-proj"}

        mod = _load_ace_before_task_module()
        mod.run_search = fake_run_search
        mod.get_context = MagicMock(return_value=fake_context)
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
# 4. Domain-shift call site (v8: Python port ace_domain_shift.py, WP-D) must
#    NOT pass --task-intent. The PreToolUse bash wrapper this used to pin is
#    deleted in v8 (DESIGN §3 REMOVED / §6 WP-D).
# ---------------------------------------------------------------------------

class TestDomainShiftCallSiteTaskIntent:
    """ace_domain_shift.py must not send task_intent / --task-intent: hardcoding
    it masks the server's own intent classifier (v7.0.1 principle)."""

    def test_domain_shift_py_omits_task_intent(self):
        mod = REPO / "plugins" / "ace" / "shared-hooks" / "ace_domain_shift.py"
        assert mod.exists(), f"ace_domain_shift.py not found at {mod} (DESIGN §6 WP-D)"
        source = mod.read_text()
        assert "--task-intent" not in source and "task_intent" not in source, (
            "ace_domain_shift.py must NOT pass task_intent; it masks the server "
            "intent classifier"
        )
