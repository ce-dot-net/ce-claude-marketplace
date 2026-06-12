#!/usr/bin/env python3
"""
RED → GREEN tests for _format_bullet_token display logic (Fix 2).

Rules:
  1. reward != 0 and present  → "⚡{reward:.1f}"
  2. reward == 0, ucb_score present → "↑{ucb:.2f}" (NOT "⚡0.0")
  3. reward == 0 (or absent), no ucb, confidence present → "{conf:.0%}"
  4. fallback → "+{helpful}"
  5. "⚡0.0" must NEVER be emitted for reward == 0.

Run with: python3 -m pytest tests/test_bullet_token_display.py -v
"""

import io
import json
import sys
import importlib
import importlib.util
import unittest.mock as mock
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import target
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
SHARED_HOOKS = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED_HOOKS))

from ace_before_task import _format_bullet_token  # noqa: E402


# ---------------------------------------------------------------------------
# Priority 1: credited reward (non-zero)
# ---------------------------------------------------------------------------

class TestCreditedReward:
    """When cumulative_v15_reward is non-zero, show ⚡ reward."""

    def test_positive_reward_shows_spark(self):
        assert _format_bullet_token({'cumulative_v15_reward': 2.3}) == "⚡2.3"

    def test_positive_reward_1_0(self):
        assert _format_bullet_token({'cumulative_v15_reward': 1.0}) == "⚡1.0"

    def test_negative_reward_shows_spark(self):
        """Negative reward (at-risk) still shows the real value."""
        result = _format_bullet_token({'cumulative_v15_reward': -1.5})
        assert result == "⚡-1.5"

    def test_positive_reward_ignores_ucb(self):
        """When reward != 0, ucb_score is irrelevant — show ⚡ reward."""
        result = _format_bullet_token({
            'cumulative_v15_reward': 3.1,
            'match_factors': {'ucb_score': 0.99},
        })
        assert result == "⚡3.1"


# ---------------------------------------------------------------------------
# Priority 2: reward == 0 + ucb_score present → bandit fallback
# ---------------------------------------------------------------------------

class TestUCBFallback:
    """When reward == 0 and ucb_score is available, show ↑ ucb."""

    def test_reward_zero_with_ucb(self):
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'match_factors': {'ucb_score': 0.94},
        })
        assert result == "↑0.94"

    def test_reward_zero_ucb_two_decimals(self):
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'match_factors': {'ucb_score': 0.1},
        })
        assert result == "↑0.10"

    def test_reward_zero_ucb_high_value(self):
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'match_factors': {'ucb_score': 1.5},
        })
        assert result == "↑1.50"

    def test_reward_zero_ucb_preferred_over_confidence(self):
        """ucb_score has priority over confidence when reward == 0."""
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'match_factors': {'ucb_score': 0.94},
            'confidence': 0.9,
        })
        assert result == "↑0.94"

    def test_reward_zero_empty_match_factors_falls_through(self):
        """Empty match_factors dict → no ucb → fall through to confidence."""
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'match_factors': {},
            'confidence': 0.8,
        })
        assert result == "80%"

    def test_reward_zero_none_match_factors_falls_through(self):
        """None match_factors → no ucb → fall through to confidence."""
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'match_factors': None,
            'confidence': 0.8,
        })
        assert result == "80%"


# ---------------------------------------------------------------------------
# Priority 3: confidence fallback
# ---------------------------------------------------------------------------

class TestConfidenceFallback:
    """When reward absent/0 and no ucb, show confidence if > 0."""

    def test_no_reward_confidence_80pct(self):
        result = _format_bullet_token({'confidence': 0.8})
        assert result == "80%"

    def test_reward_zero_confidence_fallback(self):
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'confidence': 0.8,
        })
        assert result == "80%"

    def test_confidence_100pct(self):
        result = _format_bullet_token({'confidence': 1.0})
        assert result == "100%"

    def test_confidence_50pct(self):
        result = _format_bullet_token({'confidence': 0.5})
        assert result == "50%"

    def test_confidence_zero_falls_through_to_helpful(self):
        """confidence == 0 is falsy — fall through to helpful."""
        result = _format_bullet_token({'confidence': 0, 'helpful': 5})
        assert result == "+5"


# ---------------------------------------------------------------------------
# Priority 4: legacy helpful fallback
# ---------------------------------------------------------------------------

class TestLegacyHelpfulFallback:
    """Pure legacy path: no reward, no ucb, no confidence → +helpful."""

    def test_helpful_fallback(self):
        assert _format_bullet_token({'helpful': 3}) == "+3"

    def test_helpful_zero(self):
        assert _format_bullet_token({'helpful': 0}) == "+0"

    def test_empty_pattern(self):
        assert _format_bullet_token({}) == "+0"


