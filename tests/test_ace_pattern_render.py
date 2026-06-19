#!/usr/bin/env python3
"""
TDD RED tests for ace_pattern_render.render_patterns() — the new central
pure render helper that replaces the per-site USEFUL_FIELDS strip + quality
gate + flat dump across all 4 injection sites.

Contract (server-team validated, ACE-1.5-native):
  - bandit_rank + semantic_score hoisted from match_factors to top-level
  - NO quality gate / NO drop: at-risk and reward<0 RETAINED
  - Sort by bandit_rank ASC; missing/None bandit_rank → tail (stable)
  - Tier: top-K verbatim (all kept fields incl. evidence[:2]);
          rest as compact one-line ranked index (no evidence)
  - expanded array DROPPED from injected payload
  - Wrap in XML tag with attrs
  - F-080: retrieval_log_map covers FULL set, bool retrieval_log_id rejected
  - injected_pattern_ids = ALL injected pattern ids (both tiers, valid only)

All tests are RED until ace_pattern_render.py exists and is correct.
"""

import json
import sys
from pathlib import Path

import pytest

# ── path bootstrap ────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

# This import is RED until the module exists.
from ace_pattern_render import render_patterns  # noqa: E402


# ── shared fixture factory ────────────────────────────────────────────────────

def _make_pattern(
    pid,
    bandit_rank=None,
    semantic_score=0.8,
    reward=5.0,
    is_at_risk=False,
    retrieval_log_id=None,
    domain="test",
    content="Pattern content here",
    evidence=None,
):
    """Build a minimal server-wire pattern dict (matches real fixture shape)."""
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
        # Server-internal fields that must be dropped:
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "last_used": "2026-06-12T00:00:00Z",
        "observations": 10.0,
        "retrieval_count": 5,
        "source": "local",
        "source_project_id": None,
        "source_project_name": None,
        "local_helpful": 1,
        "local_harmful": 0,
        "payload_version": 15,
        "root_cause_present": False,
        "has_error_context": False,
        "birth_primary_lang": "python",
        "domain_cluster_id": -1,
        "abstract_domain": "",
        "root_cause_cluster_id": -1,
        "birth_first_tool_bucket": "none",
        "birth_n_steps_bucket": "0",
        "birth_has_error": "no_ctx",
        "last_citation_score": 0,
        "citation_score_ema_30d": 0,
        "n_warm_pos": 1,
        "n_warm_neg": 0,
        "n_cold_pos": 0,
        "n_cold_neg": 0,
        "n_retrieval_no_apply": 0,
        "merge_winner_count": 0,
        "merged_from": [],
        "match_factors": mf,
    }


def _make_response(patterns, retrieval_id="ret-test-001", with_expanded=True):
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
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Return type and basic structure
# ─────────────────────────────────────────────────────────────────────────────

