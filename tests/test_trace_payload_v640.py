#!/usr/bin/env python3
"""
v6.4.0 trace payload: agent_id, parent_agent_id, session_id fields.
Main agent trace must have session_id + agent_type.
Subagent trace must have session_id + agent_type + agent_id + parent_agent_id.
"""
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AFTER_TASK = REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "ace_after_task.py"


def _read():
    return AFTER_TASK.read_text()


def test_session_id_uses_task_session_id_conditionally():
    src = _read()
    # per-task session_id: trace["session_id"] must use task_session_id (conditional),
    # NOT the CC conversation session_id (which was the old unconditional behavior).
    # Asserts the new design: only set when task_session_id is present, else omit.
    assert 'task_session_id' in src, \
        "ace_after_task must reference task_session_id"
    assert ('trace["session_id"] = task_session_id' in src or
            "trace['session_id'] = task_session_id" in src), \
        "trace['session_id'] must be assigned from task_session_id (per-task), not session_id (CC)"
    # Must NOT unconditionally assign trace["session_id"] = session_id (CC conversation id)
    assert 'trace["session_id"] = session_id' not in src and \
           "trace['session_id'] = session_id" not in src, \
        ("trace['session_id'] = session_id (CC conversation id) must be removed; "
         "only task_session_id may be placed in trace['session_id']")


def test_agent_id_conditionally_on_trace():
    src = _read()
    # Conditional assignment for agent_id when present
    assert ('if agent_id:' in src and ('trace["agent_id"]' in src or "trace['agent_id']" in src)), \
        "Trace must conditionally include agent_id when present"


def test_parent_agent_id_conditionally_on_trace():
    src = _read()
    assert 'parent_agent_id' in src, "parent_agent_id must be referenced"
    assert ('if parent_agent_id:' in src and
            ('trace["parent_agent_id"]' in src or "trace['parent_agent_id']" in src)), \
        "Trace must conditionally include parent_agent_id when present"


def test_agent_id_extracted_from_event():
    src = _read()
    assert "event.get('agent_id')" in src or 'event.get("agent_id")' in src, \
        "agent_id must be extracted from hook event"