# ---------------------------------------------------------------------------
# Critical invariant: ⚡0.0 must NEVER be emitted
# ---------------------------------------------------------------------------

class TestNeverEmitSpark00:
    """⚡0.0 must never be emitted for any input."""

    def test_reward_zero_no_spark_00(self):
        """Core rule: reward == 0 must NOT produce ⚡0.0."""
        result = _format_bullet_token({'cumulative_v15_reward': 0})
        assert result != "⚡0.0", f"Got forbidden '⚡0.0': {result!r}"

    def test_reward_zero_with_ucb_no_spark_00(self):
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'match_factors': {'ucb_score': 0.94},
        })
        assert result != "⚡0.0", f"Got forbidden '⚡0.0': {result!r}"

    def test_reward_zero_with_confidence_no_spark_00(self):
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'confidence': 0.8,
        })
        assert result != "⚡0.0", f"Got forbidden '⚡0.0': {result!r}"

    def test_reward_zero_with_helpful_no_spark_00(self):
        result = _format_bullet_token({
            'cumulative_v15_reward': 0,
            'helpful': 3,
        })
        assert result != "⚡0.0", f"Got forbidden '⚡0.0': {result!r}"

    def test_spark_00_never_returned_for_any_zero_reward_combo(self):
        """Parametric check across various zero-reward patterns."""
        patterns = [
            {'cumulative_v15_reward': 0},
            {'cumulative_v15_reward': 0, 'match_factors': {'ucb_score': 0.5}},
            {'cumulative_v15_reward': 0, 'confidence': 0.9},
            {'cumulative_v15_reward': 0, 'helpful': 2},
            {'cumulative_v15_reward': 0, 'confidence': 0.0, 'helpful': 1},
        ]
        for p in patterns:
            r = _format_bullet_token(p)
            assert r != "⚡0.0", f"Pattern {p!r} returned forbidden '⚡0.0'"


# ---------------------------------------------------------------------------
# Integration test: _display_top3 pre-strip capture → summary rendering
# ---------------------------------------------------------------------------

