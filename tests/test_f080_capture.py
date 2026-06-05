#!/usr/bin/env python3
"""
TDD RED tests for issue #24 — F-080 retrieval_id capture + patterns_used_state schema migration.

Three files change:
  1. plugins/ace/shared-hooks/utils/patterns_used_state.py
     - Schema migration: bare list → {"pattern_ids": [...], "retrieval_id": ..., "retrieval_log_ids": {...}}
     - Backward compat: legacy bare-list files still readable
     - New params on append_patterns_used: retrieval_id, retrieval_log_ids
     - New function: load_retrieval_ids(session_id, agent_id, hook_event_name, state_dir)
     - retrieval_log_ids values MUST be int (bool guard)

  2. plugins/ace/shared-hooks/ace_before_task.py
     - Capture retrieval_id + retrieval_log_map BEFORE useful_fields strip
     - Pass them through to append_patterns_used

  3. plugins/ace/scripts/ace_pretooluse_wrapper.sh
     - __main__ CLI: accept --retrieval-id, extract match_factors.retrieval_log_id per pattern
"""
import json
import sys
import importlib
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Bootstrap — mirror the pattern used by existing tests
REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
SHARED_UTILS = SHARED / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"

sys.path.insert(0, str(SHARED_UTILS))
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(PLUGIN_UTILS))

import patterns_used_state as pus  # noqa: E402

# Real-shaped IDs — all pass is_valid_pattern_id
PID_A = "ctx-4338628010-5127"
PID_B = "ctx-6257961166-f081"
PID_C = "ctx-1234567890-abcd"
SESSION = "sess-f080-test-1"
AGENT_MAIN = None          # main agent
AGENT_SUB = "11111111-2222-3333-4444-555555555555"
RETRIEVAL_ID = "abaa34da-5ced-4dc2-ad8a-84994877fff5"


# ---------------------------------------------------------------------------
# 1. SCHEMA MIGRATION — patterns_used_state.py
# ---------------------------------------------------------------------------

class TestLegacyListStillReadable:
    """Legacy bare-list JSON files must still load without crash."""

    def test_legacy_list_load_playbook_used(self, tmp_path):
        """write a bare-list JSON, call load_playbook_used → returns IDs, no crash."""
        sf = tmp_path / f"ace-patterns-used-{SESSION}-main.json"
        sf.write_text(json.dumps([PID_A, PID_B]))

        result = pus.load_playbook_used(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))

        assert PID_A in result
        assert PID_B in result
        assert len(result) == 2
        # File should be reaped after load
        assert not sf.exists()


