#!/usr/bin/env python3
"""
parse_agent_transcript: parses CC per-agent JSONL transcript into the
(tool_name, tool_input_json, tool_response_json, tool_use_id, agent_id)
tuple shape expected by get_session_tools.
"""
import json
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED = REPO_ROOT / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / "utils"))


def test_parse_agent_transcript_happy_path(tmp_path):
    from ace_after_task import parse_agent_transcript

    agent_id = str(uuid.uuid4())
    path = tmp_path / f"agent-{agent_id}.jsonl"
    lines = [
        {
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu-1", "name": "Read",
                     "input": {"file_path": "/tmp/a"}},
                ],
            }
        },
        {
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu-1",
                     "content": "hello world"},
                ],
            }
        },
        {
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu-2", "name": "Bash",
                     "input": {"command": "echo hi"}},
                ],
            }
        },
        {
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu-2",
                     "content": [{"type": "text", "text": "hi"}]},
                ],
            }
        },
    ]
    path.write_text("\n".join(json.dumps(l) for l in lines))

    results = parse_agent_transcript(str(path))
    assert len(results) == 2
    names = [r[0] for r in results]
    assert names == ["Read", "Bash"]
    # tuple shape: (name, input_json, response_json, tool_use_id, agent_id)
    for r in results:
        assert len(r) == 5
        assert r[4] == agent_id
    # input JSON round-trip
    assert json.loads(results[0][1]) == {"file_path": "/tmp/a"}
    # response JSON round-trip (string content)
    r0 = json.loads(results[0][2])
    assert r0.get("content") == "hello world"
    # response JSON round-trip (list content)
    r1 = json.loads(results[1][2])
    assert r1.get("content") == "hi"


def test_parse_agent_transcript_unreadable_raises(tmp_path):
    from ace_after_task import parse_agent_transcript
    with pytest.raises(Exception):
        parse_agent_transcript(str(tmp_path / "does-not-exist.jsonl"))


def test_parse_agent_transcript_ignores_blank_and_bad_lines(tmp_path):
    from ace_after_task import parse_agent_transcript
    path = tmp_path / "agent-xyz.jsonl"
    path.write_text(
        "\n"
        "not-json\n"
        + json.dumps({
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu-1", "name": "Read",
                     "input": {"p": 1}}
                ],
            }
        }) + "\n"
        + json.dumps({
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu-1",
                     "content": "ok"}
                ],
            }
        }) + "\n"
    )
    results = parse_agent_transcript(str(path))
    assert len(results) == 1
    assert results[0][0] == "Read"
    assert results[0][4] == "xyz"
