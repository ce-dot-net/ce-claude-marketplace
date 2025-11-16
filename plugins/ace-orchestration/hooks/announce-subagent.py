#!/usr/bin/env python3
"""
Subagent Completion Announcement Hook (PostToolUse)

Fires when Task tool completes with a subagent, reminding Claude to
announce the subagent's completion and summarize its output for conversation visibility.
"""

import json
import sys

def main():
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)

        tool_name = input_data.get('tool_name', '')

        # Only trigger for Task tool (subagent invocations)
        if tool_name != 'Task':
            sys.exit(0)

        # Extract subagent info from tool_input
        tool_input = input_data.get('tool_input', {})
        subagent_type = tool_input.get('subagent_type', '')

        # Only trigger if this was a subagent invocation
        if not subagent_type:
            sys.exit(0)

        # Determine which subagent completed
        subagent_name = subagent_type.replace('ace-orchestration:', '').replace('-', ' ').title()

        # Inject reminder to announce subagent completion
        reminder = f"""
✅ Subagent Execution Complete

The {subagent_name} subagent just finished running.

For conversation visibility, you should announce:
1. What subagent just ran (e.g., "[ACE Retrieval] completed" or "[ACE Learning] completed")
2. Brief summary of what it returned (patterns found, patterns saved, etc.)
3. Any next steps based on the subagent's output

This helps the user see the subagent execution in the conversation without CLI debug flags.
"""

        # Print reminder directly (same format as other hooks)
        print(reminder)
        sys.exit(0)

    except Exception as e:
        # On error, don't block - just exit silently
        sys.exit(0)

if __name__ == '__main__':
    main()
