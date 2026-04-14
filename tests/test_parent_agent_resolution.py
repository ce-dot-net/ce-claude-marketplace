#!/usr/bin/env python3
"""
parent_agent_id resolution: ace_after_task.py reads
.claude/data/logs/ace-spawn-log.jsonl looking for an event=subagent_done
entry whose child_agent_id matches the current agent_id, then pulls
parent_agent_id from that entry.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AFTER = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "ace_after_task.py"


def test_spawn_log_lookup_logic_present():
    src = AFTER.read_text()
    assert "ace-spawn-log.jsonl" in src, "Must read from ace-spawn-log.jsonl"
    assert "subagent_done" in src, "Must look up subagent_done events"
    assert "child_agent_id" in src, "Must match on child_agent_id"
    assert "parent_agent_id" in src, "Must set parent_agent_id"


def test_parent_resolution_gated_on_agent_id():
    """parent_agent_id lookup must only happen when we have an agent_id."""
    src = AFTER.read_text()
    # Find the block: `if agent_id:` followed (within ~30 lines) by spawn_log read
    lines = src.splitlines()
    found_gated_lookup = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("if agent_id:"):
            window = "\n".join(lines[i:i + 30])
            if "ace-spawn-log.jsonl" in window and "subagent_done" in window:
                found_gated_lookup = True
                break
    assert found_gated_lookup, (
        "parent_agent_id resolution via spawn-log must be guarded by `if agent_id:`"
    )