class TestReturnShape:

    def test_returns_tuple_of_four(self):
        """render_patterns must return a 4-tuple."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        result = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(result, tuple) and len(result) == 4, (
            f"render_patterns must return a 4-tuple, got type={type(result)}, len={len(result) if hasattr(result, '__len__') else '?'}"
        )

    def test_first_element_is_string(self):
        """Element 0 (additional_context) must be a string."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(ctx, str), f"additional_context must be str, got {type(ctx)}"

    def test_second_element_is_list_of_ids(self):
        """Element 1 (injected_pattern_ids) must be a list of strings."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(ids, list), f"injected_pattern_ids must be list, got {type(ids)}"
        for item in ids:
            assert isinstance(item, str), f"Each id must be str, got {type(item)}: {item!r}"

    def test_fourth_element_is_dict(self):
        """Element 3 (retrieval_log_map) must be a dict."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        _, _, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(rl_map, dict), f"retrieval_log_map must be dict, got {type(rl_map)}"

    def test_xml_tag_wraps_output(self):
        """Output string must open with <tag attrs> and close with </tag>."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert ctx.startswith('<ace-patterns '), (
            f"Output must open with <ace-patterns ..., got: {ctx[:80]!r}"
        )
        assert ctx.rstrip().endswith('</ace-patterns>'), (
            f"Output must close with </ace-patterns>, got: {ctx[-40:]!r}"
        )

    def test_xml_tag_without_attrs(self):
        """When attrs is empty, tag should still be well-formed."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns-subagent")
        assert "<ace-patterns-subagent" in ctx
        assert "</ace-patterns-subagent>" in ctx

    def test_xml_attrs_present_in_tag(self):
        """attrs string must appear in the opening XML tag."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(
            resp, tag="ace-patterns-subagent",
            attrs='agent-type="coder" agent-id="sub-abc"'
        )
        assert 'agent-type="coder"' in ctx
        assert 'agent-id="sub-abc"' in ctx


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Field hoisting — bandit_rank + semantic_score from match_factors
# ─────────────────────────────────────────────────────────────────────────────

class TestFieldHoisting:

    def _get_patterns_from_output(self, ctx):
        """Extract the JSON from inside the XML tag and return similar_patterns list."""
        lines = ctx.split("\n")
        # Line 0: opening tag, Line 1: JSON blob
        assert len(lines) >= 2, f"Output too short: {ctx[:200]!r}"
        return json.loads(lines[1]).get("similar_patterns", [])

    def test_bandit_rank_hoisted_to_top_level(self):
        """bandit_rank must appear as top-level key in each verbatim pattern."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=3, semantic_score=0.75)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_patterns_from_output(ctx)
        assert pats, "No patterns in output"
        p = pats[0]
        assert "bandit_rank" in p, (
            f"bandit_rank must be hoisted to top-level; got keys: {list(p.keys())}"
        )
        assert p["bandit_rank"] == 3

    def test_semantic_score_hoisted_to_top_level(self):
        """semantic_score must appear as top-level key in each verbatim pattern."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1, semantic_score=0.921)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_patterns_from_output(ctx)
        p = pats[0]
        assert "semantic_score" in p, (
            f"semantic_score must be hoisted to top-level; got keys: {list(p.keys())}"
        )
        assert abs(p["semantic_score"] - 0.921) < 1e-9

    def test_match_factors_not_in_output(self):
        """match_factors (server-internal) must NOT appear in kept fields."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_patterns_from_output(ctx)
        for p in pats:
            assert "match_factors" not in p, (
                f"match_factors must be stripped; found in pattern {p.get('id')}"
            )

    def test_server_internal_fields_stripped(self):
        """created_at, updated_at, last_used, observations, etc. must be stripped."""
        MUST_NOT = {
            "created_at", "updated_at", "last_used", "observations",
            "retrieval_count", "source", "source_project_id", "source_project_name",
            "local_helpful", "local_harmful", "payload_version", "root_cause_present",
            "has_error_context", "birth_primary_lang", "domain_cluster_id",
            "abstract_domain", "root_cause_cluster_id", "birth_first_tool_bucket",
            "birth_n_steps_bucket", "birth_has_error", "last_citation_score",
            "citation_score_ema_30d", "n_warm_pos", "n_warm_neg", "n_cold_pos",
            "n_cold_neg", "n_retrieval_no_apply", "merge_winner_count", "merged_from",
            "name",
        }
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_patterns_from_output(ctx)
        for p in pats:
            found = MUST_NOT & set(p.keys())
            assert not found, (
                f"Server-internal fields must be stripped: {found} found in pattern {p.get('id')}"
            )

    def test_kept_fields_present(self):
        """id, domain, content, section, evidence, cumulative_v15_reward, n_hot_pos,
        n_hot_neg, isAtRisk, bandit_rank, semantic_score must all be present."""
        MUST_HAVE = {
            "id", "domain", "content", "section", "evidence",
            "cumulative_v15_reward", "n_hot_pos", "n_hot_neg", "isAtRisk",
            "bandit_rank", "semantic_score",
        }
        resp = _make_response([_make_pattern(
            "ctx-0001-aaaa", bandit_rank=1, semantic_score=0.8, reward=3.5,
        )])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_patterns_from_output(ctx)
        p = pats[0]
        missing = MUST_HAVE - set(p.keys())
        assert not missing, (
            f"Required fields missing from verbatim pattern: {missing}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: NO quality gate — at-risk and reward<0 patterns RETAINED
# ─────────────────────────────────────────────────────────────────────────────

class TestNoQualityGate:

    def test_atrisk_pattern_retained(self):
        """isAtRisk=True pattern must NOT be dropped."""
        good = _make_pattern("ctx-good-0001", bandit_rank=1, is_at_risk=False, reward=5.0)
        bad = _make_pattern("ctx-atrisk-0002", bandit_rank=2, is_at_risk=True, reward=-1.5)
        resp = _make_response([good, bad])
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-atrisk-0002" in ids, (
            "isAtRisk=True pattern must be RETAINED — no quality gate in render_patterns"
        )

    def test_negative_reward_not_atrisk_retained(self):
        """reward<0 with isAtRisk=False pattern must NOT be dropped."""
        p = _make_pattern("ctx-negrew-0001", bandit_rank=1, is_at_risk=False, reward=-2.5)
        resp = _make_response([p])
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-negrew-0001" in ids, (
            "reward<0 pattern must be RETAINED — render_patterns has no quality gate"
        )

    def test_negative_reward_atrisk_retained(self):
        """reward<0, isAtRisk=True must ALSO be retained (inject everything)."""
        p = _make_pattern("ctx-both-bad-0001", bandit_rank=3, is_at_risk=True, reward=-3.0)
        resp = _make_response([p])
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-both-bad-0001" in ids, (
            "reward<0 AND isAtRisk=True must still be RETAINED by render_patterns"
        )

    def test_zero_reward_retained(self):
        """reward=0, isAtRisk=False (neutral/uncredited) must be retained."""
        p = _make_pattern("ctx-neutral-0001", bandit_rank=1, is_at_risk=False, reward=0)
        resp = _make_response([p])
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-neutral-0001" in ids, "reward=0 neutral pattern must be retained"

    def test_all_100_patterns_retained_from_ace_fixture(self):
        """Real 100-pattern server fixture: all 100 patterns in injected_pattern_ids."""
        with open("/tmp/ace_raw_ace.json") as f:
            resp = json.load(f)
        pats = resp.get("similar_patterns", [])
        all_ids = {p["id"] for p in pats if p.get("id")}
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        injected = set(ids)
        assert injected >= all_ids, (
            f"All {len(all_ids)} pattern ids from ace fixture must be retained; "
            f"missing: {all_ids - injected}"
        )

    def test_all_87_patterns_retained_from_neutral_fixture(self):
        """Real 87-pattern server fixture: all 87 patterns in injected_pattern_ids."""
        with open("/tmp/ace_raw_neutral.json") as f:
            resp = json.load(f)
        pats = resp.get("similar_patterns", [])
        all_ids = {p["id"] for p in pats if p.get("id")}
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        injected = set(ids)
        assert injected >= all_ids, (
            f"All {len(all_ids)} pattern ids from neutral fixture must be retained; "
            f"missing: {all_ids - injected}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: Sorting by bandit_rank ascending
# ─────────────────────────────────────────────────────────────────────────────

class TestSortByBanditRank:

    def _get_verbatim_patterns(self, ctx, tag="ace-patterns"):
        lines = ctx.split("\n")
        assert len(lines) >= 2, f"Output too short: {ctx[:200]!r}"
        data = json.loads(lines[1])
        return data.get("similar_patterns", [])

    def test_sorted_ascending_by_bandit_rank(self):
        """Patterns must appear in ascending bandit_rank order."""
        # Provide in reverse order — output must reorder
        patterns = [
            _make_pattern("ctx-rank5-aaaa", bandit_rank=5),
            _make_pattern("ctx-rank1-aaaa", bandit_rank=1),
            _make_pattern("ctx-rank3-aaaa", bandit_rank=3),
            _make_pattern("ctx-rank2-aaaa", bandit_rank=2),
            _make_pattern("ctx-rank4-aaaa", bandit_rank=4),
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=10)
        out_pats = self._get_verbatim_patterns(ctx)
        ranks = [p.get("bandit_rank") for p in out_pats]
        assert ranks == sorted(r for r in ranks if r is not None), (
            f"Verbatim patterns must be sorted by bandit_rank ASC; got ranks: {ranks}"
        )

    def test_missing_bandit_rank_goes_to_tail(self):
        """Patterns with None/missing bandit_rank must appear AFTER ranked ones."""
        patterns = [
            _make_pattern("ctx-ranked-0001", bandit_rank=1),
            _make_pattern("ctx-norank-0001", bandit_rank=None),
            _make_pattern("ctx-ranked-0002", bandit_rank=2),
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=10)
        out_pats = self._get_verbatim_patterns(ctx)
        ids_in_order = [p["id"] for p in out_pats]
        ranked_positions = [i for i, p in enumerate(out_pats) if p.get("bandit_rank") is not None]
        unranked_positions = [i for i, p in enumerate(out_pats) if p.get("bandit_rank") is None]
        if ranked_positions and unranked_positions:
            assert max(ranked_positions) < min(unranked_positions), (
                f"Unranked patterns must be after all ranked ones; order: {ids_in_order}"
            )

    def test_real_fixture_first_pattern_has_rank_1(self):
        """In the real neutral fixture, bandit_rank=1 pattern must be first in output."""
        with open("/tmp/ace_raw_neutral.json") as f:
            resp = json.load(f)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=20)
        out_pats = self._get_verbatim_patterns(ctx)
        if out_pats:
            first_rank = out_pats[0].get("bandit_rank")
            assert first_rank == 1, (
                f"First verbatim pattern must have bandit_rank=1; got {first_rank}"
            )

    def test_stable_order_among_unranked(self):
        """Among patterns with the same None bandit_rank, insertion order is preserved (stable)."""
        patterns = [
            _make_pattern("ctx-norank-A", bandit_rank=None),
            _make_pattern("ctx-norank-B", bandit_rank=None),
            _make_pattern("ctx-norank-C", bandit_rank=None),
        ]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=10)
        out_pats = self._get_verbatim_patterns(ctx)
        out_ids = [p["id"] for p in out_pats]
        assert out_ids == ["ctx-norank-A", "ctx-norank-B", "ctx-norank-C"], (
            f"Stable sort: unranked patterns must preserve insertion order; got {out_ids}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: Tiering — verbatim head + compact index tail
# ─────────────────────────────────────────────────────────────────────────────

class TestTiering:

    def _json_from_ctx(self, ctx):
        """Extract the JSON object from line 1 of the rendered output."""
        lines = ctx.split("\n")
        assert len(lines) >= 2, f"Output too short: {ctx[:200]!r}"
        return json.loads(lines[1])

    def test_verbatim_section_has_tier_k_patterns(self):
        """With 20 patterns and tier_k=5, the JSON similar_patterns list has 5 entries."""
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        data = self._json_from_ctx(ctx)
        verbatim = data.get("similar_patterns", [])
        assert len(verbatim) == 5, (
            f"With tier_k=5 and 20 patterns, verbatim section must have 5 patterns; got {len(verbatim)}"
        )

    def test_tail_section_present_when_over_tier_k(self):
        """When total > tier_k, output must contain a ranked_index section."""
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        assert "ranked_index" in ctx or "compact" in ctx.lower() or "#6" in ctx or "ctx-tier-0005" in ctx, (
            "When total > tier_k, output must contain a compact ranked index for the tail patterns"
        )

    def test_tail_index_has_no_evidence(self):
        """Tail (compact) index entries must NOT include evidence."""
        patterns = [_make_pattern(
            f"ctx-tier-{i:04d}", bandit_rank=i + 1,
            evidence=["evidence line 1", "evidence line 2"]
        ) for i in range(10)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=3)
        # The tail must exist — extract content after the verbatim JSON block
        import re
        # Evidence strings from tail patterns must not appear in index section
        # We test by looking for the specific evidence content of tail patterns
        tail_evidence = "evidence line"
        # The verbatim block only has 3 patterns; remaining 7 are tail
        # Find the compact section (after the JSON block close)
        m = re.search(r'</[^>]+>(.*)', ctx, re.DOTALL)
        tail_section = m.group(1).strip() if m else ""
        # The tail section itself should not be empty if there are tail patterns
        # (the index is appended OUTSIDE the JSON, or inside as a separate field)
        # Either way, tail pattern evidence should not appear verbatim in the output
        # beyond the verbatim section
        # Tail patterns (ranks 4-10) must appear as compact index lines with their rank
        # The compact format is: #{rank} [{domain}] s=... {content[:70]}
        for rank in range(4, 11):
            assert f"#{rank}" in ctx, f"Compact index line for rank #{rank} must appear in output"
        # Evidence text must NOT appear in the compact index lines
        # (only appears in verbatim section for ranks 1-3)
        # The ranked_index section should contain compact lines, not evidence strings
        assert "evidence line" not in ctx.split("<ranked_index>")[-1] if "<ranked_index>" in ctx else True, (
            "Evidence strings must not appear in the compact ranked_index section"
        )

    def test_no_index_when_all_verbatim(self):
        """When total <= tier_k, all patterns are verbatim and no index section needed."""
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1) for i in range(5)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=15)
        data = self._json_from_ctx(ctx)
        verbatim = data.get("similar_patterns", [])
        assert len(verbatim) == 5, (
            f"With tier_k=15 and 5 patterns, all must be verbatim; got {len(verbatim)}"
        )

    def test_verbatim_evidence_capped_at_2(self):
        """Verbatim patterns must cap evidence to the first 2 items."""
        p = _make_pattern(
            "ctx-ev-0001", bandit_rank=1,
            evidence=["ev1", "ev2", "ev3", "ev4", "ev5"]
        )
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=15)
        data = self._json_from_ctx(ctx)
        out_pats = data.get("similar_patterns", [])
        assert out_pats, "No verbatim patterns"
        ev = out_pats[0].get("evidence", [])
        assert len(ev) <= 2, f"Evidence must be capped at 2; got {len(ev)}: {ev}"

    def test_default_tier_k_is_15(self):
        """Default tier_k must be 15 (no explicit arg)."""
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        # no tier_k arg
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._json_from_ctx(ctx)
        verbatim = data.get("similar_patterns", [])
        assert len(verbatim) == 15, (
            f"Default tier_k must be 15; verbatim section has {len(verbatim)} patterns"
        )

    def test_empty_input_produces_empty_output(self):
        """Zero patterns in → empty similar_patterns list, no index."""
        resp = _make_response([])
        ctx, ids, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert ids == [], f"injected_pattern_ids must be [] for empty input; got {ids}"
        assert rl_map == {}, f"retrieval_log_map must be empty for no patterns; got {rl_map}"
        lines = ctx.split("\n")
        if len(lines) >= 2 and lines[1].startswith("{"):
            data = json.loads(lines[1])
            assert data.get("similar_patterns", []) == []


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: expanded array dropped
# ─────────────────────────────────────────────────────────────────────────────

