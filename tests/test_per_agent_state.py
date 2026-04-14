#!/usr/bin/env python3
"""
Per-agent state file naming: ace-patterns-used-{session_id}-{agent_suffix}.json
where agent_suffix = agent_id (for subagents) or 'main' (for main agent).
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BEFORE = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "ace_before_task.py"
AFTER = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "ace_after_task.py"


def test_before_task_uses_agent_suffix():
    src = BEFORE.read_text()
    assert 'ace-patterns-used-{session_id}-{agent_suffix}' in src, \
        "before_task must write to per-agent state file"
    assert "agent_suffix = agent_id if agent_id else 'main'" in src or \
           'agent_suffix = agent_id if agent_id else "main"' in src, \
        "agent_suffix must default to 'main' when no agent_id"


def test_after_task_reads_agent_suffix():
    src = AFTER.read_text()
    assert 'ace-patterns-used-{session_id}-{agent_suffix}' in src, \
        "after_task must read per-agent state file"
    assert "agent_suffix = agent_id if agent_id else 'main'" in src or \
           'agent_suffix = agent_id if agent_id else "main"' in src, \
        "agent_suffix naming must match"
