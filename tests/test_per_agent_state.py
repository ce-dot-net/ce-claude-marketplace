#!/usr/bin/env python3
"""
Per-agent state file naming: ace-patterns-used-{session_id}-{agent_suffix}.json
where agent_suffix = agent_id (for subagents) or 'main' (for main agent).

v6.5.2: The naming scheme + agent_suffix logic was extracted into the single
source of truth plugins/ace/shared-hooks/utils/patterns_used_state.py. The hook
modules now DELEGATE to that util (append_patterns_used / load_playbook_used)
instead of inlining the path. These grep tests follow the contract to the util.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BEFORE = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "ace_before_task.py"
AFTER = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "ace_after_task.py"
UTIL = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "utils" / "patterns_used_state.py"


def test_util_owns_per_agent_naming():
    """The single source of truth defines the per-agent file name + suffix rule."""
    src = UTIL.read_text()
    assert 'ace-patterns-used-{session_id}-{agent_suffix}' in src, \
        "util must define the per-agent state file name"
    assert "agent_suffix = agent_id if agent_id else 'main'" in src or \
           'agent_suffix = agent_id if agent_id else "main"' in src, \
        "agent_suffix must default to 'main' when no agent_id"


def test_before_task_uses_agent_suffix():
    """before_task must write the per-agent state via the util writer."""
    src = BEFORE.read_text()
    assert 'append_patterns_used' in src, \
        "before_task must delegate writes to patterns_used_state.append_patterns_used"
    assert "event.get('agent_id')" in src, \
        "before_task must still key the state file by agent_id"


def test_after_task_reads_agent_suffix():
    """after_task must read the per-agent state via the util reader."""
    src = AFTER.read_text()
    assert 'load_playbook_used' in src, \
        "after_task must delegate reads to patterns_used_state.load_playbook_used"
