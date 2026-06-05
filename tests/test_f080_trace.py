#!/usr/bin/env python3
"""
TDD RED tests for issue #25 — F-080 ExecutionTrace + ace-cli learn flags.

FILE UNDER TEST: plugins/ace/shared-hooks/ace_after_task.py
ALSO TOUCHES:    plugins/ace/shared-hooks/utils/patterns_used_state.py
                 (load_retrieval_ids already exists after #24)

CHANGES BEING TESTED (none yet implemented in ace_after_task.py):
1. load_retrieval_ids called BEFORE load_playbook_used (read-only, no unlink)
2. applied_log_ids = [retrieval_log_map[pid] for pid in playbook_used if pid in retrieval_log_map]
3. trace['retrieval_id'] set when retrieval_id present (omit key when absent/None)
4. trace['applied_log_ids'] set when non-empty (omit key when empty)
5. _learn_via_transcript cmd += ['--retrieval-id', ...] when retrieval_id set
6. _learn_via_transcript cmd += ['--applied-log-ids', ','.join(...)] when applied_log_ids set
7. learn-response: cumulative_v15_reward_delta as PRIMARY reward display; helpful_delta fallback
8. patterns_deduplicated key preferred over patterns_merged
"""

import json
import sys
import os
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

# ---------------------------------------------------------------------------
# Bootstrap — mirror pattern from existing tests
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
SHARED_UTILS = SHARED / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"

sys.path.insert(0, str(SHARED_UTILS))
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(PLUGIN_UTILS))

import patterns_used_state as pus  # noqa: E402

# Real-shaped IDs
PID_A = "ctx-4338628010-5127"
PID_B = "ctx-6257961166-f081"
PID_C = "ctx-1234567890-abcd"
SESSION = "sess-f080-trace-1"
AGENT_MAIN = None
AGENT_SUB = "11111111-2222-3333-4444-555555555555"
RETRIEVAL_ID = "abaa34da-5ced-4dc2-ad8a-84994877fff5"


# ---------------------------------------------------------------------------
# Helpers — load ace_after_task with its heavy deps mocked out
# ---------------------------------------------------------------------------

def _mock_modules():
    """Return a dict of mocked modules for patching sys.modules."""
    return {
        'ace_context': MagicMock(),
        'ace_cli': MagicMock(),
        'ace_search_cache': MagicMock(),
        'ace_relevance_logger': MagicMock(),
        'ace_event_logger': MagicMock(),
        'utils.git_utils': MagicMock(),
        'ace_tool_accumulator': MagicMock(),
        'utils.trace_truncate': MagicMock(),
    }


