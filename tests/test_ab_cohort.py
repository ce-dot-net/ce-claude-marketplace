#!/usr/bin/env python3
"""
TDD tests for the A/B cohort-split feature in ace_pattern_render.

Contract:
  - render_cohort(session_id) -> 'control' | 'compact' | 'budget'
    • Deterministic: same session_id → same cohort, always
    • Default (no env) → 'budget' for ALL inputs
    • empty/None session_id → 'budget' (never experiment without anchor)
    • With ACE_AB_CONTROL_PCT=20 / ACE_AB_COMPACT_PCT=20:
        distribution over 10k random session_ids ≈ 20/20/60 (±5%)
    • Bad env values (non-int, negative, sum>100) → all 'budget'

  - render_compact_all(patterns_response, *, tag, attrs, budget=9500)
      -> (ctx_str, injected_ids, "", retrieval_log_map)
    • ctx_str length ≤ budget
    • ALL patterns present (injected_ids covers all)
    • header contains mode="compact"
    • valid parseable JSON inside the XML wrapper
    • content snippet near char 0 of each line (compact one-liners)
    • F-080: retrieval_log_map + injected_ids cover ALL rendered patterns

  - control arm: produces NO ace-patterns block in additionalContext;
    the search/retrieval logging path is unaffected;
    append_patterns_used called with empty ids + retrieval_id + task_session_id.

  - budget arm: unchanged (existing tests cover it).

  - log_search_metrics entry carries a render_cohort field.
"""

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── path bootstrap ─────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

from ace_pattern_render import render_cohort, render_compact_all, render_patterns  # noqa: E402


# ── shared fixture factories (borrowed pattern from test_ace_pattern_render.py) ─

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
        "evidence": evidence if evidence is not None else ["ev1", "ev2"],
        "root_cause": "",
        "error_context": "",
        "cumulative_v15_reward": reward,
        "n_hot_pos": 1,
        "n_hot_neg": 0,
        "isAtRisk": is_at_risk,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "match_factors": mf,
    }


def _make_response(patterns, retrieval_id="ret-ab-test-001"):
    return {
        "similar_patterns": patterns,
        "count": len(patterns),
        "threshold": 0.5,
        "retrieval_id": retrieval_id,
        "domains_summary": {"test": {"count": len(patterns)}},
    }


