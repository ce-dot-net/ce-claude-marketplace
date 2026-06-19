#!/usr/bin/env python3
"""
TDD RED tests for the remediation of ace_pattern_render + patterns_used_state.

Tests cover:
  MUST-FIX 1: render_patterns_dict() exists + strip_and_gate uses it directly
  MUST-FIX 2: count == len(processed) (full injected set, not just head)
  NICE-TO-HAVE 3: _strip_patterns / _extract_retrieval_ids removed from ace_subagent_start
  NICE-TO-HAVE 4: bandit_rank omitted when None (not set to None); sort still works

All tests are RED until the implementation is complete.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ── path bootstrap ─────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))
sys.path.insert(0, str(SHARED))


# ── shared fixture helpers (same style as test_ace_pattern_render.py) ─────────

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
        "match_factors": mf,
        "expanded": [{"cached": True}],
        "observations": 10.0,
        "source": "local",
        "n_warm_pos": 1,
        "n_warm_neg": 0,
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
# Section A: render_patterns_dict — exists and returns correct tuple type
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderPatternsDictExists:

    def test_importable(self):
        """render_patterns_dict must be importable from ace_pattern_render."""
        from ace_pattern_render import render_patterns_dict  # noqa: F401

    def test_returns_3_tuple(self):
        """render_patterns_dict must return a 3-tuple."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        result = render_patterns_dict(resp, tier_k=15)
        assert isinstance(result, tuple) and len(result) == 3, (
            f"render_patterns_dict must return a 3-tuple; got {type(result)} len={getattr(result, '__len__', lambda: '?')()}"
        )

    def test_first_element_is_dict(self):
        """render_patterns_dict element 0 must be a dict (the output response dict)."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        out_dict, _, _ = render_patterns_dict(resp)
        assert isinstance(out_dict, dict), f"First element must be dict; got {type(out_dict)}"

    def test_second_element_is_list(self):
        """render_patterns_dict element 1 must be a list (injected_pattern_ids)."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        _, ids, _ = render_patterns_dict(resp)
        assert isinstance(ids, list), f"Second element must be list; got {type(ids)}"

    def test_third_element_is_dict(self):
        """render_patterns_dict element 2 must be a dict (retrieval_log_map)."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        _, _, rl_map = render_patterns_dict(resp)
        assert isinstance(rl_map, dict), f"Third element must be dict; got {type(rl_map)}"


# ─────────────────────────────────────────────────────────────────────────────
# Section B: render_patterns_dict — correct dict output (hoisted, sorted, no-gate)
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderPatternsDictOutput:

    def test_similar_patterns_present_in_output_dict(self):
        """output_response_dict must have 'similar_patterns' key."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        out_dict, _, _ = render_patterns_dict(resp)
        assert "similar_patterns" in out_dict, "output dict must have similar_patterns key"

    def test_similar_patterns_not_tiered_all_present(self):
        """output_response_dict['similar_patterns'] must contain ALL processed patterns (not tiered)."""
        from ace_pattern_render import render_patterns_dict
        patterns = [_make_pattern(f"ctx-all-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        # tier_k=5 — but dict output is NOT tiered, all 20 must be present
        out_dict, _, _ = render_patterns_dict(resp, tier_k=5)
        out_pats = out_dict.get("similar_patterns", [])
        assert len(out_pats) == 20, (
            f"render_patterns_dict similar_patterns must be ALL processed (not tiered); "
            f"tier_k=5 but got {len(out_pats)}"
        )

    def test_expanded_dropped_from_output_dict(self):
        """expanded must NOT appear in the output dict."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)], with_expanded=True)
        out_dict, _, _ = render_patterns_dict(resp)
        assert "expanded" not in out_dict, "expanded must be dropped from render_patterns_dict output"

    def test_match_factors_stripped_from_patterns(self):
        """match_factors must be stripped from each pattern in the output dict."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        out_dict, _, _ = render_patterns_dict(resp)
        for p in out_dict.get("similar_patterns", []):
            assert "match_factors" not in p, f"match_factors must be stripped; found in {p.get('id')}"

    def test_bandit_rank_hoisted_in_output_dict(self):
        """bandit_rank must be hoisted to top-level in patterns inside the dict."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=7)])
        out_dict, _, _ = render_patterns_dict(resp)
        pats = out_dict.get("similar_patterns", [])
        assert pats, "no patterns in output"
        p = pats[0]
        assert p.get("bandit_rank") == 7, f"bandit_rank must be hoisted; got {p.get('bandit_rank')}"

    def test_sorted_by_bandit_rank_in_output_dict(self):
        """similar_patterns in output dict must be sorted by bandit_rank ASC."""
        from ace_pattern_render import render_patterns_dict
        patterns = [
            _make_pattern("ctx-rank5-aaaa", bandit_rank=5),
            _make_pattern("ctx-rank1-aaaa", bandit_rank=1),
            _make_pattern("ctx-rank3-aaaa", bandit_rank=3),
        ]
        resp = _make_response(patterns)
        out_dict, _, _ = render_patterns_dict(resp)
        ranks = [p.get("bandit_rank") for p in out_dict.get("similar_patterns", []) if p.get("bandit_rank") is not None]
        assert ranks == sorted(ranks), f"similar_patterns must be sorted by bandit_rank ASC; got {ranks}"

    def test_at_risk_retained_in_output_dict(self):
        """isAtRisk=True patterns must be retained (no gate)."""
        from ace_pattern_render import render_patterns_dict
        patterns = [
            _make_pattern("ctx-good-0001", bandit_rank=1, is_at_risk=False),
            _make_pattern("ctx-atrisk-0002", bandit_rank=2, is_at_risk=True, reward=-1.5),
        ]
        resp = _make_response(patterns)
        out_dict, ids, _ = render_patterns_dict(resp)
        all_ids_in_dict = {p.get("id") for p in out_dict.get("similar_patterns", [])}
        assert "ctx-atrisk-0002" in all_ids_in_dict, "at-risk pattern must be retained in dict output"
        assert "ctx-atrisk-0002" in ids, "at-risk pattern must be in injected_pattern_ids"

    def test_retrieval_log_map_covers_full_set(self):
        """retrieval_log_map must cover ALL patterns (not just head tier)."""
        from ace_pattern_render import render_patterns_dict
        patterns = [
            _make_pattern(f"ctx-f080-{i:04d}", bandit_rank=i + 1, retrieval_log_id=100 + i)
            for i in range(20)
        ]
        resp = _make_response(patterns)
        # tier_k=5, but retrieval_log_map covers all 20
        _, _, rl_map = render_patterns_dict(resp, tier_k=5)
        for i in range(20):
            pid = f"ctx-f080-{i:04d}"
            assert pid in rl_map, f"retrieval_log_map must cover full set; missing {pid}"

    def test_injected_pattern_ids_covers_full_set(self):
        """injected_pattern_ids must cover ALL patterns (not just head tier)."""
        from ace_pattern_render import render_patterns_dict
        patterns = [_make_pattern(f"ctx-all-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        _, ids, _ = render_patterns_dict(resp, tier_k=5)
        assert len(ids) == 20, (
            f"injected_pattern_ids must cover all 20 patterns; got {len(ids)}"
        )

    def test_top_level_fields_preserved_in_output_dict(self):
        """retrieval_id and other top-level fields must be preserved in the output dict."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)], retrieval_id="ret-xyz-789")
        out_dict, _, _ = render_patterns_dict(resp)
        assert out_dict.get("retrieval_id") == "ret-xyz-789", (
            f"retrieval_id must be preserved in output dict; got {out_dict.get('retrieval_id')}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section C: MUST-FIX 2 — count == len(processed) (full injected set)
# ─────────────────────────────────────────────────────────────────────────────

class TestCountEqualsFullProcessed:

    def test_count_equals_len_processed_in_dict(self):
        """render_patterns_dict: count must equal len(processed) — the FULL set, not just head."""
        from ace_pattern_render import render_patterns_dict
        patterns = [_make_pattern(f"ctx-cnt-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        # tier_k=5; count must be 20, not 5
        out_dict, _, _ = render_patterns_dict(resp, tier_k=5)
        assert out_dict.get("count") == 20, (
            f"count must be len(processed)=20 (full set), not just head tier=5; "
            f"got {out_dict.get('count')}"
        )

    def test_count_equals_len_processed_string_render(self):
        """render_patterns (string): count in the JSON blob must equal len(processed)."""
        from ace_pattern_render import render_patterns
        patterns = [_make_pattern(f"ctx-cnt-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        # tier_k=5; count in the verbatim JSON must be 20, not 5
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        lines = ctx.split("\n")
        assert len(lines) >= 2, "output must have at least 2 lines"
        data = json.loads(lines[1])
        assert data.get("count") == 20, (
            f"count in rendered JSON must be len(processed)=20 (full set), not 5; "
            f"got {data.get('count')}"
        )

    def test_count_with_tier_k_larger_than_set(self):
        """When tier_k >= len(patterns), count still equals len(processed)."""
        from ace_pattern_render import render_patterns_dict
        patterns = [_make_pattern(f"ctx-cnt-{i:04d}", bandit_rank=i + 1) for i in range(5)]
        resp = _make_response(patterns)
        out_dict, _, _ = render_patterns_dict(resp, tier_k=100)
        assert out_dict.get("count") == 5, (
            f"count must be 5 (all patterns processed); got {out_dict.get('count')}"
        )

    def test_count_empty_input(self):
        """Empty input: count must be 0."""
        from ace_pattern_render import render_patterns_dict
        resp = _make_response([])
        out_dict, _, _ = render_patterns_dict(resp)
        assert out_dict.get("count") == 0, f"count for empty input must be 0; got {out_dict.get('count')}"


# ─────────────────────────────────────────────────────────────────────────────
# Section D: MUST-FIX 1 — strip_and_gate no longer has string-split or fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestStripAndGateNoFallback:

    def test_strip_and_gate_returns_dict(self):
        """strip_and_gate must return a dict."""
        from patterns_used_state import strip_and_gate
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        result = strip_and_gate(resp)
        assert isinstance(result, dict), f"strip_and_gate must return dict; got {type(result)}"

    def test_strip_and_gate_match_factors_absent(self):
        """strip_and_gate output must not contain match_factors in any pattern."""
        from patterns_used_state import strip_and_gate
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        result = strip_and_gate(resp)
        for p in result.get("similar_patterns", []):
            assert "match_factors" not in p, (
                f"match_factors must be stripped by strip_and_gate; found in {p.get('id')}"
            )

    def test_strip_and_gate_expanded_absent(self):
        """strip_and_gate output must not contain 'expanded'."""
        from patterns_used_state import strip_and_gate
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)], with_expanded=True)
        result = strip_and_gate(resp)
        assert "expanded" not in result, "expanded must be absent from strip_and_gate output"

    def test_strip_and_gate_retains_at_risk(self):
        """strip_and_gate must retain at-risk patterns (no quality gate)."""
        from patterns_used_state import strip_and_gate
        patterns = [
            _make_pattern("ctx-good-0001", bandit_rank=1, is_at_risk=False),
            _make_pattern("ctx-atrisk-0002", bandit_rank=2, is_at_risk=True, reward=-1.5),
        ]
        resp = _make_response(patterns)
        result = strip_and_gate(resp)
        ids_in_result = {p.get("id") for p in result.get("similar_patterns", [])}
        assert "ctx-atrisk-0002" in ids_in_result, (
            "strip_and_gate must retain at-risk patterns (no gate)"
        )

    def test_strip_and_gate_count_correct(self):
        """strip_and_gate output 'count' must reflect the full rendered pattern count."""
        from patterns_used_state import strip_and_gate
        patterns = [_make_pattern(f"ctx-sg-{i:04d}", bandit_rank=i + 1) for i in range(8)]
        resp = _make_response(patterns)
        result = strip_and_gate(resp)
        assert result.get("count") == 8, (
            f"strip_and_gate count must be 8 (full set); got {result.get('count')}"
        )

    def test_strip_and_gate_delegates_to_render_patterns_dict(self):
        """strip_and_gate must NOT contain json.loads or string.split logic.

        We verify this structurally: strip_and_gate should call render_patterns_dict
        and return its first element. We do this by checking the call path via
        source inspection — the string-split fallback must be absent.
        """
        import inspect
        from patterns_used_state import strip_and_gate
        src = inspect.getsource(strip_and_gate)
        assert "split(" not in src, (
            "strip_and_gate must not contain string split() — the string-split approach is the old buggy path"
        )
        assert "json.loads" not in src, (
            "strip_and_gate must not contain json.loads — the JSON parse-back approach is the old buggy path"
        )
        assert "dict(data)" not in src, (
            "strip_and_gate must not contain dict(data) fallback — silent raw payload return is the bug"
        )

    def test_strip_and_gate_calls_render_patterns_dict(self):
        """strip_and_gate must call render_patterns_dict (not render_patterns for extraction)."""
        import inspect
        from patterns_used_state import strip_and_gate
        src = inspect.getsource(strip_and_gate)
        assert "render_patterns_dict" in src, (
            "strip_and_gate must delegate to render_patterns_dict"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section E: DRY — render_patterns delegates to render_patterns_dict
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderPatternsDryDelegation:

    def test_render_patterns_calls_render_patterns_dict(self):
        """render_patterns (string version) must call render_patterns_dict internally (DRY)."""
        import inspect
        from ace_pattern_render import render_patterns
        src = inspect.getsource(render_patterns)
        assert "render_patterns_dict" in src, (
            "render_patterns must call render_patterns_dict to be DRY"
        )

    def test_render_patterns_and_dict_agree_on_processed_set(self):
        """render_patterns and render_patterns_dict must agree on which patterns are processed."""
        from ace_pattern_render import render_patterns, render_patterns_dict
        patterns = [
            _make_pattern(f"ctx-agree-{i:04d}", bandit_rank=i + 1, retrieval_log_id=200 + i)
            for i in range(20)
        ]
        resp = _make_response(patterns)

        ctx, str_ids, _, str_rl_map = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        dict_out, dict_ids, dict_rl_map = render_patterns_dict(resp, tier_k=5)

        # Both must agree on injected_pattern_ids
        assert set(str_ids) == set(dict_ids), (
            f"render_patterns and render_patterns_dict must agree on injected ids; "
            f"string={set(str_ids)}, dict={set(dict_ids)}"
        )
        # Both must agree on retrieval_log_map
        assert str_rl_map == dict_rl_map, (
            "render_patterns and render_patterns_dict must agree on retrieval_log_map"
        )

    def test_render_patterns_string_still_tiered(self):
        """render_patterns (string) must still produce verbatim head + compact tail tiering."""
        from ace_pattern_render import render_patterns
        patterns = [_make_pattern(f"ctx-tier-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        lines = ctx.split("\n")
        data = json.loads(lines[1])
        verbatim = data.get("similar_patterns", [])
        # verbatim section must still have only tier_k=5 patterns
        assert len(verbatim) == 5, (
            f"render_patterns string output: verbatim must still be tier_k=5; got {len(verbatim)}"
        )
        # compact index must be present for the tail 15
        assert "<ranked_index>" in ctx, "render_patterns string output must still have ranked_index for tail"

    def test_render_patterns_dict_all_in_similar_patterns(self):
        """render_patterns_dict: all processed patterns appear in similar_patterns (no tiering)."""
        from ace_pattern_render import render_patterns_dict
        patterns = [_make_pattern(f"ctx-notier-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        out_dict, _, _ = render_patterns_dict(resp, tier_k=5)
        # similar_patterns in the dict has ALL 20 (no compact tail)
        assert len(out_dict["similar_patterns"]) == 20, (
            "render_patterns_dict similar_patterns must be all 20 (not tiered); "
            f"got {len(out_dict['similar_patterns'])}"
        )
        assert "ranked_index" not in json.dumps(out_dict), (
            "render_patterns_dict output dict must not contain ranked_index (no tiering)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section F: NICE-TO-HAVE 3 — dead code removed from ace_subagent_start
# ─────────────────────────────────────────────────────────────────────────────

class TestDeadCodeRemoved:

    def _load_subagent_start_source(self):
        src_path = SHARED / "ace_subagent_start.py"
        return src_path.read_text()

    def test_strip_patterns_function_removed(self):
        """_strip_patterns must NOT be defined in ace_subagent_start.py."""
        src = self._load_subagent_start_source()
        assert "def _strip_patterns" not in src, (
            "_strip_patterns is unused dead code and must be removed from ace_subagent_start.py"
        )

    def test_extract_retrieval_ids_function_removed(self):
        """_extract_retrieval_ids must NOT be defined in ace_subagent_start.py."""
        src = self._load_subagent_start_source()
        assert "def _extract_retrieval_ids" not in src, (
            "_extract_retrieval_ids is unused dead code and must be removed from ace_subagent_start.py"
        )

    def test_useful_fields_constant_removed(self):
        """_USEFUL_FIELDS constant must NOT appear in ace_subagent_start.py (was only used by dead code)."""
        src = self._load_subagent_start_source()
        assert "_USEFUL_FIELDS" not in src, (
            "_USEFUL_FIELDS was only used by _strip_patterns; it must be removed with the dead code"
        )

    def test_subagent_start_still_importable(self):
        """ace_subagent_start must still be importable after dead code removal."""
        import importlib.util
        mod_path = SHARED / "ace_subagent_start.py"
        spec = importlib.util.spec_from_file_location("ace_subagent_start_deadcode_test", mod_path)
        mod = importlib.util.module_from_spec(spec)
        # Should not raise
        spec.loader.exec_module(mod)
        # render_patterns must still be imported
        assert hasattr(mod, "render_patterns"), (
            "render_patterns import must still be present in ace_subagent_start"
        )

    def test_subagent_start_has_no_strip_patterns_call(self):
        """_strip_patterns must not be called anywhere in ace_subagent_start.py."""
        src = self._load_subagent_start_source()
        assert "_strip_patterns(" not in src, "_strip_patterns must not be called"

    def test_subagent_start_has_no_extract_retrieval_ids_call(self):
        """_extract_retrieval_ids must not be called anywhere in ace_subagent_start.py."""
        src = self._load_subagent_start_source()
        assert "_extract_retrieval_ids(" not in src, "_extract_retrieval_ids must not be called"


# ─────────────────────────────────────────────────────────────────────────────
# Section G: NICE-TO-HAVE 4 — bandit_rank omitted when None (not set to None)
# ─────────────────────────────────────────────────────────────────────────────

class TestBanditRankOmittedWhenNone:

    def _get_patterns_from_ctx(self, ctx):
        lines = ctx.split("\n")
        return json.loads(lines[1]).get("similar_patterns", [])

    def test_bandit_rank_absent_when_none_in_string_render(self):
        """When bandit_rank is None, the key must be ABSENT from the rendered pattern (not set to null)."""
        from ace_pattern_render import render_patterns
        p = _make_pattern("ctx-norank-0001", bandit_rank=None)
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_patterns_from_ctx(ctx)
        assert pats, "no patterns in output"
        p_out = pats[0]
        assert "bandit_rank" not in p_out, (
            f"bandit_rank must be ABSENT (not null) when None; "
            f"got bandit_rank={p_out.get('bandit_rank')!r} keys={list(p_out.keys())}"
        )

    def test_bandit_rank_absent_when_none_in_dict(self):
        """render_patterns_dict: bandit_rank must be ABSENT when None."""
        from ace_pattern_render import render_patterns_dict
        p = _make_pattern("ctx-norank-dict-0001", bandit_rank=None)
        resp = _make_response([p])
        out_dict, _, _ = render_patterns_dict(resp)
        pats = out_dict.get("similar_patterns", [])
        assert pats, "no patterns in dict output"
        p_out = pats[0]
        assert "bandit_rank" not in p_out, (
            f"render_patterns_dict: bandit_rank must be ABSENT when None; got keys={list(p_out.keys())}"
        )

    def test_bandit_rank_present_when_ranked(self):
        """When bandit_rank has an integer value, it must be present in the output."""
        from ace_pattern_render import render_patterns
        p = _make_pattern("ctx-ranked-0001", bandit_rank=3)
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        pats = self._get_patterns_from_ctx(ctx)
        assert pats, "no patterns"
        assert pats[0].get("bandit_rank") == 3, (
            f"bandit_rank=3 must be present; got {pats[0].get('bandit_rank')}"
        )

    def test_none_bandit_rank_goes_to_tail_sort(self):
        """Patterns with absent bandit_rank must still be sorted to the tail after ranked ones."""
        from ace_pattern_render import render_patterns_dict
        patterns = [
            _make_pattern("ctx-ranked-0001", bandit_rank=1),
            _make_pattern("ctx-norank-0001", bandit_rank=None),
            _make_pattern("ctx-ranked-0002", bandit_rank=2),
        ]
        resp = _make_response(patterns)
        out_dict, _, _ = render_patterns_dict(resp)
        out_pats = out_dict.get("similar_patterns", [])
        ids_in_order = [p["id"] for p in out_pats]
        # Ranked must come before unranked
        ranked_pos = [i for i, p in enumerate(out_pats) if "bandit_rank" in p]
        unranked_pos = [i for i, p in enumerate(out_pats) if "bandit_rank" not in p]
        if ranked_pos and unranked_pos:
            assert max(ranked_pos) < min(unranked_pos), (
                f"Unranked (absent bandit_rank) must come after ranked; order: {ids_in_order}"
            )

    def test_compact_index_shows_hash_question_for_missing_rank(self):
        """Compact index for a None-rank pattern must render '#?' (not '#None')."""
        from ace_pattern_render import render_patterns
        patterns = [
            _make_pattern("ctx-ranked-0001", bandit_rank=1),
            _make_pattern("ctx-norank-tail-0001", bandit_rank=None),
        ]
        resp = _make_response(patterns)
        # tier_k=1 → ranked pattern is verbatim, unranked pattern goes to tail compact index
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=1)
        assert "#?" in ctx, (
            f"Compact index for None bandit_rank must render '#?'; ctx excerpt: {ctx[-200:]!r}"
        )
        assert "#None" not in ctx, (
            "Compact index must not render '#None' for absent bandit_rank"
        )

    def test_semantic_score_still_omitted_when_absent(self):
        """semantic_score must still be OMITTED when absent (same behavior as before)."""
        from ace_pattern_render import render_patterns
        p = _make_pattern("ctx-noscore-0001", bandit_rank=1, semantic_score=None)
        # Override match_factors to have no semantic_score
        p["match_factors"]["semantic_score"] = None
        resp = _make_response([p])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        lines = ctx.split("\n")
        data = json.loads(lines[1])
        pats = data.get("similar_patterns", [])
        assert pats, "no patterns"
        p_out = pats[0]
        # semantic_score must be absent when None (existing behavior preserved)
        assert "semantic_score" not in p_out, (
            f"semantic_score must be omitted when None; keys={list(p_out.keys())}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section H: Regression — existing render_patterns tests still hold
# ─────────────────────────────────────────────────────────────────────────────

class TestRegressionExistingBehavior:
    """Verify that after the refactor, existing render_patterns behavior is unchanged."""

    def _get_verbatim_from_ctx(self, ctx):
        lines = ctx.split("\n")
        return json.loads(lines[1]).get("similar_patterns", [])

    def test_xml_wrapping_unchanged(self):
        """render_patterns must still produce XML-wrapped output."""
        from ace_pattern_render import render_patterns
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert ctx.startswith("<ace-patterns "), "XML opening tag must be present"
        assert ctx.rstrip().endswith("</ace-patterns>"), "XML closing tag must be present"

    def test_4_tuple_return_unchanged(self):
        """render_patterns must still return a 4-tuple."""
        from ace_pattern_render import render_patterns
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        result = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert len(result) == 4, f"must be 4-tuple; got {len(result)}"

    def test_third_element_still_empty_string(self):
        """Element 2 of render_patterns 4-tuple must still be empty string (reserved)."""
        from ace_pattern_render import render_patterns
        resp = _make_response([_make_pattern("ctx-0001-aaaa", bandit_rank=1)])
        _, _, reserved, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"')
        assert reserved == "", f"Third element must be empty string; got {reserved!r}"

    def test_tiering_unchanged_verbatim_head_compact_tail(self):
        """render_patterns tiering must still work: top tier_k verbatim, rest compact."""
        from ace_pattern_render import render_patterns
        patterns = [_make_pattern(f"ctx-t-{i:04d}", bandit_rank=i + 1) for i in range(10)]
        resp = _make_response(patterns)
        ctx, _, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=3)
        verbatim = self._get_verbatim_from_ctx(ctx)
        assert len(verbatim) == 3, f"verbatim head must be tier_k=3; got {len(verbatim)}"
        assert "<ranked_index>" in ctx, "compact ranked_index must be present for tail"

    def test_all_ids_in_injected_ids_unchanged(self):
        """injected_pattern_ids must still cover all valid ids from both tiers."""
        from ace_pattern_render import render_patterns
        patterns = [_make_pattern(f"ctx-all-{i:04d}", bandit_rank=i + 1) for i in range(20)]
        resp = _make_response(patterns)
        _, ids, _, _ = render_patterns(resp, tag="ace-patterns", attrs='agent-type="main"', tier_k=5)
        assert len(ids) == 20, f"All 20 ids must be in injected_pattern_ids; got {len(ids)}"