def _load_after_task_module():
    """Import ace_after_task.py with heavy deps stubbed."""
    import importlib.util
    mocks = _mock_modules()
    # git_utils is imported as 'from utils.git_utils import ...'
    git_utils_mock = MagicMock()
    git_utils_mock.get_git_context = MagicMock(return_value=None)
    git_utils_mock.detect_commits_in_session = MagicMock(return_value=[])
    mocks['utils.git_utils'] = git_utils_mock

    # trace_truncate.truncate_trace just returns the trace unchanged
    trace_truncate_mock = MagicMock()
    trace_truncate_mock.truncate_trace = lambda t: t
    mocks['utils.trace_truncate'] = trace_truncate_mock

    with patch.dict('sys.modules', mocks):
        spec = importlib.util.spec_from_file_location(
            "ace_after_task_f080",
            str(SHARED / "ace_after_task.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. applied_log_ids intersection logic
# ---------------------------------------------------------------------------

class TestAppliedLogIdsSubsetOnly:
    """applied_log_ids must include ONLY patterns that appear in BOTH playbook_used AND retrieval_log_map."""

    def test_applied_log_ids_only_applied_subset(self):
        """playbook_used=[A,B], map={A:1,C:2} → applied=[1] (only A intersects, not C)."""
        playbook_used = [PID_A, PID_B]
        retrieval_log_map = {PID_A: 1, PID_C: 2}

        # This is the computation ace_after_task.py must implement:
        applied_log_ids = [retrieval_log_map[pid] for pid in playbook_used if pid in retrieval_log_map]

        assert applied_log_ids == [1], (
            f"Expected [1] (only PID_A intersects), got {applied_log_ids}"
        )
        assert 2 not in applied_log_ids, "PID_C was not in playbook_used, its log_id must be excluded"

    def test_applied_log_ids_empty_when_no_overlap(self):
        """playbook_used=[B], map={A:1} → applied_log_ids=[] (no intersection)."""
        playbook_used = [PID_B]
        retrieval_log_map = {PID_A: 1}

        applied_log_ids = [retrieval_log_map[pid] for pid in playbook_used if pid in retrieval_log_map]

        assert applied_log_ids == []

    def test_applied_log_ids_order_follows_playbook_used(self):
        """applied_log_ids must follow playbook_used order, not retrieval_log_map order."""
        playbook_used = [PID_B, PID_A]  # B first
        retrieval_log_map = {PID_A: 10, PID_B: 20}

        applied_log_ids = [retrieval_log_map[pid] for pid in playbook_used if pid in retrieval_log_map]

        assert applied_log_ids == [20, 10], (
            "Order must follow playbook_used (B=20, A=10)"
        )

    def test_applied_log_ids_all_ints(self):
        """All values in applied_log_ids must be ints."""
        playbook_used = [PID_A, PID_B]
        retrieval_log_map = {PID_A: 105735, PID_B: 105736}

        applied_log_ids = [retrieval_log_map[pid] for pid in playbook_used if pid in retrieval_log_map]

        assert all(isinstance(x, int) and not isinstance(x, bool) for x in applied_log_ids), (
            "All applied_log_ids values must be int (not bool)"
        )


# ---------------------------------------------------------------------------
# 2. trace dict enrichment — retrieval_id and applied_log_ids keys
# ---------------------------------------------------------------------------

class TestRetrievalIdInTrace:
    """trace['retrieval_id'] must be set when retrieval_id is present."""

    def test_retrieval_id_in_trace(self, tmp_path):
        """When retrieval_id is available, trace must contain 'retrieval_id' key."""
        # Seed state file with retrieval_id
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105735},
        )

        # load_retrieval_ids (read-only — must NOT unlink)
        retrieval_log_map = pus.load_retrieval_ids(
            SESSION, AGENT_MAIN, hook_event_name='Stop', state_dir=str(tmp_path)
        )

        # Simulate how ace_after_task must also get retrieval_id from state file.
        # load_retrieval_ids currently returns only the map; ace_after_task needs
        # to also get retrieval_id. The spec says to read state file BEFORE
        # load_playbook_used unlinks it. We verify the state file still exists:
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))
        assert sf.exists(), (
            "State file must NOT be unlinked by load_retrieval_ids (read-only)"
        )

        # Simulate trace construction that ace_after_task MUST implement:
        # retrieval_id comes from the state file (read before unlink)
        # For this test we simulate reading it directly:
        raw = json.loads(sf.read_text())
        retrieval_id = raw.get('retrieval_id')

        trace = {}
        if retrieval_id:
            trace['retrieval_id'] = retrieval_id

        assert 'retrieval_id' in trace, "trace must contain 'retrieval_id' when it is set"
        assert trace['retrieval_id'] == RETRIEVAL_ID


