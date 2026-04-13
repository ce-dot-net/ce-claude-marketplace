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
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, Any

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

from validation import is_valid_pattern_id


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

from ace_cli import run_search, check_session_pinning_available, check_auth_status
from ace_context import get_context
from ace_relevance_logger import log_search_metrics


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
            patterns_injected = eval_data.get('patterns_injected', 0)
            avg_relevance = eval_data.get('avg_relevance', 0)
            domains = eval_data.get('domains', 0)
            tools_executed = eval_data.get('tools_executed', 0)

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


def main():
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)
        user_prompt = event.get('prompt', '')

        if not user_prompt:
            # No prompt, nothing to search
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
        context = get_context()
        if not context:
            print("⚠️ [ACE] No project context found - skipping search")
            sys.exit(0)

        # Use Claude's session_id for state file consistency (Issue #16)
        # ace_after_task.py reads event.get('session_id') — we must use the same key
        session_id = event.get('session_id', str(uuid.uuid4()))
        use_session_pinning = check_session_pinning_available()

        # v6.0.0: Read agent_type natively from hook event (CC 2.1.69+)
        # agent_type identifies subagent type: "main", "refactorer", "coder", etc.
        agent_type = event.get('agent_type', 'main')

        # Store session ID for PreCompact hook (recall patterns after compaction)
        if use_session_pinning and context['project']:
            try:
                session_file = Path(f"/tmp/ace-session-{context['project']}.txt")
                session_file.write_text(session_id)
            except Exception:
                # Non-fatal: continue without session pinning
                use_session_pinning = False

        # v5.4.18: Granular token expiration check (warn if < 2 hours)
        # Catches 48h standby scenario AND warns before complex tasks
        auth_warning = check_auth_status(warn_threshold_hours=2.0)

        # Minimal enhancement: Expand abbreviations for semantic clarity
        # (Server team: DO NOT add generic keywords - hurts embedding quality!)
        search_query = expand_abbreviations(user_prompt)

        # Call ace-cli search --stdin with optional session pinning
        # Context passed via environment, CLI reads server config for top_k/threshold
        patterns_response = run_search(
            query=search_query,
            org=context['org'],
            project=context['project'],
            session_id=session_id if use_session_pinning else None
        )

        # v5.3.5: Sanitize response to remove invalid Unicode surrogates
        # These can break the Claude API's JSON parser
        if patterns_response:
            patterns_response = sanitize_response(patterns_response)

        # v5.4.21: Check for error responses from run_search()
        if not patterns_response:
            # Search failed - check if it's an auth error
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
                output = {"systemMessage": f"❌ [ACE] {error_msg}"}
            else:
                output = {"systemMessage": f"❌ [ACE] {error_msg}"}

            print(json.dumps(output))
            sys.exit(0)

        # Client-side filtering: Filter low-quality patterns (server team recommendation)
        # Only filter if we have enough results (keep at least 3)
        pattern_list = patterns_response.get('similar_patterns', [])
        original_pattern_list = list(pattern_list)  # Keep original for logging
        if len(pattern_list) > 5:
            # Filter: confidence >= 0.5 OR helpful >= 2
            high_quality = [p for p in pattern_list if p.get('confidence', 0) >= 0.5 or p.get('helpful', 0) >= 2]
            if len(high_quality) >= 3:
                pattern_list = high_quality
                patterns_response['similar_patterns'] = pattern_list
                patterns_response['count'] = len(pattern_list)

        # v5.4.2: Log relevance metrics for analysis
        try:
            domains = list(set(p.get('domain', 'unknown') for p in pattern_list if p.get('domain')))
            log_search_metrics(
                hook='UserPromptSubmit',
                session_id=session_id,
                user_prompt=user_prompt,
                search_query=search_query,
                patterns_returned=original_pattern_list,
                patterns_injected=pattern_list,
                domains=domains,
                project_id=context.get('project'),
                org_id=context.get('org'),
                agent_type=agent_type
            )
        except Exception:
            pass  # Non-fatal: continue without logging

        # CRITICAL: Save pattern IDs for reinforcement learning (ACE paper feedback loop)
        # When task completes, ace_after_task.py will load these IDs and include in ExecutionTrace
        # Server uses this to update 'helpful' scores for patterns that worked
        if pattern_list and context['project']:
            try:
                pattern_ids = [p.get('id') for p in pattern_list if p.get('id') and is_valid_pattern_id(p.get('id'))]
                if pattern_ids:
                    state_dir = Path('.claude/data/logs')
                    state_dir.mkdir(parents=True, exist_ok=True)
                    state_file = state_dir / f"ace-patterns-used-{session_id}.json"
                    # Append, don't overwrite — a task can have multiple searches
                    # (main agent + subagents, multiple prompts in same task)
                    existing = []
                    if state_file.exists():
                        try:
                            existing = json.loads(state_file.read_text())
                        except Exception:
                            existing = []
                    # Deduplicate while preserving order
                    seen = set(existing)
                    for pid in pattern_ids:
                        if pid not in seen:
                            existing.append(pid)
                            seen.add(pid)
                    state_file.write_text(json.dumps(existing))
            except Exception:
                # Non-fatal: continue without pattern tracking
                pass

        # v5.3.0: Store domains for PreToolUse hook (domain-aware reminders)
        # When Claude enters a new domain, hook can suggest targeted search
        # Extract domains from patterns if domains_summary is empty
        domains_summary = patterns_response.get('domains_summary', {})
        if not domains_summary:
            # Build domains from pattern list
            pattern_domains = {}
            for p in patterns_response.get('similar_patterns', []):
                domain = p.get('domain', '')
                if domain:
                    pattern_domains[domain] = pattern_domains.get(domain, 0) + 1
            domains_summary = pattern_domains

        if context['project'] and domains_summary:
            try:
                domains_file = Path(f"/tmp/ace-domains-{context['project']}.json")
                domains_file.write_text(json.dumps(domains_summary))
            except Exception:
                # Non-fatal: continue without domain tracking
                pass

        # Strip internal metadata fields from patterns before injection (reduce token usage)
        # These server-internal fields are stripped: 'created_at', 'updated_at', 'last_used',
        # 'impressions', 'retrieval_count', 'root_cause', 'error_context', 'source',
        # 'source_project_id', 'source_project_name', 'local_helpful', 'local_harmful',
        # 'match_factors', 'observations', 'name'
        useful_fields = {'id', 'domain', 'content', 'confidence', 'helpful', 'harmful', 'section', 'evidence'}
        if 'similar_patterns' in patterns_response:
            patterns_response['similar_patterns'] = [
                {k: v for k, v in p.items() if k in useful_fields}
                for p in patterns_response['similar_patterns']
            ]

        # Build context for Claude (JSON in XML tags - includes domain metadata)
        # v5.4.11: Include agent_type attribute for server-side pattern weighting
        ace_context = f'<ace-patterns agent-type="{agent_type}">\n{json.dumps(patterns_response)}\n</ace-patterns>'

        # Append fire-and-forget eval injection if present (from previous task's Stop hook)
        if eval_injection:
            ace_context = ace_context + "\n" + eval_injection

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

            # Show top 3 bullets with domain tags
            for bullet in pattern_list[:3]:
                content = bullet.get('content', '')
                if len(content) > 80:
                    content = content[:77] + '...'
                domain = bullet.get('domain', 'general')
                helpful = bullet.get('helpful', 0)
                summary_lines.append(f"   • [{domain}] {content} (+{helpful})")

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
            # Build session title from domains
            domains_list = sorted(set(p.get('domain', '') for p in pattern_list if p.get('domain')))[:3]
            session_title = f"ACE: {pattern_count} patterns"
            if domains_list:
                session_title += f" · {', '.join(domains_list)}"

            output = {
                "systemMessage": user_message,
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": ace_context,
                    "sessionTitle": session_title
                }
            }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block workflow
        print(f"[ERROR] ACE before-task hook failed: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
