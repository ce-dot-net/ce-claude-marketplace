#!/usr/bin/env python3
"""
Tests for v7.1.3 R1 (reduced) — SubagentStop read_key==transcript_uuid invariant monitor.

Background: a previous pass added a "read-recovery" to ace_after_task that, on a
per-agent state-file miss, derived the work agent_id from the subagent transcript
filename and retried.  Live probes (5/5, 100%) proved the recovery is structurally
inert: at SubagentStop, event.agent_id ALWAYS equals the transcript-derived uuid, so
the "recovery key" is always identical to the read-key that just missed — recovery can
never do anything.

The recovery branch has been intentionally REMOVED.  What remains is a lean always-on
invariant monitor: emit a "subagent_stop_keymap" record to ace-relevance.jsonl for
every SubagentStop so we would detect it immediately if the invariant ever breaks.

Deleted recovery tests (and why):
  - TestSubagentStopRecoveryOnMiss.test_recovered_playbook_used_contains_pattern_ids
  - TestSubagentStopRecoveryOnMiss.test_recovered_task_session_id_in_trace
  - TestSubagentStopRecoveryOnMiss.test_recovered_retrieval_id_passed_to_learn
  - TestSubagentStopRecoveryOnMiss.test_recovered_applied_log_ids_passed_to_learn
  - TestSubagentStopRecoveryOnMiss.test_orphaned_state_file_is_reaped
  All five tested the "recover from transcript uuid" behaviour that is intentionally
  gone.  Keeping tests for deliberately-removed behaviour would make them permanently
  red with no remediation path.  The invariant monitor tests below provide equivalent
  observability coverage.

Tests kept / added:
  1. _agent_id_from_transcript_path helper — unit tests (unchanged from previous pass)
  2. Happy path: agent_id is NOT reassigned — state reads use event.agent_id unchanged
  3. Invariant monitor emits subagent_stop_keymap with invariant_ok=True (keys match)
  4. Invariant monitor emits subagent_stop_keymap with invariant_ok=False (keys differ)
  5. No transcript / non-matching filename — graceful, record still emitted, no raise
  6. Main Stop emits NO keymap record
"""

import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

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
SESSION = "cc-sess-recovery-test-abc"
WORK_UUID = "aaaabbbb-1111-2222-3333-ccccdddd0001"
# In the new invariant, event.agent_id should ALWAYS equal the transcript uuid.
# For the invariant_ok=True tests we set agent_id == WORK_UUID.
# For the invariant_ok=False tests we deliberately set a DIFFERENT agent_id to
# prove the monitor would catch a breakage.
EVENT_AGENT_ID = WORK_UUID          # normal: matches transcript
DIFFERENT_AGENT_ID = "different-key-9999-from-event"  # abnormal: breaks invariant
TASK_SID = "tttt-1111-2222-3333-task-session-uuid"
RETRIEVAL_ID = "ret-uuid-aaaa-bbbb-cccc"


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_after_task():
    """Load ace_after_task module fresh (avoids cross-test state)."""
    mod_path = SHARED / "ace_after_task.py"
    spec = importlib.util.spec_from_file_location("ace_after_task", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_state(tmp_path, agent_id, pattern_ids=None, task_session_id=None,
                 retrieval_id=None, retrieval_log_ids=None):
    """Write a state file under the given agent_id (or 'main' if None)."""
    pus.append_patterns_used(
        SESSION,
        agent_id,
        pattern_ids or [PID_A],
        state_dir=str(tmp_path),
        task_session_id=task_session_id,
        retrieval_id=retrieval_id,
        retrieval_log_ids=retrieval_log_ids or {},
    )


def _read_relevance_log(log_path):
    """Read all lines from ace-relevance.jsonl, parse as JSON."""
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


# ── minimal event builder ─────────────────────────────────────────────────────

def _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                         transcript_uuid=None, include_transcript=True):
    """Build a SubagentStop event dict.

    If transcript_uuid is given, agent_transcript_path is set to a filename
    matching agent-{transcript_uuid}.jsonl; otherwise it is omitted or set
    to a non-matching path based on include_transcript.
    """
    event = {
        "hook_event_name": "SubagentStop",
        "session_id": SESSION,
        "agent_id": agent_id,
        "agent_type": "coder",
        "cwd": str(tmp_path),
    }
    if transcript_uuid:
        # Create a real (but empty) file so Path(...).stem works
        transcript_path = tmp_path / f"agent-{transcript_uuid}.jsonl"
        transcript_path.touch()
        event["agent_transcript_path"] = str(transcript_path)
    elif include_transcript:
        # Present but non-matching filename
        transcript_path = tmp_path / "main-transcript.jsonl"
        transcript_path.touch()
        event["agent_transcript_path"] = str(transcript_path)
    return event


