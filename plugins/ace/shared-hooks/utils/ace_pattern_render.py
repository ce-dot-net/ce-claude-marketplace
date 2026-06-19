#!/usr/bin/env python3
"""
ace_pattern_render — Central pure render helper for ACE pattern injection.

Server-team validated contract (ACE-1.5-native):
  - bandit_rank + semantic_score hoisted from match_factors to top-level
  - NO quality gate / NO drop: at-risk and reward<0 patterns RETAINED
  - Sort by bandit_rank ASC; missing/None bandit_rank → tail (stable)
  - Tier: top-K verbatim (all kept fields incl. evidence[:2]);
          rest as compact one-line ranked index (no evidence)
  - expanded array DROPPED from injected payload (cache-warming metadata)
  - Wrap output in caller-supplied XML tag with optional attrs
  - F-080: retrieval_log_map covers FULL injected set, bool rejected
  - injected_pattern_ids = ALL valid ids from both tiers

Wired into all 4 injection sites:
  1. ace_before_task.py      — <ace-patterns agent-type="...">
  2. ace_subagent_start.py   — <ace-patterns-subagent agent-type="..." agent-id="...">
  3. patterns_used_state.py  — strip_and_gate / --strip-and-gate (domain-shift bash paths)
  4. (implicit via #3)       — ace_pretooluse_wrapper.sh, ace_posttooluse_domain_inject.sh
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure validation module is importable
_PLUGIN_UTILS = Path(__file__).resolve().parent.parent.parent / "utils"
if str(_PLUGIN_UTILS) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_UTILS))
from validation import is_valid_pattern_id  # noqa: E402

# ---------------------------------------------------------------------------
# Fields kept in each pattern after stripping server-internal metadata.
# bandit_rank and semantic_score are NOT in this set — they are hoisted from
# match_factors and added explicitly.
# ---------------------------------------------------------------------------
_KEEP_FIELDS = frozenset({
    'id', 'domain', 'content', 'section', 'evidence',
    'root_cause', 'error_context',
    'cumulative_v15_reward', 'n_hot_pos', 'n_hot_neg', 'isAtRisk',
    # Kept for display / sessionTitle (confidence/helpful/harmful used by
    # build_session_title and _format_bullet_token callers)
    'confidence', 'helpful', 'harmful',
})


def _hoist_and_strip(pattern: Dict[str, Any]) -> Dict[str, Any]:
    """Strip server-internal fields, hoist bandit_rank + semantic_score, cap evidence.

    Returns a new dict with:
      - only _KEEP_FIELDS (plus hoisted bandit_rank/semantic_score when not None)
      - evidence capped to first 2 items
      - match_factors and all other internal fields removed
      - bandit_rank OMITTED when None (consistent with semantic_score behavior)
      - semantic_score OMITTED when None
    """
    mf = pattern.get('match_factors') or {}
    bandit_rank = mf.get('bandit_rank') if isinstance(mf, dict) else None
    semantic_score = mf.get('semantic_score') if isinstance(mf, dict) else None

    result: Dict[str, Any] = {}
    for k in _KEEP_FIELDS:
        if k == 'evidence':
            ev = pattern.get('evidence')
            if ev:
                result['evidence'] = ev[:2]
        elif k in ('root_cause', 'error_context'):
            v = pattern.get(k)
            if v:  # skip empty strings
                result[k] = v
        else:
            if k in pattern:
                result[k] = pattern[k]

    # Hoist bandit_rank and semantic_score to top-level — OMIT when None
    # (consistent behavior: both fields absent when not available, not set to null)
    if bandit_rank is not None:
        result['bandit_rank'] = bandit_rank
    if semantic_score is not None:
        result['semantic_score'] = semantic_score

    return result


def _compact_line(pattern: Dict[str, Any]) -> str:
    """Render one compact index line for a tail pattern.

    Format: #{bandit_rank} [{domain}] s={semantic_score:.2f} {content[:70]}
    Missing bandit_rank renders as '#?' (not '#None').
    """
    rank = pattern.get('bandit_rank')
    domain = pattern.get('domain', 'unknown')
    score = pattern.get('semantic_score')
    content = (pattern.get('content') or '')[:70]
    rank_str = str(rank) if rank is not None else '?'
    score_str = f"{score:.2f}" if score is not None else "?.??"
    return f"#{rank_str} [{domain}] s={score_str} {content}"


def _extract_retrieval_log_id(pattern: Dict[str, Any]) -> Optional[int]:
    """Extract retrieval_log_id from match_factors; reject bool, require int."""
    mf = pattern.get('match_factors')
    if not isinstance(mf, dict):
        return None
    rlid = mf.get('retrieval_log_id')
    if rlid is None:
        return None
    # bool is a subclass of int — must be rejected
    if isinstance(rlid, bool):
        return None
    if isinstance(rlid, int):
        return rlid
    return None


def render_patterns_dict(
    patterns_response: Dict[str, Any],
    *,
    tier_k: int = 15,
) -> Tuple[Dict[str, Any], List[str], Dict[str, int]]:
    """Process ACE patterns into a stripped, sorted, structured dict.

    Performs the core processing pipeline:
      - Sort by bandit_rank ASC; None bandit_rank → stable tail
      - Extract F-080 retrieval_log_map from FULL set (before strip)
      - Hoist bandit_rank + semantic_score, strip server-internal fields
      - Drop expanded array
      - Collect ALL valid injected_pattern_ids

    The output_response_dict['similar_patterns'] contains ALL processed patterns
    (hoisted, sorted, no gate, expanded dropped) — NOT tiered. This is the dict
    the domain-shift path (strip_and_gate) needs.

    count is set to len(processed) — the FULL injected set, matching the contract
    and ensuring `jq '.count'` is correct even if tier_k changes or sets grow.

    Args:
        patterns_response: Raw server response dict with 'similar_patterns' list.
        tier_k: Kept for API consistency with render_patterns but does NOT affect
                the dict output (all processed patterns are in similar_patterns).

    Returns:
        3-tuple:
          (output_response_dict,   # stripped/sorted/hoisted; similar_patterns = FULL set
           injected_pattern_ids,   # ALL valid ids from the full processed set
           retrieval_log_map)      # {pattern_id: retrieval_log_id (int)}, full set

    Key contract points:
      - NO quality gate: all patterns retained regardless of isAtRisk/reward
      - Sort by bandit_rank ASC; None bandit_rank → stable tail
      - bandit_rank OMITTED from pattern when None (consistent with semantic_score)
      - expanded dropped
      - count = len(processed) (full set, not just head)
      - retrieval_log_map covers FULL set
    """
    patterns = (patterns_response.get('similar_patterns') or [])

    # ── Step 1: Sort by bandit_rank ASC; None → tail (stable) ────────────────
    def _sort_key(p):
        mf = p.get('match_factors') or {}
        rank = mf.get('bandit_rank') if isinstance(mf, dict) else None
        if rank is None:
            return (1, 0)   # tail group, preserve input order via stable sort
        return (0, rank)    # ranked group, ascending

    sorted_patterns = sorted(patterns, key=_sort_key)

    # ── Step 2: Extract F-080 retrieval_log_map from FULL set (before strip) ─
    retrieval_log_map: Dict[str, int] = {}
    for p in sorted_patterns:
        pid = p.get('id')
        if not pid:
            continue
        rlid = _extract_retrieval_log_id(p)
        if rlid is not None:
            retrieval_log_map[pid] = rlid

    # ── Step 3: Hoist + strip each pattern ───────────────────────────────────
    processed = [_hoist_and_strip(p) for p in sorted_patterns]

    # ── Step 4: Collect ALL valid injected_pattern_ids ────────────────────────
    injected_pattern_ids: List[str] = [
        p.get('id')
        for p in processed
        if p.get('id') and is_valid_pattern_id(p.get('id'))
    ]

    # ── Step 5: Build output response dict ───────────────────────────────────
    # Copy top-level fields, drop 'similar_patterns' and 'expanded'
    output_response: Dict[str, Any] = {}
    for k, v in patterns_response.items():
        if k in ('similar_patterns', 'expanded'):
            continue
        output_response[k] = v

    # similar_patterns = FULL processed set (not tiered — callers that need
    # tiering use render_patterns which builds on top of this function)
    output_response['similar_patterns'] = processed
    # count = FULL injected set, matching the contract
    output_response['count'] = len(processed)

    return output_response, injected_pattern_ids, retrieval_log_map


def render_patterns(
    patterns_response: Dict[str, Any],
    *,
    tag: str,
    attrs: str = "",
    tier_k: int = 15,
) -> Tuple[str, List[str], str, Dict[str, int]]:
    """Render ACE patterns into context string with tiered verbatim/compact format.

    Delegates to render_patterns_dict for the core processing (DRY), then applies
    verbatim head + compact tail tiering and XML wrapping for context injection.

    Args:
        patterns_response: Raw server response dict with 'similar_patterns' list.
        tag: XML element name (e.g. 'ace-patterns' or 'ace-patterns-subagent').
        attrs: Additional XML attributes string (e.g. 'agent-type="main"').
        tier_k: Number of verbatim patterns (head tier). Default 15.

    Returns:
        4-tuple:
          (additional_context_string,
           injected_pattern_ids,        # ALL valid ids from both tiers
           _reserved,                   # empty string (reserved for compat)
           retrieval_log_map)           # {pattern_id: retrieval_log_id (int)}

    Key contract points:
      - NO quality gate: all patterns retained regardless of isAtRisk/reward
      - Sort by bandit_rank ASC; None bandit_rank → stable tail
      - bandit_rank OMITTED from pattern when None (consistent with semantic_score)
      - expanded dropped
      - count = len(processed) (full set, not just tier_k head)
      - retrieval_log_map covers FULL set
    """
    # ── Core processing delegated to render_patterns_dict (DRY) ──────────────
    output_response, injected_pattern_ids, retrieval_log_map = render_patterns_dict(
        patterns_response, tier_k=tier_k
    )

    # ── Extract the fully processed list for tiering ──────────────────────────
    processed = output_response['similar_patterns']

    # ── Split into verbatim head + compact tail ───────────────────────────────
    head = processed[:tier_k]
    tail = processed[tier_k:]

    # ── Build verbatim response dict (head only for XML injection) ────────────
    # Start from the processed dict (already has correct top-level fields + count)
    # but replace similar_patterns with just the head tier for the XML JSON blob.
    verbatim_response: Dict[str, Any] = {}
    for k, v in output_response.items():
        if k == 'similar_patterns':
            continue
        verbatim_response[k] = v
    verbatim_response['similar_patterns'] = head
    # count stays as len(processed) — the full injected count, not just head
    # (already set correctly in output_response, preserved via the loop above)

    # ── Build compact index for tail ─────────────────────────────────────────
    compact_lines = [_compact_line(p) for p in tail]

    # ── Build XML-wrapped output ──────────────────────────────────────────────
    tag_open = f'<{tag} {attrs}>' if attrs else f'<{tag}>'
    tag_close = f'</{tag}>'

    parts = [tag_open, json.dumps(verbatim_response)]
    if compact_lines:
        parts.append("<ranked_index>")
        parts.extend(compact_lines)
        parts.append("</ranked_index>")
    parts.append(tag_close)

    additional_context = "\n".join(parts)

    return additional_context, injected_pattern_ids, "", retrieval_log_map
