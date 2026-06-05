#!/usr/bin/env python3
"""
TDD RED tests for issue #21: ace-top --min-reward migration.

These tests verify that ace-top.md has been updated to use the v15 reward
API (cumulative_v15_reward, --min-reward, MIN_REWARD, isAtRisk) and no
longer references the deprecated helpful/harmful scoring system.

All tests are expected to FAIL (red) until the fix is applied.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

ACE_TOP_MD = REPO / "plugins" / "ace" / "commands" / "ace-top.md"


def _content() -> str:
    return ACE_TOP_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Old flag names must be gone
# ---------------------------------------------------------------------------

def test_no_min_helpful_flag():
    """--min-helpful and MIN_HELPFUL must be removed (replaced by --min-reward / MIN_REWARD)."""
    content = _content()
    assert "min-helpful" not in content, (
        "ace-top.md still references 'min-helpful'; should be '--min-reward'"
    )
    assert "MIN_HELPFUL" not in content, (
        "ace-top.md still references 'MIN_HELPFUL'; should be 'MIN_REWARD'"
    )


# ---------------------------------------------------------------------------
# 2. New flag names must be present
# ---------------------------------------------------------------------------

def test_has_min_reward_flag():
    """--min-reward flag must appear in the command definition."""
    content = _content()
    assert "--min-reward" in content, (
        "ace-top.md missing '--min-reward' flag"
    )


def test_min_reward_var():
    """MIN_REWARD shell variable must appear in the bash script block."""
    content = _content()
    assert "MIN_REWARD" in content, (
        "ace-top.md missing 'MIN_REWARD' variable"
    )


# ---------------------------------------------------------------------------
# 3. Output Format JSON example must use v15 reward fields
# ---------------------------------------------------------------------------

def test_output_format_no_helpful_harmful():
    """Output Format JSON example must not contain deprecated 'helpful' or 'harmful' keys."""
    content = _content()
    assert "cumulative_v15_reward" in content, (
        "ace-top.md Output Format example missing 'cumulative_v15_reward' field"
    )
    assert '"helpful":' not in content, (
        "ace-top.md Output Format example still contains deprecated '\"helpful\":' key"
    )
    assert '"harmful":' not in content, (
        "ace-top.md Output Format example still contains deprecated '\"harmful\":' key"
    )


def test_output_format_has_isAtRisk():
    """Output Format JSON example must include 'isAtRisk' field."""
    content = _content()
    assert "isAtRisk" in content, (
        "ace-top.md Output Format example missing 'isAtRisk' field"
    )


# ---------------------------------------------------------------------------
# 4. No fabricated reward-range text that would mislead users
# ---------------------------------------------------------------------------

def test_no_fabricated_range():
    """Fabricated range strings '0.0-10.0' and 'reward>=1' must not appear."""
    content = _content()
    assert "0.0-10.0" not in content, (
        "ace-top.md contains fabricated range '0.0-10.0'"
    )
    assert "reward>=1" not in content, (
        "ace-top.md contains fabricated threshold string 'reward>=1'"
    )
