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


def test_session_id_always_on_trace():
    src = _read()
    # Source must contain an assignment like trace["session_id"] = session_id
    assert 'trace["session_id"] = session_id' in src or \
           "trace['session_id'] = session_id" in src, \
        "Trace must always include session_id"


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
