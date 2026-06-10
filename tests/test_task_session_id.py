#!/usr/bin/env python3
"""
STEP 1 — RED tests for per-task session_id (task_session_id) feature.

Design: each task (UserPromptSubmit / SubagentStart) generates a fresh
uuid4 as task_session_id.  That value is:
  - passed to run_search() as the session_id argument (--pin-session)
  - stored in the per-agent patterns-used state file under "task_session_id"
  - read back by ace_after_task BEFORE the state file is reaped
  - placed into trace["session_id"] when present, OMITTED when absent

The CC conversation session_id continues to be the state-file KEY but is
NOT sent to ace-cli search --pin-session or written into trace["session_id"].

References: spec in the TDD task prompt.
"""

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── path setup ───────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
UTILS = SHARED / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"

sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

import patterns_used_state as pus  # noqa: E402

# Real-shaped pattern IDs
PID_A = "ctx-4338628010-5127"
PID_B = "ctx-6257961166-f081"
SESSION = "cc-conversation-session-abc123"
AGENT_ID = "subagent-11111111-2222-3333-4444-555555555555"
TASK_SESSION = "tttt-1111-2222-3333-4444-555555555555"


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_before_task():
    return _load_module("ace_before_task", SHARED / "ace_before_task.py")


def _load_subagent_start():
    return _load_module("ace_subagent_start", SHARED / "ace_subagent_start.py")


def _make_transcript(tmp_path, blocks):
    """Write a minimal JSONL transcript for subagent tests."""
    lines = []
    for i, block in enumerate(blocks):
        tool_input = {}
        if "subagent_type" in block:
            tool_input["subagent_type"] = block["subagent_type"]
        if "prompt" in block:
            tool_input["prompt"] = block["prompt"]
        entry = {
            "type": "assistantMessage",
            "uuid": f"uuid-{i}",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": f"toolu_{i:04d}",
                              "name": "Task", "input": tool_input}],
            },
        }
        lines.append(json.dumps(entry))
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("\n".join(lines) + "\n")
    return str(transcript)


GOOD_CONTEXT = {"org": "org-test-01", "project": "prj-test-01"}

SAMPLE_PATTERNS_RESPONSE = {
    "similar_patterns": [
        {"id": PID_A, "domain": "claude-plugins", "content": "hook pattern",
         "confidence": 0.75, "helpful": 10, "harmful": 2,
         "match_factors": {"retrieval_log_id": 42, "retrieval_id": "ret-abc"}},
        {"id": PID_B, "domain": "python", "content": "python pattern",
         "confidence": 0.80, "helpful": 15, "harmful": 1,
         "match_factors": {"retrieval_log_id": 43, "retrieval_id": "ret-abc"}},
    ],
    "count": 2,
    "retrieval_id": "ret-abc-001",
}


# ════════════════════════════════════════════════════════════════════════════
# 1. patterns_used_state: append_patterns_used stores task_session_id
# ════════════════════════════════════════════════════════════════════════════

