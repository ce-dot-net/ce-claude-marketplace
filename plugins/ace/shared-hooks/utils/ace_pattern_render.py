#!/usr/bin/env python3
"""
ace_pattern_render — Central pure render helper for ACE pattern injection.

Server-team validated contract (ACE-1.5-native, v7.1.11+):
  - bandit_rank + semantic_score hoisted from match_factors to top-level
  - NO quality gate / NO drop: at-risk and reward<0 patterns RETAINED
  - Sort by bandit_rank ASC; missing/None bandit_rank → tail (stable)
  - BUDGET-VERBATIM-NO-TAIL: greedily include patterns verbatim from the top
    until the total additionalContext string (including XML wrapper + header)
    would exceed the budget (default 9500 chars).  DROP tail entirely — no
    compact index, no one-liners, no ranked_index.
  - EDGE CASE: if even the single top-1 pattern verbatim alone exceeds the
    budget, include it TRUNCATED so the total still fits — never emit empty,
    never exceed.
  - Header: shown="N" of="M" in the opening XML tag.
  - BLOAT DROPPED from rendered JSON: domains_summary, expanded, threshold.
  - F-080: retrieval_log_map + injected_pattern_ids cover ONLY the injected
    top-N (what the model actually sees). bool retrieval_log_id rejected.
  - retrieval_id preserved at top-level.
  - Budget is a parameter (default 9500).

render_patterns_dict — unchanged: returns ALL processed patterns with no budget
applied. Used by strip_and_gate (domain-shift, ≤8 patterns always fit).

Wired into all 3 injection sites:
  1. ace_before_task.py      — <ace-patterns agent-type="...">
  2. ace_subagent_start.py   — <ace-patterns-subagent agent-type="..." agent-id="...">
  3. patterns_used_state.py  — strip_and_gate / --strip-and-gate (domain-shift bash paths)
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
# Default budget (chars) for the full returned additionalContext string.
# CC hard-caps hook additionalContext at 10,000 chars; we stay comfortably
# below that so the model always gets the full injection (never a 2KB preview).
# ---------------------------------------------------------------------------
_DEFAULT_BUDGET = 9500

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

# Top-level response fields that are BLOAT and must be dropped from the
# rendered JSON payload (save chars, no value to the model).
_DROP_TOP_LEVEL = frozenset({'domains_summary', 'expanded', 'threshold'})


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


def _build_retrieval_log_map_for_raw(raw_patterns: List[Dict[str, Any]]) -> Dict[str, int]:
    """Build retrieval_log_map from a list of raw (un-stripped) patterns."""
    retrieval_log_map: Dict[str, int] = {}
    for p in raw_patterns:
        pid = p.get('id')
        if not pid:
            continue
        rlid = _extract_retrieval_log_id(p)
        if rlid is not None:
            retrieval_log_map[pid] = rlid
    return retrieval_log_map


def render_patterns_dict(
    patterns_response: Dict[str, Any],
    *,
    tier_k: int = 15,
) -> Tuple[Dict[str, Any], List[str], Dict[str, int]]:
    """Process ACE patterns into a stripped, sorted, structured dict.

    NO budget applied here — returns ALL processed patterns.  Used by
    strip_and_gate (domain-shift, ≤8 patterns always fit in budget anyway).

    Performs the core processing pipeline:
      - Sort by bandit_rank ASC; None bandit_rank → stable tail
      - Extract F-080 retrieval_log_map from FULL set (before strip)
      - Hoist bandit_rank + semantic_score, strip server-internal fields
      - Drop expanded array + other bloat (domains_summary, threshold)
      - Collect ALL valid injected_pattern_ids

    The output_response_dict['similar_patterns'] contains ALL processed patterns
    (hoisted, sorted, no gate, expanded+bloat dropped) — NOT budget-limited.

    count is set to len(processed) — the FULL injected set.

    Args:
        patterns_response: Raw server response dict with 'similar_patterns' list.
        tier_k: Accepted for API compatibility but does NOT affect the dict output.

    Returns:
        3-tuple:
          (output_response_dict,   # stripped/sorted/hoisted; similar_patterns = FULL set
           injected_pattern_ids,   # ALL valid ids from the full processed set
           retrieval_log_map)      # {pattern_id: retrieval_log_id (int)}, full set

    Key contract points:
      - NO quality gate: all patterns retained regardless of isAtRisk/reward
      - Sort by bandit_rank ASC; None bandit_rank → stable tail
      - bandit_rank OMITTED from pattern when None (consistent with semantic_score)
      - domains_summary, expanded, threshold dropped
      - count = len(processed) (full set)
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
    retrieval_log_map: Dict[str, int] = _build_retrieval_log_map_for_raw(sorted_patterns)

    # ── Step 3: Hoist + strip each pattern ───────────────────────────────────
    processed = [_hoist_and_strip(p) for p in sorted_patterns]

    # ── Step 4: Collect ALL valid injected_pattern_ids ────────────────────────
    injected_pattern_ids: List[str] = [
        p.get('id')
        for p in processed
        if p.get('id') and is_valid_pattern_id(p.get('id'))
    ]

    # ── Step 5: Build output response dict ───────────────────────────────────
    # Copy top-level fields, drop bloat fields
    output_response: Dict[str, Any] = {}
    for k, v in patterns_response.items():
        if k in _DROP_TOP_LEVEL or k == 'similar_patterns':
            continue
        output_response[k] = v

    # similar_patterns = FULL processed set (not tiered, not budget-limited)
    output_response['similar_patterns'] = processed
    # count = FULL injected set
    output_response['count'] = len(processed)

    return output_response, injected_pattern_ids, retrieval_log_map


