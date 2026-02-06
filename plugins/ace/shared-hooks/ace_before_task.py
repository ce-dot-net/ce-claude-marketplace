#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
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


def main():
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)
        user_prompt = event.get('prompt', '')

        if not user_prompt:
            # No prompt, nothing to search
            sys.exit(0)

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

        # v5.4.11: Read agent_type set by SessionStart hook (Claude Code 2.1.2+)
        # agent_type identifies subagent type: "main", "refactorer", "coder", etc.
        agent_type = "main"
        try:
            # SessionStart creates this file with agent_type from Claude Code input
            agent_type_file = Path(f"/tmp/ace-agent-type-{event.get('session_id', 'default')}.txt")
            if agent_type_file.exists():
                agent_type = agent_type_file.read_text().strip() or "main"
        except Exception:
            pass  # Default to "main" if file not found or unreadable

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
                org_id=context.get('org')
            )
        except Exception:
            pass  # Non-fatal: continue without logging

        # CRITICAL: Save pattern IDs for reinforcement learning (ACE paper feedback loop)
        # When task completes, ace_after_task.py will load these IDs and include in ExecutionTrace
        # Server uses this to update 'helpful' scores for patterns that worked
        if pattern_list and context['project']:
            try:
                pattern_ids = [p.get('id') for p in pattern_list if p.get('id')]
                if pattern_ids:
                    state_dir = Path('.claude/data/logs')
                    state_dir.mkdir(parents=True, exist_ok=True)
                    state_file = state_dir / f"ace-patterns-used-{session_id}.json"
                    state_file.write_text(json.dumps(pattern_ids))
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

        # Build context for Claude (JSON in XML tags - includes domain metadata)
        # v5.4.11: Include agent_type attribute for server-side pattern weighting
        ace_context = f'<ace-patterns agent-type="{agent_type}">\n{json.dumps(patterns_response, indent=2)}\n</ace-patterns>'

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
        output = {
            "systemMessage": user_message,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": ace_context
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