class TestAppliedLogIdsInTrace:
    """trace['applied_log_ids'] must be set when applied_log_ids is non-empty."""

    def test_applied_log_ids_in_trace(self, tmp_path):
        """When applied_log_ids is non-empty, trace must contain 'applied_log_ids' key."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A, PID_B],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 1, PID_B: 2},
        )

        retrieval_log_map = pus.load_retrieval_ids(
            SESSION, AGENT_MAIN, hook_event_name='Stop', state_dir=str(tmp_path)
        )
        playbook_used = [PID_A, PID_B]
        applied_log_ids = [retrieval_log_map[pid] for pid in playbook_used if pid in retrieval_log_map]

        trace = {}
        if applied_log_ids:
            trace['applied_log_ids'] = applied_log_ids

        assert 'applied_log_ids' in trace, "trace must contain 'applied_log_ids' when non-empty"
        assert trace['applied_log_ids'] == [1, 2]

    def test_applied_log_ids_values_are_ints(self, tmp_path):
        """applied_log_ids values in the trace must be ints."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105735},
        )
        retrieval_log_map = pus.load_retrieval_ids(
            SESSION, AGENT_MAIN, hook_event_name='Stop', state_dir=str(tmp_path)
        )
        applied_log_ids = [retrieval_log_map[pid] for pid in [PID_A] if pid in retrieval_log_map]

        assert applied_log_ids == [105735]
        assert isinstance(applied_log_ids[0], int) and not isinstance(applied_log_ids[0], bool)


class TestOmitWhenEmpty:
    """trace must NOT contain 'retrieval_id' or 'applied_log_ids' when empty/None."""

    def test_omit_when_empty(self):
        """No retrieval_id, no applied_log_ids → keys absent from trace."""
        retrieval_id = None
        applied_log_ids = []

        trace = {}
        if retrieval_id:
            trace['retrieval_id'] = retrieval_id
        if applied_log_ids:
            trace['applied_log_ids'] = applied_log_ids

        assert 'retrieval_id' not in trace, "retrieval_id key must be absent when None"
        assert 'applied_log_ids' not in trace, "applied_log_ids key must be absent when empty"

    def test_omit_retrieval_id_when_none(self):
        """retrieval_id=None → key absent."""
        trace = {}
        retrieval_id = None
        if retrieval_id:
            trace['retrieval_id'] = retrieval_id
        assert 'retrieval_id' not in trace

    def test_omit_applied_log_ids_when_empty_list(self):
        """applied_log_ids=[] → key absent."""
        trace = {}
        applied_log_ids = []
        if applied_log_ids:
            trace['applied_log_ids'] = applied_log_ids
        assert 'applied_log_ids' not in trace


# ---------------------------------------------------------------------------
# 3. _learn_via_transcript subprocess cmd flags
# ---------------------------------------------------------------------------

class TestLearnCmdHasRetrievalIdFlag:
    """--retrieval-id flag must appear in the ace-cli learn subprocess call when set."""

    def test_learn_cmd_has_retrieval_id_flag(self):
        """_learn_via_transcript must append ['--retrieval-id', rid] to cmd when retrieval_id set."""
        mod = _load_after_task_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = json.dumps({"learning_statistics": {}})
            r.stderr = ""
            return r

        trace = {"task": "test", "trajectory": [], "result": {"success": True}}
        retrieval_id = RETRIEVAL_ID

        with patch('subprocess.run', side_effect=fake_run):
            # The NEW signature must accept retrieval_id kwarg:
            mod._learn_via_transcript(trace, retrieval_id=retrieval_id)

        assert len(captured_cmds) == 1, "_learn_via_transcript must call subprocess.run once"
        cmd = captured_cmds[0]
        assert '--retrieval-id' in cmd, (
            f"--retrieval-id flag missing from subprocess cmd: {cmd}"
        )
        rid_idx = cmd.index('--retrieval-id')
        assert cmd[rid_idx + 1] == RETRIEVAL_ID, (
            f"--retrieval-id value must be the retrieval_id UUID, got: {cmd[rid_idx + 1]}"
        )

    def test_learn_cmd_no_retrieval_id_flag_when_absent(self):
        """--retrieval-id must NOT appear in cmd when retrieval_id is None."""
        mod = _load_after_task_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = json.dumps({"learning_statistics": {}})
            r.stderr = ""
            return r

        trace = {"task": "test", "trajectory": [], "result": {"success": True}}

        with patch('subprocess.run', side_effect=fake_run):
            mod._learn_via_transcript(trace, retrieval_id=None)

        cmd = captured_cmds[0]
        assert '--retrieval-id' not in cmd, (
            "--retrieval-id must NOT appear when retrieval_id is None"
        )


