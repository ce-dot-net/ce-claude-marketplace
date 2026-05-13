#!/usr/bin/env python3
"""
ARCHIVED: v5.2.0 Per-Task + Delta Learning Architecture tests.

v5.3.0 replaced transcript-parsing trajectory building with a SQLite-backed
`ace_tool_accumulator` flow. The helpers this file imported
(`get_task_messages`, `filter_garbage_trajectory`, `record_captured_position`,
`POSITION_STATE_FILE`, etc.) were removed during that refactor. Equivalent
coverage now lives in:
  - `test_hooks_json_matcher.py` — hook wiring
  - `test_precompact_handoff.py` — PreCompact → SessionStart compact handoff
  - `test_native_agent_type.py`, `test_parent_agent_resolution.py` — agent IDs
  - `tests/ace_v522_test.py` — accumulator/trajectory smoke

The original module body is preserved in git history (last seen on tag v5.2.x);
re-writing it against the accumulator architecture is deferred until/unless
any of the removed helpers come back.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Archived v5.2.0 transcript-parsing tests; v5.3.0+ uses SQLite accumulator."
)


def test_archived_marker() -> None:
    """Placeholder so pytest reports a single 'skipped' entry for this file."""
    assert True
