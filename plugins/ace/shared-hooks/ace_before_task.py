#!/usr/bin/env python3
"""
ACE Before Task Hook - UserPromptSubmit Event Handler

Searches ACE playbook for relevant patterns when user starts a task.
Uses ace-cli search --stdin to avoid shell escaping issues.
Supports session pinning (v1.0.11+) for pattern persistence across compaction.

v5.4.13: Added check_auth_status() to catch 48h standby scenario.
v5.4.18: Granular token expiration using token_expires_in (seconds).
         Warns if token expires within 2 hours before complex tasks.
"""

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

from validation import is_valid_pattern_id
from patterns_used_state import append_patterns_used, injected_contents, task_session_id_for
from ace_pattern_render import render_patterns, render_cohort, render_compact_all


def sanitize_unicode(text: str) -> str:
    """
    Remove invalid Unicode surrogate pairs that break JSON parsing.
    Surrogates are UTF-16 encoding artifacts (U+D800 to U+DFFF) that
    shouldn't appear in valid UTF-8 strings.
    """
    if not isinstance(text, str):
        return text
    # Remove lone surrogates (high surrogate not followed by low, or lone low)
    # This regex matches surrogate code points
    return text.encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')


def sanitize_response(obj: Any) -> Any:
    """Recursively sanitize all strings in a dict/list structure."""
    if isinstance(obj, str):
        return sanitize_unicode(obj)
    elif isinstance(obj, dict):
        return {k: sanitize_response(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_response(item) for item in obj]
    else:
        return obj

from ace_cli import run_search, check_auth_status
from ace_context import get_context
from ace_relevance_logger import log_search_metrics, log_search_skipped
from machine_prompts import is_machine_prompt
import plugin_data_dir

# Machine-generated "prompts" (CC injects these as UserPromptSubmit turns): searching them is
# pure noise (critic T1). One shared prefix list (utils/machine_prompts.py).
_LEADING_REMINDER = re.compile(r'\A(?:\s*<system-reminder>.*?</system-reminder>)+\s*', re.DOTALL | re.IGNORECASE)


def _skip_reason(prompt):
    """Return a reason string when the prompt must not trigger a search, else None."""
    stripped = prompt.strip()
    # Leading injected <system-reminder> blocks are not the human's text: drop them all,
    # then judge what is left (a reminder-only prompt becomes empty -> machine).
    stripped = _LEADING_REMINDER.sub('', stripped).strip()
    if not stripped and prompt.strip():
        return 'machine_prompt'
    if is_machine_prompt(stripped):
        return 'machine_prompt'
    try:
        min_chars = int(os.environ.get('ACE_MIN_PROMPT_CHARS', '12'))
    except ValueError:
        min_chars = 12
    if len(stripped) < min_chars:
        return 'prompt_too_short'
    return None


def _log_skipped(event, reason, context):
    if not (context or {}).get('project'):
        return  # ACE not configured here: do not litter .claude/data/logs in unrelated repos
    try:
        log_search_skipped('UserPromptSubmit', reason, event.get('session_id'),
                           (context or {}).get('project'))
    except Exception:
        pass


def _title_for_guarded_mod(project, event):
    """The mod searched, but a managed-settings guard filters its classic.UserPromptSubmit (no mod-classic marker):
    set the title it computed (mod-title). Never over a custom /rename title, never while disabled."""
    sid = event.get('session_id') or ''
    if (event.get('session_title') or plugin_data_dir.is_disabled(project, sid) or not plugin_data_dir.is_mod_active(project, sid)
            or plugin_data_dir.mod_owns_learn(project, sid)):
        return
    try:
        title = (plugin_data_dir.session_dir(project, sid, create=False) / 'mod-title').read_text().strip()
    except OSError:
        return
    if title:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "sessionTitle": title[:200]}}))


