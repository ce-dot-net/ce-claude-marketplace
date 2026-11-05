#!/usr/bin/env python3
"""WP-H (v8.0.0 round 2) RED — PostToolBatch accumulator (`ace_tool_accumulator.py --batch`).

DESIGN §9 G4 / §10 S8 / §10 P-10: one async PostToolBatch event per parallel batch replaces
the per-tool PostToolUse `*` accumulator. Input shape: cc_hooks_reference.md:2348-2388
(`tool_calls[]`, each {tool_name, tool_input, tool_use_id, tool_response}; tool_response is a
serialized STRING or a content-block ARRAY, :2381). The accumulator records every call with
its tool_use_id, dedupes against PostToolUseFailure rows by tool_use_id (the failure row keeps
its error text, whichever event arrives first), keeps duration_ms (P-10), prints nothing
(§9 G3) and never spawns ace-cli. hooks.json wiring is WP-G's; here the shim is called with
`--batch` exactly as the PostToolBatch entry will call it.
"""
import json
import sqlite3

import pytest

from test_stop_v8 import Box, PROJECT_ID, ORG_ID  # noqa: F401

SHIM = "ace_posttooluse_wrapper.sh"
FAIL_SHIM = "ace_posttoolusefailure_wrapper.sh"


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def _batch(box, sid, calls, **kw):
    ev = {"session_id": sid, "transcript_path": str(box.root / "t.jsonl"),
          "cwd": str(box.project), "permission_mode": "default",
          "hook_event_name": "PostToolBatch", "tool_calls": calls}
    ev.update(kw)
    return ev


def _failure(box, sid, tuid, tool="Bash", error="Exit code 1\nError: boom", duration_ms=4187):
    return {"session_id": sid, "transcript_path": str(box.root / "t.jsonl"),
            "cwd": str(box.project), "permission_mode": "default",
            "hook_event_name": "PostToolUseFailure", "tool_name": tool,
            "tool_input": {"command": "npm test"}, "tool_use_id": tuid,
            "error": error, "is_interrupt": False, "duration_ms": duration_ms}


def _rows(box, sid):
    db = box.session_dir(sid) / "tools.db"
    if not db.exists():
        return []
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM tool_uses WHERE session_id=? ORDER BY id", (sid,))]
    con.close()
    return rows


CALLS = [
    {"tool_name": "Read", "tool_input": {"file_path": "/p/ledger/accounts.py"},
     "tool_use_id": "toolu_b1", "tool_response": "1\tfrom __future__ import annotations\n2\t..."},
    {"tool_name": "mcp__linear__get_issue", "tool_input": {"id": "ENG-1"},
     "tool_use_id": "toolu_b2", "tool_response": [{"type": "text", "text": "issue body ENG-1"}]},
    {"tool_name": "Bash", "tool_input": {"command": "pytest -q"},
     "tool_use_id": "toolu_b3", "tool_response": "12 passed in 0.31s"},
]


def test_batch_records_every_call_with_tool_use_id_silently(box):
    """G4: string AND content-block-array responses -> one row per call, success=1;
    async hook prints nothing (G3) and makes zero ace-cli calls."""
    sid = "s-batch"
    p = box.run_shim(SHIM, _batch(box, sid, CALLS), args=["--batch"])
    assert p.returncode == 0, p.stderr
    assert p.stdout == "", "async PostToolBatch hook must print nothing (G3)"
    assert box.cli_calls() == []
    rows = _rows(box, sid)
    assert [(r["tool_name"], r["tool_use_id"], r["success"]) for r in rows] == [
        ("Read", "toolu_b1", 1), ("mcp__linear__get_issue", "toolu_b2", 1), ("Bash", "toolu_b3", 1)]
    assert "issue body ENG-1" in rows[1]["tool_response"], "array response text must be kept"
    assert "12 passed" in rows[2]["tool_response"]


def test_batch_response_is_capped(box):
    """Responses can be large (doc :2381 'parse only the fields you need'): cap per field."""
    sid = "s-batch-big"
    big = [{"tool_name": "Read", "tool_input": {"file_path": "/p/big.py"},
            "tool_use_id": "toolu_big", "tool_response": "x" * 500000}]
    p = box.run_shim(SHIM, _batch(box, sid, big), args=["--batch"])
    assert p.returncode == 0, p.stderr
    rows = _rows(box, sid)
    assert len(rows) == 1 and len(rows[0]["tool_response"]) <= 8192 + 64


def test_batch_skips_malformed_entries_but_records_the_rest(box):
    sid = "s-batch-bad"
    calls = ["junk", {"tool_name": "Edit"}, {"tool_use_id": "toolu_x"}] + CALLS[:1]
    p = box.run_shim(SHIM, _batch(box, sid, calls), args=["--batch"])
    assert p.returncode == 0 and p.stdout == ""
    assert [r["tool_use_id"] for r in _rows(box, sid)] == ["toolu_b1"]


def test_batch_inside_subagent_records_agent_id(box):
    """PostToolBatch fires inside subagents too (§9 G4); common input carries agent_id."""
    sid = "s-batch-agent"
    p = box.run_shim(SHIM, _batch(box, sid, CALLS[:1], agent_id="agent-77", agent_type="Explore"),
                     args=["--batch"])
    assert p.returncode == 0
    assert [r["agent_id"] for r in _rows(box, sid)] == ["agent-77"]


