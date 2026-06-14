#!/usr/bin/env python3
"""
v7.1.4 — SubagentStop degenerate-trace fix (RED→GREEN TDD).

Bug: when many subagents are spawned concurrently (high fan-out), CC sometimes
delivers SubagentStop with empty agent_id/agent_type AND/OR a missing transcript
file.  The plugin then:
  - falls back to the '-main' state file (no task_session_id)
  - reads the wrong/empty transcript → user_prompt = "No user prompt found"
  - still sends the trace → anchorless server noise (session_id empty,
    no retrieval_id, task = "No user prompt found").

Fix (two stages, SubagentStop path only):

  Stage 1 — agent_id recovery: if event.agent_id is empty, derive it from
  agent_transcript_path ("agent-{uuid}.jsonl").  If recovered, set agent_id
  BEFORE all state-file reads so they key off the correct per-agent file.
  Emit agent_id_recovered: true in the existing subagent_stop_keymap record.

  Stage 2 — hygiene skip: after all anchors are computed, if ALL of
  task_session_id, retrieval_id, applied_log_ids are absent AND user_prompt is
  the default sentinel, skip the trace.  Emit a "subagent_degenerate_skip"
  relevance record, reap the state file, exit 0 cleanly (no learn call).

Coverage:
  1. Stage 1: empty agent_id recovered from transcript path; seeded state file
     keyed under the recovered uuid is read → task_session_id in trace → NOT
     skipped; telemetry shows agent_id_recovered=True.
  2. Stage 2 skip: empty agent_id + missing transcript + no anchors → learn NOT
     called; subagent_degenerate_skip record emitted; state reaped; exit 0.
  3. Happy path unchanged: normal SubagentStop with populated agent_id → learn
     called; no degenerate_skip record.
  4. Partial-anchor NOT skipped: tsid present but prompt = sentinel → NOT
     skipped (anchor present); AND real prompt but no tsid/retrieval → NOT
     skipped (prompt present → send).
  5. Main Stop never skipped by Stage 2 logic (SubagentStop-only).
"""

import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
UTILS = SHARED / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"

sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

