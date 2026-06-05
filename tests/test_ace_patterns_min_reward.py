#!/usr/bin/env python3
"""
TDD RED tests for issue #22: ace-patterns --min-reward flag.

These tests verify that ace-patterns.md uses --min-reward / MIN_REWARD
(not the old --min-helpful / MIN_HELPFUL names) and that the argument
hint line and docs are correct.

All tests should FAIL (red) until the implementation is done.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

# tests read .md files as text — no Python import needed
_CMD_FILE = REPO / "plugins" / "ace" / "commands" / "ace-patterns.md"


def _content() -> str:
    return _CMD_FILE.read_text(encoding="utf-8")


def test_no_min_helpful_anywhere():
    """The old flag name 'min-helpful' and env-var 'MIN_HELPFUL' must be gone."""
    content = _content()
    assert "min-helpful" not in content, (
        "Found 'min-helpful' in ace-patterns.md — rename to '--min-reward'"
    )
    assert "MIN_HELPFUL" not in content, (
        "Found 'MIN_HELPFUL' in ace-patterns.md — rename to 'MIN_REWARD'"
    )


def test_has_min_reward_flag():
    """The new flag '--min-reward' must be present."""
    content = _content()
    assert "--min-reward" in content, (
        "'--min-reward' not found in ace-patterns.md — add the new flag"
    )


def test_has_min_reward_var():
    """The environment/shell variable 'MIN_REWARD' must be present."""
    content = _content()
    assert "MIN_REWARD" in content, (
        "'MIN_REWARD' not found in ace-patterns.md — add the new variable name"
    )


def test_arg_hint_updated():
    """The argument hint line must show '[section] [min-reward]'."""
    content = _content()
    assert "[section] [min-reward]" in content, (
        "'[section] [min-reward]' not found in ace-patterns.md — update the argument hint"
    )


def test_doc_no_fabricated_range():
    """Docs must not contain fabricated range strings '0.0-10.0' or 'reward>=1'."""
    content = _content()
    assert "0.0-10.0" not in content, (
        "Found fabricated range '0.0-10.0' in ace-patterns.md — remove it"
    )
    assert "reward>=1" not in content, (
        "Found fabricated constraint 'reward>=1' in ace-patterns.md — remove it"
    )


def test_all_5_occurrences_replaced():
    """Case-insensitive count of 'min-helpful' must be zero (all occurrences renamed)."""
    content = _content()
    count = content.lower().count("min-helpful")
    assert count == 0, (
        f"Found {count} occurrence(s) of 'min-helpful' (case-insensitive) in ace-patterns.md — "
        "all must be replaced with 'min-reward'"
    )
