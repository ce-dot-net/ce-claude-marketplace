#!/usr/bin/env python3
"""User rejection as a downvote on the NEXT task's trace (server-team spec, Python chain + phrase parity with the mod).

- A human main prompt (no machine prompt, no slash command) <= 300 chars holding a REJECTION_PHRASES phrase as a whole
  word, not negated ("nicht falsch" / "not wrong"), is a rejection of the previous main task.
- Each main learn stores <session dir>/last-main-applied.json {task_session_id, applied_log_ids, at}. A rejection with
  evidenced previous ids (< 6 h) and the server gate on (search response feedback_downvote, < 7 days; env
  ACE_FEEDBACK_DOWNVOTE=1/0 overrides; default off) adds feedback {kind: downvote, applied_log_ids} to the next main trace.
- Relevance row rejection_detected {matched, downvote_sent, prev_task (8 chars)}, never the prompt text.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_stop_v8 import Box, ORG_ID, PROJECT_ID, WORK, box  # noqa: F401  (puts shared-hooks on sys.path)
from ace_feedback import REJECTION_PHRASES, rejection_match  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MOD = REPO / "plugins" / "ace" / "mod"
BEFORE = REPO / "plugins" / "ace" / "shared-hooks" / "ace_before_task.py"
CASES = json.loads((MOD / "tests" / "fixtures" / "rejection_cases.ts").read_text()[len("export default "):])
A = "11c8834e-fcca-5c36-9897-000000000001"


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
def test_rejection_cases(case):
    assert rejection_match(case["text"]) == case["match"]


def test_phrase_list_parity_with_the_mod():
    src = (MOD / "lib" / "evidence.ts").read_text()
    m = re.search(r"export const REJECTION_PHRASES = (\[.*?\])", src, re.S)
    assert m and json.loads(m.group(1)) == list(REJECTION_PHRASES)


def _prompt(box, sid, text, **env):
    ev = {"session_id": sid, "prompt": text, "cwd": str(box.project), "hook_event_name": "UserPromptSubmit"}
    p = subprocess.run([sys.executable, str(BEFORE)], input=json.dumps(ev), capture_output=True, text=True,
                       timeout=60, cwd=str(box.project), env=box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, **env))
    assert p.returncode == 0, p.stderr


def _task(box, sid, tsid, answer, **env):
    box.write_state(sid, user_prompt="refactor the parser module", pattern_ids=[A], retrieval_id="ret-1",
                    retrieval_log_ids={A: 7}, task_session_id=tsid, render_variant="budget")
    box.seed_tools(sid, WORK)
    p = box.run_after_task(box.stop_event(sid, last_assistant_message=answer), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, **env)
    assert p.returncode == 0, p.stderr
    return box.cli_calls("learn")[-1]["trace"]


def _flow(box, sid, prev_answer, reply, **env):
    t1 = _task(box, sid, "tsid-aaaaaaaa-1", prev_answer, **env)
    rec = json.loads((box.session_dir(sid) / "last-main-applied.json").read_text())
    assert rec["task_session_id"] == "tsid-aaaaaaaa-1" and rec["applied_log_ids"] == t1["applied_log_ids"]
    _prompt(box, sid, reply, **env)
    return _task(box, sid, "tsid-bbbbbbbb-2", "did something else", **env)


def test_rejection_with_evidenced_ids_and_gate_on_downvotes_the_next_trace(box):
    t2 = _flow(box, "rej-1", "applied " + A, "falsch", ACE_FEEDBACK_DOWNVOTE="1")
    assert t2["feedback"] == {"kind": "downvote", "applied_log_ids": [7]}
    (row,) = box.relevance_rows("rejection_detected")
    assert row == {**row, "matched": "falsch", "downvote_sent": True, "prev_task": "tsid-aaa"}
    assert "falsch" not in json.dumps({k: v for k, v in row.items() if k != "matched"})
    t3 = _task(box, "rej-1", "tsid-cccccccc-3", "next", ACE_FEEDBACK_DOWNVOTE="1")
    assert "feedback" not in t3, "a downvote is sent once"


def test_gate_off_sends_nothing(box):
    t2 = _flow(box, "rej-2", "applied " + A, "das ist falsch")
    assert "feedback" not in t2
    assert box.relevance_rows("rejection_detected")[0]["downvote_sent"] is False


def test_server_gate_from_the_search_response(box):
    import plugin_data_dir
    sid = "rej-3"
    plugin_data_dir.private_write(box.pd / "feedback-downvote.json", json.dumps({"on": True, "at": int(time.time())}))
    assert "feedback" in _flow(box, sid, "applied " + A, "that's wrong")


def test_stale_server_gate_is_off(box):
    import plugin_data_dir
    plugin_data_dir.private_write(box.pd / "feedback-downvote.json", json.dumps({"on": True, "at": int(time.time()) - 8 * 86400}))
    assert "feedback" not in _flow(box, "rej-3b", "applied " + A, "that's wrong")


def test_no_previous_evidenced_ids_sends_nothing(box):
    t2 = _flow(box, "rej-4", "done", "falsch", ACE_FEEDBACK_DOWNVOTE="1")
    assert "feedback" not in t2
    assert box.relevance_rows("rejection_detected")[0]["downvote_sent"] is False


def test_negated_phrase_is_no_rejection(box):
    assert "feedback" not in _flow(box, "rej-5", "applied " + A, "das ist nicht falsch", ACE_FEEDBACK_DOWNVOTE="1")
    assert box.relevance_rows("rejection_detected") == []


@pytest.mark.parametrize("text", ["<task-notification>falsch</task-notification>", "/ace:ace-status falsch"])
def test_machine_prompt_and_slash_command_are_no_rejection(box, text):
    assert "feedback" not in _flow(box, "rej-6", "applied " + A, text, ACE_FEEDBACK_DOWNVOTE="1")
    assert box.relevance_rows("rejection_detected") == []


def test_previous_record_older_than_6h_is_ignored(box):
    sid = "rej-7"
    _task(box, sid, "tsid-aaaaaaaa-1", "applied " + A, ACE_FEEDBACK_DOWNVOTE="1")
    f = box.session_dir(sid) / "last-main-applied.json"
    f.write_text(json.dumps(dict(json.loads(f.read_text()), at=time.time() - 7 * 3600)))
    _prompt(box, sid, "falsch", ACE_FEEDBACK_DOWNVOTE="1")
    assert "feedback" not in _task(box, sid, "tsid-bbbbbbbb-2", "x", ACE_FEEDBACK_DOWNVOTE="1")


def test_search_response_gate_is_persisted():
    import plugin_data_dir
    plugin_data_dir.store_server_switches({"similar_patterns": [], "feedback_downvote": True})
    assert plugin_data_dir.stored_feedback_downvote() is True
    plugin_data_dir.store_server_switches({"similar_patterns": []})  # missing field keeps the stored value
    assert plugin_data_dir.stored_feedback_downvote() is True
    plugin_data_dir.store_server_switches({"feedback_downvote": "yes"})  # invalid ignored
    assert plugin_data_dir.stored_feedback_downvote() is True
    plugin_data_dir.store_server_switches({"feedback_downvote": False})
    assert plugin_data_dir.stored_feedback_downvote() is False


# ---- 8.2.9: the per-prompt check row, the skipped-task record, the wider guards ----

def _skipped_stop(box, sid, tsid):
    """A main Stop with a state but no substantial work (no tool rows): learn_skipped no_substantial_work."""
    box.write_state(sid, user_prompt="refactor the parser module", pattern_ids=[A], retrieval_id="ret-1",
                    retrieval_log_ids={A: 7}, task_session_id=tsid, render_variant="budget")
    p = box.run_after_task(box.stop_event(sid, last_assistant_message="just talking"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr


def test_skipped_main_task_replaces_the_record_with_empty_ids(box):
    sid = "rej-8"
    _task(box, sid, "tsid-aaaaaaaa-1", "applied " + A, ACE_FEEDBACK_DOWNVOTE="1")
    _skipped_stop(box, sid, "tsid-bbbbbbbb-2")
    rec = json.loads((box.session_dir(sid) / "last-main-applied.json").read_text())
    assert rec["task_session_id"] == "tsid-bbbbbbbb-2" and rec["applied_log_ids"] == []
    _prompt(box, sid, "falsch", ACE_FEEDBACK_DOWNVOTE="1")
    assert "feedback" not in _task(box, sid, "tsid-cccccccc-3", "x", ACE_FEEDBACK_DOWNVOTE="1")  # nothing hits the old task
    assert [r["failed"] for r in box.relevance_rows("rejection_check")] == ["empty_ids"]


def test_check_row_for_every_prompt_without_text(box):
    sid = "rej-9"
    _task(box, sid, "tsid-aaaaaaaa-1", "applied " + A, ACE_FEEDBACK_DOWNVOTE="1")
    for text in ("mach weiter damit", "oder sehe ich das falsch ?", "das ist falsch"):
        _prompt(box, sid, text, ACE_FEEDBACK_DOWNVOTE="1")
    rows = box.relevance_rows("rejection_check")
    assert [(r["matched"], r["blocked"], r["failed"]) for r in rows] == [
        (None, None, "no_phrase"), (None, "falsch", "no_phrase"), ("das ist falsch", None, None)]
    assert all(r["prev_ids"] == 1 and isinstance(r["chars"], int) for r in rows)
    assert not any(t in json.dumps(rows) for t in ("mach weiter", "sehe ich"))


def test_check_row_failed_conditions(box):
    sid = "rej-10"
    _prompt(box, sid, "falsch", ACE_FEEDBACK_DOWNVOTE="1")                       # no previous record
    _prompt(box, sid, "x " * 200 + "falsch", ACE_FEEDBACK_DOWNVOTE="1")           # > 300 chars
    _task(box, sid, "tsid-aaaaaaaa-1", "applied " + A, ACE_FEEDBACK_DOWNVOTE="0")
    _prompt(box, sid, "falsch", ACE_FEEDBACK_DOWNVOTE="0")                        # switch off
    assert [r["failed"] for r in box.relevance_rows("rejection_check")] == ["prev_stale", "too_long", "switch_off"]


def test_main_stop_without_state_keeps_the_previous_record(box):
    sid = "rej-11"
    _task(box, sid, "tsid-aaaaaaaa-1", "applied " + A, ACE_FEEDBACK_DOWNVOTE="1")
    p = box.run_after_task(box.stop_event(sid, last_assistant_message="notified"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)  # no state
    assert p.returncode == 0, p.stderr
    rec = json.loads((box.session_dir(sid) / "last-main-applied.json").read_text())
    assert rec["task_session_id"] == "tsid-aaaaaaaa-1" and rec["applied_log_ids"] == [7]
    _prompt(box, sid, "falsch", ACE_FEEDBACK_DOWNVOTE="1")
    assert _task(box, sid, "tsid-bbbbbbbb-2", "x", ACE_FEEDBACK_DOWNVOTE="1")["feedback"]["applied_log_ids"] == [7]
