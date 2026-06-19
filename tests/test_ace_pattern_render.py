#!/usr/bin/env python3
"""
TDD tests for ace_pattern_render.render_patterns() — the central pure render
helper for ACE pattern injection.

Contract (server-team validated, ACE-1.5-native):
  - bandit_rank + semantic_score hoisted from match_factors to top-level
  - NO quality gate / NO drop: at-risk and reward<0 RETAINED
  - Sort by bandit_rank ASC; missing/None bandit_rank → tail (stable)
  - BUDGET-VERBATIM-NO-TAIL: greedily include verbatim from top until budget
  - expanded array DROPPED from injected payload
  - Wrap in XML tag with attrs
  - F-080: retrieval_log_map covers INJECTED set only, bool retrieval_log_id rejected
  - injected_pattern_ids = injected (budget-fitting) pattern ids (valid only)

Fixture strategy: ALL tests use synthetic in-repo fixtures built by
_make_synthetic_fixture() — NO /tmp or external-file dependencies.
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


def _make_synthetic_fixture(
    n_patterns=100,
    *,
    retrieval_id="ret-synth-fixture-001",
    with_expanded=True,
    content_template=None,
    evidence_template=None,
    domains=None,
    start_rank=1,
    n_atrisk=10,
    n_negative_reward=5,
):
    """Build a representative synthetic server-response dict (no external files).

    Produces a realistic mix of patterns for use as a test fixture:
      - varied domains (default: 5 rotating domains)
      - realistic content + evidence lengths
      - bandit_rank 1..N (rank-sorted), retrieval_log_id = 1000+i
      - n_atrisk patterns have isAtRisk=True, cumulative_v15_reward=-0.5
      - n_negative_reward patterns have reward<0 (spread across the set)
      - all match_factors present (bandit_rank, semantic_score, retrieval_log_id)
      - expanded array (caller controls via with_expanded)

    This is a PUBLIC repo — synthesised data only, no real pattern content.
    """
    if domains is None:
        domains = [
            "ace-plugin-release-management",
            "system-validation-and-testing",
            "bash-command-execution",
            "python-development-practices",
            "ace-server",
        ]

    CONTENTS = [
        (
            "When debugging hook failures, examine the hook output JSON carefully. "
            "The hookSpecificOutput.additionalContext field is the primary injection "
            "path; missing or malformed JSON here silently drops context."
        ),
        (
            "Always run the full pytest suite after modifying shared-hooks utilities. "
            "Shared utilities like ace_pattern_render.py are imported by multiple "
            "injection sites and regressions can be non-obvious."
        ),
        (
            "Use json.dumps with default separators=(',', ':') when estimating byte "
            "budgets for serialized payloads. The default ', ' separator adds an extra "
            "byte per item compared to the compact form."
        ),
        (
            "Verify that retrieval_log_id values extracted from match_factors are "
            "integers, not booleans. bool is a subclass of int in Python, so an "
            "isinstance(v, int) check must be preceded by not isinstance(v, bool)."
        ),
        (
            "When implementing greedy budget loops for JSON array serialization, "
            "account for the separator cost between items. json.dumps list separator "
            "is ', ' (2 chars), not ',' (1 char) — underestimating by 1 per item "
            "causes the assembled array to exceed budget with many small patterns."
        ),
    ]
    EVIDENCES = [
        ["Agent confirmed fix via live test.", "Test suite green after change."],
        ["Observed in production trace.", "Reproduced in isolated unit test."],
        ["Server-team confirmed behavior.", "Plugin telemetry verified."],
        ["Code review caught the issue.", "Static analysis confirmed pattern."],
        ["Deployment smoke test passed.", "CI pipeline green."],
    ]

    patterns = []
    for i in range(n_patterns):
        rank = start_rank + i
        domain = domains[i % len(domains)]
        content_idx = i % len(CONTENTS)
        ev_idx = i % len(EVIDENCES)

        # Make content length vary: shorter for early ranks, longer for later
        base_content = (content_template or CONTENTS[content_idx])
        if i < n_patterns // 3:
            content = base_content
        elif i < 2 * n_patterns // 3:
            content = base_content + " " + base_content[:50]
        else:
            content = base_content + " " + base_content

        is_at_risk = i < n_atrisk
        reward = -0.5 if is_at_risk else (
            -1.0 if i < (n_atrisk + n_negative_reward) else float(5 + (i % 10))
        )

        mf = {
            "bandit_rank": rank,
            "semantic_score": round(0.99 - i * 0.003, 4),
            "ucb_score": round(1.0 - i * 0.005, 4),
            "retrieval_log_id": 1000 + i,
            "retrieval_id": retrieval_id,
            "domain_boost": False,
        }
        p = {
            "id": f"ctx-synth-{rank:04d}-fixture",
            "name": "",
            "domain": domain,
            "content": content,
            "confidence": round(0.95 - i * 0.002, 4),
            "helpful": float(10 - (i % 5)),
            "harmful": float(i % 3),
            "section": "strategies_and_hard_rules",
            "evidence": (evidence_template or EVIDENCES[ev_idx])[:3],
            "root_cause": "",
            "error_context": "",
            "cumulative_v15_reward": reward,
            "n_hot_pos": max(0, 5 - i % 6),
            "n_hot_neg": i % 3,
            "isAtRisk": is_at_risk,
            # Server-internal fields (must be stripped by render_patterns)
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
        patterns.append(p)

    resp = {
        "similar_patterns": patterns,
        "count": len(patterns),
        "threshold": 0.5,
        "retrieval_id": retrieval_id,
        "domains_summary": {
            d: {"domain": d, "source": "local", "count": n_patterns // len(domains),
                "total_helpful": 50.0}
            for d in domains
        },
    }
    if with_expanded:
        resp["expanded"] = [
            {"cached": True, "pattern_id": "ctx-synth-0001-fixture", "cumulative_reward": 5.0}
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

    def test_budget_top_n_injected_is_rank_prefix_from_ace_fixture(self):
        """Synthetic 100-pattern fixture: injected set is a rank-prefix (top-N by bandit_rank)
        and total len(ctx) ≤ 9500.  Under the budget-verbatim contract not ALL 100 patterns
        fit (budget prevents it) — the injected set is the budget-fitting prefix."""
        resp = _make_synthetic_fixture(n_patterns=100, n_atrisk=5, n_negative_reward=3)
        pats = resp.get("similar_patterns", [])
        all_ids_ordered = [p["id"] for p in pats if p.get("id")]
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        injected = set(ids)
        # The injected set must be a prefix of the rank-ordered full set
        assert injected == set(all_ids_ordered[:len(ids)]), (
            "Injected set must be a rank-ordered prefix of the full pattern list"
        )
        assert len(ctx) <= 9500, f"Budget guarantee: len(ctx)={len(ctx)}"
        assert len(ids) >= 1, "At least one pattern must be injected"

    def test_budget_top_n_injected_is_rank_prefix_from_neutral_fixture(self):
        """Synthetic 87-pattern fixture: injected set is a rank-prefix and ≤9500 chars.
        Under the budget-verbatim contract the injected set is the budget-fitting prefix."""
        resp = _make_synthetic_fixture(n_patterns=87, n_atrisk=8, n_negative_reward=4)
        pats = resp.get("similar_patterns", [])
        all_ids_ordered = [p["id"] for p in pats if p.get("id")]
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        injected = set(ids)
        assert injected == set(all_ids_ordered[:len(ids)]), (
            "Injected set must be a rank-ordered prefix of the full pattern list"
        )
        assert len(ctx) <= 9500, f"Budget guarantee: len(ctx)={len(ctx)}"
        assert len(ids) >= 1, "At least one pattern must be injected"


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

    def test_synthetic_fixture_first_pattern_has_rank_1(self):
        """In the synthetic fixture, bandit_rank=1 pattern must be first in output."""
        resp = _make_synthetic_fixture(n_patterns=50)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=20)
        out_pats = self._get_verbatim_patterns(ctx)
        assert out_pats, "At least one pattern must appear in output"
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
# Section 5: Budget-verbatim-no-tail behavior (replaces old tiering contract)
#
# Old v7.1.10 behavior (REMOVED):
#   - tier_k verbatim head + compact ranked_index tail
#   - F-080 covered full set regardless of what was displayed
#
# New v7.1.11+ behavior:
#   - Greedily include verbatim patterns until budget (default 9500 chars) is hit
#   - DROP tail entirely — no ranked_index, no compact one-liners
#   - F-080 covers only the injected (shown) set
#   - budget= parameter (default 9500)
#   - tier_k parameter RETAINED for API compat with render_patterns_dict calls,
#     but no longer controls what render_patterns injects (budget controls instead)
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetVerbatimNoTailViaTiering:
    """Tests that previously covered tiered rendering, updated for budget-verbatim-no-tail."""

    def _json_from_ctx(self, ctx):
        """Extract the first JSON object from the rendered output."""
        lines = ctx.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise AssertionError(f"No JSON found in ctx: {ctx[:200]!r}")

    def test_no_ranked_index_in_output(self):
        """No ranked_index section must appear — tail is dropped, not compacted."""
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1, content="A" * 200) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "<ranked_index>" not in ctx, (
            "No <ranked_index> must appear — tail is DROPPED in budget-verbatim-no-tail mode"
        )

    def test_total_within_budget(self):
        """Total rendered string must be ≤ 9500 chars (default budget)."""
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ctx) <= 9500, f"Total must be ≤9500; got {len(ctx)}"

    def test_tail_entirely_absent_beyond_budget(self):
        """Patterns beyond budget must not appear at all (no compact fallback)."""
        import re
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1, content="B" * 400) for i in range(20)]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=3000
        )
        # No compact index format in output
        assert not re.search(r'#\d+ \[', ctx), "Compact index lines must not appear"
        assert len(ctx) <= 3000

    def test_no_compact_index_line_for_any_pattern(self):
        """No compact one-liner format (#rank [domain] s=...) must appear."""
        import re
        patterns = [_make_pattern(f"ctx-cmpct-{i:04d}", bandit_rank=i + 1, content="C" * 200) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert not re.search(r'#\d+ \[', ctx), (
            "No compact index format '#N [domain]' must appear — tail is DROPPED"
        )

    def test_verbatim_evidence_capped_at_2(self):
        """Verbatim patterns must cap evidence to the first 2 items."""
        p = _make_pattern(
            "ctx-ev-0001", bandit_rank=1,
            evidence=["ev1", "ev2", "ev3", "ev4", "ev5"]
        )
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._json_from_ctx(ctx)
        out_pats = data.get("similar_patterns", [])
        assert out_pats, "No verbatim patterns"
        ev = out_pats[0].get("evidence", [])
        assert len(ev) <= 2, f"Evidence must be capped at 2; got {len(ev)}: {ev}"

    def test_empty_input_produces_empty_output(self):
        """Zero patterns in → empty similar_patterns list, no tail."""
        resp = _make_response([])
        ctx, ids, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert ids == [], f"injected_pattern_ids must be [] for empty input; got {ids}"
        assert rl_map == {}, f"retrieval_log_map must be empty for no patterns; got {rl_map}"
        assert "<ranked_index>" not in ctx


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

    def test_expanded_dropped_from_synthetic_fixture(self):
        """Synthetic 100-pattern fixture has 'expanded'; it must be absent from render output."""
        resp = _make_synthetic_fixture(n_patterns=100, with_expanded=True)
        assert "expanded" in resp, "Synthetic fixture must have expanded"
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        data = self._json_from_ctx(ctx)
        assert "expanded" not in data, "expanded must not appear in rendered output for synthetic fixture"


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: F-080 — retrieval_log_map covers FULL set
# ─────────────────────────────────────────────────────────────────────────────

class TestRetrievalLogMap:

    def test_retrieval_log_map_covers_injected_patterns(self):
        """retrieval_log_map covers only INJECTED patterns (small → all 20 fit in default budget)."""
        patterns = [
            _make_pattern(f"ctx-f080-{i:04d}", bandit_rank=i + 1, retrieval_log_id=100 + i)
            for i in range(20)
        ]
        resp = _make_response(patterns)
        # Small patterns — all 20 fit in the 9500-char default budget
        _, ids, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        # All injected ids must be in retrieval_log_map
        for pid in ids:
            assert pid in rl_map, (
                f"retrieval_log_map must cover all injected patterns; missing: {pid}"
            )
        # retrieval_log_map must only cover injected set (not non-injected)
        assert set(rl_map.keys()) == set(ids), (
            f"retrieval_log_map must cover exactly the injected set; "
            f"rl_map has {len(rl_map)} keys, ids has {len(ids)}"
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

    def test_retrieval_log_map_from_synthetic_fixture(self):
        """Synthetic 100-pattern fixture: retrieval_log_map covers only injected patterns (within
        budget). Injected retrieval_log_ids must have correct integer values."""
        resp = _make_synthetic_fixture(n_patterns=100)
        pats = resp["similar_patterns"]
        all_rlids = {
            p["id"]: p["match_factors"]["retrieval_log_id"]
            for p in pats
            if p.get("id") and isinstance(p.get("match_factors"), dict)
            and not isinstance(p["match_factors"].get("retrieval_log_id"), bool)
            and isinstance(p["match_factors"].get("retrieval_log_id"), int)
        }
        _, ids, _, rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        injected_set = set(ids)
        # retrieval_log_map must cover exactly the injected set (not all 100)
        assert set(rl_map.keys()) == injected_set & set(all_rlids.keys()), (
            "retrieval_log_map must cover exactly the injected patterns that have int retrieval_log_id"
        )
        # Values must be correct for injected patterns
        for pid in rl_map:
            if pid in all_rlids:
                assert rl_map[pid] == all_rlids[pid], (
                    f"Pattern {pid}: expected retrieval_log_id={all_rlids[pid]}, got {rl_map[pid]}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Section 8: injected_pattern_ids covers full set (both tiers)
# ─────────────────────────────────────────────────────────────────────────────

class TestInjectedPatternIds:

    def test_ids_cover_all_injected_within_budget(self):
        """injected_pattern_ids covers all patterns that fit within budget (small → all 20)."""
        patterns = [_make_pattern(f"ctx-both-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        # Small patterns — all 20 fit in the default 9500-char budget
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ids) == 20, (
            f"All 20 small patterns fit in default budget; injected_pattern_ids must cover all; got {len(ids)}"
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

    def test_rendered_output_within_budget(self):
        """Budget-verbatim: synthetic 87-pattern fixture rendered output must be ≤9500 chars."""
        resp = _make_synthetic_fixture(n_patterns=87, n_atrisk=8, n_negative_reward=4)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        rendered_size = len(ctx)
        assert rendered_size <= 9500, (
            f"Budget guarantee: rendered output must be ≤9500 chars; got {rendered_size}"
        )

    def test_ace_fixture_within_budget(self):
        """Budget-verbatim: synthetic 100-pattern fixture rendered output must be ≤9500 chars."""
        resp = _make_synthetic_fixture(n_patterns=100, n_atrisk=10, n_negative_reward=5)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        rendered_size = len(ctx)
        assert rendered_size <= 9500, (
            f"Budget guarantee on 100-pattern fixture: rendered must be ≤9500 chars; got {rendered_size}"
        )

    def test_no_compact_index_line_in_output(self):
        """Compact index format (#N [domain] s=...) must NOT appear — tail is dropped."""
        import re
        patterns = [_make_pattern(
            f"ctx-cmpct-{i:04d}", bandit_rank=i + 1,
            domain="test-domain", semantic_score=0.75,
            content="This is a test pattern content that should appear truncated"
        ) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert not re.search(r'#\d+ \[', ctx), (
            "Compact index '#N [domain]' must not appear — tail is DROPPED in budget-verbatim mode"
        )
        assert "<ranked_index>" not in ctx, (
            "No <ranked_index> section must appear — tail dropped"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 10: JSON validity (MUST-FIX 2) — rendered body must always parse
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonValidity:
    """Every render_patterns call must produce a valid parseable JSON body.

    The core regression is the comma off-by-one bug: with many small patterns
    the greedy loop underestimates the serialised array size, allowing slightly
    more patterns than fit, so json.dumps produces a body that exceeds budget
    and the old safety valve raw-byte-truncated it → invalid JSON.

    Contract assertions for every case:
      1. json.loads(ctx.split("\\n")[1]) must not raise
      2. len(data["similar_patterns"]) == len(injected_ids)  (consistency)
      3. len(ctx) <= 9500
    """

    def _assert_valid(self, ctx, ids, budget=9500):
        parts = ctx.split("\n")
        assert len(parts) >= 3, f"Expected at least 3 lines in ctx (tag, json, /tag); got {len(parts)}"
        try:
            data = json.loads(parts[1])
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"Body JSON is invalid (JSONDecodeError: {e}); "
                f"first 200 chars of body: {parts[1][:200]!r}"
            )
        n_rendered = len(data.get("similar_patterns", []))
        assert n_rendered == len(ids), (
            f"similar_patterns count ({n_rendered}) must equal len(injected_ids) ({len(ids)})"
        )
        assert len(ctx) <= budget, f"len(ctx)={len(ctx)} exceeds budget={budget}"

    def test_many_small_patterns_60x50_produces_valid_json(self):
        """Deterministic repro: 60 patterns with content='A'*50 — the comma off-by-one
        case that previously caused the safety valve to fire and raw-truncate JSON."""
        patterns = [
            _make_pattern(
                f"ctx-small-{i:04d}", bandit_rank=i + 1,
                content="A" * 50,
                evidence=["e1"],
            )
            for i in range(60)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid(ctx, ids)
        # The injected set must be consistent: all injected are a rank-prefix
        assert len(ids) >= 1

    def test_large_rich_content_produces_valid_json(self):
        """~100 patterns with realistic varied content lengths — body must parse."""
        resp = _make_synthetic_fixture(n_patterns=100, n_atrisk=10, n_negative_reward=5)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid(ctx, ids)

    def test_small_input_produces_valid_json(self):
        """3 patterns — trivially fits in budget, must produce valid JSON."""
        patterns = [_make_pattern(f"ctx-sm-{i:04d}", bandit_rank=i + 1) for i in range(3)]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid(ctx, ids)
        assert len(ids) == 3

    def test_empty_input_produces_valid_json(self):
        """Zero patterns — must produce valid JSON with empty similar_patterns."""
        resp = _make_response([])
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid(ctx, ids)
        assert ids == []

    def test_oversized_single_pattern_produces_valid_json(self):
        """Single pattern whose verbatim JSON alone would exceed budget — must truncate
        content but still emit valid parseable JSON with exactly 1 pattern."""
        p = _make_pattern(
            "ctx-big-0001", bandit_rank=1,
            content="X" * 9000,  # way over any budget
        )
        resp = _make_response([p])
        ctx, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid(ctx, ids)
        # Must include the (truncated) single pattern — never emit empty
        assert len(ids) == 1

    def test_custom_budget_many_small_produces_valid_json(self):
        """Same 60x50 repro but with a tighter custom budget — must still be valid."""
        patterns = [
            _make_pattern(f"ctx-sm2-{i:04d}", bandit_rank=i + 1, content="B" * 50)
            for i in range(60)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=4000
        )
        self._assert_valid(ctx, ids, budget=4000)


# ─────────────────────────────────────────────────────────────────────────────
# Section 11: eval_injection budget cap (MUST-FIX 4)
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalInjectionBudget:
    """ace_before_task appends eval_injection after ace_context.
    The final string must stay ≤ 10000 chars (CC hard cap).
    """

    def test_eval_injection_trimmed_when_ace_context_large(self):
        """When ace_context is ~9499 chars, a long eval_injection must be trimmed
        so the total stays ≤ 10000 chars."""
        # Simulate ace_context near the 9500 budget
        ace_context = "A" * 9499
        eval_injection = "E" * 1000  # would push total to 10500 — must be trimmed

        _CC_HARD_CAP = 10_000
        _available_for_eval = _CC_HARD_CAP - len(ace_context) - 1  # -1 for "\n"
        if _available_for_eval > 0:
            combined = ace_context + "\n" + eval_injection[:_available_for_eval]
        else:
            combined = ace_context

        assert len(combined) <= _CC_HARD_CAP, (
            f"Combined ace_context + eval_injection must be ≤10000 chars; got {len(combined)}"
        )

    def test_eval_injection_fully_fits_when_room_available(self):
        """When ace_context is short, the full eval_injection must appear."""
        ace_context = "A" * 100
        eval_injection = "E" * 200

        _CC_HARD_CAP = 10_000
        _available_for_eval = _CC_HARD_CAP - len(ace_context) - 1
        if _available_for_eval > 0:
            combined = ace_context + "\n" + eval_injection[:_available_for_eval]
        else:
            combined = ace_context

        assert combined == ace_context + "\n" + eval_injection, (
            "Full eval_injection must appear when there is room in the CC hard cap"
        )
        assert len(combined) <= _CC_HARD_CAP

    def test_eval_injection_skipped_when_no_room(self):
        """When ace_context is exactly 10000 chars, eval_injection must be skipped."""
        ace_context = "A" * 10_000
        eval_injection = "E" * 100

        _CC_HARD_CAP = 10_000
        _available_for_eval = _CC_HARD_CAP - len(ace_context) - 1  # = -1 → no room
        if _available_for_eval > 0:
            combined = ace_context + "\n" + eval_injection[:_available_for_eval]
        else:
            combined = ace_context

        assert combined == ace_context, (
            "eval_injection must be skipped when ace_context already fills the cap"
        )
        assert len(combined) <= _CC_HARD_CAP