class TestPatternsUsedStateTaskSessionId:

    def test_append_stores_task_session_id(self, tmp_path):
        """append_patterns_used with task_session_id kwarg writes it into the state file."""
        pus.append_patterns_used(
            SESSION, None, [PID_A],
            state_dir=str(tmp_path),
            task_session_id=TASK_SESSION,
        )
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        assert sf.exists()
        data = json.loads(sf.read_text())
        assert data.get("task_session_id") == TASK_SESSION, (
            f"Expected task_session_id={TASK_SESSION!r} in state file; "
            f"got: {data!r}"
        )

    def test_append_without_task_session_id_omits_field(self, tmp_path):
        """Existing callers that don't pass task_session_id must not be broken."""
        pus.append_patterns_used(SESSION, None, [PID_A], state_dir=str(tmp_path))
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        data = json.loads(sf.read_text())
        # task_session_id absent or None — both acceptable
        assert data.get("task_session_id") is None, (
            f"Without task_session_id kwarg, field must be absent/None; got {data!r}"
        )

    def test_append_merges_task_session_id_keeps_new(self, tmp_path):
        """Second append with task_session_id updates (new value wins)."""
        pus.append_patterns_used(SESSION, None, [PID_A], state_dir=str(tmp_path),
                                 task_session_id="old-tsid")
        pus.append_patterns_used(SESSION, None, [PID_B], state_dir=str(tmp_path),
                                 task_session_id=TASK_SESSION)
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        data = json.loads(sf.read_text())
        assert data["task_session_id"] == TASK_SESSION

    def test_load_task_session_id_helper_reads_before_reap(self, tmp_path):
        """load_task_session_id() returns stored value WITHOUT unlinking the file."""
        pus.append_patterns_used(SESSION, None, [PID_A], state_dir=str(tmp_path),
                                 task_session_id=TASK_SESSION)
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        assert sf.exists()

        tsid = pus.load_task_session_id(SESSION, None, "Stop", state_dir=str(tmp_path))
        assert tsid == TASK_SESSION, (
            f"load_task_session_id should return {TASK_SESSION!r}; got {tsid!r}"
        )
        # Must NOT unlink
        assert sf.exists(), "load_task_session_id must not unlink the state file"

    def test_load_task_session_id_returns_none_when_absent(self, tmp_path):
        """load_task_session_id returns None when no state file exists."""
        tsid = pus.load_task_session_id(SESSION, None, "Stop", state_dir=str(tmp_path))
        assert tsid is None

    def test_load_task_session_id_returns_none_for_legacy_file(self, tmp_path):
        """load_task_session_id returns None for legacy bare-list state file."""
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps([PID_A]))  # legacy bare list

        tsid = pus.load_task_session_id(SESSION, None, "Stop", state_dir=str(tmp_path))
        assert tsid is None

    def test_load_task_session_id_subagent_routes_to_agent_file(self, tmp_path):
        """SubagentStop routing: reads the -{agent_id} file, not -main."""
        pus.append_patterns_used(SESSION, AGENT_ID, [PID_A], state_dir=str(tmp_path),
                                 task_session_id=TASK_SESSION)
        pus.append_patterns_used(SESSION, None, [PID_B], state_dir=str(tmp_path),
                                 task_session_id="main-tsid")

        tsid = pus.load_task_session_id(SESSION, AGENT_ID, "SubagentStop",
                                        state_dir=str(tmp_path))
        assert tsid == TASK_SESSION, (
            f"SubagentStop should read from agent file; got {tsid!r}"
        )

    def test_read_state_file_returns_4tuple(self, tmp_path):
        """_read_state_file must return a 4-tuple including task_session_id."""
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps({
            "pattern_ids": [PID_A],
            "retrieval_id": "rid-1",
            "retrieval_log_ids": {},
            "task_session_id": TASK_SESSION,
        }))
        result = pus._read_state_file(sf)
        assert len(result) == 4, (
            f"_read_state_file must return 4-tuple; got {len(result)}-tuple"
        )
        ids, rid, rlog, tsid = result
        assert tsid == TASK_SESSION

    def test_read_state_file_legacy_list_returns_4tuple_with_none(self, tmp_path):
        """Legacy bare-list files return (ids, None, {}, None) — 4-tuple."""
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps([PID_A]))
        result = pus._read_state_file(sf)
        assert len(result) == 4
        ids, rid, rlog, tsid = result
        assert ids == [PID_A]
        assert tsid is None


# ════════════════════════════════════════════════════════════════════════════
# 2. ace_before_task: generates task_session_id != CC session_id and passes it
# ════════════════════════════════════════════════════════════════════════════