import patterns_used_state as pus  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
PID_A = "ctx-4338628010-5127"
PID_B = "ctx-6257961166-f081"
SESSION = "cc-sess-degen-skip-test-abc"
WORK_UUID = "bbbbcccc-1111-2222-3333-ddddeeee0002"
TASK_SID = "tttt-2222-3333-4444-task-session-uuid"
RETRIEVAL_ID = "ret-uuid-cccc-dddd-eeee"
NO_PROMPT_SENTINEL = "No user prompt found"


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_after_task():
    """Load ace_after_task module fresh (avoids cross-test state)."""
    mod_path = SHARED / "ace_after_task.py"
    spec = importlib.util.spec_from_file_location("ace_after_task_degen", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_state(state_dir, agent_id, pattern_ids=None, task_session_id=None,
                 retrieval_id=None, retrieval_log_ids=None):
    """Write a patterns-used state file under the given agent_id (or 'main' if None)."""
    pus.append_patterns_used(
        SESSION,
        agent_id,
        pattern_ids or [PID_A],
        state_dir=str(state_dir),
        task_session_id=task_session_id,
        retrieval_id=retrieval_id,
        retrieval_log_ids=retrieval_log_ids or {},
    )


def _read_relevance_log(log_path):
    """Parse all lines from ace-relevance.jsonl as JSON objects."""
    p = Path(log_path)
    if not p.exists():
        return []
    records = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def _run_main(tmp_path, monkeypatch, event,
              write_state_under=None,
              user_prompt_return=None,
              learn_spy=None):
    """
    Wire minimal mocks and run main(), returning (all_relevance_records, captured).

    captured["learn_calls"] is the list of (trace, kwargs) tuples if learn was called.
    captured["learn_called"] is True if _learn_via_transcript was called at all.
    """
    state_dir = tmp_path / ".claude" / "data" / "logs"

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    if write_state_under is not None:
        _write_state(
            state_dir,
            write_state_under,
            pattern_ids=[PID_A],
            task_session_id=TASK_SID,
            retrieval_id=RETRIEVAL_ID,
        )

    mod = _load_after_task()
    monkeypatch.setattr(mod, "get_context",
                        lambda: {"org": "org-1", "project": "prj-1"})
    monkeypatch.setattr(mod, "build_trajectory_from_accumulated_tools",
                        lambda *a, **k: ([], [
                            ("Edit", "{}", "{}", "tu-01", None, None, None, None),
                        ]))

    prompt_to_return = user_prompt_return if user_prompt_return is not None else "implement feature X"
    monkeypatch.setattr(mod, "get_user_prompt_from_transcript",
                        lambda p: prompt_to_return)
    monkeypatch.setattr(mod, "is_trivial_task", lambda t: False)
    monkeypatch.setattr(mod, "has_substantial_work_from_accumulated",
                        lambda tools: True)

    captured = {"learn_called": False, "learn_calls": []}

    def fake_learn(trace, env=None, verbosity="detailed",
                   retrieval_id=None, applied_log_ids=None, **kw):
        captured["learn_called"] = True
        captured["learn_calls"].append({
            "trace": trace,
            "retrieval_id": retrieval_id,
            "applied_log_ids": applied_log_ids,
        })
        if learn_spy:
            learn_spy(trace, retrieval_id=retrieval_id, applied_log_ids=applied_log_ids)
        r = MagicMock()
        r.returncode = 1  # skip success branch (avoid stdout parsing)
        return r

    monkeypatch.setattr(mod, "_learn_via_transcript", fake_learn)
    monkeypatch.setattr(mod, "get_git_context", lambda wd: None)
    monkeypatch.setattr(mod, "detect_commits_in_session", lambda t: [])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr("sys.stdout", io.StringIO())

    exit_code = 0
    try:
        mod.main()
    except SystemExit as e:
        exit_code = e.code or 0

    captured["exit_code"] = exit_code

    log_path = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    records = _read_relevance_log(str(log_path))
    return records, captured


# ── event builders ────────────────────────────────────────────────────────────

def _subagent_stop_event(tmp_path, agent_id=WORK_UUID, transcript_uuid=WORK_UUID,
                         create_transcript=True):
    """Build a SubagentStop event dict."""
    event = {
        "hook_event_name": "SubagentStop",
        "session_id": SESSION,
        "agent_id": agent_id,
        "agent_type": "coder",
        "cwd": str(tmp_path),
    }
    if transcript_uuid is not None:
        tp = tmp_path / f"agent-{transcript_uuid}.jsonl"
        if create_transcript:
            tp.touch()
        event["agent_transcript_path"] = str(tp)
    return event


def _empty_agent_subagent_event(tmp_path, transcript_uuid=None, create_transcript=False):
    """SubagentStop with empty agent_id — the degenerate fan-out case."""
    event = {
        "hook_event_name": "SubagentStop",
        "session_id": SESSION,
        "agent_id": "",          # empty — the degenerate case
        "agent_type": "",
        "cwd": str(tmp_path),
    }
    if transcript_uuid is not None:
        tp = tmp_path / f"agent-{transcript_uuid}.jsonl"
        if create_transcript:
            tp.touch()
        event["agent_transcript_path"] = str(tp)
    return event


# ══════════════════════════════════════════════════════════════════════════════
# 1. Stage 1: agent_id recovery from transcript path
# ══════════════════════════════════════════════════════════════════════════════

class TestStage1AgentIdRecovery:
    """Stage 1: when event.agent_id is empty but agent_transcript_path is
    agent-{uuid}.jsonl, recover agent_id from the filename BEFORE state reads.
    """

    def test_recovered_agent_id_reads_correct_state_file(self, tmp_path, monkeypatch):
        """Empty agent_id + agent_transcript_path=agent-{uuid}.jsonl + seeded state
        under {uuid} → task_session_id is read from the {uuid} file → learn is NOT
        skipped (anchor is present via recovered task_session_id).

        RED: before Stage 1 fix, agent_id stays empty → load_task_session_id reads
        the '-main' file (or nothing) → task_session_id=None → Stage 2 (once
        implemented) would skip OR learn sends an unanchored trace.
        """
        event = _empty_agent_subagent_event(
            tmp_path, transcript_uuid=WORK_UUID, create_transcript=True
        )
        # State seeded under WORK_UUID (what Stage 1 should recover)
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,         # key = recovered agent_id
            user_prompt_return="implement feature X",
        )
        # After Stage 1 fix, the recovered agent_id reads the state, so tsid is found
        # and learn is called (trace is not degenerate).
        assert captured["learn_called"], (
            "After Stage 1 recovery, state file under WORK_UUID should be read, "
            "task_session_id found, and learn should be called (trace is NOT degenerate)"
        )
        trace = captured["learn_calls"][0]["trace"]
        # task_session_id should appear in the trace's session_id field
        assert trace.get("session_id") == TASK_SID, (
            f"Recovered agent_id must read state under {WORK_UUID!r}; "
            f"expected session_id={TASK_SID!r}, got {trace.get('session_id')!r}"
        )

    def test_telemetry_agent_id_recovered_true(self, tmp_path, monkeypatch):
        """subagent_stop_keymap telemetry record must include agent_id_recovered=True
        when Stage 1 changed agent_id from empty to recovered.

        RED: current code never sets agent_id_recovered in the keymap record.
        """
        event = _empty_agent_subagent_event(
            tmp_path, transcript_uuid=WORK_UUID, create_transcript=True
        )
        records, _ = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,
        )
        keymap_records = [r for r in records if r.get("event") == "subagent_stop_keymap"]
        assert keymap_records, "Expected subagent_stop_keymap record"
        rec = keymap_records[-1]
        assert "agent_id_recovered" in rec, (
            f"subagent_stop_keymap must contain 'agent_id_recovered' field; got {rec}"
        )
        assert rec["agent_id_recovered"] is True, (
            f"agent_id_recovered must be True when Stage 1 changed agent_id; got {rec}"
        )

    def test_no_recovery_when_agent_id_already_set(self, tmp_path, monkeypatch):
        """When agent_id is already set (normal case), agent_id_recovered=False
        and no recovery takes place.
        """
        event = _subagent_stop_event(tmp_path, agent_id=WORK_UUID,
                                     transcript_uuid=WORK_UUID, create_transcript=True)
        records, _ = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,
        )
        keymap_records = [r for r in records if r.get("event") == "subagent_stop_keymap"]
        assert keymap_records, "Expected subagent_stop_keymap record"
        rec = keymap_records[-1]
        # agent_id_recovered should be present and False (no recovery needed)
        assert rec.get("agent_id_recovered") is False, (
            f"agent_id_recovered must be False when event.agent_id was already set; got {rec}"
        )

    def test_existing_keymap_fields_still_present(self, tmp_path, monkeypatch):
        """Stage 1 must NOT remove existing invariant_ok/read_key/transcript_uuid fields."""
        event = _empty_agent_subagent_event(
            tmp_path, transcript_uuid=WORK_UUID, create_transcript=True
        )
        records, _ = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,
        )
        keymap_records = [r for r in records if r.get("event") == "subagent_stop_keymap"]
        assert keymap_records, "Expected subagent_stop_keymap record"
        rec = keymap_records[-1]
        for field in ("invariant_ok", "read_key", "transcript_uuid", "timestamp"):
            assert field in rec, (
                f"Existing field {field!r} must still be present in keymap record; got {rec}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 2. Stage 2: skip anchorless degenerate subagent traces
# ══════════════════════════════════════════════════════════════════════════════

class TestStage2DegenerateSkip:
    """Stage 2: if ALL anchors absent AND prompt = sentinel → skip + emit record."""

    def test_fully_degenerate_skip_no_learn_call(self, tmp_path, monkeypatch):
        """SubagentStop with empty agent_id, no recoverable transcript, no state,
        no anchors, user_prompt = sentinel → _learn_via_transcript must NOT be called.

        RED: current code always calls _learn_via_transcript (no degenerate skip guard).
        """
        # No transcript_uuid → recovery fails → agent_id stays empty → no state file
        event = _empty_agent_subagent_event(tmp_path, transcript_uuid=None)
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=None,
            user_prompt_return=NO_PROMPT_SENTINEL,
        )
        assert not captured["learn_called"], (
            "Fully degenerate SubagentStop must NOT call _learn_via_transcript; "
            "learn was called unexpectedly"
        )

    def test_fully_degenerate_skip_emits_relevance_record(self, tmp_path, monkeypatch):
        """A subagent_degenerate_skip relevance record must be emitted when skipping.

        RED: current code emits no such record.
        """
        event = _empty_agent_subagent_event(tmp_path, transcript_uuid=None)
        records, _ = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=None,
            user_prompt_return=NO_PROMPT_SENTINEL,
        )
        skip_records = [r for r in records if r.get("event") == "subagent_degenerate_skip"]
        assert skip_records, (
            "Expected a 'subagent_degenerate_skip' record in ace-relevance.jsonl; "
            f"got records: {[r.get('event') for r in records]}"
        )

    def test_degenerate_skip_record_has_required_fields(self, tmp_path, monkeypatch):
        """subagent_degenerate_skip record must have session_id, agent_id, reason."""
        event = _empty_agent_subagent_event(tmp_path, transcript_uuid=None)
        records, _ = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=None,
            user_prompt_return=NO_PROMPT_SENTINEL,
        )
        skip_records = [r for r in records if r.get("event") == "subagent_degenerate_skip"]
        assert skip_records, "Expected subagent_degenerate_skip record"
        rec = skip_records[-1]
        assert "session_id" in rec, f"session_id missing from skip record: {rec}"
        assert "agent_id" in rec, f"agent_id missing from skip record: {rec}"
        assert "reason" in rec, f"reason missing from skip record: {rec}"

    def test_degenerate_skip_exits_zero(self, tmp_path, monkeypatch):
        """Degenerate skip must exit with code 0 (clean hook termination)."""
        event = _empty_agent_subagent_event(tmp_path, transcript_uuid=None)
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=None,
            user_prompt_return=NO_PROMPT_SENTINEL,
        )
        assert captured.get("exit_code", 0) == 0, (
            f"Degenerate skip must exit 0; got {captured.get('exit_code')}"
        )

    def test_degenerate_skip_reaps_state_file(self, tmp_path, monkeypatch):
        """Even a degenerate trace must reap its state file (best-effort clean-up).
        For fully empty agent_id with no recovery, there may be no state file to reap;
        the important thing is reap_patterns_used is called (does not raise).
        This test verifies no state file is left behind for the empty-agent_id key.
        """
        event = _empty_agent_subagent_event(tmp_path, transcript_uuid=None)
        # Write a state file under 'None' agent (the '-main' suffix) to verify it gets reaped
        state_dir = tmp_path / ".claude" / "data" / "logs"
        pus.append_patterns_used(
            SESSION, None, [PID_A],
            state_dir=str(state_dir),
            task_session_id=None,
        )
        main_sf = pus.state_file_path(SESSION, None, state_dir=str(state_dir))
        assert main_sf.exists(), "Precondition: state file must exist before test"

        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=None,  # don't re-seed (already written above)
            user_prompt_return=NO_PROMPT_SENTINEL,
        )
        # Skip must have fired (guard verified by no learn call)
        assert not captured["learn_called"], "Degenerate skip: learn must not be called"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Happy path: normal SubagentStop unchanged
