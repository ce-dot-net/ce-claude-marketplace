#!/usr/bin/env python3
"""
TDD RED tests for issue #31: ace-status.md hardening.

Changes expected:
1. helpful_total / harmful_total jq paths must still be present (not removed).
2. avg_confidence fallback: when helpful_total + harmful_total == 0, show avg_confidence %
   instead of a zero-divide or blank confidence line.
3. New lines reading at_risk_count and patterns_with_v15_reward directly from the
   ace-cli status --json output (ace-cli >= 4.0.1 exposes these top-level keys).

All tests should FAIL (red) until the implementation is done.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_CMD_FILE = REPO / "plugins" / "ace" / "commands" / "ace-status.md"


def _content() -> str:
    return _CMD_FILE.read_text(encoding="utf-8")


def _jq_block() -> str:
    """Return only the text of the Step 3 jq formatting expression.

    This is the block between the last 'jq -r' invocation and the closing
    backtick fence.  We specifically exclude the ## Example Output section
    (which contains a sample JSON blob) so that tests can distinguish between
    a live jq accessor and a prose example value.
    """
    content = _content()
    # Find the last bash fenced block that contains 'jq -r'
    # Pattern: ```bash ... jq -r ' ... ' ... ```
    fences = list(re.finditer(r"```bash(.*?)```", content, re.DOTALL))
    for fence in reversed(fences):
        block = fence.group(1)
        if "jq -r" in block:
            return block
    return ""


# ---------------------------------------------------------------------------
# 1. Regression guard — helpful_total / harmful_total must NOT be removed
# ---------------------------------------------------------------------------

def test_helpful_total_still_present():
    """helpful_total jq path must remain (was valid before, still valid in >= 4.0.1)."""
    content = _content()
    assert "helpful_total" in content, (
        "'helpful_total' not found in ace-status.md — do NOT remove the existing jq path; "
        "the key is still returned by ace-cli status --json"
    )


def test_harmful_total_still_present():
    """harmful_total jq path must remain (was valid before, still valid in >= 4.0.1)."""
    content = _content()
    assert "harmful_total" in content, (
        "'harmful_total' not found in ace-status.md — do NOT remove the existing jq path; "
        "the key is still returned by ace-cli status --json"
    )


# ---------------------------------------------------------------------------
# 2. avg_confidence fallback when helpful+harmful == 0
# ---------------------------------------------------------------------------

def test_avg_confidence_fallback_present():
    """When helpful_total + harmful_total == 0, the script must display avg_confidence %.

    The jq expression (not just the example JSON) must reference avg_confidence so
    that a fresh/empty playbook shows a meaningful confidence value instead of 0%.
    """
    jq = _jq_block()
    assert "avg_confidence" in jq, (
        "'avg_confidence' not found in the jq formatting block of ace-status.md — "
        "add a fallback branch that shows avg_confidence % when "
        "helpful_total + harmful_total == 0. "
        "(Note: it currently only appears in the ## Example Output JSON blob, not in the "
        "live jq expression.)"
    )


def test_avg_confidence_fallback_zero_branch():
    """The jq logic must have an explicit else branch for the zero-total case.

    The current expression hard-codes 0 when the total is zero:
      else 0 end
    It must instead use avg_confidence for that branch:
      else (.avg_confidence // 0) * 100 end   (or equivalent)
    """
    jq = _jq_block()
    # Must reference avg_confidence inside the jq block AND have an else branch
    has_conditional_fallback = (
        "avg_confidence" in jq
        and "else" in jq
    )
    assert has_conditional_fallback, (
        "avg_confidence fallback logic not found in the jq block of ace-status.md — "
        "the confidence expression must use avg_confidence in its else branch "
        "when helpful_total + harmful_total == 0. "
        "Currently the else branch just returns 0."
    )


def test_avg_confidence_displayed_as_percentage():
    """avg_confidence (0.0-1.0 float) must be multiplied by 100 in the jq block."""
    jq = _jq_block()
    # Look for avg_confidence used alongside * 100 inside the jq expression.
    has_pct = (
        "avg_confidence" in jq
        and (
            "avg_confidence * 100" in jq
            or "(.avg_confidence" in jq          # jq arithmetic context
            or "avg_confidence) * 100" in jq
            or "avg_confidence | . * 100" in jq
            or "avg_confidence // 0) * 100" in jq
        )
    )
    assert has_pct, (
        "avg_confidence does not appear to be multiplied by 100 in the jq block of "
        "ace-status.md — multiply by 100 so output reads e.g. '78%' not '0.78'"
    )


# ---------------------------------------------------------------------------
# 3. New fields: at_risk_count and patterns_with_v15_reward
# ---------------------------------------------------------------------------

def test_at_risk_count_present():
    """at_risk_count must be read directly from the ace-cli status --json output."""
    content = _content()
    assert "at_risk_count" in content, (
        "'at_risk_count' not found in ace-status.md — add a display line that reads "
        ".at_risk_count from the top-level JSON (available in ace-cli >= 4.0.1)"
    )


def test_patterns_with_v15_reward_present():
    """patterns_with_v15_reward must be read directly from the ace-cli status --json output."""
    content = _content()
    assert "patterns_with_v15_reward" in content, (
        "'patterns_with_v15_reward' not found in ace-status.md — add a display line that reads "
        ".patterns_with_v15_reward from the top-level JSON (available in ace-cli >= 4.0.1)"
    )


def test_at_risk_count_in_jq_block():
    """at_risk_count must appear inside a jq expression (not just in a comment or prose)."""
    content = _content()
    # The jq block starts with 'jq -r' and ends before the next ```
    # A simple heuristic: at_risk_count must follow a dot (jq field accessor)
    assert ".at_risk_count" in content, (
        "'.at_risk_count' (with leading dot) not found in ace-status.md — the field must "
        "be accessed via jq path '.at_risk_count', not just mentioned in prose"
    )


def test_patterns_with_v15_reward_in_jq_block():
    """patterns_with_v15_reward must appear inside a jq expression."""
    content = _content()
    assert ".patterns_with_v15_reward" in content, (
        "'.patterns_with_v15_reward' (with leading dot) not found in ace-status.md — "
        "the field must be accessed via jq path, not just mentioned in prose"
    )


# ---------------------------------------------------------------------------
# 4. Sanity: the command file itself must exist and be non-empty
# ---------------------------------------------------------------------------

def test_command_file_exists():
    """ace-status.md must exist at the expected path."""
    assert _CMD_FILE.exists(), f"ace-status.md not found at {_CMD_FILE}"


def test_command_file_non_empty():
    """ace-status.md must not be empty."""
    assert len(_content()) > 100, "ace-status.md appears to be empty or near-empty"