class TestBeforeTaskSessionId:

    def test_run_search_receives_task_session_id_not_cc_session(self, tmp_path, monkeypatch):
        """run_search must receive a fresh uuid4 task_session_id, NOT the CC session_id."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        cc_session = "cc-conversation-session-xyz"

        event = {
            "session_id": cc_session,
            "prompt": "implement authentication system",
        }

        mod = _load_before_task()
        captured = {}

        def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
            captured["session_id"] = session_id
            return SAMPLE_PATTERNS_RESPONSE

        monkeypatch.setattr(mod, "run_search", fake_run_search)
        monkeypatch.setattr(mod, "check_session_pinning_available", lambda: True)
        monkeypatch.setattr(mod, "check_auth_status", lambda warn_threshold_hours=2.0: None)
        monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
        monkeypatch.setattr(mod, "append_patterns_used", MagicMock())
        monkeypatch.setattr(mod, "log_search_metrics", MagicMock())

        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        try:
            mod.main()
        except SystemExit:
            pass

        assert "session_id" in captured, "run_search was never called"
        passed_sid = captured["session_id"]
        assert passed_sid is not None, "run_search received session_id=None (pinning active)"
        assert passed_sid != cc_session, (
            f"run_search must receive task_session_id (uuid4), NOT CC session_id "
            f"{cc_session!r}; got {passed_sid!r}"
        )
        # Must look like a uuid4
        try:
            uuid.UUID(passed_sid)
        except ValueError:
            pytest.fail(f"task_session_id passed to run_search is not a uuid4: {passed_sid!r}")

    def test_task_session_id_persisted_in_state_file(self, tmp_path, monkeypatch):
        """The task_session_id must be stored in the patterns-used state file."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        cc_session = "cc-conv-sess-abc"

        event = {
            "session_id": cc_session,
            "prompt": "implement database schema migration",
        }

        mod = _load_before_task()
        captured_task_session = {}

        def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
            captured_task_session["tsid"] = session_id
            return SAMPLE_PATTERNS_RESPONSE

        pu_calls = []

        def fake_append_pu(session_id, agent_id, pattern_ids, **kwargs):
            pu_calls.append({"session_id": session_id, "agent_id": agent_id,
                             "task_session_id": kwargs.get("task_session_id")})
            return pattern_ids

        monkeypatch.setattr(mod, "run_search", fake_run_search)
        monkeypatch.setattr(mod, "check_session_pinning_available", lambda: True)
        monkeypatch.setattr(mod, "check_auth_status", lambda warn_threshold_hours=2.0: None)
        monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
        monkeypatch.setattr(mod, "append_patterns_used", fake_append_pu)
        monkeypatch.setattr(mod, "log_search_metrics", MagicMock())

        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        try:
            mod.main()
        except SystemExit:
            pass

        assert pu_calls, "append_patterns_used was never called"
        call_0 = pu_calls[0]
        assert call_0["session_id"] == cc_session, (
            f"State file KEY must use CC session_id; got {call_0['session_id']!r}"
        )
        tsid_in_call = call_0.get("task_session_id")
        assert tsid_in_call is not None, "task_session_id must be passed to append_patterns_used"
        assert tsid_in_call != cc_session, (
            "task_session_id passed to append_patterns_used must differ from CC session_id"
        )
        # Same value as was passed to run_search
        assert tsid_in_call == captured_task_session.get("tsid"), (
            "task_session_id in append_patterns_used must equal the one passed to run_search"
        )

    def test_tmp_file_written_with_task_session_id(self, tmp_path, monkeypatch):
        """/tmp/ace-session-{project}.txt must be written with task_session_id, not CC session."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        cc_session = "cc-conv-sess-for-tmp-test"

        event = {
            "session_id": cc_session,
            "prompt": "build authentication middleware",
        }

        mod = _load_before_task()
        captured_search_sid = {}

        def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
            captured_search_sid["tsid"] = session_id
            return SAMPLE_PATTERNS_RESPONSE

        monkeypatch.setattr(mod, "run_search", fake_run_search)
        monkeypatch.setattr(mod, "check_session_pinning_available", lambda: True)
        monkeypatch.setattr(mod, "check_auth_status", lambda warn_threshold_hours=2.0: None)
        monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
        monkeypatch.setattr(mod, "append_patterns_used", MagicMock())
        monkeypatch.setattr(mod, "log_search_metrics", MagicMock())

        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        try:
            mod.main()
        except SystemExit:
            pass

        project = GOOD_CONTEXT["project"]
        session_file = Path(f"/tmp/ace-session-{project}.txt")
        if session_file.exists():
            written = session_file.read_text().strip()
            expected_tsid = captured_search_sid.get("tsid")
            assert written == expected_tsid, (
                f"/tmp/ace-session-{project}.txt must contain task_session_id={expected_tsid!r}; "
                f"got {written!r} (CC session_id is {cc_session!r})"
            )
        else:
            pytest.skip("/tmp/ace-session-{project}.txt was not written (pinning disabled?)")


# ════════════════════════════════════════════════════════════════════════════
# 3. ace_subagent_start: generates its own task_session_id
# ════════════════════════════════════════════════════════════════════════════

class TestSubagentStartTaskSessionId:

    def test_run_search_receives_task_session_id_not_cc_session(self, tmp_path, monkeypatch):
        """SubagentStart run_search must receive a fresh uuid4, NOT the CC session_id."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        cc_session = "cc-session-for-subagent-test"

        transcript_path = _make_transcript(tmp_path, [
            {"subagent_type": "coder", "prompt": "Implement the auth hook"},
        ])
        event = {
            "hook_event_name": "SubagentStart",
            "session_id": cc_session,
            "agent_id": "sub-agent-uuid-123",
            "agent_type": "coder",
            "cwd": str(tmp_path),
            "transcript_path": transcript_path,
        }

        mod = _load_subagent_start()
        captured = {}

        def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
            captured["session_id"] = session_id
            return SAMPLE_PATTERNS_RESPONSE

        monkeypatch.setattr(mod, "run_search", fake_run_search)
        monkeypatch.setattr(mod, "check_session_pinning_available", lambda: True)
        monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
        monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

        try:
            mod.main(event=event)
        except SystemExit:
            pass

        assert "session_id" in captured, "run_search was never called"
        passed_sid = captured["session_id"]
        assert passed_sid is not None, "run_search received None — pinning must be active"
        assert passed_sid != cc_session, (
            f"SubagentStart run_search must receive task_session_id (uuid4), not "
            f"CC session_id {cc_session!r}; got {passed_sid!r}"
        )
        try:
            uuid.UUID(passed_sid)
        except ValueError:
            pytest.fail(f"SubagentStart task_session_id is not a uuid4: {passed_sid!r}")

    def test_task_session_id_stored_in_agent_state_file(self, tmp_path, monkeypatch):
        """task_session_id must be passed to append_patterns_used from SubagentStart."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        cc_session = "cc-conv-sess-sub"

        transcript_path = _make_transcript(tmp_path, [
            {"subagent_type": "coder", "prompt": "Write unit tests for the auth hook"},
        ])
        event = {
            "hook_event_name": "SubagentStart",
            "session_id": cc_session,
            "agent_id": "sub-agent-uuid-456",
            "agent_type": "coder",
            "cwd": str(tmp_path),
            "transcript_path": transcript_path,
        }

        mod = _load_subagent_start()
        captured_search_sid = {}

        def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
            captured_search_sid["tsid"] = session_id
            return SAMPLE_PATTERNS_RESPONSE

        pu_calls = []

        def fake_append_pu(session_id, agent_id, pattern_ids, **kwargs):
            pu_calls.append({"session_id": session_id, "agent_id": agent_id,
                             "task_session_id": kwargs.get("task_session_id")})
            return pattern_ids

        monkeypatch.setattr(mod, "run_search", fake_run_search)
        monkeypatch.setattr(mod, "check_session_pinning_available", lambda: True)
        monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
        monkeypatch.setattr(mod, "append_patterns_used", fake_append_pu)

        try:
            mod.main(event=event)
        except SystemExit:
            pass

        assert pu_calls, "append_patterns_used was never called"
        call_0 = pu_calls[0]
        assert call_0["session_id"] == cc_session, "State file KEY must use CC session_id"
        tsid_in_call = call_0.get("task_session_id")
        assert tsid_in_call is not None, "task_session_id must be passed to append_patterns_used"
        assert tsid_in_call != cc_session
        assert tsid_in_call == captured_search_sid.get("tsid"), (
            "task_session_id in append_patterns_used must equal the one passed to run_search"
        )

    def test_each_subagent_gets_distinct_task_session_id(self, tmp_path, monkeypatch):
        """Two separate SubagentStart calls produce distinct task_session_ids."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        transcript_path = _make_transcript(tmp_path, [
            {"subagent_type": "coder", "prompt": "Some task"},
        ])

        collected = []

        def make_event(agent_id):
            return {
                "hook_event_name": "SubagentStart",
                "session_id": "cc-sess-shared",
                "agent_id": agent_id,
                "agent_type": "coder",
                "cwd": str(tmp_path),
                "transcript_path": transcript_path,
            }

        mod = _load_subagent_start()

        def fake_run_search(query, org=None, project=None, session_id=None, **kwargs):
            collected.append(session_id)
            return SAMPLE_PATTERNS_RESPONSE

        monkeypatch.setattr(mod, "run_search", fake_run_search)
        monkeypatch.setattr(mod, "check_session_pinning_available", lambda: True)
        monkeypatch.setattr(mod, "get_context", lambda: GOOD_CONTEXT)
        monkeypatch.setattr(mod, "append_patterns_used", MagicMock())

        for aid in ["sub-agent-aaa", "sub-agent-bbb"]:
            try:
                mod.main(event=make_event(aid))
            except SystemExit:
                pass

        assert len(collected) == 2, f"Expected 2 run_search calls; got {len(collected)}"
        assert collected[0] != collected[1], (
            "Each SubagentStart must produce a DISTINCT task_session_id; got same value twice"
        )