def build_session_title(pattern_list, pattern_count, agent_type, review_file=None):
    """Build CC sessionTitle from pattern state + optional ROI suffix.

    State machine (verified in installed cache v6.3.2):
      - pattern_count == 0         → None (caller omits sessionTitle key)
      - agent_type != 'main'       → "ACE/sub · {count}"
      - avg_conf < 0.50            → "ACE low · {count}"
      - 5+ patterns, conf>=0.70,
        top-domain helpful>=20     → "ACE ready · {topic}[ · +{Nm}]"
      - otherwise                  → "ACE · {count} · {topic}[ · +{Nm}]"

    ROI suffix: parses time_saved (e.g. "15m", "~45m") from
    .claude/data/logs/ace-review-result.json. Missing/zero → no suffix.
    """
    if pattern_count == 0 or not pattern_list:
        return None

    # Aggregate helpful by domain, pick top
    domain_helpful = {}
    for p in pattern_list:
        d = p.get('domain', '')
        if d:
            domain_helpful[d] = domain_helpful.get(d, 0) + p.get('helpful', 0)
    top_domains = sorted(domain_helpful.items(), key=lambda x: -x[1])

    avg_conf = sum(p.get('confidence', 0) for p in pattern_list) / len(pattern_list) if pattern_list else 0
    top_helpful = top_domains[0][1] if top_domains else 0
    top_short = top_domains[0][0].split('-')[0] if top_domains else ''

    # ROI signal: parse time_saved from last task's ACE_REVIEW (self-eval result)
    # File format: {"helpful_pct": N, "time_saved": "15m"}
    roi_suffix = ''
    try:
        rf = Path(review_file) if review_file else Path('.claude/data/logs/ace-review-result.json')
        if rf.exists():
            review_data = json.loads(rf.read_text())
            ts = review_data.get('time_saved', '').strip()
            # Extract leading digits (handles "15m", "~4m", "20m", etc)
            m = re.search(r'(\d+)\s*m', ts)
            if m and int(m.group(1)) > 0:
                roi_suffix = f" · +{m.group(1)}m"
    except Exception:
        pass  # non-fatal, ROI suffix stays empty

    # OR-fallback for "ACE ready" tier (issue #27):
    # v15 patterns qualify if not isAtRisk AND reward >= 0 (neutral==0 is fine); legacy via top_helpful >= 20
    # Fix 3c: @ace-sdk/core 3.2.2 changed isAtRisk to mean reward<0; reward==0 = neutral/kept
    # Fix A: guard reward >= 0 in addition to not isAtRisk — stale/mixed server data can produce
    #         reward<0 with isAtRisk=False; negative reward is unsafe regardless of that flag.
    has_reliable = any(
        p.get('cumulative_v15_reward') is not None
        and not p.get('isAtRisk', False)
        and p.get('cumulative_v15_reward') >= 0
        for p in pattern_list
    ) or top_helpful >= 20

    # State machine
    if agent_type and agent_type != 'main':
        return f"ACE/sub · {pattern_count}"
    if avg_conf < 0.50:
        return f"ACE low · {pattern_count}"
    if pattern_count >= 5 and avg_conf >= 0.70 and has_reliable:
        base = f"ACE ready · {top_short}" if top_short else f"ACE ready · {pattern_count}"
        return base + roi_suffix
    base = f"ACE · {pattern_count} · {top_short}" if top_short else f"ACE · {pattern_count}"
    return base + roi_suffix


def expand_abbreviations(prompt: str) -> str:
    """
    Minimal query enhancement: Expand ONLY common abbreviations for clarity.
    DO NOT add generic keywords - embeddings work better with natural language!

    Based on server team feedback: Semantic search uses embeddings, not keyword
    matching. Adding generic words like "patterns examples strategies" actually
    DILUTES the semantic signal.

    Research evidence:
    - Natural language queries: 0.82 NDCG
    - Keyword-stuffed queries: 0.71 NDCG (worse!)
    """
    replacements = {
        ' JWT ': ' JSON Web Token ',
        ' API ': ' REST API ',
        ' DB ': ' database ',
        ' env ': ' environment ',
        ' auth ': ' authentication ',
        ' config ': ' configuration ',
        ' deps ': ' dependencies ',
        ' repo ': ' repository ',
    }

    result = f" {prompt} "  # Add spaces for word boundary matching
    for abbrev, full in replacements.items():
        result = result.replace(abbrev, full)

    return result.strip()


