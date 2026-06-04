#!/usr/bin/env python3
"""
Regression: the effort signal must be resolved to a hashable STRING.

CC 2.1.133+ delivers effort as a dict {"level": "high"} in the hook event. The
old code used that raw value directly as a dict key
(`_EFFORT_WEIGHT.get(effort_level)`), which raised
`TypeError: unhashable type: 'dict'` and killed ace_after_task BEFORE the trace
was ever sent to the server — for main AND subagent stops, on every event that
carried an effort dict.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

import ace_after_task as at  # noqa: E402


def test_effort_dict_extracts_level_and_is_hashable():
    lvl = at._resolve_effort_level({"effort": {"level": "high"}})
    assert lvl == "high"
    # the exact operation that crashed: using it as a dict key must work
    assert {"high": 1.5}.get(lvl, 1.0) == 1.5


def test_effort_string_absent_and_garbage_fall_back_safely(monkeypatch):
    # isolate from the ambient CLAUDE_EFFORT env so "absent" deterministically -> "normal"
    monkeypatch.delenv("CLAUDE_EFFORT", raising=False)
    assert at._resolve_effort_level({"effort": "max"}) == "max"
    assert at._resolve_effort_level({}) == "normal"
    assert at._resolve_effort_level({"effort": {"foo": 1}}) == "normal"
    assert at._resolve_effort_level({"effort": 123}) == "normal"
    assert at._resolve_effort_level({"effort": {"level": ""}}) == "normal"
