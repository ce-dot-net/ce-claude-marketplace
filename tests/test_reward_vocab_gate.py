#!/usr/bin/env python3
"""
TDD RED tests for issue #27: reward-vocab quality gate + session title.

Covers:
1. Quality gate: cumulative_v15_reward (v15 path) vs helpful (legacy fallback)
2. session-title "ACE ready" tier: has_reliable OR-fallback
3. Top-3 display token: ⚡{reward} for v15, +{helpful} for legacy
4. useful_fields set must include cumulative_v15_reward, n_hot_pos,
   n_hot_neg, isAtRisk

All tests FAIL (red) until implementation is done.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SHARED_HOOKS = REPO / "plugins" / "ace" / "shared-hooks"

sys.path.insert(0, str(SHARED_HOOKS))
sys.path.insert(0, str(SHARED_HOOKS / "utils"))

import ace_before_task  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pat_v15(reward, is_at_risk=False, confidence=0.8, domain="git-workflow"):
    """Pattern with payload_version=15 fields."""
    return {
        "id": "ctx-test-0001",
        "domain": domain,
        "content": "some pattern content",
        "confidence": confidence,
        "helpful": 0,
        "harmful": 0,
        "cumulative_v15_reward": reward,
        "isAtRisk": is_at_risk,
        "n_hot_pos": 3,
        "n_hot_neg": 0,
        "section": "strategies",
        "evidence": [],
    }


def _pat_legacy(helpful, confidence=0.8, domain="git-workflow"):
    """Legacy pattern without cumulative_v15_reward."""
    return {
        "id": "ctx-test-0002",
        "domain": domain,
        "content": "some legacy pattern content",
        "confidence": confidence,
        "helpful": helpful,
        "harmful": 0,
        "section": "strategies",
        "evidence": [],
    }


def _apply_quality_gate(patterns):
    """
    Replicate the quality-gate logic from ace_before_task._apply_quality_gate
    (the new helper expected by these tests) or fall back to testing the
    inline filtering expression directly.

    The implementation must expose a callable `_quality_gate_passes(p)` OR
    `_apply_quality_gate(patterns)` at module level, OR change the inline
    list-comprehension so it can be extracted here.  For now we call the
    expected module-level helper.
    """
    return ace_before_task._apply_quality_gate(patterns)


# ---------------------------------------------------------------------------
# 1. Quality gate — v15 path
# ---------------------------------------------------------------------------

def test_reward_gate_v15_positive():
    """cumulative_v15_reward=1.5, isAtRisk=False → passes gate."""
    p = _pat_v15(reward=1.5, is_at_risk=False)
    result = _apply_quality_gate([p])
    assert p in result, (
        "Pattern with cumulative_v15_reward=1.5, isAtRisk=False should pass "
        "the quality gate but was filtered out."
    )


def test_reward_gate_v15_atrisk():
    """cumulative_v15_reward=0, isAtRisk=True → filtered out."""
    p = _pat_v15(reward=0, is_at_risk=True)
    result = _apply_quality_gate([p])
    assert p not in result, (
        "Pattern with cumulative_v15_reward=0, isAtRisk=True should be "
        "filtered by the quality gate but was kept."
    )


def test_reward_gate_v15_zero_reward_not_atrisk():
    """cumulative_v15_reward=0, isAtRisk=False → filtered (reward not > 0)."""
    p = _pat_v15(reward=0, is_at_risk=False)
    result = _apply_quality_gate([p])
    assert p not in result, (
        "Pattern with cumulative_v15_reward=0 (not > 0) should be filtered "
        "even if isAtRisk=False."
    )


def test_reward_gate_v15_positive_but_atrisk():
    """cumulative_v15_reward=2.0, isAtRisk=True → filtered out (isAtRisk wins)."""
    p = _pat_v15(reward=2.0, is_at_risk=True)
    result = _apply_quality_gate([p])
    assert p not in result, (
        "Pattern with cumulative_v15_reward=2.0 but isAtRisk=True should be "
        "filtered — isAtRisk flag overrides positive reward."
    )


# ---------------------------------------------------------------------------
# 2. Quality gate — legacy fallback (no cumulative_v15_reward field)
# ---------------------------------------------------------------------------

def test_legacy_fallback_no_v15():
    """No cumulative_v15_reward field, helpful=2 → passes gate (legacy path)."""
    p = _pat_legacy(helpful=2)
    result = _apply_quality_gate([p])
    assert p in result, (
        "Legacy pattern with helpful=2 (no cumulative_v15_reward) should pass "
        "the quality gate via the legacy fallback."
    )


def test_legacy_fallback_helpful_low():
    """helpful=1 AND low confidence → filtered out (neither arm passes)."""
    p = _pat_legacy(helpful=1, confidence=0.1)
    result = _apply_quality_gate([p])
    assert p not in result, (
        "Legacy pattern with helpful=1 and confidence=0.1 should be filtered — "
        "neither confidence>=0.5 nor helpful>=2."
    )


def test_legacy_fallback_helpful_zero():
    """helpful=0 AND low confidence → filtered out."""
    p = _pat_legacy(helpful=0, confidence=0.1)
    result = _apply_quality_gate([p])
    assert p not in result, (
        "Legacy pattern with helpful=0 and confidence=0.1 should be filtered out."
    )


def test_legacy_fallback_high_confidence_low_helpful():
    """confidence>=0.5 with helpful=0 → passes (newly retrieved, relevant pattern)."""
    p = _pat_legacy(helpful=0, confidence=0.8)
    result = _apply_quality_gate([p])
    assert p in result, (
        "High-confidence legacy pattern (confidence=0.8) should pass even with helpful=0 "
        "— ACE 1.5 native: confidence>=0.5 OR helpful>=2."
    )


def test_legacy_fallback_helpful_high():
    """helpful=10, no cumulative_v15_reward → passes (legacy path)."""
    p = _pat_legacy(helpful=10)
    result = _apply_quality_gate([p])
    assert p in result, (
        "Legacy pattern with helpful=10 should pass the quality gate."
    )


# ---------------------------------------------------------------------------
# 3. session-title "ACE ready" tier — has_reliable OR-fallback
# ---------------------------------------------------------------------------

def test_session_title_v15_ready(tmp_path):
    """Pattern with cumulative_v15_reward > 0 → has_reliable=True → 'ACE ready'."""
    patterns = [
        _pat_v15(reward=1.5, confidence=0.8, domain="git-workflow")
        for _ in range(5)
    ]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type="main",
        review_file=tmp_path / "no-such.json",
    )
    assert title is not None and "ready" in title, (
        f"Expected 'ACE ready ...' when patterns have cumulative_v15_reward>0, "
        f"got: {title!r}"
    )


def test_session_title_legacy_fallback(tmp_path):
    """No v15 patterns, but top_helpful >= 20 → has_reliable=True (OR-fallback)."""
    # 5 legacy patterns, each helpful=5 (same domain → top domain helpful=25)
    patterns = [
        _pat_legacy(helpful=5, confidence=0.8, domain="git-workflow")
        for _ in range(5)
    ]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type="main",
        review_file=tmp_path / "no-such.json",
    )
    assert title is not None and "ready" in title, (
        f"Expected 'ACE ready ...' when top_helpful >= 20 (OR-fallback), "
        f"got: {title!r}"
    )


def test_session_title_v15_ready_overrides_low_helpful(tmp_path):
    """v15 patterns with reward>0 qualify for 'ACE ready' even if helpful is 0."""
    # helpful=0 on all — would fail the old top_helpful>=20 check alone
    patterns = [
        _pat_v15(reward=0.5, confidence=0.8, domain="git-workflow")
        for _ in range(5)
    ]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type="main",
        review_file=tmp_path / "no-such.json",
    )
    assert title is not None and "ready" in title, (
        f"v15 patterns with reward>0 should qualify for 'ACE ready' "
        f"even with helpful=0, got: {title!r}"
    )


def test_session_title_neither_v15_nor_high_helpful(tmp_path):
    """No v15, top_helpful < 20 → should NOT produce 'ACE ready'."""
    # helpful=3 each × 5 = top domain helpful=15, below threshold
    patterns = [
        _pat_legacy(helpful=3, confidence=0.8, domain="git-workflow")
        for _ in range(5)
    ]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type="main",
        review_file=tmp_path / "no-such.json",
    )
    assert title is None or "ready" not in title, (
        f"Should not produce 'ACE ready' when neither condition is met, "
        f"got: {title!r}"
    )


# ---------------------------------------------------------------------------
# 4. Top-3 display token — ⚡{reward} for v15, +{helpful} for legacy
# ---------------------------------------------------------------------------

def _build_user_message(patterns):
    """
    Call the module-level helper that builds the user-visible bullet summary.
    The implementation must expose `_build_summary_lines(pattern_list)` OR
    `_format_bullet_token(pattern)` at module level so we can unit-test it
    without running the full main() loop.
    """
    return ace_before_task._format_bullet_token


def test_top3_display_v15_reward_token():
    """Pattern with cumulative_v15_reward shows ⚡{reward} token."""
    p = _pat_v15(reward=1.5)
    fmt_fn = ace_before_task._format_bullet_token
    token = fmt_fn(p)
    assert token.startswith("⚡"), (
        f"Expected token starting with ⚡ for v15 pattern, got: {token!r}"
    )
    assert "1.5" in token, (
        f"Expected reward value '1.5' in token, got: {token!r}"
    )


def test_top3_display_legacy_helpful_token():
    """Legacy pattern (no cumulative_v15_reward) shows +{helpful} token."""
    p = _pat_legacy(helpful=7)
    fmt_fn = ace_before_task._format_bullet_token
    token = fmt_fn(p)
    assert token.startswith("+"), (
        f"Expected token starting with '+' for legacy pattern, got: {token!r}"
    )
    assert "7" in token, (
        f"Expected helpful value '7' in token, got: {token!r}"
    )


def test_top3_display_v15_zero_reward_shows_zero():
    """cumulative_v15_reward=0.0 → ⚡0.0 (v15 path taken even at zero)."""
    p = _pat_v15(reward=0.0)
    fmt_fn = ace_before_task._format_bullet_token
    token = fmt_fn(p)
    assert token.startswith("⚡"), (
        f"Expected ⚡ token for v15 field present (even at 0), got: {token!r}"
    )


# ---------------------------------------------------------------------------
# 5. useful_fields set includes the new v15 fields
# ---------------------------------------------------------------------------

def test_useful_fields_has_v15_fields():
    """useful_fields must include cumulative_v15_reward, n_hot_pos, n_hot_neg, isAtRisk."""
    uf = ace_before_task.USEFUL_FIELDS
    for field in ("cumulative_v15_reward", "n_hot_pos", "n_hot_neg", "isAtRisk"):
        assert field in uf, (
            f"'{field}' not found in ace_before_task.USEFUL_FIELDS — "
            f"add it so v15 reward data survives the strip step."
        )


def test_useful_fields_still_has_legacy_fields():
    """Existing fields must not be removed (backward-compat guard)."""
    uf = ace_before_task.USEFUL_FIELDS
    for field in ("id", "domain", "content", "confidence", "helpful", "harmful", "section"):
        assert field in uf, (
            f"Legacy field '{field}' was removed from USEFUL_FIELDS — must be kept."
        )


def test_useful_fields_strips_match_factors():
    """match_factors must NOT be in useful_fields (server-internal, large, excluded by design)."""
    uf = ace_before_task.USEFUL_FIELDS
    assert "match_factors" not in uf, (
        "'match_factors' must not be in USEFUL_FIELDS — it is server-internal "
        "and was explicitly excluded before these changes."
    )