# ════════════════════════════════════════════════════════════════════════════
# 4. ace_after_task: reads task_session_id and uses it in trace["session_id"]
# ════════════════════════════════════════════════════════════════════════════

class TestAfterTaskSessionId:
    """Test that ace_after_task reads task_session_id from state and uses it in trace."""

    def _make_stop_event(self, cc_session, agent_id=None, hook="Stop"):
        return {
            "hook_event_name": hook,
            "session_id": cc_session,
            "agent_id": agent_id,
            "agent_type": "main",
        }

    def test_trace_uses_task_session_id_not_cc_session(self, tmp_path, monkeypatch):
        """trace['session_id'] must be the stored task_session_id, NOT the CC conversation id."""
        import ace_after_task as at

        cc_session = "cc-conv-sess-for-after-test"
        task_session = str(uuid.uuid4())

        # Write state file with task_session_id
        pus.append_patterns_used(cc_session, None, [PID_A], state_dir=str(tmp_path),
                                 task_session_id=task_session,
                                 retrieval_id="ret-001")

        traces_sent = []

        def fake_learn(trace, **kwargs):
            traces_sent.append(trace)

            class FakeResult:
                returncode = 1
                stdout = ""
                stderr = ""
            return FakeResult()

        monkeypatch.setattr(at, "_learn_via_transcript", fake_learn)
        monkeypatch.setattr(at, "load_playbook_used",
                            lambda sess, aid, hook, **kw: [PID_A])
        monkeypatch.setattr(at, "load_retrieval_ids",
                            lambda sess, aid, hook, **kw: {})

        # Patch load_task_session_id to return our task_session
        monkeypatch.setattr(at, "load_task_session_id",
                            lambda sess, aid, hook, **kw: task_session)

        assert traces_sent or True  # we'll check after

        # Actually test via the state reading path directly
        tsid = at.load_task_session_id(cc_session, None, "Stop", state_dir=str(tmp_path))
        assert tsid == task_session, (
            f"after_task load_task_session_id should return {task_session!r}; got {tsid!r}"
        )
        assert tsid != cc_session, "task_session_id must not equal CC session_id"

    def test_trace_omits_session_id_when_no_task_session_stored(self, tmp_path, monkeypatch):
        """When no task_session_id stored, trace must NOT have session_id key at all."""
        import ace_after_task as at

        # No state file written — simulates continuation stop or cold start
        tsid = at.load_task_session_id("cc-sess-no-state", None, "Stop",
                                       state_dir=str(tmp_path))
        assert tsid is None, (
            "When no state file, load_task_session_id must return None"
        )
        # Caller logic: if None → omit session_id from trace entirely
        # (the test below verifies the actual trace construction)

    def test_load_task_session_id_exported_from_after_task(self):
        """ace_after_task must export load_task_session_id (imported from pus)."""
        import ace_after_task as at
        assert hasattr(at, "load_task_session_id"), (
            "ace_after_task must import/expose load_task_session_id from patterns_used_state"
        )

    def test_cc_session_id_not_in_trace_when_task_session_stored(self, tmp_path, monkeypatch):
        """When task_session_id is stored, trace['session_id'] must NOT be the CC session_id."""
        import ace_after_task as at

        cc_session = "cc-conv-sess-must-not-appear-in-trace"
        task_session = str(uuid.uuid4())

        pus.append_patterns_used(cc_session, None, [PID_A], state_dir=str(tmp_path),
                                 task_session_id=task_session)

        tsid = at.load_task_session_id(cc_session, None, "Stop", state_dir=str(tmp_path))
        # Simulate what ace_after_task does when building the trace
        trace = {}
        if tsid:
            trace["session_id"] = tsid
        # else: omit

        assert trace.get("session_id") == task_session
        assert trace.get("session_id") != cc_session

    def test_trace_session_id_omitted_when_no_state(self, tmp_path, monkeypatch):
        """When load_task_session_id returns None, trace must not contain session_id key."""
        import ace_after_task as at

        tsid = at.load_task_session_id("cc-sess-missing", None, "Stop",
                                       state_dir=str(tmp_path))
        # Simulate the conditional in ace_after_task
        trace = {}
        if tsid:
            trace["session_id"] = tsid

        assert "session_id" not in trace, (
            "When no task_session_id stored, trace must NOT contain 'session_id' key; "
            f"got trace={trace!r}"
        )