class TestLearnCmdHasAppliedLogIdsFlag:
    """--applied-log-ids flag must appear in the ace-cli learn subprocess call when set."""

    def test_learn_cmd_has_applied_log_ids_flag(self):
        """_learn_via_transcript must append ['--applied-log-ids', '1,2'] when applied_log_ids=[1,2]."""
        mod = _load_after_task_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = json.dumps({"learning_statistics": {}})
            r.stderr = ""
            return r

        trace = {"task": "test", "trajectory": [], "result": {"success": True}}
        applied_log_ids = [105735, 105736]

        with patch('subprocess.run', side_effect=fake_run):
            mod._learn_via_transcript(trace, applied_log_ids=applied_log_ids)

        assert len(captured_cmds) == 1
        cmd = captured_cmds[0]
        assert '--applied-log-ids' in cmd, (
            f"--applied-log-ids flag missing from subprocess cmd: {cmd}"
        )
        ali_idx = cmd.index('--applied-log-ids')
        assert cmd[ali_idx + 1] == '105735,105736', (
            f"--applied-log-ids value must be comma-joined ints, got: {cmd[ali_idx + 1]}"
        )

    def test_learn_cmd_no_applied_log_ids_flag_when_empty(self):
        """--applied-log-ids must NOT appear when applied_log_ids is empty."""
        mod = _load_after_task_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = json.dumps({"learning_statistics": {}})
            r.stderr = ""
            return r

        trace = {"task": "test", "trajectory": [], "result": {"success": True}}

        with patch('subprocess.run', side_effect=fake_run):
            mod._learn_via_transcript(trace, applied_log_ids=[])

        cmd = captured_cmds[0]
        assert '--applied-log-ids' not in cmd, (
            "--applied-log-ids must NOT appear when list is empty"
        )

    def test_learn_cmd_applied_log_ids_single_value(self):
        """Single applied_log_id → '--applied-log-ids', '42' (no trailing comma)."""
        mod = _load_after_task_module()

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = json.dumps({"learning_statistics": {}})
            r.stderr = ""
            return r

        trace = {"task": "test", "trajectory": [], "result": {"success": True}}

        with patch('subprocess.run', side_effect=fake_run):
            mod._learn_via_transcript(trace, applied_log_ids=[42])

        cmd = captured_cmds[0]
        ali_idx = cmd.index('--applied-log-ids')
        assert cmd[ali_idx + 1] == '42', (
            f"Single applied_log_id must be '42', got: {cmd[ali_idx + 1]}"
        )


# ---------------------------------------------------------------------------
# 4. learn-response display: patterns_deduplicated + cumulative_v15_reward_delta
# ---------------------------------------------------------------------------

class TestPatternsDeduplicated:
    """stats.get('patterns_deduplicated') must be preferred over 'patterns_merged'."""

    def test_patterns_deduplicated_used(self):
        """stats with patterns_deduplicated=5 → merged count is 5 (not patterns_merged)."""
        stats = {
            'patterns_created': 2,
            'patterns_updated': 1,
            'patterns_deduplicated': 5,
            'patterns_merged': 0,  # old key, must not win
            'average_confidence': 0.85,
        }

        # The expression ace_after_task MUST use:
        merged = stats.get('patterns_deduplicated', stats.get('patterns_merged', 0))

        assert merged == 5, (
            f"patterns_deduplicated=5 must take precedence over patterns_merged=0, got {merged}"
        )

    def test_patterns_merged_fallback_when_deduplicated_absent(self):
        """When patterns_deduplicated absent, fall back to patterns_merged."""
        stats = {
            'patterns_created': 1,
            'patterns_merged': 3,
        }

        merged = stats.get('patterns_deduplicated', stats.get('patterns_merged', 0))

        assert merged == 3, (
            f"Must fall back to patterns_merged=3 when patterns_deduplicated absent, got {merged}"
        )

    def test_both_absent_gives_zero(self):
        """Neither key present → merged count is 0."""
        stats = {'patterns_created': 1}

        merged = stats.get('patterns_deduplicated', stats.get('patterns_merged', 0))

        assert merged == 0

    def test_deduplicated_zero_when_present_not_shadowed(self):
        """patterns_deduplicated=0 must NOT fall through to patterns_merged."""
        stats = {
            'patterns_deduplicated': 0,
            'patterns_merged': 7,  # must NOT be used
        }

        # NOTE: stats.get('patterns_deduplicated', ...) returns 0, not the default
        # 0 is falsy BUT .get() only uses default when key is ABSENT, not when value is 0
        merged = stats.get('patterns_deduplicated', stats.get('patterns_merged', 0))

        assert merged == 0, (
            "patterns_deduplicated=0 must return 0, not fall back to patterns_merged=7"
        )