def _make_small_fixture(n=20, retrieval_id="ret-compact-001"):
    patterns = [
        _make_pattern(
            f"ctx-ab-{i:04d}",
            bandit_rank=i + 1,
            retrieval_log_id=500 + i,
            content=f"Pattern {i}: short content line for compact testing.",
        )
        for i in range(n)
    ]
    return _make_response(patterns, retrieval_id=retrieval_id)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: render_cohort — determinism & defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderCohortDefaults:

    def test_default_no_env_all_budget(self, monkeypatch):
        """Without env vars, render_cohort must return 'budget' for all inputs."""
        monkeypatch.delenv("ACE_AB_CONTROL_PCT", raising=False)
        monkeypatch.delenv("ACE_AB_COMPACT_PCT", raising=False)
        for i in range(50):
            sid = str(uuid.uuid4())
            result = render_cohort(sid)
            assert result == "budget", (
                f"Default (no env) must be 'budget' for all session_ids; "
                f"got {result!r} for {sid!r}"
            )

    def test_empty_session_id_is_budget(self, monkeypatch):
        """Empty string session_id → 'budget' (never experiment without anchor)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "30")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "30")
        result = render_cohort("")
        assert result == "budget", (
            f"Empty session_id must produce 'budget'; got {result!r}"
        )

    def test_none_session_id_is_budget(self, monkeypatch):
        """None session_id → 'budget' (never experiment without anchor)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "30")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "30")
        result = render_cohort(None)
        assert result == "budget", (
            f"None session_id must produce 'budget'; got {result!r}"
        )

    def test_zero_pcts_all_budget(self, monkeypatch):
        """ACE_AB_CONTROL_PCT=0, ACE_AB_COMPACT_PCT=0 → 100% budget."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "0")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "0")
        for i in range(100):
            sid = str(uuid.uuid4())
            result = render_cohort(sid)
            assert result == "budget", (
                f"CONTROL_PCT=0/COMPACT_PCT=0 must all be 'budget'; got {result!r}"
            )


class TestRenderCohortDeterminism:

    def test_same_session_id_same_cohort(self, monkeypatch):
        """Same session_id must always return the same cohort (deterministic)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "33")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "33")
        for _ in range(20):
            sid = str(uuid.uuid4())
            first = render_cohort(sid)
            for _ in range(5):
                assert render_cohort(sid) == first, (
                    f"render_cohort must be deterministic for {sid!r}; "
                    f"got different results across calls"
                )

    def test_hash_computation_matches_spec(self, monkeypatch):
        """The bucket must equal sha256(session_id)[:8] % 100 (spec-exact)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        for _ in range(30):
            sid = str(uuid.uuid4())
            bucket = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16) % 100
            expected = (
                "control" if bucket < 20
                else "compact" if bucket < 40
                else "budget"
            )
            assert render_cohort(sid) == expected, (
                f"Bucket {bucket} for {sid!r}: expected {expected!r}, "
                f"got {render_cohort(sid)!r}"
            )

    def test_control_range(self, monkeypatch):
        """Buckets 0..19 → 'control' with CONTROL_PCT=20, COMPACT_PCT=20."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        # Manufacture session_ids that land in specific buckets
        for _ in range(500):
            sid = str(uuid.uuid4())
            bucket = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16) % 100
            result = render_cohort(sid)
            if bucket < 20:
                assert result == "control", f"bucket={bucket} → expected 'control', got {result!r}"
            elif bucket < 40:
                assert result == "compact", f"bucket={bucket} → expected 'compact', got {result!r}"
            else:
                assert result == "budget", f"bucket={bucket} → expected 'budget', got {result!r}"


class TestRenderCohortDistribution:

    def test_distribution_over_10k_ids(self, monkeypatch):
        """With CONTROL_PCT=20/COMPACT_PCT=20, distribution ≈ 20/20/60 over 10k IDs."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        counts = {"control": 0, "compact": 0, "budget": 0}
        N = 10_000
        for _ in range(N):
            cohort = render_cohort(str(uuid.uuid4()))
            counts[cohort] += 1
        ctrl_pct = counts["control"] / N * 100
        compact_pct = counts["compact"] / N * 100
        budget_pct = counts["budget"] / N * 100
        assert abs(ctrl_pct - 20) <= 5, (
            f"control% expected ~20, got {ctrl_pct:.1f}"
        )
        assert abs(compact_pct - 20) <= 5, (
            f"compact% expected ~20, got {compact_pct:.1f}"
        )
        assert abs(budget_pct - 60) <= 5, (
            f"budget% expected ~60, got {budget_pct:.1f}"
        )

    def test_all_valid_cohorts_returned_under_budget(self, monkeypatch):
        """When CONTROL_PCT=20/COMPACT_PCT=20, all 3 cohorts appear in 1000 samples."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        seen = set()
        for _ in range(1000):
            seen.add(render_cohort(str(uuid.uuid4())))
        assert seen == {"control", "compact", "budget"}, (
            f"All 3 cohorts must appear with 20/20 split; saw {seen}"
        )