def test_batch_respects_disabled_flag(box):
    """§10 P-26: every hook early-exits on <session>/disabled.flag."""
    sid = "s-batch-off"
    box.session_dir(sid).mkdir(parents=True)
    (box.session_dir(sid) / "disabled.flag").write_text("x")
    box.run_shim(SHIM, _batch(box, sid, CALLS), args=["--batch"])
    assert _rows(box, sid) == []


def test_failure_then_batch_keeps_single_failed_row_with_error(box):
    """G4 dedupe: PostToolUseFailure arrives first, the batch repeats the call -> one row,
    success=0, error text and duration_ms (P-10) kept."""
    sid = "s-dedupe-1"
    box.run_shim(FAIL_SHIM, _failure(box, sid, "toolu_b3"))
    box.run_shim(SHIM, _batch(box, sid, CALLS), args=["--batch"])
    rows = [r for r in _rows(box, sid) if r["tool_use_id"] == "toolu_b3"]
    assert len(rows) == 1
    assert rows[0]["success"] == 0
    assert rows[0]["error_first_line"] == "Exit code 1"
    assert rows[0]["duration_ms"] == 4187
    assert len(_rows(box, sid)) == 3


def test_batch_then_failure_failure_wins(box):
    """Async hooks race: the batch row may land first. The later failure must still win
    (success=0 + error text); today the UNIQUE(tool_use_id) IntegrityError silently drops it."""
    sid = "s-dedupe-2"
    box.run_shim(SHIM, _batch(box, sid, CALLS), args=["--batch"])
    assert [r["success"] for r in _rows(box, sid) if r["tool_use_id"] == "toolu_b3"] == [1], \
        "batch must have recorded the call before the failure arrives"
    box.run_shim(FAIL_SHIM, _failure(box, sid, "toolu_b3"))
    rows = [r for r in _rows(box, sid) if r["tool_use_id"] == "toolu_b3"]
    assert len(rows) == 1, rows
    assert rows[0]["success"] == 0, "failure must overwrite the batch's success row"
    assert rows[0]["error_first_line"] == "Exit code 1"
    assert rows[0]["duration_ms"] == 4187


def test_non_bash_failure_is_recorded(box):
    """§10 S8: matcher becomes `*` — Edit/MCP failures are recorded like Bash."""
    sid = "s-fail-edit"
    box.run_shim(FAIL_SHIM, _failure(box, sid, "toolu_e1", tool="Edit",
                                     error="String to replace not found in file."))
    rows = _rows(box, sid)
    assert [(r["tool_name"], r["success"], r["error_first_line"]) for r in rows] == [
        ("Edit", 0, "String to replace not found in file.")]


def test_batch_rows_reach_learn_trajectory(box):
    """End to end: batch rows (string/array responses) feed the Stop trajectory with readable
    results, and a deduped failure flips result.success."""
    sid = "s-batch-learn"
    calls = CALLS + [{"tool_name": "Edit", "tool_input": {"file_path": "/p/app.py"},
                      "tool_use_id": "toolu_b4", "tool_response": "The file /p/app.py has been updated."}]
    box.run_shim(SHIM, _batch(box, sid, calls), args=["--batch"])
    box.run_shim(FAIL_SHIM, _failure(box, sid, "toolu_b3"))
    box.write_state(sid, user_prompt="fix the ledger rounding bug and run tests")
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1
    traj = learns[0]["trace"]["trajectory"]
    assert [s["tool"] for s in traj] == ["Read", "mcp__linear__get_issue", "Bash", "Edit"]
    assert "issue body" in traj[1]["result"], traj[1]
    assert "Exit code 1" in traj[2]["result"], traj[2]
    assert learns[0]["trace"]["result"]["success"] is False  # 8.1.3: npm test left red (never rerun green)
    assert learns[0]["trace"]["result"]["failed_steps"] == 1


def test_recovered_failure_keeps_success_true(box):
    """8.1.3 end outcome: a red `npm test` rerun green and a grep without matches do not fail the task;
    failed_steps counts the red run only (grep exit 1 is benign, not a failed step)."""
    sid = "s-recovered"
    box.run_shim(FAIL_SHIM, _failure(box, sid, "toolu_r1"))
    grep = _failure(box, sid, "toolu_r2", error="Exit code 1")
    grep["tool_input"] = {"command": "grep -rn needle src"}
    box.run_shim(FAIL_SHIM, grep)
    box.run_shim(SHIM, _batch(box, sid, [
        {"tool_name": "Edit", "tool_input": {"file_path": "/p/app.py"}, "tool_use_id": "toolu_r3",
         "tool_response": "The file /p/app.py has been updated."},
        {"tool_name": "Bash", "tool_input": {"command": "npm test"}, "tool_use_id": "toolu_r4",
         "tool_response": "12 passing"}]), args=["--batch"])
    box.write_state(sid, user_prompt="fix the ledger rounding bug and run tests")
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    result = box.cli_calls("learn")[0]["trace"]["result"]
    assert (result["success"], result["failed_steps"]) == (True, 1)


def test_failure_row_keeps_duration_ms(box):
    """P-10: duration_ms (doc PostToolUseFailure input) survives into the trajectory step."""
    sid = "s-dur"
    box.run_shim(FAIL_SHIM, _failure(box, sid, "toolu_d1", duration_ms=321))
    assert _rows(box, sid)[0]["duration_ms"] == 321