def _num(v):
    """int/float (not bool, finite) as-is, else 0."""
    import math
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    return v if math.isfinite(v) else 0


def check_eval_request_and_review():
    """Fire-and-forget self-eval: read eval request, inject context, parse ACE_REVIEW.

    1. If ace-eval-request.json exists from previous Stop hook, build eval additionalContext
       asking Claude to evaluate previous task's ACE patterns from a HUMAN DEVELOPER perspective.
       Returns eval context string and deletes the request file.
    2. If ace-review-result.json needs updating (future: parse from transcript), handle it.
    Returns: (eval_context_str or None)
    """
    eval_request_file = Path('.claude/data/logs/ace-eval-request.json')
    eval_context = None

    # Check if eval request exists from previous task's Stop hook
    if eval_request_file.exists():
        try:
            eval_data = json.loads(eval_request_file.read_text())
            if not isinstance(eval_data, dict):
                eval_data = {}
            # §24: a repo-controlled file reaches the model's context: numbers only, anything else is 0.
            patterns_injected = _num(eval_data.get('patterns_injected'))
            avg_relevance = _num(eval_data.get('avg_relevance'))
            domains = _num(eval_data.get('domains'))
            tools_executed = _num(eval_data.get('tools_executed'))

            # Build additionalContext for silent eval injection
            # Frame for HUMAN DEVELOPER perspective — ask for ACE_REVIEW marker
            eval_context = (
                f"<!-- ACE Self-Eval Request: Previous task used {patterns_injected} patterns "
                f"({avg_relevance}% relevance, {domains} domains, {tools_executed} tools). "
                f"As a human developer, how much time did these patterns save? "
                f"Without ACE, a developer would search docs, explore codebases, ask colleagues, or trial-and-error. "
                f"Rate from a HUMAN DEVELOPER perspective, not AI perspective. "
                f"Include in your response: ACE_REVIEW: N% | Xm saved | one-line reason -->"
            )

            # Clean up: delete eval request after reading (unlink)
            eval_request_file.unlink(missing_ok=True)
        except Exception:
            # Non-fatal: continue without eval injection
            eval_request_file.unlink(missing_ok=True)

    return eval_context


# ---------------------------------------------------------------------------
# Module-level constants and helpers (issue #27: reward-vocab quality gate)
# ---------------------------------------------------------------------------

# Fields to keep when stripping server-internal metadata before injection.
# v15 wire fields (cumulative_v15_reward, n_hot_pos, n_hot_neg, isAtRisk) added
# so reward data survives the strip step; match_factors excluded by design.
USEFUL_FIELDS = {
    'id', 'domain', 'content', 'confidence', 'helpful', 'harmful',
    'section', 'evidence', 'root_cause', 'error_context',
    # v15 reward-vocab fields (issue #27)
    'cumulative_v15_reward', 'n_hot_pos', 'n_hot_neg', 'isAtRisk',
}


def _apply_quality_gate(patterns):
    """Dual-format quality gate (issue #27, ACE 1.5 native).

    v15 path  (cumulative_v15_reward present):
        keep if NOT isAtRisk AND reward >= 0
        (@ace-sdk/core 3.2.2: isAtRisk means reward<0; reward==0 = neutral/uncredited,
        kept. Only reward<0 / at-risk patterns are dropped. Fix A: also guard reward >= 0
        so stale/mixed server data with reward<0 + isAtRisk=False is still dropped.
        Mirrors patterns_used_state _quality_gate — keep both in sync.)
    Legacy path (no cumulative_v15_reward field):
        keep if confidence >= 0.5 OR helpful >= 2
        (restore original OR-condition: high-confidence new patterns pass
        even before accumulating helpful votes)
    """
    result = []
    for p in patterns:
        reward = p.get('cumulative_v15_reward')
        if reward is not None:
            if not p.get('isAtRisk', False) and reward >= 0:
                result.append(p)
        else:
            if p.get('confidence', 0) >= 0.5 or p.get('helpful', 0) >= 2:
                result.append(p)
    return result