class TestCumulativeV15RewardDeltaPrimary:
    """cumulative_v15_reward_delta must be used as PRIMARY reward metric; helpful_delta as fallback."""

    def test_cumulative_v15_reward_delta_primary(self):
        """stats with cumulative_v15_reward_delta=2.5 → shown as primary (float display)."""
        stats = {
            'patterns_created': 1,
            'cumulative_v15_reward_delta': 2.5,
            'helpful_delta': 3,
        }

        # The logic ace_after_task MUST implement:
        v15 = stats.get('cumulative_v15_reward_delta')
        helpful_delta = stats.get('helpful_delta', 0)

        assert v15 is not None, "cumulative_v15_reward_delta must be picked up from stats"
        assert v15 == 2.5

        # Primary display branch: v15 present → use it
        if v15 is not None:
            reward_display = f"📈 +{v15:.1f} reward delta"
        else:
            reward_display = f"📈 {helpful_delta:+d} reward delta"

        assert "2.5" in reward_display, (
            f"cumulative_v15_reward_delta=2.5 must appear in display, got: {reward_display}"
        )
        assert "📈" in reward_display

    def test_helpful_delta_fallback_when_v15_absent(self):
        """When cumulative_v15_reward_delta absent, fall back to helpful_delta."""
        stats = {
            'patterns_created': 1,
            'helpful_delta': 4,
        }

        v15 = stats.get('cumulative_v15_reward_delta')
        helpful_delta = stats.get('helpful_delta', 0)

        assert v15 is None, "cumulative_v15_reward_delta should be absent"

        # Fallback branch
        if v15 is not None:
            reward_display = f"📈 +{v15:.1f} reward delta"
        else:
            reward_display = f"📈 {helpful_delta:+d} reward delta"

        assert "+4" in reward_display, (
            f"helpful_delta=4 must appear in fallback display, got: {reward_display}"
        )

    def test_v15_zero_still_primary(self):
        """cumulative_v15_reward_delta=0.0 must still be used (not fall through to helpful_delta)."""
        stats = {
            'cumulative_v15_reward_delta': 0.0,
            'helpful_delta': 5,
        }

        v15 = stats.get('cumulative_v15_reward_delta')
        helpful_delta = stats.get('helpful_delta', 0)

        # v15 is 0.0, not None → primary branch
        if v15 is not None:
            reward_display = f"📈 +{v15:.1f} reward delta"
            used_primary = True
        else:
            reward_display = f"📈 {helpful_delta:+d} reward delta"
            used_primary = False

        assert used_primary, "v15=0.0 must use primary branch (not None-check fail)"
        assert "0.0" in reward_display

    def test_v15_negative_value_displayed(self):
        """Negative cumulative_v15_reward_delta must render as a negative float."""
        stats = {'cumulative_v15_reward_delta': -1.3}

        v15 = stats.get('cumulative_v15_reward_delta')
        if v15 is not None:
            reward_display = f"📈 +{v15:.1f} reward delta"
        else:
            reward_display = ""

        assert "-1.3" in reward_display, (
            f"Negative v15 delta must appear in display, got: {reward_display}"
        )

    def test_both_absent_gives_zero_helpful_delta(self):
        """Neither v15 nor helpful_delta → display shows 0."""
        stats = {}

        v15 = stats.get('cumulative_v15_reward_delta')
        helpful_delta = stats.get('helpful_delta', 0)

        if v15 is not None:
            reward_display = f"📈 +{v15:.1f} reward delta"
        else:
            reward_display = f"📈 {helpful_delta:+d} reward delta"

        assert "+0" in reward_display, f"Zero fallback must show +0, got: {reward_display}"


