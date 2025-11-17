#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE Before Task Hook - UserPromptSubmit Event Handler

Searches ACE playbook for relevant patterns when user starts a task.
Uses ce-ace search --stdin to avoid shell escaping issues.
"""

import json
import sys
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_cli import run_search
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

        # Always show that search is running
        print("🔍 [ACE] Searching playbook...")

        # Call ce-ace search --stdin
        patterns = run_search(
            query=user_prompt,
            org=context['org'],
            project=context['project'],
            threshold=0.85
        )

        if not patterns:
            # Search failed or returned no results
            print("❌ [ACE] Search failed or returned no results")
            sys.exit(0)

        # Output for Claude (hidden context block)
        print("<ace-patterns>")
        print(json.dumps(patterns, indent=2))
        print("</ace-patterns>")

        # Output for user (visible summary)
        pattern_list = patterns.get('similar_patterns', [])
        pattern_count = len(pattern_list)

        if pattern_count > 0:
            print(f"✅ [ACE] Found {pattern_count} relevant patterns:")
            for pattern in pattern_list[:5]:
                content = pattern.get('content', '')
                # Truncate long content
                if len(content) > 80:
                    content = content[:77] + '...'
                helpful = pattern.get('helpful', 0)
                print(f"   • {content} (+{helpful} helpful)")
        else:
            print("ℹ️  [ACE] Playbook is empty - no patterns found (try /ace-bootstrap)")

        sys.exit(0)

    except Exception as e:
        # Log error but don't block workflow
        print(f"[ERROR] ACE before-task hook failed: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