def _format_bullet_token(pattern):
    """Return display token for a pattern bullet (issue #27 / Fix 2).

    Priority order:
      1. reward != 0 and present  → "⚡{reward:.1f}"  (credited reward)
      2. reward == 0, ucb_score present → "↑{ucb:.2f}"  (org-fallback ranking)
      3. reward absent/0, confidence present and > 0 → "{conf:.0%}"
      4. fallback → "+{helpful}"
    "⚡0.0" is never emitted (reward==0 is neutral/uncredited, not worthless).
    """
    reward = pattern.get('cumulative_v15_reward')
    if reward is not None and reward != 0:
        return f"⚡{reward:.1f}"
    # reward is 0 or absent — try ucb_score from match_factors
    ucb = (pattern.get('match_factors') or {}).get('ucb_score')
    if ucb is not None:
        try:
            return f"↑{float(ucb):.2f}"
        except (TypeError, ValueError):
            pass
    # fall through to confidence
    conf = pattern.get('confidence')
    if conf is not None and conf:
        try:
            return f"{float(conf):.0%}"
        except (TypeError, ValueError):
            pass
    return f"+{pattern.get('helpful', 0)}"


def main():
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)
        user_prompt = event.get('prompt', '')

        if not user_prompt:
            # No prompt, nothing to search
            sys.exit(0)

        t_start = time.monotonic()
        # DESIGN §3.1: no `cd` in the shim - resolve .claude/settings.json from the hook cwd.
        _cwd = event.get('cwd')
        if _cwd and os.path.isdir(_cwd):
            os.chdir(_cwd)

        # P-26: session OR project disabled.flag stops everything BEFORE any state/log is written.
        try:
            _ctx = get_context()
        except Exception:
            _ctx = None
        if _ctx and (plugin_data_dir.is_disabled(_ctx['project'], event.get('session_id') or '') or plugin_data_dir.is_mod_active(_ctx['project'], event.get('session_id') or '')):
            _title_for_guarded_mod(_ctx['project'], event)
            sys.exit(0)

        _reason = _skip_reason(user_prompt)
        if _reason == 'machine_prompt' or _reason == 'prompt_too_short':
            _log_skipped(event, _reason, _ctx)
            sys.exit(0)

        # ── Fire-and-forget self-eval: inject eval request as additionalContext ──
        # Reads ace-eval-request.json from previous task, injects eval context,
        # and writes ace-review-result.json when ACE_REVIEW is found
        eval_injection = check_eval_request_and_review()

        # Skip only ACE slash commands (not other plugins' commands!)
        # Other plugins like /c4-architecture should still trigger ACE pattern search
        prompt_lower = user_prompt.strip().lower()
        if prompt_lower.startswith('/ace-') or prompt_lower.startswith('/ace:'):
            sys.exit(0)

        # Get project context from .claude/settings.json
        context = _ctx or get_context()
        if not context:
            sys.exit(0)  # silent: /ace:ace-doctor reports a missing project context

        # Use Claude's session_id for state file consistency (Issue #16)
        # ace_after_task.py reads event.get('session_id') — we must use the same key
        session_id = event.get('session_id', str(uuid.uuid4()))

        # P-26: session OR project disabled.flag stops everything, before any state is written.
        if plugin_data_dir.is_disabled(context['project'], session_id) or plugin_data_dir.is_mod_active(context['project'], session_id):
            sys.exit(0)

        # Per-task session_id = hook prompt_id (G2), else uuid4.
        # This is passed to ace-cli search --pin-session and stored in the state file
        # so ace_after_task can set trace["session_id"] = task_session_id, pinning
        # each task's retrieval rows + trajectory under one ID on the server.
        # The CC conversation session_id (above) remains the state-file KEY and is
        # used for ace-relevance.jsonl / ace-spawn-log.jsonl telemetry.
        task_session_id = task_session_id_for(event)  # G2: prompt_id anchor, else uuid4

        use_session_pinning = True  # v8: always pin (no --version probe)

        # v6.0.0: Read agent_type natively from hook event (CC 2.1.69+)
        # agent_type identifies subagent type: "main", "refactorer", "coder", etc.
        agent_type = event.get('agent_type', 'main')

        # Resolve agent_id early (also used below at append_patterns_used).
        agent_id = event.get('agent_id') if isinstance(event, dict) else None

        # Persist the per-task anchor IMMEDIATELY (before run_search / early-exits) so
        # Stop's load_task_session_id finds it even if the search returns 0 patterns,
        # fails, or errors.  The later append_patterns_used call (inside `if pattern_ids:`)
        # will merge pattern_ids + retrieval_id into this same file via merge logic.
        try:
            if not agent_id:  # a Stop deferred for a running agent never got its notification: record the loss
                _mark = plugin_data_dir.session_dir(context.get('project'), session_id, create=False) / 'learn-deferred'
                if _mark.exists():
                    from ace_relevance_logger import log_event
                    log_event('learn_deferred_lost', reason='new_prompt', session_id=session_id)
                    _mark.unlink()
        except Exception:
            pass
        try:
            append_patterns_used(session_id, agent_id, [], task_session_id=task_session_id,
                                 user_prompt=user_prompt, hook_event_name='UserPromptSubmit', reset=True)
        except Exception:
            pass  # non-fatal

        auth_warning = None  # v8: auth check only in the failure branch (C2)

        # Minimal enhancement: Expand abbreviations for semantic clarity
        # (Server team: DO NOT add generic keywords - hurts embedding quality!)
        search_query = expand_abbreviations(user_prompt)

        # Call ace-cli search --stdin with optional session pinning.
        # Pass task_session_id (not CC conversation session_id) so the server pins
        # retrieved patterns under this task's ID — each task gets its own pin bucket.
        # F-080: ALWAYS search with --pin-session for this task's tsid. A disk-cache hit would
        # carry no retrieval_id / applied_log_ids and never pin the tsid, so a repeated prompt
        # ("continue with the refactor") would lose its credit. (ace_search_cache is for the
        # SubagentStart fan-out only.)
        _cache_hit = False
        patterns_response, _search_ms = run_search(
            query=search_query,
            org=context['org'],
            project=context['project'],
            session_id=task_session_id,
            timeout=25,
            hook_event_name='UserPromptSubmit',
        )

        # v5.3.5: Sanitize response to remove invalid Unicode surrogates
        # These can break the Claude API's JSON parser
        if patterns_response:
            patterns_response = sanitize_response(patterns_response)

        # v5.4.21: Check for error responses from run_search()
        if not patterns_response:
            # Search failed - check if it's an auth error
            # the 5 s whoami probe must fit the 30 s hook timeout after a slow (<=25 s) search
            auth_warning = (check_auth_status(warn_threshold_hours=2.0)
                            if time.monotonic() - t_start < 18 else None)
            if auth_warning:
                # Auth issue detected - show auth warning instead of generic error
                output = {"systemMessage": auth_warning}
            else:
                # Generic search failure
                output = {"systemMessage": "❌ [ACE] Search failed or returned no results"}
            print(json.dumps(output))
            sys.exit(0)

        # v5.4.21: Handle structured error responses
        if isinstance(patterns_response, dict) and patterns_response.get('error'):
            error_type = patterns_response.get('error')
            error_msg = patterns_response.get('message', 'Unknown error')

            if error_type == 'not_authenticated':
                output = {"systemMessage": f"⚠️ [ACE] {error_msg}"}
            elif error_type == 'timeout':
                output = {"systemMessage": f"⏱️ [ACE] {error_msg}"}
            elif error_type == 'cli_not_found':
                # SessionStart already said it once (§23); a message on every prompt is noise. Log only.
                _log_skipped(event, 'cli_not_found', context)
                sys.exit(0)
            else:
                output = {"systemMessage": f"❌ [ACE] {error_msg}"}

            print(json.dumps(output))
            sys.exit(0)

        pattern_list = patterns_response.get('similar_patterns', [])
        original_pattern_list = list(pattern_list)  # Keep original for logging

        # ── A/B cohort (§28): bucket on the STABLE CC session_id (one arm per conversation), never the
        # per-task pin. Default: the full arm, which this chain renders as budget. Domain-shift unaffected.
        _cohort = render_cohort(session_id)

        # Capture top-3 patterns WITH match_factors BEFORE render so that
        # _format_bullet_token can use ucb_score for display.  render_patterns
        # sorts by bandit_rank ASC, so pre-sort here to match display order.
        _sorted_for_display = sorted(
            pattern_list,
            key=lambda p: (
                (0, (p.get('match_factors') or {}).get('bandit_rank'))
                if (p.get('match_factors') or {}).get('bandit_rank') is not None
                else (1, 0)
            )
        )
        _display_top3 = [dict(p) for p in _sorted_for_display[:3]]

        # v5.3.0: Store domains for PreToolUse hook (domain-aware reminders)
        # Extract domains from patterns if domains_summary is empty
        domains_summary = patterns_response.get('domains_summary', {})
        if not domains_summary:
            pattern_domains = {}
            for p in pattern_list:
                domain = p.get('domain', '')
                if domain:
                    pattern_domains[domain] = pattern_domains.get(domain, 0) + 1
            domains_summary = pattern_domains

        if context['project'] and domains_summary:
            try:
                plugin_data_dir.domains_file(context['project']).write_text(json.dumps(domains_summary))
            except Exception:
                pass

        # ── Render dispatch by cohort ─────────────────────────────────────────
        _retrieval_id = patterns_response.get('retrieval_id') or None
        _tag_attrs = f'agent-type="{agent_type}"'

        if _cohort == 'control':
            # Control arm: search ran (retrieval_id logged), but inject ZERO patterns.
            # F-080 anchor: append_patterns_used with empty ids + retrieval_id + tsid.
            ace_context = None  # no additionalContext block
            _pattern_ids = []
            _retrieval_log_map = {}

        elif _cohort == 'compact':
            # Compact arm: all patterns as compact one-liners, total ≤ 9500 chars.
            ace_context, _pattern_ids, _, _retrieval_log_map = render_compact_all(
                patterns_response,
                tag='ace-patterns',
                attrs=_tag_attrs,
            )

        else:
            # Budget arm (default): existing budget-verbatim render (unchanged).
            ace_context, _pattern_ids, _, _retrieval_log_map = render_patterns(
                patterns_response,
                tag='ace-patterns',
                attrs=_tag_attrs,
            )
            # CRITICAL: Save pattern IDs for reinforcement learning.
            # render_patterns returns only budget-limited injected ids (no gate drop).

        _rendered_for_state = ace_context  # pattern block only: compact re-inject must not replay the eval ask

        # Append fire-and-forget eval injection if present (from previous task's Stop hook).
        # CC hard-caps additionalContext at 10,000 chars; trim eval_injection (cosmetic) to fit.
        # Control arm: ace_context is None — skip eval injection (model sees zero patterns).
        if eval_injection and ace_context is not None:
            _CC_HARD_CAP = 10_000
            _available_for_eval = _CC_HARD_CAP - len(ace_context) - 1  # -1 for the "\n"
            if _available_for_eval > 0:
                ace_context = ace_context + "\n" + eval_injection[:_available_for_eval]

        # CRITICAL: Save pattern IDs for reinforcement learning (+ C1 keys).
        # Ids are the budget-limited injected ids; control arm saves the F-080 anchor only.
        try:
            append_patterns_used(session_id, agent_id, _pattern_ids,
                                 retrieval_id=_retrieval_id,
                                 retrieval_log_ids=_retrieval_log_map,
                                 task_session_id=task_session_id,
                                 user_prompt=user_prompt,
                                 rendered_context=_rendered_for_state if _rendered_for_state is not None else '',
                                 hook_event_name='UserPromptSubmit', render_variant=_cohort,
                                 pattern_contents=injected_contents(original_pattern_list, _pattern_ids))
        except Exception as e:
            from ace_relevance_logger import log_error
            log_error('UserPromptSubmit', 'ace_before_task.state_write', session_id, context['project'], e)

        # v5.4.2 / C5: log AFTER render with the real injected count + hook latency.
        try:
            domains = list(set(p.get('domain', 'unknown') for p in original_pattern_list if p.get('domain')))
            _injected = set(_pattern_ids)
            _injected_dicts = [p for p in original_pattern_list if p.get('id') in _injected]
            log_search_metrics(
                hook='UserPromptSubmit',
                session_id=session_id,
                user_prompt=user_prompt,
                search_query=search_query,
                patterns_returned=original_pattern_list,
                patterns_injected=_injected_dicts,
                domains=domains,
                project_id=context.get('project'),
                org_id=context.get('org'),
                agent_type=agent_type,
                render_cohort=_cohort,
                hook_ms=int((time.monotonic() - t_start) * 1000),
                cache_hit=_cache_hit,
            )
        except Exception:
            pass  # Non-fatal: continue without logging

        # Build user-visible message
        pattern_list = patterns_response.get('similar_patterns', [])
        pattern_count = len(pattern_list)
        domains_summary = patterns_response.get('domains_summary', {})

        if pattern_count > 0:
            # Build summary with domain info
            summary_lines = [f"✅ [ACE] Found {pattern_count} relevant bullets"]

            # Show domain summary
            abstract_domains = domains_summary.get('abstract', [])
            if abstract_domains:
                domains_str = ', '.join(abstract_domains[:3])
                if len(abstract_domains) > 3:
                    domains_str += f' (+{len(abstract_domains) - 3} more)'
                summary_lines.append(f"   Domains: {domains_str}")

            # Show top 3 bullets with domain tags (uses _display_top3 which retains
            # match_factors so _format_bullet_token can fall back to ucb_score)
            for bullet in _display_top3:
                content = bullet.get('content', '')
                if len(content) > 80:
                    content = content[:77] + '...'
                domain = bullet.get('domain', 'general')
                token = _format_bullet_token(bullet)
                summary_lines.append(f"   • [{domain}] {content} ({token})")

            if pattern_count > 3:
                summary_lines.append(f"   ... and {pattern_count - 3} more bullets")

            user_message = "\n".join(summary_lines)
        else:
            user_message = "ℹ️  [ACE] No patterns found for this query"

        # v5.4.13: Prepend auth warning if detected (still show patterns if found)
        if auth_warning and pattern_count > 0:
            user_message = f"{auth_warning}\n\n{user_message}"

        # Output JSON with both user message and Claude context
        if pattern_count == 0:
            output = {"systemMessage": user_message}
        else:
            # Build session title — state + topic + ROI signal (UX pro max v3)
            # Shows VALUE (time saved from previous task's self-eval) not inventory.
            session_title = build_session_title(
                pattern_list=pattern_list,
                pattern_count=pattern_count,
                agent_type=agent_type,
            )

            hso = {"hookEventName": "UserPromptSubmit"}
            if ace_context is not None:
                # Budget or compact arm: inject additionalContext (control arm omits it)
                hso["additionalContext"] = ace_context
            # cc_hooks_reference.md ~1265/~1496: never clobber a custom /rename or --name title
            if not event.get('session_title'):
                hso["sessionTitle"] = session_title
            output = {"systemMessage": user_message, "hookSpecificOutput": hso}
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block workflow
        print(f"[ERROR] ACE before-task hook failed: {e}", file=sys.stderr)
        try:
            from ace_relevance_logger import log_error
            log_error('UserPromptSubmit', 'ace_before_task.main', error=e)
        except Exception:
            pass
        sys.exit(0)


if __name__ == '__main__':
    main()
