#!/usr/bin/env python3
"""
SubagentStop wrapper must write a spawn-log entry:
  {event: "subagent_done", child_agent_id, parent_agent_id: "main", session_id, timestamp}
to .claude/data/logs/ace-spawn-log.jsonl before invoking ace_after_task.py.
"""
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "plugins" / "ace" / "scripts" / "ace_subagent_stop_wrapper.sh"


def test_subagent_stop_writes_spawn_log(tmp_path):
    event = {
        "session_id": "sess-sub-1",
        "agent_id": "agent-abc-123",
        "cwd": str(tmp_path),
        "transcript_path": str(tmp_path / "transcript.jsonl"),
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(tmp_path),
    )
    # We don't require success from ace_after_task — only that the
    # spawn log is written by the wrapper before it invokes the hook.
    spawn_log = tmp_path / ".claude" / "data" / "logs" / "ace-spawn-log.jsonl"
    assert spawn_log.exists(), (
        f"Wrapper must write spawn log. stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    lines = [json.loads(l) for l in spawn_log.read_text().splitlines() if l.strip()]
    done = [e for e in lines if e.get("event") == "subagent_done"]
    assert len(done) >= 1
    entry = done[0]
    assert entry["child_agent_id"] == "agent-abc-123"
    assert entry["parent_agent_id"] == "main"
    assert entry["session_id"] == "sess-sub-1"
    assert entry.get("timestamp")


def test_subagent_stop_skips_when_no_agent_id(tmp_path):
    """Missing agent_id → no spawn-log entry written."""
    event = {
        "session_id": "sess-no-agent",
        "cwd": str(tmp_path),
        "transcript_path": str(tmp_path / "transcript.jsonl"),
    }
    subprocess.run(
        ["bash", str(WRAPPER)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(tmp_path),
    )
    spawn_log = tmp_path / ".claude" / "data" / "logs" / "ace-spawn-log.jsonl"
    if spawn_log.exists():
        lines = [json.loads(l) for l in spawn_log.read_text().splitlines() if l.strip()]
        assert not any(e.get("event") == "subagent_done" for e in lines)
