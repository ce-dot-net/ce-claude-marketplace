#!/usr/bin/env python3
"""
Regression: SubagentStop after_task must not crash on the per-agent transcript.

parse_agent_transcript() must return 8-tuples compatible with
get_session_tools() — build_trajectory_from_accumulated_tools() unpacks 8 values
(…, agent_id, start_ms, end_ms, duration_ms). A 5-tuple from the transcript path
raised "not enough values to unpack (expected 8, got 5)" and killed the whole
subagent learning trace before it could be sent (pre-existing since v6.4.0).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

import ace_after_task as at  # noqa: E402


def _write_transcript(tmp_path):
    tpath = tmp_path / "agent-deadbeefcafe1234.jsonl"
    tpath.write_text("\n".join(json.dumps(x) for x in [
        {"message": {"content": [
            {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {"command": "wc -l f"}}]}},
        {"message": {"content": [
            {"type": "tool_result", "tool_use_id": "tu_1", "content": "919"}]}},
    ]))
    return tpath


def test_parse_agent_transcript_returns_8tuples(tmp_path):
    tools = at.parse_agent_transcript(str(_write_transcript(tmp_path)))
    assert tools, "should parse the one tool_use"
    assert all(len(t) == 8 for t in tools), f"expected 8-tuples, got arities {[len(t) for t in tools]}"
    # agent_id derived from agent-{id}.jsonl filename, timing fields padded
    tname, tinput, tresp, tu_id, agent_id, start_ms, end_ms, duration_ms = tools[0]
    assert tname == "Bash"
    assert agent_id == "deadbeefcafe1234"
    assert (start_ms, end_ms, duration_ms) == (None, None, None)


def test_build_trajectory_from_subagent_transcript_does_not_crash(tmp_path):
    # THE regression: must NOT raise "expected 8, got 5"
    trajectory, tools = at.build_trajectory_from_accumulated_tools(
        "sess-x", agent_transcript_path=str(_write_transcript(tmp_path))
    )
    assert any(step.get("tool") == "Bash" for step in trajectory), trajectory
    assert all(len(t) == 8 for t in tools)
