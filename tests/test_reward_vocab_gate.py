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
    """Legacy pattern (no cumulative_v15_reward) with confidence shows confidence %.

    Fix 2: confidence (priority 3) now wins over helpful (priority 4) when present.
    For a pure helpful-only fallback, confidence must be absent or 0.
    """
    # Pattern with confidence=0.8 → shows "80%" (confidence priority over helpful)
    p = _pat_legacy(helpful=7)
    fmt_fn = ace_before_task._format_bullet_token
    token = fmt_fn(p)
    assert token == "80%", (
        f"Expected '80%' for legacy pattern with confidence=0.8, got: {token!r}"
    )


def test_top3_display_legacy_helpful_only_token():
    """Legacy pattern (no cumulative_v15_reward, no confidence) shows +{helpful}."""
    p = _pat_legacy(helpful=7, confidence=0)
    fmt_fn = ace_before_task._format_bullet_token
    token = fmt_fn(p)
    assert token.startswith("+"), (
        f"Expected token starting with '+' for legacy pattern with no confidence, got: {token!r}"
    )
    assert "7" in token, (
        f"Expected helpful value '7' in token, got: {token!r}"
    )


def test_top3_display_v15_zero_reward_shows_confidence():
    """cumulative_v15_reward=0.0 → NOT ⚡0.0; falls through to confidence (Fix 2).

    reward==0 is neutral/uncredited, so ⚡0.0 must never be emitted.
    The pattern has confidence=0.8, so the token should be '80%'.
    """
    p = _pat_v15(reward=0.0)
    fmt_fn = ace_before_task._format_bullet_token
    token = fmt_fn(p)
    assert token != "⚡0.0", (
        f"⚡0.0 must never be emitted for reward==0; got: {token!r}"
    )
    assert token == "80%", (
        f"Expected '80%' (confidence fallback) for v15 zero-reward pattern, got: {token!r}"
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


# ---------------------------------------------------------------------------
# FIX 3 — New gate semantics: v15 path trusts isAtRisk, drops reward>0 check
# (RED until _apply_quality_gate is updated)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FIX 3c — has_reliable: neutral v15 patterns → has_reliable=True
# (RED under old reward>0 check, GREEN after Fix 3c)
# ---------------------------------------------------------------------------

def test_has_reliable_fix3c_neutral_v15_patterns(tmp_path):
    """FIX 3c: neutral v15 patterns (reward=0, isAtRisk=False) → has_reliable=True.

    build_session_title must return 'ACE ready' for a list of 5 neutral-but-not-
    at-risk patterns with avg_conf>=0.70.
    RED under old `reward > 0` check; GREEN after Fix 3c.
    """
    patterns = [
        _pat_v15(reward=0, is_at_risk=False, confidence=0.8)
        for _ in range(5)
    ]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type="main",
        review_file=tmp_path / "no-such.json",
    )
    assert title is not None and "ready" in title, (
        "FIX 3c: neutral v15 patterns (reward=0, isAtRisk=False) must yield "
        f"'ACE ready' via has_reliable, got: {title!r}"
    )


# ---------------------------------------------------------------------------
# FIX A — gate robustness: negative reward + isAtRisk=False (stale/mixed data)
# The old gate `not isAtRisk` lets reward=-1.5, isAtRisk=False PASS — that is
# the hole. The new gate requires: NOT isAtRisk AND reward >= 0.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FIX A — has_reliable regression: only negative-reward patterns → False
# ---------------------------------------------------------------------------

def test_has_reliable_fixA_only_negative_reward_not_atrisk(tmp_path):
    """FIX A: a list of patterns with only reward=-1, isAtRisk=False
    → has_reliable must be False (not reliable).

    Under the old gate, reward=-1+isAtRisk=False passed → has_reliable=True.
    After FIX A these are dropped → has_reliable=False (no reliable pattern).
    RED against current code, GREEN after FIX A.
    """
    patterns = [
        _pat_v15(reward=-1, is_at_risk=False, confidence=0.8)
        for _ in range(5)
    ]
    title = ace_before_task.build_session_title(
        pattern_list=patterns,
        pattern_count=5,
        agent_type="main",
        review_file=tmp_path / "no-such.json",
    )
    # has_reliable=False → title must NOT contain "ready"
    assert title is None or "ready" not in title, (
        "FIX A: patterns with reward=-1, isAtRisk=False must yield has_reliable=False "
        f"(not 'ACE ready'). Got: {title!r}"
    )