# ══════════════════════════════════════════════════════════════════════════════

class TestHappyPathUnchanged:
    """Normal SubagentStop (populated agent_id + seeded state) must learn normally."""

    def test_normal_subagent_stop_calls_learn(self, tmp_path, monkeypatch):
        """Normal SubagentStop with agent_id + seeded state → learn is called."""
        event = _subagent_stop_event(tmp_path, agent_id=WORK_UUID,
                                     transcript_uuid=WORK_UUID, create_transcript=True)
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,
        )
        assert captured["learn_called"], (
            "Normal SubagentStop (agent_id set, state seeded) must call learn"
        )

    def test_normal_subagent_stop_no_degenerate_skip_record(self, tmp_path, monkeypatch):
        """Normal SubagentStop must NOT emit a subagent_degenerate_skip record."""
        event = _subagent_stop_event(tmp_path, agent_id=WORK_UUID,
                                     transcript_uuid=WORK_UUID, create_transcript=True)
        records, _ = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,
        )
        skip_records = [r for r in records if r.get("event") == "subagent_degenerate_skip"]
        assert not skip_records, (
            f"Normal SubagentStop must NOT produce degenerate_skip record; got {skip_records}"
        )

    def test_normal_subagent_stop_carries_task_session_id(self, tmp_path, monkeypatch):
        """Normal SubagentStop: trace contains task_session_id from state file."""
        event = _subagent_stop_event(tmp_path, agent_id=WORK_UUID,
                                     transcript_uuid=WORK_UUID, create_transcript=True)
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,
        )
        assert captured["learn_called"]
        trace = captured["learn_calls"][0]["trace"]
        assert trace.get("session_id") == TASK_SID, (
            f"Normal SubagentStop trace must carry task_session_id={TASK_SID!r}; "
            f"got {trace.get('session_id')!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Partial-anchor NOT skipped (precision: only skip when FULLY anchorless+promptless)
# ══════════════════════════════════════════════════════════════════════════════

class TestPartialAnchorNotSkipped:
    """Stage 2 must only skip when ALL anchors absent AND prompt = sentinel.
    If ANY anchor is present OR there is a real prompt, do NOT skip.
    """

    def test_tsid_present_prompt_sentinel_not_skipped(self, tmp_path, monkeypatch):
        """task_session_id present, prompt = sentinel → NOT skipped (anchor present)."""
        event = _empty_agent_subagent_event(
            tmp_path, transcript_uuid=WORK_UUID, create_transcript=True
        )
        # State seeded under WORK_UUID so Stage 1 recovery gets task_session_id
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=WORK_UUID,
            user_prompt_return=NO_PROMPT_SENTINEL,  # prompt is sentinel
        )
        # tsid comes from recovered state → anchor is present → must NOT skip
        assert captured["learn_called"], (
            "task_session_id present (even with sentinel prompt) → NOT skipped; "
            "learn must be called"
        )
        skip_records = [r for r in records if r.get("event") == "subagent_degenerate_skip"]
        assert not skip_records, (
            "Partial-anchor (tsid present, prompt=sentinel) must NOT produce skip record"
        )

    def test_real_prompt_no_anchors_not_skipped(self, tmp_path, monkeypatch):
        """Real user prompt but no tsid/retrieval_id/applied_log_ids → NOT skipped.

        A real prompt means the trace is not fully promptless; send it normally.
        The event must include a transcript path so get_user_prompt_from_transcript
        is actually called (otherwise transcript_path is '' and prompt stays sentinel).
        We use a non-agent-pattern filename so Stage 1 recovery also fails (no
        agent_id recovered → no state) but the prompt mock returns a real prompt.
        """
        # Non-agent-pattern transcript → Stage 1 recovery fails (not "agent-{uuid}.jsonl")
        non_agent_transcript = tmp_path / "main-conversation.jsonl"
        non_agent_transcript.touch()
        event = {
            "hook_event_name": "SubagentStop",
            "session_id": SESSION,
            "agent_id": "",          # empty — degenerate
            "agent_type": "",
            "cwd": str(tmp_path),
            "agent_transcript_path": str(non_agent_transcript),  # present but non-agent pattern
        }
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=None,
            user_prompt_return="implement the payment system",  # real prompt
        )
        assert captured["learn_called"], (
            "Real prompt present (no anchors) → NOT skipped; learn must be called"
        )
        skip_records = [r for r in records if r.get("event") == "subagent_degenerate_skip"]
        assert not skip_records, (
            "Real prompt but no anchors must NOT produce subagent_degenerate_skip record"
        )

    def test_retrieval_id_only_not_skipped(self, tmp_path, monkeypatch):
        """retrieval_id present (no tsid, no applied_log_ids, sentinel prompt) → NOT skipped."""
        # Build state with retrieval_id but no task_session_id
        state_dir = tmp_path / ".claude" / "data" / "logs"
        state_dir.mkdir(parents=True, exist_ok=True)
        pus.append_patterns_used(
            SESSION, WORK_UUID, [PID_A],
            state_dir=str(state_dir),
            task_session_id=None,       # no tsid
            retrieval_id=RETRIEVAL_ID,  # but retrieval_id present
        )
        event = _empty_agent_subagent_event(
            tmp_path, transcript_uuid=WORK_UUID, create_transcript=True
        )
        records, captured = _run_main(
            tmp_path, monkeypatch, event,
            write_state_under=None,     # already written above
            user_prompt_return=NO_PROMPT_SENTINEL,
        )
        # retrieval_id comes from state (read via Stage 1 recovered agent_id)
        # Since retrieval_id is an anchor, must NOT skip
        assert captured["learn_called"], (
            "retrieval_id present (even without tsid/prompt) → NOT skipped"
        )
        skip_records = [r for r in records if r.get("event") == "subagent_degenerate_skip"]
        assert not skip_records, (
            "retrieval_id present → must NOT produce degenerate_skip record"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. Main Stop never skipped by Stage 2 logic
# ══════════════════════════════════════════════════════════════════════════════

class TestMainStopNotAffected:
    """Stage 2 is SubagentStop-only; main Stop must never be affected."""

    def test_main_stop_calls_learn_even_when_no_anchors(self, tmp_path, monkeypatch):
        """Main Stop with no state, prompt = sentinel → Stage 2 does NOT fire;
        learn is called (or skipped for other reasons, but not the degenerate guard).
        """
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        transcript = tmp_path / "transcript.jsonl"
        transcript.touch()
        event = {
            "hook_event_name": "Stop",
            "session_id": SESSION,
            "agent_id": None,
            "agent_type": "main",
            "cwd": str(tmp_path),
            "transcript_path": str(transcript),
        }

        mod = _load_after_task()
        monkeypatch.setattr(mod, "get_context",
                            lambda: {"org": "org-1", "project": "prj-1"})
        monkeypatch.setattr(mod, "build_trajectory_from_accumulated_tools",
                            lambda *a, **k: ([], [
                                ("Edit", "{}", "{}", "tu-01", None, None, None, None),
                            ]))
        monkeypatch.setattr(mod, "get_user_prompt_from_transcript",
                            lambda p: NO_PROMPT_SENTINEL)
        monkeypatch.setattr(mod, "is_trivial_task", lambda t: False)
        monkeypatch.setattr(mod, "has_substantial_work_from_accumulated",
                            lambda tools: True)

        captured = {"learn_called": False}

        def fake_learn(trace, **kw):
            captured["learn_called"] = True
            r = MagicMock()
            r.returncode = 1
            return r

        monkeypatch.setattr(mod, "_learn_via_transcript", fake_learn)
        monkeypatch.setattr(mod, "get_git_context", lambda wd: None)
        monkeypatch.setattr(mod, "detect_commits_in_session", lambda t: [])
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        monkeypatch.setattr("sys.stdout", io.StringIO())

        try:
            mod.main()
        except SystemExit:
            pass

        # Stage 2 is SubagentStop-only. Main Stop must reach learn (or be skipped
        # for a different reason — but NOT the degenerate skip guard).
        log_path = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
        records = _read_relevance_log(str(log_path))
        skip_records = [r for r in records if r.get("event") == "subagent_degenerate_skip"]
        assert not skip_records, (
            f"subagent_degenerate_skip must NEVER fire for main Stop; got {skip_records}"
        )
        # learn must have been called (no anchors on Stop shouldn't trigger degenerate skip)
        assert captured["learn_called"], (
            "Main Stop must NOT be suppressed by the SubagentStop degenerate-skip guard"
        )