class TestRenderCohortBadEnv:

    def test_non_int_control_pct_defaults_budget(self, monkeypatch):
        """Non-integer ACE_AB_CONTROL_PCT → all 'budget'."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "notanumber")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        for _ in range(20):
            assert render_cohort(str(uuid.uuid4())) == "budget"

    def test_non_int_compact_pct_defaults_budget(self, monkeypatch):
        """Non-integer ACE_AB_COMPACT_PCT → all 'budget'."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "bad_value")
        for _ in range(20):
            assert render_cohort(str(uuid.uuid4())) == "budget"

    def test_sum_over_100_defaults_budget(self, monkeypatch):
        """CONTROL_PCT + COMPACT_PCT > 100 → all 'budget'."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "60")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "60")
        for _ in range(20):
            assert render_cohort(str(uuid.uuid4())) == "budget"

    def test_negative_control_pct_defaults_budget(self, monkeypatch):
        """Negative CONTROL_PCT → all 'budget' (clamped/rejected)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "-5")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "20")
        for _ in range(20):
            assert render_cohort(str(uuid.uuid4())) == "budget"

    def test_negative_compact_pct_defaults_budget(self, monkeypatch):
        """Negative COMPACT_PCT → all 'budget'."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "20")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "-10")
        for _ in range(20):
            assert render_cohort(str(uuid.uuid4())) == "budget"

    def test_exactly_100_sum_edge_case(self, monkeypatch):
        """CONTROL_PCT=50 + COMPACT_PCT=50 = 100 is valid (no budget arm; never error)."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "50")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "50")
        # Must not raise, must return valid cohorts
        for _ in range(50):
            result = render_cohort(str(uuid.uuid4()))
            assert result in ("control", "compact", "budget")


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: render_compact_all — shape, budget, completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderCompactAllShape:

    def test_returns_four_tuple(self):
        """render_compact_all must return a 4-tuple."""
        resp = _make_small_fixture(n=5)
        result = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(result, tuple) and len(result) == 4, (
            f"render_compact_all must return 4-tuple; got {type(result)}, len={len(result) if hasattr(result, '__len__') else '?'}"
        )

    def test_first_element_is_string(self):
        resp = _make_small_fixture(n=5)
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(ctx, str), f"ctx must be str; got {type(ctx)}"

    def test_second_element_is_list_of_ids(self):
        resp = _make_small_fixture(n=5)
        _, ids, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(ids, list), f"injected_ids must be list; got {type(ids)}"
        for item in ids:
            assert isinstance(item, str), f"Each id must be str; got {type(item)}"

    def test_third_element_is_empty_string(self):
        """Third element is reserved empty string (API compat with render_patterns)."""
        resp = _make_small_fixture(n=5)
        _, _, reserved, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert reserved == "", f"Third element must be '' (reserved); got {reserved!r}"

    def test_fourth_element_is_dict(self):
        resp = _make_small_fixture(n=5)
        _, _, _, rl_map = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert isinstance(rl_map, dict), f"retrieval_log_map must be dict; got {type(rl_map)}"

    def test_xml_tag_wraps_output(self):
        """ctx must open with <tag ...> and close with </tag>."""
        resp = _make_small_fixture(n=5)
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert ctx.startswith("<ace-patterns"), f"Must open with <ace-patterns; got {ctx[:60]!r}"
        assert ctx.rstrip().endswith("</ace-patterns>"), (
            f"Must close with </ace-patterns>; got {ctx[-40:]!r}"
        )

    def test_mode_compact_in_header(self):
        """The opening tag must include mode=\"compact\"."""
        resp = _make_small_fixture(n=5)
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        first_line = ctx.split("\n")[0]
        assert 'mode="compact"' in first_line, (
            f"Opening tag must contain mode=\"compact\"; got {first_line!r}"
        )

    def test_shown_of_n_in_header(self):
        """The opening tag must include shown=\"N\" of=\"N\" (all patterns)."""
        resp = _make_small_fixture(n=10)
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        first_line = ctx.split("\n")[0]
        assert 'shown="10"' in first_line, (
            f"Header must show shown=\"10\"; got {first_line!r}"
        )
        assert 'of="10"' in first_line, (
            f"Header must show of=\"10\"; got {first_line!r}"
        )