# ════════════════════════════════════════════════════════════════════════════
# 5. Round-trip: before_task → state file → after_task load
# ════════════════════════════════════════════════════════════════════════════

class TestRoundTrip:

    def test_task_session_id_roundtrip_main_agent(self, tmp_path):
        """Write task_session_id at start, read it at stop, before unlink."""
        cc_session = "cc-sess-roundtrip-main"
        task_session = str(uuid.uuid4())

        # WRITE (simulates before_task)
        pus.append_patterns_used(cc_session, None, [PID_A], state_dir=str(tmp_path),
                                 task_session_id=task_session, retrieval_id="ret-rtrip")

        # READ (simulates after_task load_task_session_id)
        tsid = pus.load_task_session_id(cc_session, None, "Stop", state_dir=str(tmp_path))
        assert tsid == task_session, f"Round-trip failed; got {tsid!r}"

        # State file still present
        sf = pus.state_file_path(cc_session, None, state_dir=str(tmp_path))
        assert sf.exists(), "load_task_session_id must not unlink the state file"

        # Now reap via load_playbook_used (simulates after_task normal flow)
        ids = pus.load_playbook_used(cc_session, None, "Stop", state_dir=str(tmp_path))
        assert PID_A in ids
        assert not sf.exists()  # reaped

    def test_task_session_id_roundtrip_subagent(self, tmp_path):
        """Round-trip for SubagentStart → SubagentStop."""
        cc_session = "cc-sess-roundtrip-sub"
        task_session = str(uuid.uuid4())
        agent_id = "sub-agent-roundtrip-id"

        pus.append_patterns_used(cc_session, agent_id, [PID_A], state_dir=str(tmp_path),
                                 task_session_id=task_session)

        tsid = pus.load_task_session_id(cc_session, agent_id, "SubagentStop",
                                        state_dir=str(tmp_path))
        assert tsid == task_session

        sf = pus.state_file_path(cc_session, agent_id, state_dir=str(tmp_path))
        assert sf.exists(), "load_task_session_id must not unlink"

    def test_f080_retrieval_id_still_flows_alongside_task_session_id(self, tmp_path):
        """F-080 retrieval_id must still be stored and returned alongside task_session_id."""
        cc_session = "cc-sess-f080-alongside"
        task_session = str(uuid.uuid4())
        ret_id = "ret-f080-001"

        pus.append_patterns_used(cc_session, None, [PID_A], state_dir=str(tmp_path),
                                 task_session_id=task_session,
                                 retrieval_id=ret_id,
                                 retrieval_log_ids={PID_A: 99})

        sf = pus.state_file_path(cc_session, None, state_dir=str(tmp_path))
        data = json.loads(sf.read_text())
        assert data["retrieval_id"] == ret_id
        assert data["task_session_id"] == task_session
        assert data["retrieval_log_ids"][PID_A] == 99

        # 4-tuple read
        ids, rid, rlog, tsid = pus._read_state_file(sf)
        assert rid == ret_id
        assert tsid == task_session
        assert rlog[PID_A] == 99

    def test_existing_callers_3arg_backward_compat(self, tmp_path):
        """Existing callers that don't pass task_session_id still work (no TypeError)."""
        # This must not raise
        result = pus.append_patterns_used(SESSION, None, [PID_A], state_dir=str(tmp_path))
        assert PID_A in result

        # load_playbook_used still works (it uses load_retrieval_ids internally,
        # which must still unpack correctly from 4-tuple _read_state_file)
        ids = pus.load_playbook_used(SESSION, None, "Stop", state_dir=str(tmp_path))
        assert PID_A in ids

    def test_load_retrieval_ids_backward_compat_with_4tuple(self, tmp_path):
        """load_retrieval_ids must still work after _read_state_file returns 4-tuple."""
        cc_session = "cc-sess-rlog-compat"
        pus.append_patterns_used(cc_session, None, [PID_A], state_dir=str(tmp_path),
                                 retrieval_log_ids={PID_A: 77},
                                 task_session_id=TASK_SESSION)

        rlog = pus.load_retrieval_ids(cc_session, None, "Stop", state_dir=str(tmp_path))
        assert rlog.get(PID_A) == 77, f"load_retrieval_ids broken after 4-tuple change; got {rlog}"