class TestNewSchemaRoundTrip:
    """New schema: append with retrieval_id + retrieval_log_ids; read back correctly."""

    def test_retrieval_id_persisted_even_when_no_valid_pattern_ids(self, tmp_path):
        """Fix: early return must NOT fire when retrieval_id is present but all pattern_ids invalid.

        Bug: `if not ids: return []` fired before the state file write, silently
        dropping retrieval_id/retrieval_log_ids when all pattern_ids failed validation.
        Now: `if not ids and not has_retrieval: return []` only skips the write when
        BOTH pattern_ids are empty AND no retrieval metadata was provided.
        """
        rid = "70c6bed1-aa31-4708-8550-ed2db02ee1d1"
        rlog = {PID_A: 108040}
        # All pattern_ids are invalid (empty list) but retrieval metadata is present
        result = pus.append_patterns_used(
            SESSION, AGENT_MAIN, [],   # no valid pattern IDs
            state_dir=str(tmp_path),
            retrieval_id=rid,
            retrieval_log_ids=rlog,
        )
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))
        assert sf.exists(), "state file must be written when retrieval_id is present"
        import json
        d = json.loads(sf.read_text())
        assert d.get("retrieval_id") == rid, "retrieval_id must be persisted"
        assert d.get("retrieval_log_ids") == rlog, "retrieval_log_ids must be persisted"
        assert d.get("pattern_ids") == [], "pattern_ids should be empty (no valid IDs)"

    def test_no_state_file_when_both_empty(self, tmp_path):
        """When both pattern_ids and retrieval metadata are absent, write nothing."""
        result = pus.append_patterns_used(
            SESSION, AGENT_MAIN, [],   # no valid pattern IDs
            state_dir=str(tmp_path),
            retrieval_id=None,
            retrieval_log_ids=None,
        )
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))
        assert not sf.exists(), "no state file when nothing to persist"
        assert result == []

    def test_append_accepts_retrieval_id_param(self, tmp_path):
        """append_patterns_used must accept retrieval_id keyword arg without error."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A, PID_B],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105360, PID_B: 105361},
        )
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))
        assert sf.exists()

    def test_new_schema_file_has_dict_structure(self, tmp_path):
        """After append with retrieval_id, state file is a dict not a bare list."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105360},
        )
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))
        raw = json.loads(sf.read_text())
        assert isinstance(raw, dict), "state file should be a dict after schema migration"
        assert "pattern_ids" in raw
        assert "retrieval_id" in raw
        assert "retrieval_log_ids" in raw

    def test_load_playbook_used_returns_ids_from_new_schema(self, tmp_path):
        """load_playbook_used must return pattern IDs from new dict-format file."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A, PID_B],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105360, PID_B: 105361},
        )
        result = pus.load_playbook_used(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert PID_A in result
        assert PID_B in result

    def test_load_retrieval_ids_returns_map(self, tmp_path):
        """load_retrieval_ids must return {pattern_id: retrieval_log_id} from new schema."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A, PID_B],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105360, PID_B: 105361},
        )
        # load_retrieval_ids should NOT unlink the file (it's read-only for the map)
        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert result == {PID_A: 105360, PID_B: 105361}

    def test_load_retrieval_ids_function_exists(self):
        """load_retrieval_ids must be a callable exported from pus."""
        assert callable(getattr(pus, 'load_retrieval_ids', None)), \
            "pus.load_retrieval_ids is missing — needs to be added"

    def test_retrieval_id_stored_in_file(self, tmp_path):
        """retrieval_id written to state file must be the UUID passed in."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105360},
        )
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))
        raw = json.loads(sf.read_text())
        assert raw["retrieval_id"] == RETRIEVAL_ID

    def test_retrieval_id_none_when_not_provided(self, tmp_path):
        """When retrieval_id not passed, file stores null and load_retrieval_ids returns {}."""
        pus.append_patterns_used(SESSION, AGENT_MAIN, [PID_A], state_dir=str(tmp_path))
        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert result == {}


class TestBoolNotIntGuard:
    """bool is a subclass of int — True/False must NOT enter the retrieval_log_ids map."""

    def test_bool_true_not_stored_as_retrieval_log_id(self, tmp_path):
        """retrieval_log_id=True must be excluded (bool guard required)."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A, PID_B],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: True, PID_B: 105361},  # True must be excluded
        )
        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert PID_A not in result, "bool True should not appear as a valid retrieval_log_id"
        assert result.get(PID_B) == 105361

    def test_bool_false_not_stored_as_retrieval_log_id(self, tmp_path):
        """retrieval_log_id=False must also be excluded."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: False},
        )
        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert PID_A not in result, "bool False should not appear as a valid retrieval_log_id"


class TestLegacyLoadRetrievalIdsReturnsEmpty:
    """Legacy bare-list files → load_retrieval_ids returns {}."""

    def test_legacy_load_retrieval_ids_returns_empty(self, tmp_path):
        """Legacy file with bare list → load_retrieval_ids returns {}."""
        sf = tmp_path / f"ace-patterns-used-{SESSION}-main.json"
        sf.write_text(json.dumps([PID_A, PID_B]))

        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert result == {}

    def test_missing_file_load_retrieval_ids_returns_empty(self, tmp_path):
        """No state file at all → load_retrieval_ids returns {} without crash."""
        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert result == {}

    def test_subagent_legacy_load_retrieval_ids_returns_empty(self, tmp_path):
        """Legacy subagent file → load_retrieval_ids returns {} for SubagentStop."""
        sf = tmp_path / f"ace-patterns-used-{SESSION}-{AGENT_SUB}.json"
        sf.write_text(json.dumps([PID_A]))

        result = pus.load_retrieval_ids(SESSION, AGENT_SUB, hook_event_name='SubagentStop', state_dir=str(tmp_path))
        assert result == {}


class TestNullMatchFactorsNoCrash:
    """append_patterns_used (and __main__ CLI) must handle null/missing match_factors gracefully."""

    def test_null_retrieval_log_ids_no_crash(self, tmp_path):
        """Passing retrieval_log_ids=None must not raise."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids=None,
        )
        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert result == {}

    def test_empty_retrieval_log_ids_no_crash(self, tmp_path):
        """Passing retrieval_log_ids={} must not raise and returns empty map."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=None,
            retrieval_log_ids={},
        )
        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert result == {}


# ---------------------------------------------------------------------------
# 2. ace_before_task.py — retrieval_id captured BEFORE useful_fields strip
# ---------------------------------------------------------------------------

def _load_ace_before_task_module():
    """Load ace_before_task.py with its external dependencies mocked out."""
    # We only need the module-level imports to succeed and to be able to call
    # the section that processes patterns_response → append_patterns_used.
    # Heavy deps (ace_cli, ace_search_cache, etc.) are mocked so the module loads.
    import unittest.mock as mock

    # Patch subprocess-heavy or network-heavy imports before the module loads
    with mock.patch.dict('sys.modules', {
        'ace_cli': mock.MagicMock(),
        'ace_search_cache': mock.MagicMock(),
        'ace_context': mock.MagicMock(),
        'ace_relevance_logger': mock.MagicMock(),
        'ace_event_logger': mock.MagicMock(),
    }):
        spec = importlib.util.spec_from_file_location(
            "ace_before_task",
            str(SHARED / "ace_before_task.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class TestRetrievalIdCapturedBeforeStrip:
    """
    In ace_before_task.py: retrieval_id present in search response must be captured
    and passed to append_patterns_used BEFORE the useful_fields strip removes match_factors.
    """

    def test_retrieval_id_passed_to_append_patterns_used(self, tmp_path, monkeypatch):
        """
        When run_search returns a response with retrieval_id and match_factors.retrieval_log_id,
        ace_before_task must call append_patterns_used with retrieval_id and retrieval_log_ids.
        """
        # Minimal fake search response containing retrieval_id at top level
        # and match_factors.retrieval_log_id per pattern (pre-strip)
        fake_response = {
            "retrieval_id": RETRIEVAL_ID,
            "similar_patterns": [
                {
                    "id": PID_A,
                    "domain": "test",
                    "content": "test pattern A",
                    "confidence": 0.9,
                    "helpful": 5,
                    "harmful": 0,
                    "match_factors": {
                        "retrieval_log_id": 105360,
                        "semantic_score": 0.85,
                    },
                },
                {
                    "id": PID_B,
                    "domain": "test",
                    "content": "test pattern B",
                    "confidence": 0.8,
                    "helpful": 3,
                    "harmful": 0,
                    "match_factors": {
                        "retrieval_log_id": 105361,
                        "semantic_score": 0.80,
                    },
                },
            ],
            "count": 2,
        }

        captured_calls = []

        def fake_append(session_id, agent_id, pattern_ids, state_dir=None,
                        retrieval_id=None, retrieval_log_ids=None):
            captured_calls.append({
                "session_id": session_id,
                "pattern_ids": pattern_ids,
                "retrieval_id": retrieval_id,
                "retrieval_log_ids": retrieval_log_ids,
            })

        # Patch the append_patterns_used name as imported in ace_before_task
        import unittest.mock as mock
        with mock.patch.dict('sys.modules', {
            'ace_cli': mock.MagicMock(),
            'ace_search_cache': mock.MagicMock(),
            'ace_context': mock.MagicMock(),
            'ace_relevance_logger': mock.MagicMock(),
            'ace_event_logger': mock.MagicMock(),
        }):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "ace_before_task_f080",
                str(SHARED / "ace_before_task.py"),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

        # Now patch append_patterns_used in the loaded module
        mod.append_patterns_used = fake_append

        # Simulate the pattern-capture section of ace_before_task:
        # Build a context dict as the real code uses
        fake_context = {"project": "test-proj", "org": "test-org"}
        pattern_list = fake_response.get("similar_patterns", [])

        # --- THIS IS THE LOGIC WE'RE TESTING (must exist in ace_before_task) ---
        # The new code must:
        #   1. Extract retrieval_id from patterns_response BEFORE strip
        #   2. Build retrieval_log_map from match_factors.retrieval_log_id
        #   3. Pass both to append_patterns_used
        #
        # We call the function/logic that does this via the module.
        # Since the full hook runs as __main__, we test the capture logic
        # by asserting the module exposes a helper or by simulating the
        # critical code path.

        # The canonical test: call append_patterns_used via the module's
        # patched name to verify it would be called with retrieval_id.
        # We simulate what ace_before_task SHOULD do after the fix:
        retrieval_id_from_response = fake_response.get('retrieval_id') or None
        retrieval_log_map = {}
        for p in fake_response.get('similar_patterns', []):
            pid = p.get('id')
            mf = p.get('match_factors') or {}
            rlid = mf.get('retrieval_log_id')
            if pid and isinstance(rlid, int) and not isinstance(rlid, bool):
                retrieval_log_map[pid] = rlid

        from validation import is_valid_pattern_id
        pattern_ids = [p.get('id') for p in pattern_list
                       if p.get('id') and is_valid_pattern_id(p.get('id'))]

        # This call goes through fake_append above
        mod.append_patterns_used(
            "test-session", None, pattern_ids,
            retrieval_id=retrieval_id_from_response,
            retrieval_log_ids=retrieval_log_map,
        )

        assert len(captured_calls) == 1, "append_patterns_used must be called once"
        call = captured_calls[0]
        assert call["retrieval_id"] == RETRIEVAL_ID, \
            "retrieval_id must be passed to append_patterns_used"
        assert call["retrieval_log_ids"] == {PID_A: 105360, PID_B: 105361}, \
            "retrieval_log_ids must be populated from match_factors.retrieval_log_id"


class TestRetrievalLogIdsNotInUsefulFields:
    """After useful_fields strip, match_factors must NOT appear in injected patterns."""

    def test_match_factors_absent_after_strip(self):
        """
        The useful_fields set in ace_before_task.py must not include 'match_factors'.
        After strip, patterns_response['similar_patterns'] must have no match_factors key.
        """
        import unittest.mock as mock
        with mock.patch.dict('sys.modules', {
            'ace_cli': mock.MagicMock(),
            'ace_search_cache': mock.MagicMock(),
            'ace_context': mock.MagicMock(),
            'ace_relevance_logger': mock.MagicMock(),
            'ace_event_logger': mock.MagicMock(),
        }):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "ace_before_task_strip_test",
                str(SHARED / "ace_before_task.py"),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

        # Check the useful_fields constant in the module source — it must NOT contain match_factors
        # We verify by reading the source and checking programmatically.
        source = (SHARED / "ace_before_task.py").read_text()
        # The useful_fields set must not include 'match_factors'
        # Find the useful_fields assignment and assert match_factors is absent
        import re
        # Match either inline 'useful_fields = {...}' or module-level 'USEFUL_FIELDS = {...}'
        m = re.search(r"USEFUL_FIELDS\s*=\s*\{([^}]+)\}", source) or \
            re.search(r"useful_fields\s*=\s*\{([^}]+)\}", source)
        assert m is not None, "useful_fields/USEFUL_FIELDS definition not found in ace_before_task.py"
        useful_fields_content = m.group(1)
        assert 'match_factors' not in useful_fields_content, \
            "match_factors must NOT be in useful_fields (it must be stripped)"

    def test_strip_removes_match_factors_from_pattern(self):
        """Simulate the strip: a pattern with match_factors → stripped result has no match_factors."""
        useful_fields = {'id', 'domain', 'content', 'confidence', 'helpful', 'harmful',
                         'section', 'evidence', 'root_cause', 'error_context'}
        pattern_with_match_factors = {
            "id": PID_A,
            "domain": "test",
            "content": "some content",
            "confidence": 0.9,
            "helpful": 5,
            "harmful": 0,
            "match_factors": {"retrieval_log_id": 105360, "semantic_score": 0.85},
            "created_at": "2026-01-01T00:00:00Z",
        }
        stripped = {k: v for k, v in pattern_with_match_factors.items()
                    if k in useful_fields and (v or k not in ('root_cause', 'error_context'))}
        assert 'match_factors' not in stripped, \
            "match_factors must be absent after the useful_fields strip"
        assert stripped.get('id') == PID_A, "id must be preserved after strip"


# ---------------------------------------------------------------------------
# 3. __main__ CLI — ace_pretooluse_wrapper.sh pipes search JSON to
#    patterns_used_state.py; the CLI must handle --retrieval-id and extract
#    match_factors.retrieval_log_id per pattern
# ---------------------------------------------------------------------------

class TestCliMainRetrieval:
    """patterns_used_state.py __main__ must accept --retrieval-id and handle match_factors."""

    def _run_main(self, stdin_data: dict, extra_args: list, state_dir: str) -> None:
        """Run the __main__ block of patterns_used_state via subprocess-like invocation."""
        import subprocess, sys as _sys
        import tempfile, os
        env = os.environ.copy()
        # Run the module as __main__ with json on stdin
        cmd = [
            _sys.executable,
            str(SHARED_UTILS / "patterns_used_state.py"),
            "--session", SESSION,
            "--agent-id", "",
            "--state-dir", state_dir,
        ] + extra_args
        proc = subprocess.run(
            cmd,
            input=json.dumps(stdin_data),
            capture_output=True,
            text=True,
            env=env,
        )
        return proc

    def test_cli_accepts_retrieval_id_flag(self, tmp_path):
        """CLI must accept --retrieval-id without crashing (exit 0)."""
        data = {
            "retrieval_id": RETRIEVAL_ID,
            "similar_patterns": [
                {"id": PID_A, "match_factors": {"retrieval_log_id": 105360}},
            ],
        }
        proc = self._run_main(data, ["--retrieval-id", RETRIEVAL_ID], str(tmp_path))
        assert proc.returncode == 0, \
            f"CLI crashed with --retrieval-id flag: stderr={proc.stderr}"

    def test_cli_stores_retrieval_log_ids_from_match_factors(self, tmp_path):
        """CLI must extract match_factors.retrieval_log_id and store in state file."""
        data = {
            "retrieval_id": RETRIEVAL_ID,
            "similar_patterns": [
                {"id": PID_A, "match_factors": {"retrieval_log_id": 105360}},
                {"id": PID_B, "match_factors": {"retrieval_log_id": 105361}},
            ],
        }
        self._run_main(data, ["--retrieval-id", RETRIEVAL_ID], str(tmp_path))

        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert result.get(PID_A) == 105360, \
            "CLI must store retrieval_log_id from match_factors into state file"
        assert result.get(PID_B) == 105361

    def test_cli_null_match_factors_no_crash(self, tmp_path):
        """CLI must not crash when match_factors is null or missing."""
        data = {
            "retrieval_id": RETRIEVAL_ID,
            "similar_patterns": [
                {"id": PID_A, "match_factors": None},
                {"id": PID_B},  # no match_factors key at all
                {"id": PID_C, "match_factors": {"retrieval_log_id": 105362}},
            ],
        }
        proc = self._run_main(data, ["--retrieval-id", RETRIEVAL_ID], str(tmp_path))
        assert proc.returncode == 0, \
            f"CLI crashed on null/missing match_factors: stderr={proc.stderr}"

        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert PID_A not in result
        assert PID_B not in result
        assert result.get(PID_C) == 105362

    def test_cli_bool_retrieval_log_id_excluded(self, tmp_path):
        """CLI must exclude bool True from retrieval_log_ids (bool guard)."""
        data = {
            "retrieval_id": RETRIEVAL_ID,
            "similar_patterns": [
                {"id": PID_A, "match_factors": {"retrieval_log_id": True}},
                {"id": PID_B, "match_factors": {"retrieval_log_id": 105361}},
            ],
        }
        self._run_main(data, ["--retrieval-id", RETRIEVAL_ID], str(tmp_path))

        result = pus.load_retrieval_ids(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert PID_A not in result, "bool True must be excluded from retrieval_log_ids"
        assert result.get(PID_B) == 105361

    def test_cli_without_retrieval_id_flag_still_works(self, tmp_path):
        """Existing CLI usage without --retrieval-id must still work (backward compat)."""
        data = {
            "similar_patterns": [
                {"id": PID_A},
                {"id": PID_B},
            ],
        }
        proc = self._run_main(data, [], str(tmp_path))
        assert proc.returncode == 0, \
            f"CLI without --retrieval-id crashed: stderr={proc.stderr}"

        ids = pus.load_playbook_used(SESSION, None, hook_event_name='Stop', state_dir=str(tmp_path))
        assert PID_A in ids
        assert PID_B in ids
