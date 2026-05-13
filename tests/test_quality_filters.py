#!/usr/bin/env python3
"""ACE quality filter unit tests.

Originally written for v5.1.22 transcript-parsing era. Updated for v5.3.0+
SQLite accumulator architecture: `has_substantial_work` was renamed to
`has_substantial_work_from_accumulated` and now takes a list of tool tuples
(from `ace_tool_accumulator.get_session_tools`) instead of a trace dict.

What's covered:
  - `is_trivial_task(task_description)` — filters ACE meta-commands, greetings,
    Claude Code system prompts so they don't leak into pattern learning
  - `has_substantial_work_from_accumulated(tools)` — verifies state-changing
    tools (Edit, Write, Bash, MCP, NotebookEdit) were used, indicating
    meaningful execution feedback per the ACE research paper.
"""

import sys
from pathlib import Path

# Make plugin shared-hooks importable from the test (consistent with peers)
_PLUGIN_HOOKS = Path(__file__).parent.parent / "plugins/ace/shared-hooks"
sys.path.insert(0, str(_PLUGIN_HOOKS))
sys.path.insert(0, str(_PLUGIN_HOOKS / "utils"))

from ace_after_task import (  # noqa: E402
    is_trivial_task,
    has_substantial_work_from_accumulated,
)


# --- is_trivial_task ---------------------------------------------------------

TRIVIAL_CASES = [
    "User request: <command-message>ace:ace-status is running</command-message>",
    "/ace-status",
    "ace:ace-patterns",
    "what is this?",
    "thanks",
    "Caveat: The messages below were generated",
]

SUBSTANTIAL_CASES = [
    "User request: implement JWT authentication",
    "User request: fix the bug in login flow",
    "User request: create test file for quality filters",
]


def test_is_trivial_task_filters_meta_and_chitchat():
    for case in TRIVIAL_CASES:
        assert is_trivial_task(case), f"Expected trivial, got substantial: {case!r}"


def test_is_trivial_task_keeps_real_requests():
    for case in SUBSTANTIAL_CASES:
        assert not is_trivial_task(case), f"Expected substantial, got trivial: {case!r}"


# --- has_substantial_work_from_accumulated -----------------------------------

# Tuple shape: (tool_name, tool_input_json, tool_response_json, tool_use_id, ...)
# Only `tool_name` (index 0) matters for the state-changing check.


def _tool(name: str) -> tuple:
    return (name, "{}", "{}", f"tu_{name}", None)


def test_has_substantial_work_rejects_read_only():
    tools = [_tool("Read"), _tool("Grep"), _tool("Glob")]
    assert has_substantial_work_from_accumulated(tools) is False


def test_has_substantial_work_accepts_edit():
    tools = [_tool("Read"), _tool("Edit")]
    assert has_substantial_work_from_accumulated(tools) is True


def test_has_substantial_work_accepts_write():
    tools = [_tool("Write")]
    assert has_substantial_work_from_accumulated(tools) is True


def test_has_substantial_work_accepts_bash():
    tools = [_tool("Bash"), _tool("Read")]
    assert has_substantial_work_from_accumulated(tools) is True


def test_has_substantial_work_accepts_mcp_prefix():
    tools = [_tool("mcp__github__create_issue")]
    assert has_substantial_work_from_accumulated(tools) is True


def test_has_substantial_work_empty_list():
    assert has_substantial_work_from_accumulated([]) is False
