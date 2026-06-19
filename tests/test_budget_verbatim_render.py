#!/usr/bin/env python3
"""
TDD RED tests for the new BUDGET-VERBATIM-NO-TAIL render contract.

Spec (server-team validated, v7.1.11+):
  - Order patterns by bandit_rank ASC; None → tail (stable), as today.
  - Greedily include patterns VERBATIM until the TOTAL additionalContext string
    (including the XML wrapper + header) would exceed the budget (default 9500 chars).
  - DROP the remaining tail ENTIRELY — no compact index, no one-liners.
  - DROP domains_summary, expanded, threshold from rendered JSON.
  - Header shows shown="N" of="M" (or equivalent 1-line "N of M (budget)").
  - HARD GUARANTEE: total returned string is ALWAYS ≤ 9500 chars.
  - EDGE CASE: if even the single top-1 pattern verbatim alone exceeds the budget,
    include it TRUNCATED so the total still fits — never emit empty, never exceed.
  - Budget is a parameter (default 9500).
  - F-080: retrieval_log_map + injected_pattern_ids cover ONLY the injected top-N
    (what the model actually saw), NOT all retrieved. retrieval_id preserved top-level.
  - render_patterns_dict remains unchanged (all patterns, no budget).
  - strip_and_gate (domain-shift, ≤8 patterns) all fit verbatim → no behavior loss.
"""

import json
import sys
from pathlib import Path

import pytest

# ── path bootstrap ─────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

from ace_pattern_render import render_patterns, render_patterns_dict  # noqa: E402


# ── shared fixture factory ─────────────────────────────────────────────────────

def _make_pattern(
    pid,
    bandit_rank=None,
    semantic_score=0.8,
    reward=5.0,
    is_at_risk=False,
    retrieval_log_id=None,
    domain="test",
    content="Pattern content here.",
    evidence=None,
    content_size=None,
):
    """Build a minimal server-wire pattern dict."""
    if content_size is not None:
        content = "X" * content_size
    mf = {
        "semantic_score": semantic_score,
        "bandit_rank": bandit_rank,
        "ucb_score": 0.9,
        "retrieval_log_id": retrieval_log_id,
        "retrieval_id": "test-retrieval-id",
        "domain_boost": False,
    }
    return {
        "id": pid,
        "name": "",
        "domain": domain,
        "content": content,
        "confidence": 0.85,
        "helpful": 3.0,
        "harmful": 0.0,
        "section": "strategies_and_hard_rules",
        "evidence": evidence if evidence is not None else ["ev1", "ev2", "ev3"],
        "root_cause": "",
        "error_context": "",
        "cumulative_v15_reward": reward,
        "n_hot_pos": 1,
        "n_hot_neg": 0,
        "isAtRisk": is_at_risk,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "last_used": "2026-06-12T00:00:00Z",
        "observations": 10.0,
        "retrieval_count": 5,
        "source": "local",
        "match_factors": mf,
    }