def render_patterns(
    patterns_response: Dict[str, Any],
    *,
    tag: str,
    attrs: str = "",
    tier_k: int = 15,
    budget: int = _DEFAULT_BUDGET,
) -> Tuple[str, List[str], str, Dict[str, int]]:
    """Render ACE patterns into context string with BUDGET-VERBATIM-NO-TAIL format.

    Delegates to render_patterns_dict for core sort/strip/hoist/bloat-drop (DRY),
    then applies budget-greedy selection and XML wrapping.

    New contract (v7.1.11+):
      1. Sort by bandit_rank ASC; None → stable tail (via render_patterns_dict).
      2. Greedily include patterns VERBATIM from the top, accumulating rendered
         char count.  STOP before the total additionalContext string (including
         XML wrapper + shown/of header) would exceed `budget`.
      3. DROP tail entirely — no compact index, no one-liners, no ranked_index.
      4. Drop domains_summary, expanded, threshold from rendered JSON (via dict).
      5. Header: shown="N" of="M" in the opening XML tag.
      6. HARD GUARANTEE: total returned string ≤ budget chars.
      7. EDGE CASE: if even top-1 alone exceeds budget, include it TRUNCATED
         so the total still fits — never emit empty, never exceed.
      8. F-080: retrieval_log_map + injected_pattern_ids cover ONLY injected top-N.

    Args:
        patterns_response: Raw server response dict with 'similar_patterns' list.
        tag: XML element name (e.g. 'ace-patterns' or 'ace-patterns-subagent').
        attrs: Additional XML attributes string (e.g. 'agent-type="main"').
        tier_k: Accepted for API compat; no longer controls injection (budget does).
        budget: Maximum chars for the full returned additionalContext string.
                Default 9500.

    Returns:
        4-tuple:
          (additional_context_string,
           injected_pattern_ids,        # valid ids for patterns ACTUALLY RENDERED
           _reserved,                   # empty string (reserved for compat)
           retrieval_log_map)           # {pattern_id: retrieval_log_id} INJECTED only
    """
    # ── Core processing delegated to render_patterns_dict (DRY) ──────────────
    # This gives us: sorted+stripped+hoisted patterns (all of them), all ids,
    # and the full retrieval_log_map (covers all). We then apply budget on top.
    output_dict, _all_ids, _full_rl_map = render_patterns_dict(
        patterns_response, tier_k=tier_k
    )

    # The sorted+processed list (all patterns, no budget yet)
    all_processed = output_dict['similar_patterns']
    total_count = output_dict['count']

    # Base response dict (bloat already dropped by render_patterns_dict)
    # We'll use its top-level fields for the JSON body.
    base_response: Dict[str, Any] = {
        k: v for k, v in output_dict.items()
        if k not in ('similar_patterns', 'count')
    }

    # We also need raw patterns for retrieval_log_id extraction (injected set).
    # Since render_patterns_dict drops match_factors, we need to re-extract from
    # the original response. We stored them in _full_rl_map already; we'll
    # filter that map to only injected patterns below.

    # ── Build tag helpers ─────────────────────────────────────────────────────
    tag_close = f'</{tag}>'

    def _build_tag_open(n_shown: int) -> str:
        shown_attr = f'shown="{n_shown}" of="{total_count}"'
        if attrs:
            return f'<{tag} {shown_attr} {attrs}>'
        return f'<{tag} {shown_attr}>'

    # ── Estimate overhead ─────────────────────────────────────────────────────
    # Final string shape: <tag shown="N" of="M" [attrs]>\n{JSON}\n</tag>
    # Overhead = tag_open + "\n" + base_response_json_with_empty_list + "\n" + tag_close
    _sample_open = _build_tag_open(total_count)  # worst case: all fit
    _base_json_empty = json.dumps(dict(base_response, similar_patterns=[], count=total_count))
    _fixed_overhead = len(_sample_open) + 1 + len(_base_json_empty) + 1 + len(tag_close)
    available = budget - _fixed_overhead

    # ── Greedy verbatim inclusion ─────────────────────────────────────────────
    injected_processed: List[Dict[str, Any]] = []
    injected_pattern_ids: List[str] = []
    retrieval_log_map: Dict[str, int] = {}

    # Track running size of the similar_patterns JSON array.
    # JSON array: "[" + items + "]" = 2 chars baseline, each item adds len(json) + comma.
    list_chars = 2  # for "[]"

    for processed_pat in all_processed:
        item_json = json.dumps(processed_pat)
        if injected_processed:
            cost = len(item_json) + 2  # +2 for ", " (json.dumps default separator)
        else:
            cost = len(item_json)      # first item: no leading comma

        if list_chars + cost <= available:
            # Pattern fits — include verbatim
            injected_processed.append(processed_pat)
            list_chars += cost
            pid = processed_pat.get('id')
            if pid and is_valid_pattern_id(pid):
                injected_pattern_ids.append(pid)
                if pid in _full_rl_map:
                    retrieval_log_map[pid] = _full_rl_map[pid]
        else:
            # Pattern doesn't fit.
            if not injected_processed:
                # EDGE CASE: first pattern — must include even if truncated.
                pat_copy = dict(processed_pat)
                # Try without evidence first
                pat_copy.pop('evidence', None)
                item_json = json.dumps(pat_copy)
                cost = len(item_json)
                if list_chars + cost <= available:
                    injected_processed.append(pat_copy)
                    list_chars += cost
                else:
                    # Still too big — truncate content to fit
                    content = pat_copy.get('content', '')
                    # How many chars can content occupy?
                    # item_json chars = cost; content occupies len(json.dumps(content)) chars
                    # within that. We need to shave off (cost - available + list_chars) chars.
                    excess = (list_chars + cost) - available
                    content_json_len = len(json.dumps(content))
                    # Trim content_json_len by excess (plus 1 for safety)
                    new_content_json_len = max(4, content_json_len - excess - 1)
                    # new_content_json_len chars of JSON string = approximately
                    # new_content_json_len - 2 chars of actual string (minus quotes)
                    max_content_chars = max(1, new_content_json_len - 2)
                    pat_copy['content'] = content[:max_content_chars]
                    item_json = json.dumps(pat_copy)
                    # Final safety: if still over, keep trimming
                    while list_chars + len(item_json) > available and len(pat_copy.get('content', '')) > 1:
                        pat_copy['content'] = pat_copy['content'][:-10]
                        item_json = json.dumps(pat_copy)
                    if list_chars + len(item_json) > available:
                        pat_copy['content'] = pat_copy.get('content', '')[:1]
                        item_json = json.dumps(pat_copy)
                    injected_processed.append(pat_copy)
                    list_chars += len(item_json)
                pid = pat_copy.get('id')
                if pid and is_valid_pattern_id(pid):
                    injected_pattern_ids.append(pid)
                    if pid in _full_rl_map:
                        retrieval_log_map[pid] = _full_rl_map[pid]
            # Tail is DROPPED — no compact index, no more patterns
            break

    # ── Build final serialised output ─────────────────────────────────────────
    n_shown = len(injected_processed)
    tag_open = _build_tag_open(n_shown)

    output_response: Dict[str, Any] = dict(base_response)
    output_response['similar_patterns'] = injected_processed
    output_response['count'] = total_count  # total retrieved (not just shown)

    body_json = json.dumps(output_response)
    additional_context = f"{tag_open}\n{body_json}\n{tag_close}"

    # ── Hard budget guarantee ─────────────────────────────────────────────────
    # Safety valve: should never trigger (the greedy loop maintains the invariant),
    # but if it does, drop whole trailing patterns and re-serialize — NEVER
    # raw-byte-truncate body_json (that produces invalid JSON).
    if len(additional_context) > budget:
        # Drop patterns from the tail one by one until the body fits.
        while injected_processed and len(additional_context) > budget:
            injected_processed.pop()
            # Also remove the trailing id / rl_map entry if present.
            if injected_pattern_ids:
                dropped_id = injected_pattern_ids[-1]
                # Only pop if the last id belongs to the dropped pattern.
                if injected_processed and injected_processed[-1].get('id') == dropped_id:
                    pass  # still in the injected list — don't pop yet
                else:
                    injected_pattern_ids.pop()
                    retrieval_log_map.pop(dropped_id, None)
            # Re-build tag + body with the reduced list.
            n_shown = len(injected_processed)
            tag_open = _build_tag_open(n_shown)
            output_response['similar_patterns'] = injected_processed
            body_json = json.dumps(output_response)
            additional_context = f"{tag_open}\n{body_json}\n{tag_close}"
        # Rebuild injected_pattern_ids and retrieval_log_map from the final list
        # to ensure perfect consistency after the drop loop.
        injected_pattern_ids = [
            p['id'] for p in injected_processed
            if p.get('id') and is_valid_pattern_id(p.get('id'))
        ]
        retrieval_log_map = {
            pid: _full_rl_map[pid]
            for pid in injected_pattern_ids
            if pid in _full_rl_map
        }

    return additional_context, injected_pattern_ids, "", retrieval_log_map