def _run_main(tmp_path, monkeypatch, event, write_state_under=None):
    """Wire up mocks and run main(), returning all subagent_stop_keymap records."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    if write_state_under is not None:
        _write_state(
            tmp_path / ".claude" / "data" / "logs",
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
    monkeypatch.setattr(mod, "get_user_prompt_from_transcript",
                        lambda p: "implement feature X")
    monkeypatch.setattr(mod, "is_trivial_task", lambda t: False)
    monkeypatch.setattr(mod, "has_substantial_work_from_accumulated",
                        lambda tools: True)

    captured = {}

    def fake_learn(trace, env=None, verbosity="detailed",
                   retrieval_id=None, applied_log_ids=None, **kw):
        captured["trace"] = trace
        r = MagicMock()
        r.returncode = 1  # skip success branch
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

    log_path = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    records = _read_relevance_log(str(log_path))
    keymap_records = [r for r in records if r.get("event") == "subagent_stop_keymap"]
    return keymap_records, captured


# ══════════════════════════════════════════════════════════════════════════════
# 1. _agent_id_from_transcript_path helper — unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentIdFromTranscriptPath:
    """Unit tests for the _agent_id_from_transcript_path helper."""

    def test_extracts_uuid_from_agent_filename(self):
        """agent-{uuid}.jsonl → returns {uuid}."""
        mod = _load_after_task()
        result = mod._agent_id_from_transcript_path(
            f"/some/dir/agent-{WORK_UUID}.jsonl"
        )
        assert result == WORK_UUID, (
            f"Expected {WORK_UUID!r}, got {result!r}"
        )

    def test_returns_none_for_non_agent_filename(self):
        """main-transcript.jsonl → None (no agent- prefix)."""
        mod = _load_after_task()
        result = mod._agent_id_from_transcript_path("/some/dir/main-transcript.jsonl")
        assert result is None, f"Expected None, got {result!r}"

    def test_returns_none_for_bare_agent_prefix(self):
        """agent-.jsonl → None (empty uuid part)."""
        mod = _load_after_task()
        result = mod._agent_id_from_transcript_path("/some/dir/agent-.jsonl")
        assert result is None, f"Expected None for empty uuid, got {result!r}"

    def test_returns_none_for_none_input(self):
        """None input → None, no raise."""
        mod = _load_after_task()
        result = mod._agent_id_from_transcript_path(None)
        assert result is None

    def test_returns_none_for_empty_string(self):
        """Empty string → None, no raise."""
        mod = _load_after_task()
        result = mod._agent_id_from_transcript_path("")
        assert result is None

    def test_does_not_raise_on_garbage_input(self):
        """Arbitrary garbage input must not raise."""
        mod = _load_after_task()
        for bad in [123, [], {}, object()]:
            try:
                mod._agent_id_from_transcript_path(bad)
                # any result (None or str) is fine; no exception is the requirement
            except Exception as e:
                pytest.fail(
                    f"_agent_id_from_transcript_path({bad!r}) raised {e!r}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# 2. Happy path: agent_id is NOT reassigned
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentIdNotReassigned:
    """agent_id must stay event.agent_id — recovery reassignment is gone."""

    def test_trace_agent_id_equals_event_agent_id(self, tmp_path, monkeypatch):
        """trace.agent_id must equal event.agent_id (not a transcript-recovered value)."""
        # State written under the same key as event.agent_id (the invariant case)
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     transcript_uuid=WORK_UUID)
        _, captured = _run_main(tmp_path, monkeypatch, event,
                                write_state_under=EVENT_AGENT_ID)
        trace = captured.get("trace") or {}
        assert trace.get("agent_id") == EVENT_AGENT_ID, (
            f"agent_id in trace should be {EVENT_AGENT_ID!r}; "
            f"got {trace.get('agent_id')!r}"
        )

    def test_no_state_file_agent_id_still_event_agent_id(self, tmp_path, monkeypatch):
        """Even with no state file at all, agent_id is unchanged (no recovery fallback)."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     transcript_uuid=WORK_UUID)
        # No state written at all
        _, captured = _run_main(tmp_path, monkeypatch, event,
                                write_state_under=None)
        trace = captured.get("trace") or {}
        # agent_id may be absent from trace if event.agent_id was falsy; if present must match
        if "agent_id" in trace:
            assert trace["agent_id"] == EVENT_AGENT_ID, (
                f"agent_id in trace should be {EVENT_AGENT_ID!r}; "
                f"got {trace.get('agent_id')!r}"
            )

    def test_patterns_read_from_event_agent_id_key(self, tmp_path, monkeypatch):
        """Patterns are read from the event.agent_id state file, not a recovered key."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     transcript_uuid=WORK_UUID)
        _, captured = _run_main(tmp_path, monkeypatch, event,
                                write_state_under=EVENT_AGENT_ID)
        trace = captured.get("trace") or {}
        assert PID_A in trace.get("playbook_used", []), (
            f"PID_A must be in playbook_used from event.agent_id key; "
            f"got {trace.get('playbook_used')!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3. Invariant monitor — invariant_ok=True (keys match)
# ══════════════════════════════════════════════════════════════════════════════

class TestInvariantMonitorMatch:
    """Monitor emits invariant_ok=True when read_key == transcript_uuid."""

    def test_record_emitted(self, tmp_path, monkeypatch):
        """A subagent_stop_keymap record is written for every SubagentStop."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     transcript_uuid=WORK_UUID)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected at least one subagent_stop_keymap record; got none"

    def test_invariant_ok_true_when_keys_match(self, tmp_path, monkeypatch):
        """invariant_ok=True when event.agent_id == transcript uuid."""
        # EVENT_AGENT_ID == WORK_UUID → keys match
        event = _subagent_stop_event(tmp_path, agent_id=WORK_UUID,
                                     transcript_uuid=WORK_UUID)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record"
        rec = records[-1]
        assert rec.get("invariant_ok") is True, (
            f"invariant_ok should be True when keys match; got {rec}"
        )

    def test_record_has_required_fields(self, tmp_path, monkeypatch):
        """Record must contain: event, hook, session_id, read_key, transcript_uuid, invariant_ok."""
        event = _subagent_stop_event(tmp_path, agent_id=WORK_UUID,
                                     transcript_uuid=WORK_UUID)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record"
        rec = records[-1]
        assert rec.get("event") == "subagent_stop_keymap", f"event field wrong: {rec}"
        assert rec.get("hook") == "SubagentStop", f"hook field wrong: {rec}"
        assert rec.get("session_id") == SESSION, f"session_id wrong: {rec}"
        assert rec.get("read_key") == WORK_UUID, f"read_key wrong: {rec}"
        assert rec.get("transcript_uuid") == WORK_UUID, f"transcript_uuid wrong: {rec}"
        assert "invariant_ok" in rec, f"invariant_ok key missing: {rec}"
        assert "timestamp" in rec, f"timestamp key missing: {rec}"

    def test_no_primary_hit_or_recovered_fields(self, tmp_path, monkeypatch):
        """The old primary_hit and recovered fields must NOT appear in the new record."""
        event = _subagent_stop_event(tmp_path, agent_id=WORK_UUID,
                                     transcript_uuid=WORK_UUID)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record"
        rec = records[-1]
        assert "primary_hit" not in rec, (
            f"primary_hit field must be absent (recovery removed); got {rec}"
        )
        assert "recovered" not in rec, (
            f"recovered field must be absent (recovery removed); got {rec}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Invariant monitor — invariant_ok=False (keys differ — alarm case)
# ══════════════════════════════════════════════════════════════════════════════

class TestInvariantMonitorMismatch:
    """Monitor emits invariant_ok=False when read_key != transcript_uuid.

    This proves the monitor WOULD catch a real invariant breakage — i.e. if CC
    ever starts providing a different agent_id than the transcript uuid, the record
    will clearly flag it.
    """

    def test_invariant_ok_false_when_keys_differ(self, tmp_path, monkeypatch):
        """invariant_ok=False when event.agent_id != transcript uuid."""
        # Set event.agent_id to something DIFFERENT from the transcript uuid
        event = _subagent_stop_event(tmp_path, agent_id=DIFFERENT_AGENT_ID,
                                     transcript_uuid=WORK_UUID)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record"
        rec = records[-1]
        assert rec.get("invariant_ok") is False, (
            f"invariant_ok should be False when keys differ; got {rec}"
        )

    def test_read_key_and_transcript_uuid_both_present(self, tmp_path, monkeypatch):
        """Both read_key and transcript_uuid are present even when they differ."""
        event = _subagent_stop_event(tmp_path, agent_id=DIFFERENT_AGENT_ID,
                                     transcript_uuid=WORK_UUID)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record"
        rec = records[-1]
        assert rec.get("read_key") == DIFFERENT_AGENT_ID, (
            f"read_key should be {DIFFERENT_AGENT_ID!r}; got {rec}"
        )
        assert rec.get("transcript_uuid") == WORK_UUID, (
            f"transcript_uuid should be {WORK_UUID!r}; got {rec}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. Graceful degradation — no transcript / non-matching filename
# ══════════════════════════════════════════════════════════════════════════════

class TestSubagentStopGracefulDegradation:
    """No transcript or non-matching filename → no raise; record still emitted."""

    def test_no_transcript_does_not_raise(self, tmp_path, monkeypatch):
        """SubagentStop without agent_transcript_path must not raise."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     include_transcript=False)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        # No exception is the requirement; record being emitted is a bonus
        # (we just don't assert on it here — no_raise is the contract)

    def test_non_matching_filename_does_not_raise(self, tmp_path, monkeypatch):
        """SubagentStop with agent_transcript_path not matching agent-*.jsonl → no raise."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     transcript_uuid=None, include_transcript=True)
        records, _ = _run_main(tmp_path, monkeypatch, event)

    def test_no_transcript_record_still_emitted(self, tmp_path, monkeypatch):
        """Record is emitted even with no agent_transcript_path."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     include_transcript=False)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record even with no transcript"

    def test_no_transcript_transcript_uuid_is_none(self, tmp_path, monkeypatch):
        """When no transcript, transcript_uuid=None and invariant_ok=False (None != read_key)."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     include_transcript=False)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record"
        rec = records[-1]
        assert rec.get("transcript_uuid") is None, (
            f"transcript_uuid should be None with no transcript; got {rec}"
        )
        # invariant_ok: None != read_key → False (unless read_key is also None)
        if rec.get("read_key") is not None:
            assert rec.get("invariant_ok") is False, (
                f"invariant_ok should be False when transcript_uuid is None; got {rec}"
            )

    def test_non_matching_filename_transcript_uuid_is_none(self, tmp_path, monkeypatch):
        """Non-matching filename → transcript_uuid=None."""
        event = _subagent_stop_event(tmp_path, agent_id=EVENT_AGENT_ID,
                                     transcript_uuid=None, include_transcript=True)
        records, _ = _run_main(tmp_path, monkeypatch, event)
        assert records, "Expected subagent_stop_keymap record"
        rec = records[-1]
        assert rec.get("transcript_uuid") is None, (
            f"Non-matching filename should yield transcript_uuid=None; got {rec}"
        )

    def test_missing_transcript_file_does_not_raise(self, tmp_path, monkeypatch):
        """agent_transcript_path pointing to nonexistent file → no raise."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        event = {
            "hook_event_name": "SubagentStop",
            "session_id": SESSION,
            "agent_id": EVENT_AGENT_ID,
            "agent_type": "coder",
            "cwd": str(tmp_path),
            "agent_transcript_path": str(tmp_path / "agent-does-not-exist.jsonl"),
        }
        # _agent_id_from_transcript_path uses Path.stem (no I/O), so missing file is fine
        records, _ = _run_main(tmp_path, monkeypatch, event)
        # No exception raised — test passes if we reach here


# ══════════════════════════════════════════════════════════════════════════════
# 6. Main Stop must NOT emit subagent_stop_keymap
# ══════════════════════════════════════════════════════════════════════════════

class TestMainStopNoKeymap:
    """subagent_stop_keymap must NOT be emitted for main Stop events."""

    def test_main_stop_emits_no_keymap_record(self, tmp_path, monkeypatch):
        """Stop (main) must not emit subagent_stop_keymap."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        event = {
            "hook_event_name": "Stop",
            "session_id": SESSION,
            "agent_id": None,
            "agent_type": "main",
            "cwd": str(tmp_path),
            "transcript_path": str(tmp_path / "transcript.jsonl"),
        }
        (tmp_path / "transcript.jsonl").touch()

        mod = _load_after_task()
        monkeypatch.setattr(mod, "get_context",
                            lambda: {"org": "org-1", "project": "prj-1"})
        monkeypatch.setattr(mod, "build_trajectory_from_accumulated_tools",
                            lambda *a, **k: ([], [
                                ("Edit", "{}", "{}", "tu-01", None, None, None, None),
                            ]))
        monkeypatch.setattr(mod, "get_user_prompt_from_transcript",
                            lambda p: "implement feature")
        monkeypatch.setattr(mod, "is_trivial_task", lambda t: False)
        monkeypatch.setattr(mod, "has_substantial_work_from_accumulated",
                            lambda tools: True)

        def fake_learn(trace, **kw):
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

        log_path = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
        records = _read_relevance_log(str(log_path))
        keymap_records = [r for r in records if r.get("event") == "subagent_stop_keymap"]
        assert not keymap_records, (
            f"subagent_stop_keymap must NOT be emitted for main Stop; "
            f"got: {keymap_records}"
        )