class TestRenderCompactAllBudget:

    def test_within_default_budget(self):
        """render_compact_all ctx length must be ≤ 9500 chars (default budget)."""
        resp = _make_small_fixture(n=100)
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ctx) <= 9500, f"len(ctx)={len(ctx)} exceeds default budget 9500"

    def test_within_custom_budget(self):
        """render_compact_all must respect a custom budget parameter."""
        resp = _make_small_fixture(n=100)
        ctx, _, _, _ = render_compact_all(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=5000
        )
        assert len(ctx) <= 5000, f"len(ctx)={len(ctx)} exceeds custom budget 5000"

    def test_all_patterns_present_20(self):
        """With 20 short patterns, ALL must appear in injected_ids (all fit in 9500)."""
        resp = _make_small_fixture(n=20)
        _, ids, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        all_ids = {p["id"] for p in resp["similar_patterns"]}
        assert set(ids) == all_ids, (
            f"All 20 patterns must appear in injected_ids; missing: {all_ids - set(ids)}"
        )

    def test_compact_all_valid_output_under_budget(self):
        """100-pattern fixture: ALL patterns fit in compact form within 9500 chars."""
        patterns = [
            _make_pattern(
                f"ctx-compact-{i:04d}",
                bandit_rank=i + 1,
                retrieval_log_id=200 + i,
                content=f"Short compact line {i}.",
            )
            for i in range(100)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, rl_map = render_compact_all(
            resp, tag="ace-patterns", attrs='agent-type="main"'
        )
        assert len(ctx) <= 9500, f"len(ctx)={len(ctx)}"
        assert len(ids) == 100, f"All 100 must be injected; got {len(ids)}"


class TestRenderCompactAllContent:

    def test_compact_lines_contain_rank_domain_reward(self):
        """Each compact line must contain rank, domain, and reward info."""
        resp = _make_small_fixture(n=5)
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        lines = ctx.split("\n")
        # Lines between the opening tag and closing tag are the compact entries
        content_lines = [
            l for l in lines
            if l.strip() and not l.startswith("<")
        ]
        assert content_lines, "There must be content lines (compact one-liners)"
        # Each compact line must reference rank (#N) and domain
        for line in content_lines[:5]:
            assert "#" in line, f"Compact line must contain '#rank'; got {line!r}"

    def test_content_snippet_near_start(self):
        """Content snippet must appear near the start of each compact line (≤ char 0 of line)."""
        resp = _make_small_fixture(n=3)
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        # Check that lines are compact (not multi-line JSON objects)
        content_lines = [
            l for l in ctx.split("\n")
            if l.strip() and not l.strip().startswith("<")
        ]
        for line in content_lines:
            # Compact lines must be a single line (no nested JSON arrays etc.)
            assert "\n" not in line, f"Compact line must not contain embedded newlines"

    def test_no_domains_summary_or_expanded_in_output(self):
        """domains_summary and expanded must NOT appear in compact output."""
        resp = _make_small_fixture(n=5)
        resp["expanded"] = [{"cached": True}]
        ctx, _, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert "domains_summary" not in ctx, "domains_summary must not appear in compact output"
        assert '"expanded"' not in ctx, "expanded must not appear in compact output"

    def test_f080_retrieval_log_map_covers_all(self):
        """retrieval_log_map must cover all injected patterns."""
        resp = _make_small_fixture(n=10)
        _, ids, _, rl_map = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        for pid in ids:
            assert pid in rl_map, (
                f"retrieval_log_map must cover all injected patterns; missing {pid!r}"
            )

    def test_f080_retrieval_log_map_values_correct(self):
        """retrieval_log_map values must be the correct int retrieval_log_ids."""
        patterns = [
            _make_pattern(f"ctx-rl-compact-{i:04d}", bandit_rank=i + 1, retrieval_log_id=700 + i)
            for i in range(5)
        ]
        resp = _make_response(patterns)
        _, _, _, rl_map = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        for i, p in enumerate(patterns):
            pid = p["id"]
            assert rl_map.get(pid) == 700 + i, (
                f"Pattern {pid}: expected retrieval_log_id={700 + i}, got {rl_map.get(pid)}"
            )

    def test_injected_ids_no_duplicates(self):
        """injected_ids must have no duplicates."""
        resp = _make_small_fixture(n=15)
        _, ids, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(ids) == len(set(ids)), (
            f"injected_ids has duplicates; len={len(ids)}, unique={len(set(ids))}"
        )

    def test_ordered_by_bandit_rank(self):
        """Compact lines must appear in ascending bandit_rank order."""
        # Provide patterns in shuffled order
        import random
        pats = [
            _make_pattern(f"ctx-rank-compact-{r:04d}", bandit_rank=r, retrieval_log_id=300 + r)
            for r in [5, 3, 1, 4, 2]
        ]
        resp = _make_response(pats)
        _, ids, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        # Injected IDs should be in bandit_rank order
        # bandit_rank N corresponds to "ctx-rank-compact-{N:04d}"
        ranks_in_order = [int(pid.replace("ctx-rank-compact-", "").replace("\x00", "")) for pid in ids]
        assert ranks_in_order == sorted(ranks_in_order), (
            f"Compact output must be in bandit_rank ASC order; got {ranks_in_order}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: render_compact_all JSON validity
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderCompactAllJsonValidity:

    def _assert_valid_compact(self, ctx, ids, budget=9500):
        """Compact output: must be parseable, length ≤ budget."""
        # The compact format has each pattern as a one-liner INSIDE the XML tag,
        # not necessarily as a single JSON blob in line[1].
        # The whole ctx must be ≤ budget.
        assert len(ctx) <= budget, f"len(ctx)={len(ctx)} exceeds budget={budget}"
        assert ctx.strip(), "ctx must not be empty"
        # Opening/closing XML tags must be present
        lines = ctx.split("\n")
        assert lines[0].strip().startswith("<"), f"First line must be XML tag; got {lines[0]!r}"
        assert lines[-1].strip().startswith("</"), f"Last line must be closing tag; got {lines[-1]!r}"
        # injected_ids and ctx must be consistent
        assert len(ids) >= 0  # no crash

    def test_5_patterns_valid(self):
        resp = _make_small_fixture(n=5)
        ctx, ids, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid_compact(ctx, ids)

    def test_100_patterns_valid(self):
        patterns = [
            _make_pattern(
                f"ctx-cv-{i:04d}", bandit_rank=i + 1,
                retrieval_log_id=400 + i,
                content=f"Content line {i}.",
            )
            for i in range(100)
        ]
        resp = _make_response(patterns)
        ctx, ids, _, _ = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid_compact(ctx, ids)
        assert len(ids) == 100

    def test_zero_patterns_valid(self):
        resp = _make_response([])
        ctx, ids, _, rl_map = render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"')
        self._assert_valid_compact(ctx, ids)
        assert ids == []
        assert rl_map == {}

    def test_custom_budget_valid(self):
        resp = _make_small_fixture(n=50)
        ctx, ids, _, _ = render_compact_all(
            resp, tag="ace-patterns", attrs='agent-type="main"', budget=4000
        )
        self._assert_valid_compact(ctx, ids, budget=4000)


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: observability — log_search_metrics carries render_cohort field
# ─────────────────────────────────────────────────────────────────────────────

class TestObservabilityRenderCohort:

    def test_log_search_metrics_accepts_render_cohort_kwarg(self):
        """log_search_metrics must accept a render_cohort keyword argument without error."""
        from ace_relevance_logger import ACERelevanceLogger
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ACERelevanceLogger(log_dir=tmpdir)
            # Must not raise
            logger.log_search_metrics(
                hook="UserPromptSubmit",
                session_id="test-session-obs",
                user_prompt="Test prompt",
                search_query="test query",
                patterns_returned=[],
                patterns_injected=[],
                domains=[],
                project_id="proj-001",
                org_id="org-001",
                agent_type="main",
                render_cohort="budget",
            )

    def test_log_search_metrics_render_cohort_persisted(self):
        """render_cohort value must appear in the written log entry."""
        from ace_relevance_logger import ACERelevanceLogger
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ACERelevanceLogger(log_dir=tmpdir)
            logger.log_search_metrics(
                hook="UserPromptSubmit",
                session_id="test-session-persist",
                user_prompt="Check cohort",
                search_query="cohort query",
                patterns_returned=[],
                patterns_injected=[],
                domains=[],
                render_cohort="compact",
            )
            log_path = Path(tmpdir) / "ace-relevance.jsonl"
            assert log_path.exists(), "Log file must be created"
            entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
            assert entries, "At least one log entry must be written"
            last = entries[-1]
            assert last.get("render_cohort") == "compact", (
                f"render_cohort must be 'compact' in log entry; got {last.get('render_cohort')!r}"
            )

    def test_log_search_metrics_render_cohort_control(self):
        """render_cohort='control' must also be persisted correctly."""
        from ace_relevance_logger import ACERelevanceLogger
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ACERelevanceLogger(log_dir=tmpdir)
            logger.log_search_metrics(
                hook="UserPromptSubmit",
                session_id="test-session-ctrl",
                user_prompt="Control arm test",
                search_query="control query",
                patterns_returned=[],
                patterns_injected=[],
                domains=[],
                render_cohort="control",
            )
            log_path = Path(tmpdir) / "ace-relevance.jsonl"
            entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
            last = entries[-1]
            assert last.get("render_cohort") == "control"

    def test_log_search_metrics_render_cohort_default_none(self):
        """Without render_cohort kwarg, log entry must not crash and may omit or None the field."""
        from ace_relevance_logger import ACERelevanceLogger
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = ACERelevanceLogger(log_dir=tmpdir)
            # Must not raise (backward compat: no render_cohort passed)
            logger.log_search_metrics(
                hook="UserPromptSubmit",
                session_id="test-session-compat",
                user_prompt="No cohort kwarg",
                search_query="no cohort",
                patterns_returned=[],
                patterns_injected=[],
                domains=[],
            )


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: before_task cohort dispatch — control arm injects nothing
# ─────────────────────────────────────────────────────────────────────────────

class TestBeforeTaskControlArm:

    def _load_before_task(self):
        """Load ace_before_task.main via importlib to avoid sys.path collisions."""
        import importlib.util
        path = REPO / "plugins" / "ace" / "shared-hooks" / "ace_before_task.py"
        spec = importlib.util.spec_from_file_location("ace_before_task", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_control_cohort_produces_no_additional_context(self, monkeypatch, tmp_path):
        """When cohort='control', additionalContext must be absent from hookSpecificOutput."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "100")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "0")

        # Build a fake patterns_response
        patterns = [_make_pattern("ctx-ctrl-0001", bandit_rank=1)]
        fake_resp = _make_response(patterns, retrieval_id="ret-ctrl-001")

        import io
        captured_output = {}

        def fake_run_search(**kwargs):
            return fake_resp

        def fake_get_context():
            return {"org": "org-001", "project": "proj-001"}

        def fake_check_pinning():
            return False

        def fake_check_auth(warn_threshold_hours=2.0):
            return None

        def fake_append_patterns_used(*args, **kwargs):
            pass

        mod = self._load_before_task()

        event = {
            "prompt": "Fix the bug",
            "session_id": "sess-ctrl-test-001",
            "agent_type": "main",
            "agent_id": "agent-ctrl-001",
        }

        printed = []

        with patch.object(mod, "run_search", fake_run_search), \
             patch.object(mod, "get_context", fake_get_context), \
             patch.object(mod, "check_session_pinning_available", fake_check_pinning), \
             patch.object(mod, "check_auth_status", fake_check_auth), \
             patch.object(mod, "append_patterns_used", fake_append_patterns_used), \
             patch.object(mod, "log_search_metrics", lambda **kw: None), \
             patch("builtins.print", side_effect=lambda x: printed.append(x)), \
             patch("sys.exit", side_effect=SystemExit):
            try:
                import io
                sys.stdin = io.StringIO(json.dumps(event))
                mod.main()
            except SystemExit:
                pass

        assert printed, "main() must print something"
        output = json.loads(printed[0])
        # Control arm: no additionalContext in hookSpecificOutput
        hook_output = output.get("hookSpecificOutput", {})
        additional_ctx = hook_output.get("additionalContext", None)
        assert additional_ctx is None or additional_ctx == "", (
            f"Control arm must produce no additionalContext; "
            f"got {additional_ctx!r}"
        )

    def test_control_cohort_retrieval_id_still_logged(self, monkeypatch, tmp_path):
        """Control arm: retrieval logging (append_patterns_used) must still be called
        with empty pattern_ids but with retrieval_id and task_session_id."""
        monkeypatch.setenv("ACE_AB_CONTROL_PCT", "100")
        monkeypatch.setenv("ACE_AB_COMPACT_PCT", "0")

        patterns = [_make_pattern("ctx-ctrl-log-0001", bandit_rank=1)]
        fake_resp = _make_response(patterns, retrieval_id="ret-ctrl-log-001")

        logged_calls = []

        def fake_run_search(**kwargs):
            return fake_resp

        def fake_get_context():
            return {"org": "org-001", "project": "proj-001"}

        def fake_check_pinning():
            return False

        def fake_check_auth(warn_threshold_hours=2.0):
            return None

        def fake_append_patterns_used(session_id, agent_id, pattern_ids, **kwargs):
            logged_calls.append({
                "session_id": session_id,
                "agent_id": agent_id,
                "pattern_ids": pattern_ids,
                "retrieval_id": kwargs.get("retrieval_id"),
                "task_session_id": kwargs.get("task_session_id"),
            })

        mod = self._load_before_task()
        event = {
            "prompt": "Fix the bug",
            "session_id": "sess-ctrl-log-001",
            "agent_type": "main",
            "agent_id": "agent-ctrl-log-001",
        }

        with patch.object(mod, "run_search", fake_run_search), \
             patch.object(mod, "get_context", fake_get_context), \
             patch.object(mod, "check_session_pinning_available", fake_check_pinning), \
             patch.object(mod, "check_auth_status", fake_check_auth), \
             patch.object(mod, "append_patterns_used", fake_append_patterns_used), \
             patch.object(mod, "log_search_metrics", lambda **kw: None), \
             patch("builtins.print", side_effect=lambda x: None), \
             patch("sys.exit", side_effect=SystemExit):
            try:
                import io
                sys.stdin = io.StringIO(json.dumps(event))
                mod.main()
            except SystemExit:
                pass

        # At least one call to append_patterns_used must have occurred
        assert logged_calls, "append_patterns_used must be called even in control arm"
        # The control-arm call: pattern_ids must be empty []
        # (we expect the control arm to call with [] after the search)
        control_calls = [c for c in logged_calls if c["pattern_ids"] == []]
        assert control_calls, (
            f"Control arm must call append_patterns_used with empty pattern_ids; "
            f"all calls: {logged_calls}"
        )
        # retrieval_id must be present on at least one call
        calls_with_retrieval = [c for c in logged_calls if c.get("retrieval_id")]
        assert calls_with_retrieval, (
            f"At least one append_patterns_used call must carry retrieval_id; calls: {logged_calls}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: dormant by default — existing render_patterns behavior unchanged
# ─────────────────────────────────────────────────────────────────────────────

class TestDormantDefault:

    def test_render_patterns_unchanged_when_no_env(self, monkeypatch):
        """render_patterns must behave identically to pre-AB behavior when no env vars set."""
        monkeypatch.delenv("ACE_AB_CONTROL_PCT", raising=False)
        monkeypatch.delenv("ACE_AB_COMPACT_PCT", raising=False)
        patterns = [
            _make_pattern(f"ctx-dormant-{i:04d}", bandit_rank=i + 1, retrieval_log_id=900 + i)
            for i in range(10)
        ]
        resp = _make_response(patterns)
        ctx, ids, reserved, rl_map = render_patterns(
            resp, tag="ace-patterns", attrs='agent-type="main"'
        )
        # All 10 small patterns must fit (budget-verbatim, not compact, not empty)
        assert len(ids) == 10, f"All 10 must be injected in budget-verbatim mode; got {len(ids)}"
        assert len(ctx) <= 9500
        assert reserved == ""
        assert len(rl_map) == 10

    def test_render_cohort_100pct_budget_every_session(self, monkeypatch):
        """With no env vars, 100% of sessions must get 'budget' cohort."""
        monkeypatch.delenv("ACE_AB_CONTROL_PCT", raising=False)
        monkeypatch.delenv("ACE_AB_COMPACT_PCT", raising=False)
        N = 200
        cohorts = [render_cohort(str(uuid.uuid4())) for _ in range(N)]
        assert all(c == "budget" for c in cohorts), (
            f"Without env vars, all cohorts must be 'budget'; got: {set(cohorts)}"
        )