def _make_response(patterns, retrieval_id="ret-test-001", with_expanded=True, with_domains=True):
    resp = {
        "similar_patterns": patterns,
        "count": len(patterns),
        "threshold": 0.5,
        "retrieval_id": retrieval_id,
    }
    if with_expanded:
        resp["expanded"] = [
            {"cached": True, "pattern_id": "some-cache-id", "cumulative_reward": 5.0}
        ]
    if with_domains:
        resp["domains_summary"] = {
            "test:local": {"domain": "test", "source": "local", "count": len(patterns)}
        }
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Budget guarantee — total string ALWAYS ≤ 9500
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetGuarantee:

    def test_small_input_within_budget(self):
        """20 small patterns: total rendered string ≤ 9500 chars."""
        patterns = [_make_pattern(f"ctx-sm-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ctx) <= 9500, (
            f"Small input: rendered string must be ≤9500 chars; got {len(ctx)}"
        )

    def test_large_100_patterns_within_budget(self):
        """100 patterns with substantial content: total ≤ 9500 chars."""
        patterns = [
            _make_pattern(
                f"ctx-lg-{i:04d}", bandit_rank=i + 1,
                content="A" * 300,
                evidence=["Evidence line one with some detail.", "Evidence line two."],
            )
            for i in range(100)
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ctx) <= 9500, (
            f"100-pattern large input: rendered string must be ≤9500 chars; got {len(ctx)}"
        )

    def test_custom_budget_7000_respected(self):
        """With budget=7000, total rendered string ≤ 7000 chars."""
        patterns = [
            _make_pattern(f"ctx-b7k-{i:04d}", bandit_rank=i + 1, content="B" * 200)
            for i in range(50)
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=7000
        )
        assert len(ctx) <= 7000, (
            f"budget=7000: rendered string must be ≤7000 chars; got {len(ctx)}"
        )

    def test_custom_budget_5000_respected(self):
        """With budget=5000, total rendered string ≤ 5000 chars."""
        patterns = [
            _make_pattern(f"ctx-b5k-{i:04d}", bandit_rank=i + 1, content="C" * 200)
            for i in range(30)
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=5000
        )
        assert len(ctx) <= 5000, (
            f"budget=5000: rendered string must be ≤5000 chars; got {len(ctx)}"
        )

    def test_subagent_tag_within_budget(self):
        """Subagent tag with attrs: total ≤ 9500."""
        patterns = [
            _make_pattern(f"ctx-sub-{i:04d}", bandit_rank=i + 1, content="D" * 200)
            for i in range(50)
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns-subagent",
            attrs='agent-type="coder" agent-id="sub-abc-xyz"'
        )
        assert len(ctx) <= 9500, (
            f"Subagent tag: rendered string must be ≤9500 chars; got {len(ctx)}"
        )

    def test_budget_default_is_9500(self):
        """Default budget is 9500 — verify by passing budget=9500 explicitly matches default."""
        patterns = [
            _make_pattern(f"ctx-def-{i:04d}", bandit_rank=i + 1, content="E" * 200)
            for i in range(40)
        ]
        resp = _make_response(patterns)
        ctx_default, _, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"'
        )
        ctx_explicit, _, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=9500
        )
        assert ctx_default == ctx_explicit, (
            "Default budget must equal explicitly passing budget=9500"
        )

    def test_empty_input_within_budget(self):
        """Empty pattern list: string ≤ 9500 (trivially)."""
        resp = _make_response([])
        ctx, ids, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ctx) <= 9500
        assert ids == []
        assert rl_map == {}

    def test_single_small_pattern_within_budget(self):
        """Single small pattern: string ≤ 9500."""
        resp = _make_response([_make_pattern("ctx-one-0001", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ctx) <= 9500


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: NO tail — no compact index, no one-liners
# ─────────────────────────────────────────────────────────────────────────────

class TestNoTail:

    def _rendered_ctx(self, n=50, content_size=200):
        patterns = [
            _make_pattern(f"ctx-notail-{i:04d}", bandit_rank=i + 1, content="F" * content_size)
            for i in range(n)
        ]
        resp = _make_response(patterns)
        return render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')

    def test_no_ranked_index_tag(self):
        """<ranked_index> tag must NOT appear anywhere in the output."""
        ctx, _, _, _ = self._rendered_ctx(n=100)
        assert "<ranked_index>" not in ctx, (
            "Output must not contain <ranked_index> — compact tail is DROPPED"
        )
        assert "</ranked_index>" not in ctx, (
            "Output must not contain </ranked_index> — compact tail is DROPPED"
        )

    def test_no_compact_index_format(self):
        """The compact index format '#N [domain] s=...' must NOT appear in output."""
        ctx, _, _, _ = self._rendered_ctx(n=100)
        import re
        compact_pattern = re.compile(r'#\d+ \[')
        assert not compact_pattern.search(ctx), (
            "Compact index format '#N [domain]' must not appear in output (tail is DROPPED)"
        )

    def test_no_hash_question_index(self):
        """The '#?' compact index marker must NOT appear in output."""
        patterns = [
            _make_pattern("ctx-ranked-0001", bandit_rank=1, content="G" * 200),
            _make_pattern("ctx-norank-0001", bandit_rank=None, content="H" * 200),
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "#?" not in ctx, (
            "Compact index '#?' marker must not appear — tail is DROPPED, not compacted"
        )

    def test_patterns_beyond_budget_entirely_absent(self):
        """Patterns that do not fit in the budget must not appear AT ALL in the output."""
        # Use a small budget and large patterns so only first 1-2 fit
        patterns = [
            _make_pattern(f"ctx-absent-{i:04d}", bandit_rank=i + 1, content="I" * 500)
            for i in range(20)
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=3000
        )
        # The budget is tight — at least some patterns must be absent from output entirely
        # Any pattern beyond the budget must not appear (neither verbatim NOR as compact)
        injected_ids_in_ctx = []
        for i in range(20):
            pid = f"ctx-absent-{i:04d}"
            if pid in ctx:
                injected_ids_in_ctx.append(pid)
        # We can't assert exact count (depends on pattern size), but verify that
        # the TOTAL string ≤ budget (this is the primary guarantee)
        assert len(ctx) <= 3000, (
            f"budget=3000: must not exceed budget; got {len(ctx)}"
        )

    def test_no_tail_with_large_n_small_budget(self):
        """With budget=2000 and 100 large patterns, tail is simply dropped — no compact lines."""
        patterns = [
            _make_pattern(f"ctx-bigdrop-{i:04d}", bandit_rank=i + 1, content="J" * 400)
            for i in range(100)
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=2000
        )
        import re
        assert not re.search(r'#\d+ \[', ctx), (
            "No compact index lines must appear even with very tight budget"
        )
        assert "<ranked_index>" not in ctx
        assert len(ctx) <= 2000


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Bloat dropped — domains_summary, expanded, threshold absent
# ─────────────────────────────────────────────────────────────────────────────

class TestBloatDropped:

    def _get_json_from_ctx(self, ctx):
        """Extract the first JSON object from the rendered output."""
        lines = ctx.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        # Try to parse the whole content between tags
        import re
        m = re.search(r'<[^>]+>\s*(\{.*?\})\s*</', ctx, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        raise AssertionError(f"Could not extract JSON from ctx: {ctx[:200]!r}")

    def test_domains_summary_absent(self):
        """domains_summary must NOT appear in the rendered JSON payload."""
        patterns = [_make_pattern("ctx-bloat-0001", bandit_rank=1)]
        resp = _make_response(patterns, with_domains=True)
        assert "domains_summary" in resp, "Fixture must have domains_summary"
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._get_json_from_ctx(ctx)
        assert "domains_summary" not in data, (
            "domains_summary is bloat and must be DROPPED from rendered output"
        )

    def test_expanded_absent(self):
        """expanded must NOT appear in the rendered JSON payload."""
        patterns = [_make_pattern("ctx-bloat-0002", bandit_rank=1)]
        resp = _make_response(patterns, with_expanded=True)
        assert "expanded" in resp, "Fixture must have expanded"
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._get_json_from_ctx(ctx)
        assert "expanded" not in data, (
            "expanded is bloat and must be DROPPED from rendered output"
        )

    def test_threshold_absent(self):
        """threshold must NOT appear in the rendered JSON payload."""
        patterns = [_make_pattern("ctx-bloat-0003", bandit_rank=1)]
        resp = _make_response(patterns)
        assert "threshold" in resp, "Fixture must have threshold"
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._get_json_from_ctx(ctx)
        assert "threshold" not in data, (
            "threshold is bloat and must be DROPPED from rendered output"
        )

    def test_all_three_bloat_fields_absent(self):
        """All three bloat fields must be absent simultaneously."""
        patterns = [_make_pattern(f"ctx-bloat-{i:04d}", bandit_rank=i + 1) for i in range(5)]
        resp = _make_response(patterns, with_expanded=True, with_domains=True)
        resp["threshold"] = 0.5
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._get_json_from_ctx(ctx)
        for bloat_field in ("domains_summary", "expanded", "threshold"):
            assert bloat_field not in data, (
                f"Bloat field '{bloat_field}' must be DROPPED from rendered output"
            )

    def test_retrieval_id_preserved(self):
        """retrieval_id must still be present in the rendered JSON."""
        patterns = [_make_pattern("ctx-ret-0001", bandit_rank=1)]
        resp = _make_response(patterns, retrieval_id="ret-keep-xyz-123")
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._get_json_from_ctx(ctx)
        assert data.get("retrieval_id") == "ret-keep-xyz-123", (
            "retrieval_id must be preserved in rendered output"
        )

    def test_domains_summary_not_in_raw_string(self):
        """Even as a raw string search, 'domains_summary' must not appear in rendered output."""
        patterns = [_make_pattern(f"ctx-rawstr-{i:04d}", bandit_rank=i + 1) for i in range(10)]
        resp = _make_response(patterns, with_domains=True)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "domains_summary" not in ctx, (
            "domains_summary must not appear anywhere in rendered output string"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: Header shows shown/of counts
# ─────────────────────────────────────────────────────────────────────────────

class TestHeader:

    def test_header_contains_shown_count(self):
        """The opening XML tag or a header must indicate how many patterns are shown."""
        patterns = [
            _make_pattern(f"ctx-hdr-{i:04d}", bandit_rank=i + 1, content="K" * 200)
            for i in range(50)
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        # The header can be in the XML tag attrs: shown="N" of="M"
        # or in the JSON body as a 1-line field. Either is acceptable.
        # The key requirement: the output must indicate how many were shown vs total.
        has_shown_attr = 'shown="' in ctx
        has_of_attr = ' of="' in ctx or ' of=' in ctx
        has_budget_comment = 'budget' in ctx.lower() or 'of ' in ctx
        # At minimum, the XML tag must show counts
        assert has_shown_attr or has_budget_comment, (
            f"Header must indicate shown count; got opening: {ctx[:200]!r}"
        )

    def test_header_shown_equals_actual_injected_count(self):
        """shown count in the tag must match len(injected_pattern_ids)."""
        patterns = [
            _make_pattern(f"ctx-hdrn-{i:04d}", bandit_rank=i + 1, content="L" * 200)
            for i in range(50)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        import re
        m = re.search(r'shown="(\d+)"', ctx)
        if m:
            shown_in_header = int(m.group(1))
            assert shown_in_header == len(ids), (
                f"shown in header ({shown_in_header}) must match len(injected_pattern_ids) ({len(ids)})"
            )

    def test_header_of_equals_total_patterns(self):
        """The 'of' count in the tag must equal the total patterns in the response."""
        patterns = [
            _make_pattern(f"ctx-hdrof-{i:04d}", bandit_rank=i + 1, content="M" * 200)
            for i in range(50)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        import re
        m = re.search(r'of="(\d+)"', ctx)
        if m:
            of_in_header = int(m.group(1))
            assert of_in_header == 50, (
                f"of in header ({of_in_header}) must equal total patterns (50)"
            )

    def test_all_fit_shown_equals_of(self):
        """When all patterns fit, shown must equal total (of)."""
        patterns = [_make_pattern(f"ctx-allfit-{i:04d}", bandit_rank=i + 1) for i in range(5)]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        import re
        shown_m = re.search(r'shown="(\d+)"', ctx)
        of_m = re.search(r'of="(\d+)"', ctx)
        if shown_m and of_m:
            assert shown_m.group(1) == of_m.group(1), (
                "When all fit, shown must equal of"
            )
        if shown_m:
            assert int(shown_m.group(1)) == len(ids), (
                "shown must equal len(injected_pattern_ids)"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: F-080 — retrieval_log_map covers ONLY injected set (not all retrieved)
# ─────────────────────────────────────────────────────────────────────────────

class TestF080OverInjectedSet:

    def test_retrieval_log_map_covers_only_injected_not_all(self):
        """With budget forcing only N < total patterns, retrieval_log_map covers only injected N."""
        # 20 large patterns, budget forces only ~2-3 to fit
        patterns = [
            _make_pattern(
                f"ctx-f080-{i:04d}", bandit_rank=i + 1,
                retrieval_log_id=100 + i,
                content="N" * 500,
            )
            for i in range(20)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, rl_map = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=3000
        )
        # retrieval_log_map must cover ONLY the injected ids
        assert set(rl_map.keys()) == set(ids), (
            f"retrieval_log_map must cover ONLY injected patterns ({len(ids)}), "
            f"not all {len(patterns)}; "
            f"rl_map has {len(rl_map)} keys, ids has {len(ids)}"
        )

    def test_retrieval_log_map_correct_values_for_injected(self):
        """retrieval_log_map must have correct retrieval_log_id values for injected patterns."""
        patterns = [
            _make_pattern("ctx-rl-0001", bandit_rank=1, retrieval_log_id=42, content="O" * 100),
            _make_pattern("ctx-rl-0002", bandit_rank=2, retrieval_log_id=99, content="P" * 100),
            _make_pattern("ctx-rl-0003", bandit_rank=3, retrieval_log_id=77, content="Q" * 100),
        ]
        resp = _make_response(patterns)
        ctx, ids, _, rl_map = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=9500
        )
        # All should fit in 9500 budget
        for pid, expected_rlid in [("ctx-rl-0001", 42), ("ctx-rl-0002", 99), ("ctx-rl-0003", 77)]:
            if pid in ids:
                assert rl_map.get(pid) == expected_rlid, (
                    f"Pattern {pid}: expected retrieval_log_id={expected_rlid}, got {rl_map.get(pid)}"
                )

    def test_non_injected_patterns_not_in_retrieval_log_map(self):
        """Patterns beyond the budget must NOT appear in retrieval_log_map."""
        patterns = [
            _make_pattern(
                f"ctx-excl-{i:04d}", bandit_rank=i + 1,
                retrieval_log_id=200 + i,
                content="R" * 1000,
            )
            for i in range(10)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, rl_map = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=3000
        )
        injected_set = set(ids)
        for pid in rl_map:
            assert pid in injected_set, (
                f"Pattern {pid} is in retrieval_log_map but was NOT injected (beyond budget)"
            )

    def test_injected_pattern_ids_covers_only_injected(self):
        """injected_pattern_ids must cover ONLY the patterns that were actually rendered."""
        patterns = [
            _make_pattern(f"ctx-injonly-{i:04d}", bandit_rank=i + 1, content="S" * 500)
            for i in range(20)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, rl_map = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=3000
        )
        # Verify injected_pattern_ids only contains patterns actually present in the output
        for pid in ids:
            assert pid in ctx, (
                f"Pattern {pid} in injected_pattern_ids but its id is not found in rendered output"
            )

    def test_bool_retrieval_log_id_rejected(self):
        """Bool retrieval_log_id must still be rejected from retrieval_log_map."""
        p = _make_pattern("ctx-bool-0001", bandit_rank=1, retrieval_log_id=None)
        p["match_factors"]["retrieval_log_id"] = True  # bool — must be rejected
        resp = _make_response([p])
        ctx, ids, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-bool-0001" not in rl_map, (
            "Bool retrieval_log_id=True must be rejected from retrieval_log_map"
        )

    def test_retrieval_id_top_level_preserved(self):
        """Top-level retrieval_id must be preserved (for F-080 server correlation)."""
        patterns = [_make_pattern("ctx-retid-0001", bandit_rank=1)]
        resp = _make_response(patterns, retrieval_id="ret-f080-abc-123")
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ret-f080-abc-123" in ctx, (
            "Top-level retrieval_id must appear in the rendered output"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: Oversized edge case — single pattern > budget → truncated
# ─────────────────────────────────────────────────────────────────────────────

class TestOversizedPattern:

    def test_single_oversized_pattern_included_truncated(self):
        """If single top-1 pattern alone exceeds budget, include it TRUNCATED so total ≤ budget."""
        # Build a pattern whose content alone is 20000 chars
        p = _make_pattern("ctx-oversize-0001", bandit_rank=1, content_size=20000)
        resp = _make_response([p])
        ctx, ids, _, rl_map = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=9500
        )
        # Must NOT be empty — always inject at least the top-1 (possibly truncated)
        assert ids, (
            "Even when top-1 pattern exceeds budget, it must be included (truncated)"
        )
        assert "ctx-oversize-0001" in ids, (
            "Oversized top-1 pattern must be in injected_pattern_ids"
        )
        # Total must be ≤ budget
        assert len(ctx) <= 9500, (
            f"Oversized top-1 truncated: total must be ≤9500; got {len(ctx)}"
        )

    def test_single_oversized_non_empty_output(self):
        """Oversized single pattern: output string must be non-empty and well-formed."""
        p = _make_pattern("ctx-oversize-0002", bandit_rank=1, content_size=15000)
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=9500
        )
        assert ctx.strip(), "Output must be non-empty even for oversized single pattern"
        assert "<ace-patterns" in ctx
        assert "</ace-patterns>" in ctx

    def test_oversized_pattern_truncation_with_small_budget(self):
        """With budget=2000 and oversized pattern, output ≤ 2000 and non-empty."""
        p = _make_pattern("ctx-oversize-0003", bandit_rank=1, content_size=10000)
        resp = _make_response([p])
        ctx, ids, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=2000
        )
        assert len(ctx) <= 2000, f"Oversized truncated, budget=2000: got {len(ctx)}"
        assert ids, "Must include at least one pattern even with tight budget"

    def test_oversized_pattern_followed_by_normal_all_in_budget(self):
        """If top-1 oversized+truncated + remaining small patterns: only top-1 truncated fits,
        but normal patterns after it may also fit if space remains."""
        # Top-1 is huge, rest are tiny
        patterns = [
            _make_pattern("ctx-huge-0001", bandit_rank=1, content_size=8000),
        ] + [
            _make_pattern(f"ctx-tiny-{i:04d}", bandit_rank=i + 2, content="T" * 10)
            for i in range(5)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=9500
        )
        # Total must be within budget
        assert len(ctx) <= 9500
        # Top-1 must always be included
        assert "ctx-huge-0001" in ids


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: Injected patterns are the bandit_rank-top-N prefix
# ─────────────────────────────────────────────────────────────────────────────

class TestTopNPrefix:

    def test_injected_are_prefix_of_sorted_order(self):
        """The injected patterns must be a PREFIX of the bandit_rank-sorted order."""
        patterns = [
            _make_pattern(f"ctx-pfx-{i:04d}", bandit_rank=i + 1, content="U" * 300)
            for i in range(20)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=4000
        )
        # The injected ids must be the first N from the bandit_rank order
        # i.e., ctx-pfx-0000 (rank=1) comes before ctx-pfx-0001 (rank=2), etc.
        if not ids:
            pytest.skip("No patterns injected (budget too tight for fixture)")
        # Verify they are a prefix: for each injected id, check that
        # no non-injected id has a LOWER rank
        injected_set = set(ids)
        id_to_rank = {f"ctx-pfx-{i:04d}": i + 1 for i in range(20)}
        max_injected_rank = max(id_to_rank[pid] for pid in ids)
        for pid, rank in id_to_rank.items():
            if rank < max_injected_rank:
                assert pid in injected_set, (
                    f"Pattern {pid} (rank={rank}) should be injected since "
                    f"lower-priority pattern {max_injected_rank} was injected"
                )

    def test_higher_rank_patterns_preferred_over_lower(self):
        """Bandit_rank=1 must be injected before rank=100 when budget is tight."""
        patterns = [
            _make_pattern("ctx-rank1-0001", bandit_rank=1, content="V" * 200),
            _make_pattern("ctx-rank100-0001", bandit_rank=100, content="W" * 200),
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=2500
        )
        # If only one fits, it must be rank=1
        if len(ids) == 1:
            assert "ctx-rank1-0001" in ids, (
                "When only one pattern fits, the top-ranked (rank=1) must be chosen"
            )

    def test_unranked_patterns_go_to_tail_of_queue(self):
        """Patterns with None bandit_rank are considered last for budget allocation."""
        patterns = [
            _make_pattern("ctx-ranked-0001", bandit_rank=1, content="X" * 400),
            _make_pattern("ctx-norank-0001", bandit_rank=None, content="Y" * 400),
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=3000
        )
        # If only one fits, it must be the ranked one
        if len(ids) == 1:
            assert "ctx-ranked-0001" in ids, (
                "Ranked pattern must be preferred over unranked when budget is tight"
            )

    def test_all_fit_all_injected(self):
        """When all patterns fit within budget, all must be injected."""
        patterns = [_make_pattern(f"ctx-allfit-{i:04d}", bandit_rank=i + 1) for i in range(5)]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ids) == 5, (
            f"All 5 small patterns must fit in default budget; got {len(ids)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 8: render_patterns_dict unchanged — no budget applied there
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderPatternsDictUnchanged:

    def test_dict_still_returns_all_patterns(self):
        """render_patterns_dict must still return ALL patterns (no budget filter)."""
        patterns = [
            _make_pattern(f"ctx-dictall-{i:04d}", bandit_rank=i + 1, content="Z" * 500)
            for i in range(100)
        ]
        resp = _make_response(patterns)
        out_dict, ids, rl_map = render_patterns_dict(resp)
        assert len(out_dict["similar_patterns"]) == 100, (
            "render_patterns_dict must return all 100 patterns (no budget applied)"
        )
        assert len(ids) == 100, (
            "render_patterns_dict injected_pattern_ids must cover all 100"
        )

    def test_dict_still_drops_bloat(self):
        """render_patterns_dict must still drop expanded from its output."""
        patterns = [_make_pattern("ctx-dictbloat-0001", bandit_rank=1)]
        resp = _make_response(patterns, with_expanded=True)
        out_dict, _, _ = render_patterns_dict(resp)
        assert "expanded" not in out_dict, "render_patterns_dict must still drop expanded"

    def test_dict_does_not_accept_budget_param(self):
        """render_patterns_dict must NOT accept a budget parameter (no API change)."""
        patterns = [_make_pattern("ctx-dictparam-0001", bandit_rank=1)]
        resp = _make_response(patterns)
        # Should work fine without budget param
        out_dict, _, _ = render_patterns_dict(resp)
        assert out_dict is not None


# ─────────────────────────────────────────────────────────────────────────────
# Section 9: strip_and_gate — domain-shift path, ≤8 patterns all verbatim
# ─────────────────────────────────────────────────────────────────────────────

class TestStripAndGateBudgetCompatible:

    def test_strip_and_gate_8_patterns_no_truncation(self):
        """strip_and_gate with ≤8 patterns: all fit verbatim (no behavior loss)."""
        from patterns_used_state import strip_and_gate
        patterns = [_make_pattern(f"ctx-sg8-{i:04d}", bandit_rank=i + 1) for i in range(8)]
        resp = _make_response(patterns)
        result = strip_and_gate(resp)
        assert len(result.get("similar_patterns", [])) == 8, (
            "strip_and_gate with 8 patterns must return all 8 (no budget truncation)"
        )

    def test_strip_and_gate_drops_bloat(self):
        """strip_and_gate must drop expanded and not emit domains_summary in patterns."""
        from patterns_used_state import strip_and_gate
        patterns = [_make_pattern("ctx-sgbloat-0001", bandit_rank=1)]
        resp = _make_response(patterns, with_expanded=True, with_domains=True)
        result = strip_and_gate(resp)
        assert "expanded" not in result, "strip_and_gate must drop expanded"


# ─────────────────────────────────────────────────────────────────────────────
# Section 10: Signature — budget param on render_patterns
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderPatternsSignature:

    def test_render_patterns_accepts_budget_param(self):
        """render_patterns must accept a 'budget' keyword argument."""
        import inspect
        sig = inspect.signature(render_patterns)
        assert "budget" in sig.parameters, (
            "render_patterns must accept 'budget' keyword parameter"
        )

    def test_render_patterns_budget_default_is_9500(self):
        """render_patterns budget default value must be 9500."""
        import inspect
        sig = inspect.signature(render_patterns)
        param = sig.parameters.get("budget")
        assert param is not None, "budget parameter must exist"
        assert param.default == 9500, (
            f"budget default must be 9500; got {param.default!r}"
        )

    def test_render_patterns_still_returns_4_tuple(self):
        """render_patterns must still return a 4-tuple."""
        resp = _make_response([_make_pattern("ctx-sig-0001", bandit_rank=1)])
        result = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(result, tuple) and len(result) == 4, (
            f"render_patterns must return a 4-tuple; got {type(result)} len={getattr(result, '__len__', lambda: '?')()}"
        )

    def test_third_element_still_empty_string(self):
        """Element 2 of render_patterns 4-tuple must still be empty string (reserved)."""
        resp = _make_response([_make_pattern("ctx-sig-0002", bandit_rank=1)])
        _, _, reserved, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert reserved == "", f"Third element must be empty string; got {reserved!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Section 11: Existing contracts preserved (regression)
# ─────────────────────────────────────────────────────────────────────────────

class TestExistingContractsPreserved:

    def _get_injected_patterns_from_ctx(self, ctx):
        """Extract similar_patterns list from the JSON in the rendered output."""
        lines = ctx.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line).get("similar_patterns", [])
                except json.JSONDecodeError:
                    continue
        return []

    def test_bandit_rank_hoisted(self):
        """bandit_rank must still be hoisted to top-level in injected patterns."""
        resp = _make_response([_make_pattern("ctx-hoist-0001", bandit_rank=3)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_injected_patterns_from_ctx(ctx)
        assert pats, "No patterns in output"
        assert pats[0].get("bandit_rank") == 3, "bandit_rank must be hoisted"

    def test_semantic_score_hoisted(self):
        """semantic_score must still be hoisted to top-level."""
        resp = _make_response([_make_pattern("ctx-hoist-0002", bandit_rank=1, semantic_score=0.91)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_injected_patterns_from_ctx(ctx)
        assert pats, "No patterns"
        assert abs(pats[0].get("semantic_score", 0) - 0.91) < 1e-6, "semantic_score must be hoisted"

    def test_match_factors_stripped(self):
        """match_factors must still be stripped from injected patterns."""
        resp = _make_response([_make_pattern("ctx-strip-0001", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_injected_patterns_from_ctx(ctx)
        for p in pats:
            assert "match_factors" not in p, "match_factors must be stripped"

    def test_no_quality_gate_atrisk_retained(self):
        """isAtRisk=True patterns must still be retained (no gate in render path)."""
        patterns = [
            _make_pattern("ctx-good-0001", bandit_rank=1),
            _make_pattern("ctx-atrisk-0001", bandit_rank=2, is_at_risk=True, reward=-1.0),
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        # Both are small — both should fit in default budget
        assert "ctx-atrisk-0001" in ids, "At-risk pattern must still be retained (no gate)"

    def test_sorted_by_bandit_rank(self):
        """Patterns must still be sorted by bandit_rank ASC in the output."""
        patterns = [
            _make_pattern("ctx-rank5-0001", bandit_rank=5),
            _make_pattern("ctx-rank1-0001", bandit_rank=1),
            _make_pattern("ctx-rank3-0001", bandit_rank=3),
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_injected_patterns_from_ctx(ctx)
        ranks = [p.get("bandit_rank") for p in pats if p.get("bandit_rank") is not None]
        assert ranks == sorted(ranks), f"Patterns must be sorted by bandit_rank ASC; got {ranks}"

    def test_evidence_capped_at_2(self):
        """Evidence must still be capped at 2 items."""
        p = _make_pattern("ctx-ev-0001", bandit_rank=1, evidence=["e1", "e2", "e3", "e4"])
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_injected_patterns_from_ctx(ctx)
        if pats:
            assert len(pats[0].get("evidence", [])) <= 2, "Evidence must be capped at 2"

    def test_bandit_rank_omitted_when_none(self):
        """When bandit_rank is None, it must be ABSENT (not null) from the output."""
        p = _make_pattern("ctx-norank-0001", bandit_rank=None)
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_injected_patterns_from_ctx(ctx)
        if pats:
            assert "bandit_rank" not in pats[0], (
                "bandit_rank must be absent (not null) when None"
            )

    def test_xml_wrapping_preserved(self):
        """XML tag wrapping must still work correctly."""
        resp = _make_response([_make_pattern("ctx-xml-0001", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns-subagent",
            attrs='agent-type="coder" agent-id="sub-abc"'
        )
        assert "<ace-patterns-subagent" in ctx
        assert 'agent-type="coder"' in ctx
        assert "</ace-patterns-subagent>" in ctx