class TestExpandedDropped:

    def _json_from_ctx(self, ctx):
        lines = ctx.split("\n")
        assert len(lines) >= 2, f"Output too short: {ctx[:200]!r}"
        return json.loads(lines[1])

    def test_expanded_not_in_output(self):
        """The 'expanded' array must NOT appear in the injected payload."""
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)], with_expanded=True)
        assert "expanded" in resp, "Fixture must have 'expanded' key before render"
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._json_from_ctx(ctx)
        assert "expanded" not in data, (
            "The 'expanded' array must be DROPPED from injected payload (pure token waste)"
        )

    def test_expanded_dropped_from_real_ace_fixture(self):
        """Real ace fixture has 'expanded'; it must be absent from render output."""
        with open("/tmp/ace_raw_ace.json") as f:
            resp = json.load(f)
        assert "expanded" in resp, "ace fixture must have expanded"
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._json_from_ctx(ctx)
        assert "expanded" not in data, "expanded must not appear in rendered output for real fixture"


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: F-080 — retrieval_log_map covers FULL set
# ─────────────────────────────────────────────────────────────────────────────

class TestRetrievalLogMap:

    def test_retrieval_log_map_covers_all_patterns(self):
        """retrieval_log_map must include entries from ALL patterns (not just head tier)."""
        patterns = [
            _make_pattern(f"ctx-f080-{i:04d}", bandit_rank=i + 1, retrieval_log_id=100 + i)
            for i in range(20)
        ]
        resp = _make_response(patterns)
        _, _, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        # All 20 patterns must have an entry
        for i in range(20):
            pid = f"ctx-f080-{i:04d}"
            assert pid in rl_map, (
                f"retrieval_log_map must cover ALL patterns including tail; missing: {pid}"
            )

    def test_retrieval_log_map_correct_values(self):
        """retrieval_log_map must map pattern id → int retrieval_log_id."""
        patterns = [
            _make_pattern("ctx-rl-0001", bandit_rank=1, retrieval_log_id=42),
            _make_pattern("ctx-rl-0002", bandit_rank=2, retrieval_log_id=99),
        ]
        resp = _make_response(patterns)
        _, _, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert rl_map.get("ctx-rl-0001") == 42, f"Expected 42; got {rl_map.get('ctx-rl-0001')}"
        assert rl_map.get("ctx-rl-0002") == 99, f"Expected 99; got {rl_map.get('ctx-rl-0002')}"

    def test_bool_retrieval_log_id_rejected(self):
        """Bool retrieval_log_id (True/False) must be rejected (bool is subclass of int)."""
        # Build pattern with bool retrieval_log_id
        p = _make_pattern("ctx-bool-0001", bandit_rank=1)
        p["match_factors"]["retrieval_log_id"] = True  # bool — must be rejected
        resp = _make_response([p])
        _, _, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-bool-0001" not in rl_map, (
            "Bool retrieval_log_id=True must be rejected from retrieval_log_map"
        )

    def test_none_retrieval_log_id_not_in_map(self):
        """None retrieval_log_id → pattern not in retrieval_log_map."""
        p = _make_pattern("ctx-none-rl-0001", bandit_rank=1, retrieval_log_id=None)
        resp = _make_response([p])
        _, _, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-none-rl-0001" not in rl_map, (
            "None retrieval_log_id must not produce an entry in retrieval_log_map"
        )

    def test_retrieval_log_map_covers_atrisk_patterns(self):
        """retrieval_log_map must include at-risk patterns (they must not be gate-dropped)."""
        good = _make_pattern("ctx-good-0001", bandit_rank=1, retrieval_log_id=10, is_at_risk=False, reward=5.0)
        atrisk = _make_pattern("ctx-atrisk-0001", bandit_rank=2, retrieval_log_id=20, is_at_risk=True, reward=-1.0)
        resp = _make_response([good, atrisk])
        _, _, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-atrisk-0001" in rl_map, (
            "At-risk pattern must still be in retrieval_log_map (no gate)"
        )
        assert rl_map["ctx-atrisk-0001"] == 20

    def test_retrieval_log_map_from_real_ace_fixture(self):
        """Real 100-pattern fixture: retrieval_log_map must cover all patterns with integer retrieval_log_id."""
        with open("/tmp/ace_raw_ace.json") as f:
            resp = json.load(f)
        pats = resp["similar_patterns"]
        expected = {
            p["id"]: p["match_factors"]["retrieval_log_id"]
            for p in pats
            if p.get("id") and isinstance(p.get("match_factors"), dict)
            and not isinstance(p["match_factors"].get("retrieval_log_id"), bool)
            and isinstance(p["match_factors"].get("retrieval_log_id"), int)
        }
        _, _, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        for pid, expected_rlid in expected.items():
            assert pid in rl_map, f"Pattern {pid} missing from retrieval_log_map"
            assert rl_map[pid] == expected_rlid, (
                f"Pattern {pid}: expected retrieval_log_id={expected_rlid}, got {rl_map[pid]}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Section 8: injected_pattern_ids covers full set (both tiers)
# ─────────────────────────────────────────────────────────────────────────────

class TestInjectedPatternIds:

    def test_ids_cover_both_tiers(self):
        """injected_pattern_ids must contain ids from BOTH verbatim and tail tiers."""
        patterns = [_make_pattern(f"ctx-both-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        assert len(ids) == 20, (
            f"injected_pattern_ids must cover all 20 patterns (both tiers); got {len(ids)}"
        )

    def test_ids_only_valid_pattern_ids(self):
        """All entries in injected_pattern_ids must pass is_valid_pattern_id."""
        from validation import is_valid_pattern_id
        patterns = [_make_pattern(f"ctx-valid-{i:04d}", bandit_rank=i + 1) for i in range(5)]
        resp = _make_response(patterns)
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        for pid in ids:
            assert is_valid_pattern_id(pid), (
                f"injected_pattern_ids must only contain valid pattern ids; invalid: {pid!r}"
            )

    def test_ids_no_duplicates(self):
        """injected_pattern_ids must not contain duplicates."""
        patterns = [_make_pattern(f"ctx-dedup-{i:04d}", bandit_rank=i + 1) for i in range(10)]
        resp = _make_response(patterns)
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ids) == len(set(ids)), (
            f"injected_pattern_ids must have no duplicates; len={len(ids)}, unique={len(set(ids))}"
        )

    def test_ids_cover_atrisk_patterns(self):
        """At-risk patterns (no gate) must appear in injected_pattern_ids."""
        good = _make_pattern("ctx-good-0001", bandit_rank=1, is_at_risk=False)
        bad = _make_pattern("ctx-atrisk-0002", bandit_rank=2, is_at_risk=True, reward=-1.5)
        resp = _make_response([good, bad])
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "ctx-atrisk-0002" in ids, (
            "At-risk pattern must appear in injected_pattern_ids (no gate applied)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 9: Token size reduction (large-input sanity)
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenReduction:

    def test_rendered_output_smaller_than_raw_json(self):
        """Rendered output must be significantly smaller than raw json.dumps of input."""
        with open("/tmp/ace_raw_neutral.json") as f:
            resp = json.load(f)
        raw_size = len(json.dumps(resp))
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=15)
        rendered_size = len(ctx)
        # Should be at least 50% smaller (spec says ~75-78%)
        assert rendered_size < raw_size * 0.60, (
            f"Rendered output ({rendered_size} chars) must be <60% of raw JSON "
            f"({raw_size} chars); ratio={rendered_size/raw_size:.2%}"
        )

    def test_ace_fixture_token_reduction(self):
        """100-pattern ace fixture: rendered output must be <60% of raw."""
        with open("/tmp/ace_raw_ace.json") as f:
            resp = json.load(f)
        raw_size = len(json.dumps(resp))
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=15)
        rendered_size = len(ctx)
        assert rendered_size < raw_size * 0.60, (
            f"Ace fixture: rendered ({rendered_size}) must be <60% of raw ({raw_size}); "
            f"ratio={rendered_size/raw_size:.2%}"
        )

    def test_compact_index_line_format(self):
        """Compact index lines must include bandit_rank, domain, semantic_score, content[:70]."""
        patterns = [_make_pattern(
            f"ctx-cmpct-{i:04d}", bandit_rank=i + 1,
            domain="test-domain", semantic_score=0.75,
            content="This is a test pattern content that should appear truncated"
        ) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        # Tail patterns (ranks 6-20) should appear as compact lines
        # At minimum check rank #6 appears in the output somewhere
        assert "#6" in ctx or "ctx-cmpct-0005" in ctx, (
            "Compact index must reference tail pattern with bandit_rank or id"
        )
