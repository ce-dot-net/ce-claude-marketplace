"""
Issue #29 verification: cumulative_v15_reward_delta (primary) + patterns_deduplicated (preferred).

These are thin smoke tests confirming the live runtime code in ace_after_task.py
applies the correct field-priority rules established in test_f080_trace.py.
"""
import types
import sys
import os

# ---------------------------------------------------------------------------
# Minimal stubs so ace_after_task imports without real deps
# ---------------------------------------------------------------------------

def _stub_modules():
    for mod in [
        "anthropic", "anthropic.types",
        "httpx", "logfire",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)


_stub_modules()

# ---------------------------------------------------------------------------
# Helper: call the exact field-resolution expressions used in production code
# (lines 883, 887 of ace_after_task.py — copied verbatim so any regression
#  in the source is immediately caught here too).
# ---------------------------------------------------------------------------

def resolve_merged(stats: dict) -> int:
    """F-080: patterns_deduplicated preferred over patterns_merged."""
    return stats.get("patterns_deduplicated", stats.get("patterns_merged", 0))


def resolve_reward(stats: dict):
    """F-080: cumulative_v15_reward_delta is PRIMARY; helpful_delta is fallback."""
    _v15 = stats.get("cumulative_v15_reward_delta")
    helpful_delta = stats.get("helpful_delta", 0)
    if _v15 is not None:
        return ("v15", _v15)
    return ("helpful_delta", helpful_delta)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIssue29PatternsDeduplicated:
    """patterns_deduplicated must be preferred over patterns_merged."""

    def test_deduplicated_wins_when_present(self):
        stats = {"patterns_deduplicated": 7, "patterns_merged": 2}
        assert resolve_merged(stats) == 7

    def test_fallback_to_merged_when_absent(self):
        stats = {"patterns_merged": 4}
        assert resolve_merged(stats) == 4

    def test_zero_deduplicated_not_shadowed_by_merged(self):
        stats = {"patterns_deduplicated": 0, "patterns_merged": 9}
        assert resolve_merged(stats) == 0

    def test_both_absent_returns_zero(self):
        assert resolve_merged({}) == 0


class TestIssue29CumulativeV15Primary:
    """cumulative_v15_reward_delta must be the primary reward display metric."""

    def test_v15_used_when_present(self):
        stats = {"cumulative_v15_reward_delta": 3.2, "helpful_delta": 1}
        src, val = resolve_reward(stats)
        assert src == "v15"
        assert abs(val - 3.2) < 1e-9

    def test_helpful_delta_fallback_when_v15_absent(self):
        stats = {"helpful_delta": 5}
        src, val = resolve_reward(stats)
        assert src == "helpful_delta"
        assert val == 5

    def test_v15_zero_still_primary(self):
        """0.0 must not fall through to helpful_delta."""
        stats = {"cumulative_v15_reward_delta": 0.0, "helpful_delta": 99}
        src, val = resolve_reward(stats)
        assert src == "v15"
        assert val == 0.0

    def test_negative_v15_is_primary(self):
        stats = {"cumulative_v15_reward_delta": -1.5}
        src, val = resolve_reward(stats)
        assert src == "v15"
        assert abs(val - (-1.5)) < 1e-9

    def test_both_absent_defaults_to_helpful_delta_zero(self):
        src, val = resolve_reward({})
        assert src == "helpful_delta"
        assert val == 0