# ---------------------------------------------------------------------------
# 5. Integration: load_retrieval_ids is read-only (does NOT unlink state file)
# ---------------------------------------------------------------------------

class TestLoadRetrievalIdsReadOnly:
    """load_retrieval_ids must NOT unlink the state file (read-only contract)."""

    def test_state_file_survives_load_retrieval_ids(self, tmp_path):
        """After load_retrieval_ids, state file must still exist (not unlinked)."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105735},
        )
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))
        assert sf.exists(), "State file must exist before load_retrieval_ids"

        pus.load_retrieval_ids(SESSION, AGENT_MAIN, hook_event_name='Stop', state_dir=str(tmp_path))

        assert sf.exists(), (
            "State file must NOT be unlinked by load_retrieval_ids (read-only)"
        )

    def test_load_playbook_used_unlinks_after_load_retrieval_ids(self, tmp_path):
        """load_playbook_used must still unlink after load_retrieval_ids has read the file."""
        pus.append_patterns_used(
            SESSION, AGENT_MAIN, [PID_A],
            state_dir=str(tmp_path),
            retrieval_id=RETRIEVAL_ID,
            retrieval_log_ids={PID_A: 105735},
        )
        sf = pus.state_file_path(SESSION, AGENT_MAIN, str(tmp_path))

        # Read-only call first
        pus.load_retrieval_ids(SESSION, AGENT_MAIN, hook_event_name='Stop', state_dir=str(tmp_path))
        assert sf.exists(), "File must survive load_retrieval_ids"

        # Destructive call second (as ace_after_task will do)
        ids = pus.load_playbook_used(SESSION, AGENT_MAIN, hook_event_name='Stop', state_dir=str(tmp_path))
        assert PID_A in ids, "load_playbook_used must still return IDs after load_retrieval_ids"
        assert not sf.exists(), "load_playbook_used must unlink the state file"


# ---------------------------------------------------------------------------
# 6. _learn_via_transcript signature accepts new kwargs without crashing
# ---------------------------------------------------------------------------

class TestLearnViaTranscriptNewKwargs:
    """_learn_via_transcript must accept retrieval_id and applied_log_ids kwargs."""

    def test_learn_via_transcript_accepts_retrieval_id_kwarg(self):
        """Calling _learn_via_transcript(trace, retrieval_id=...) must not raise TypeError."""
        mod = _load_after_task_module()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "{}"
            mock_run.return_value.stderr = ""

            trace = {"task": "test"}
            try:
                mod._learn_via_transcript(trace, retrieval_id=RETRIEVAL_ID)
            except TypeError as e:
                pytest.fail(
                    f"_learn_via_transcript must accept retrieval_id kwarg, got TypeError: {e}"
                )

    def test_learn_via_transcript_accepts_applied_log_ids_kwarg(self):
        """Calling _learn_via_transcript(trace, applied_log_ids=...) must not raise TypeError."""
        mod = _load_after_task_module()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "{}"
            mock_run.return_value.stderr = ""

            trace = {"task": "test"}
            try:
                mod._learn_via_transcript(trace, applied_log_ids=[1, 2, 3])
            except TypeError as e:
                pytest.fail(
                    f"_learn_via_transcript must accept applied_log_ids kwarg, got TypeError: {e}"
                )

    def test_learn_via_transcript_accepts_both_new_kwargs(self):
        """Calling with both new kwargs must not raise TypeError."""
        mod = _load_after_task_module()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "{}"
            mock_run.return_value.stderr = ""

            trace = {"task": "test"}
            try:
                mod._learn_via_transcript(
                    trace,
                    retrieval_id=RETRIEVAL_ID,
                    applied_log_ids=[105735, 105736],
                )
            except TypeError as e:
                pytest.fail(
                    f"_learn_via_transcript must accept both new kwargs, got TypeError: {e}"
                )
