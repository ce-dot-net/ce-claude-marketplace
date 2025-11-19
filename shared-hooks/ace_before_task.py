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

        # Call ce-ace search --stdin with optional session pinning
        # Context passed via environment, CLI reads server config for top_k/threshold
        patterns_response = run_search(
            query=user_prompt,
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
