#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE Before Task Hook - UserPromptSubmit Event Handler

Searches ACE playbook for relevant patterns when user starts a task.
Uses ce-ace search --stdin to avoid shell escaping issues.
Supports session pinning (v1.0.11+) for pattern persistence across compaction.
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Dict, Any

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_cli import run_search, check_session_pinning_available
from ace_context import get_context


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

        # Skip slash commands (e.g., /plugin, /ace-configure, etc.)
        if user_prompt.strip().startswith('/'):
            sys.exit(0)

        # Get project context from .claude/settings.json
        context = get_context()
        if not context:
            print("⚠️ [ACE] No project context found - skipping search")
            sys.exit(0)

        # Generate unique session ID for pattern pinning
        session_id = str(uuid.uuid4())
        use_session_pinning = check_session_pinning_available()

        # Store session ID for PreCompact hook (recall patterns after compaction)
        if use_session_pinning and context['project']:
            try:
                session_file = Path(f"/tmp/ace-session-{context['project']}.txt")
                session_file.write_text(session_id)
            except Exception:
                # Non-fatal: continue without session pinning
                use_session_pinning = False

        # Minimal enhancement: Expand abbreviations for semantic clarity
        # (Server team: DO NOT add generic keywords - hurts embedding quality!)
        search_query = expand_abbreviations(user_prompt)

        # Call ce-ace search --stdin with optional session pinning
        # Context passed via environment, CLI reads server config for top_k/threshold
        patterns_response = run_search(
            query=search_query,
            org=context['org'],
            project=context['project'],
            session_id=session_id if use_session_pinning else None
        )

        if not patterns_response:
            # Search failed - show error to user
            output = {
                "systemMessage": "❌ [ACE] Search failed or returned no results"
            }
            print(json.dumps(output))
            sys.exit(0)

        # Client-side filtering: Filter low-quality patterns (server team recommendation)
        # Only filter if we have enough results (keep at least 3)
        pattern_list = patterns_response.get('similar_patterns', [])
        if len(pattern_list) > 5:
            # Filter: confidence >= 0.5 OR helpful >= 2
            high_quality = [p for p in pattern_list if p.get('confidence', 0) >= 0.5 or p.get('helpful', 0) >= 2]
            if len(high_quality) >= 3:
                pattern_list = high_quality
                patterns_response['similar_patterns'] = pattern_list
                patterns_response['count'] = len(pattern_list)

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
        domains_summary = patterns_response.get('domains_summary', {})
        if context['project'] and domains_summary:
            try:
                domains_file = Path(f"/tmp/ace-domains-{context['project']}.json")
                domains_file.write_text(json.dumps(domains_summary))
            except Exception:
                # Non-fatal: continue without domain tracking
                pass

        # Build context for Claude (JSON in XML tags - includes domain metadata)
        ace_context = f"<ace-patterns>\n{json.dumps(patterns_response, indent=2)}\n</ace-patterns>"

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
