#!/usr/bin/env python3
"""WP-C (v8.0.0) RED tests — PostToolUseFailure feeds failed Bash calls into
the learn trajectory.

Spec: DESIGN.md §3 (PostToolUseFailure row: matcher Bash, async, shim
`scripts/ace_posttoolusefailure_wrapper.sh` -> accumulator `--failure`),
§5 C4 (record_tool success=False, error_first_line), §5 C6.
Evidence: critic-completeness.md T18 — failed Bash calls arrive ONLY as
PostToolUseFailure (cc_hooks_reference.md:2287-2330: `error`, `is_interrupt`,
`duration_ms`), which was unregistered, so failures never entered the trajectory.
"""
import json
import os
import sqlite3

import pytest

from test_stop_v8 import Box, PROJECT_ID, ORG_ID, SCRIPTS

FAILURE_WRAPPER = SCRIPTS / "ace_posttoolusefailure_wrapper.sh"


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def _failure_event(box, sid, tool_use_id="toolu_fail_1"):
    # Shape copied from cc_hooks_reference.md "PostToolUseFailure input" example.
    return {
        "session_id": sid,
        "transcript_path": str(box.root / "t.jsonl"),
        "cwd": str(box.project),
        "permission_mode": "default",
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test", "description": "Run test suite"},
        "tool_use_id": tool_use_id,
        "error": "Exit code 1\nError: Cannot find module 'express'",
        "is_interrupt": False,
        "duration_ms": 4187,
    }


def test_failure_wrapper_is_thin_shim():
    """DESIGN §3.1 + C6: WP-C creates the shim; it execs the accumulator with
    `--failure` and contains no jq / argv payload passing."""
    assert FAILURE_WRAPPER.exists(), "scripts/ace_posttoolusefailure_wrapper.sh missing"
    assert os.access(str(FAILURE_WRAPPER), os.X_OK), "shim must be executable"
    code = "\n".join(l for l in FAILURE_WRAPPER.read_text().splitlines()
                     if not l.lstrip().startswith("#"))
    assert "exec " in code and "ace_tool_accumulator.py" in code and "--failure" in code
    assert "jq" not in code and "--tool-input" not in code


def test_failure_event_recorded_as_failed_row(box):
    """C4: PostToolUseFailure writes success=False and the `Exit code N` first
    line of `error` (doc: key on the first line, rest is display text).
    Silent: no stdout, no ace-cli call."""
    sid = "sess-fail-row"
    proc = box.run_shim("ace_posttoolusefailure_wrapper.sh", _failure_event(box, sid))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""
    assert box.cli_calls() == []
    db = box.session_dir(sid) / "tools.db"
    assert db.exists()
    con = sqlite3.connect(str(db))
    rows = con.execute("SELECT tool_name, success, error_first_line FROM tool_uses"
                       " WHERE session_id=?", (sid,)).fetchall()
    con.close()
    assert rows == [("Bash", 0, "Exit code 1")]


def test_failed_bash_reaches_learn_trajectory(box):
    """critic T18: a failed Bash call recorded by PostToolUseFailure appears in
    the Stop learn trace as a failed step and flips result.success to False."""
    sid = "sess-fail-learn"
    proc = box.run_shim("ace_posttoolusefailure_wrapper.sh", _failure_event(box, sid))
    assert proc.returncode == 0, proc.stderr
    box.write_state(sid, user_prompt="make the test suite pass again")
    ev = {
        "session_id": sid, "transcript_path": str(box.root / "none.jsonl"),
        "cwd": str(box.project), "permission_mode": "default",
        "hook_event_name": "Stop", "stop_hook_active": False,
        "last_assistant_message": "Tests still fail.", "background_tasks": [],
    }
    proc = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1, proc.stdout
    trace = learns[0]["trace"]
    bash_steps = [s for s in trace["trajectory"] if s["tool"] == "Bash"]
    assert bash_steps and "Exit code 1" in bash_steps[0]["result"]
    assert trace["result"]["success"] is False
    assert trace["result"]["failed_steps"] == 1
    assert "aborted" not in trace["result"]


def test_interrupt_as_last_step_sends_aborted(box):
    """8.1.3: a run whose last recorded step was an abort (PostToolUseFailure is_interrupt) is success=false,
    aborted=true; a run without one carries no `aborted` key (contract: only when true)."""
    sid = "sess-abort"
    ev = _failure_event(box, sid)
    ev.update(is_interrupt=True, error="Interrupted")
    assert box.run_shim("ace_posttoolusefailure_wrapper.sh", ev).returncode == 0
    box.write_state(sid, user_prompt="make the test suite pass again")
    stop = {"session_id": sid, "transcript_path": str(box.root / "none.jsonl"), "cwd": str(box.project),
            "permission_mode": "default", "hook_event_name": "Stop", "stop_hook_active": False,
            "last_assistant_message": "stopped", "background_tasks": []}
    assert box.run_after_task(stop, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID).returncode == 0
    result = box.cli_calls("learn")[0]["trace"]["result"]
    assert (result["success"], result["failed_steps"], result.get("aborted")) == (False, 1, True)