def _load_ace_before_task():
    """Load ace_before_task with heavy external deps mocked out (same pattern as test_f080_capture)."""
    with mock.patch.dict('sys.modules', {
        'ace_cli': mock.MagicMock(),
        'ace_search_cache': mock.MagicMock(),
        'ace_context': mock.MagicMock(),
        'ace_relevance_logger': mock.MagicMock(),
        'ace_event_logger': mock.MagicMock(),
    }):
        spec = importlib.util.spec_from_file_location(
            "ace_before_task_integration",
            str(SHARED_HOOKS / "ace_before_task.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def _run_main_with_response(mod, fake_response, event=None):
    """
    Drive mod.main() end-to-end with a fake run_search response.

    Mocks all I/O and external calls; returns the parsed JSON output dict
    printed to stdout.  The pattern fed via fake_response must have
    match_factors still intact (pre-strip state) — the function asserts
    the SUMMARY uses _display_top3 (pre-strip copy) not the stripped list.
    """
    if event is None:
        event = {
            "prompt": "implement the new feature",
            "session_id": "test-session-integration-001",
            "agent_type": "main",
        }

    # Mock run_search → returns our fake_response directly
    mock_run_search = mock.MagicMock(return_value=fake_response)
    mock_check_pinning = mock.MagicMock(return_value=False)
    mock_check_auth = mock.MagicMock(return_value=None)   # no warning
    mock_get_context = mock.MagicMock(return_value={"project": "test-proj", "org": "test-org"})
    mock_log_metrics = mock.MagicMock()
    mock_append = mock.MagicMock()
    mock_eval_check = mock.MagicMock(return_value=None)

    mod.run_search = mock_run_search
    mod.check_session_pinning_available = mock_check_pinning
    mod.check_auth_status = mock_check_auth
    mod.get_context = mock_get_context
    mod.log_search_metrics = mock_log_metrics
    mod.append_patterns_used = mock_append
    mod.check_eval_request_and_review = mock_eval_check

    fake_stdin = io.StringIO(json.dumps(event))
    captured_stdout = io.StringIO()

    with mock.patch('sys.stdin', fake_stdin), \
         mock.patch('sys.stdout', captured_stdout), \
         pytest.raises(SystemExit):
        mod.main()

    output_text = captured_stdout.getvalue().strip()
    return json.loads(output_text)


class TestDisplayTop3Integration:
    """
    Integration test: _display_top3 pre-strip capture feeds the summary correctly.

    The test verifies the REAL path:
      1. patterns_response is built with match_factors intact (including ucb_score)
      2. _display_top3 is captured BEFORE useful_fields strip (Fix B)
      3. The strip removes match_factors from patterns_response['similar_patterns']
      4. The summary loop iterates _display_top3 (which still has match_factors)
      5. _format_bullet_token picks up ucb_score → emits "↑{ucb:.2f}"

    The test MUST FAIL (RED) if:
      - The summary loop uses the stripped list instead of _display_top3
        (match_factors gone → confidence fallback → "80%" instead of "↑0.94")
      - The capture order is reversed (capture after strip → same failure)
      - Fix B is reverted to `list(...)` shallow reference AND strip mutates in-place
    """

    def _build_fake_response_ucb_pattern(self):
        """
        Pattern with:
          - cumulative_v15_reward: 0  → ⚡ path skipped
          - match_factors.ucb_score: 0.94  → ↑0.94 if match_factors intact
          - confidence: 0.8  → 80% if match_factors stripped (wrong fallback)
        """
        return {
            "similar_patterns": [
                {
                    "id": "ctx-9999999999-test",
                    "domain": "ace-integration-test",
                    "content": "use the pre-strip capture to retain ucb_score for display",
                    "confidence": 0.8,
                    "helpful": 3,
                    "harmful": 0,
                    "cumulative_v15_reward": 0,
                    "match_factors": {
                        "ucb_score": 0.94,
                        "semantic_score": 0.82,
                    },
                    "section": "useful_code_snippets",
                    "evidence": ["_display_top3 = [dict(p) ...]"],
                },
            ],
            "count": 1,
            "domains_summary": {"abstract": ["ace-integration-test"]},
        }

    def test_summary_uses_ucb_path_not_confidence_fallback(self):
        """
        Core contract: when match_factors has ucb_score and reward==0,
        the summary token must be '↑0.94' (ucb path), NOT '80%' (confidence
        fallback that would appear if match_factors were stripped before summary).
        """
        mod = _load_ace_before_task()
        fake_response = self._build_fake_response_ucb_pattern()
        output = _run_main_with_response(mod, fake_response)

        user_message = output.get("systemMessage") or ""
        assert "↑0.94" in user_message, (
            f"Expected '↑0.94' (ucb path) in summary but got: {user_message!r}\n"
            "This means match_factors were stripped BEFORE the summary was built — "
            "_display_top3 is not being captured pre-strip, or the summary loop "
            "is iterating the stripped list instead of _display_top3."
        )
        assert "80%" not in user_message, (
            f"Got confidence fallback '80%' instead of ucb '↑0.94': {user_message!r}\n"
            "This is the canary for match_factors being absent at summary-build time."
        )

    def test_summary_never_emits_spark_00_for_zero_reward(self):
        """
        End-to-end: reward==0 must not produce ⚡0.0 in the user-visible summary.
        """
        mod = _load_ace_before_task()
        fake_response = self._build_fake_response_ucb_pattern()
        output = _run_main_with_response(mod, fake_response)

        user_message = output.get("systemMessage") or ""
        assert "⚡0.0" not in user_message, (
            f"Forbidden '⚡0.0' appeared in summary: {user_message!r}"
        )

    def test_stripped_list_in_injected_context_has_no_match_factors(self):
        """
        The injected ace_context (hookSpecificOutput.additionalContext) must NOT
        contain match_factors — those are stripped for token economy.
        The display summary and the injected context are built from different sources.
        """
        mod = _load_ace_before_task()
        fake_response = self._build_fake_response_ucb_pattern()
        output = _run_main_with_response(mod, fake_response)

        additional_context = (
            output.get("hookSpecificOutput", {}).get("additionalContext", "") or ""
        )
        # Parse the JSON inside the XML tags
        import re as _re
        m = _re.search(r'<ace-patterns[^>]*>\s*(\{.*?\})\s*</ace-patterns>', additional_context, _re.DOTALL)
        if m:
            injected = json.loads(m.group(1))
            for p in injected.get("similar_patterns", []):
                assert "match_factors" not in p, (
                    f"match_factors must be stripped from injected context, but found in: {p}"
                )

    def test_red_guard_confidence_fallback_detected(self):
        """
        RED-proof guard: if the summary were built from the stripped list
        (no match_factors), the token would be '80%' (confidence=0.8).
        This test documents the failure mode we protect against — and confirms
        that '80%' does NOT appear in the correct output (ucb path wins).

        To see RED: revert _display_top3 to point at stripped patterns_response
        (e.g. `_display_top3 = patterns_response.get('similar_patterns', [])[:3]`
        placed AFTER the strip loop) → '↑0.94' disappears, '80%' appears.
        """
        mod = _load_ace_before_task()
        fake_response = self._build_fake_response_ucb_pattern()
        output = _run_main_with_response(mod, fake_response)

        user_message = output.get("systemMessage") or ""
        # The confidence token '80%' must be absent — ucb '↑0.94' wins
        assert "80%" not in user_message, (
            "Confidence fallback '80%' appeared — this means _display_top3 is "
            "reading from the post-strip list (match_factors absent). "
            "Fix: ensure _display_top3 is captured BEFORE the strip."
        )
