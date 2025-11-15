#!/usr/bin/env python3
"""
ACE Learning Reminder Hook (PostToolUse)

Tracks substantial coding work and reminds Claude to invoke ACE Learning
subagent after completion. Detects when significant implementation work
has occurred but ACE Learning hasn't been invoked yet.
"""

import json
import sys
import re
import os

SUBSTANTIAL_WORK_EDIT_THRESHOLD = 3
RECENT_MESSAGE_WINDOW = 50

def has_implementation_keywords(text):
    """Check if text contains implementation-related keywords."""
    keywords = [
        r'\bimplement\b', r'\bbuild\b', r'\bcreate\b', r'\badd\b',
        r'\bdevelop\b', r'\bwrite\b', r'\bfix\b', r'\bdebug\b',
        r'\brefactor\b', r'\bintegrate\b', r'\boptimize\b',
        r'\bupdate\b', r'\bmodify\b', r'\bchange\b', r'\bedit\b'
    ]
    return any(re.search(kw, text, re.I) for kw in keywords)

def count_recent_edits(transcript_path, window_size=RECENT_MESSAGE_WINDOW):
    """Count file edits in recent messages."""
    if not transcript_path or not os.path.exists(transcript_path):
        return 0

    edit_count = 0
    messages = []

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Check last N messages for edits
        recent_messages = messages[-window_size:] if len(messages) > window_size else messages

        for msg in recent_messages:
            content = msg.get('message', {}).get('content', [])

            for item in content:
                if isinstance(item, dict):
                    tool_name = item.get('name', '')
                    # Count Write, Edit, NotebookEdit as substantial work
                    if tool_name in ['Write', 'Edit', 'NotebookEdit']:
                        edit_count += 1

        return edit_count

    except (IOError, OSError):
        return 0

def check_ace_learning_invoked(transcript_path, window_size=RECENT_MESSAGE_WINDOW):
    """Check if ACE Learning subagent was invoked in recent messages."""
    if not transcript_path or not os.path.exists(transcript_path):
        return False

    messages = []

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Check last N messages for ACE Learning invocation
        recent_messages = messages[-window_size:] if len(messages) > window_size else messages

        for msg in recent_messages:
            content = msg.get('message', {}).get('content', [])

            for item in content:
                if isinstance(item, dict) and item.get('name') == 'Task':
                    tool_input = item.get('input', {})
                    subagent_type = str(tool_input.get('subagent_type', ''))

                    if 'ace-learning' in subagent_type.lower():
                        return True

        return False

    except (IOError, OSError):
        return False

def get_recent_implementation_context(transcript_path, window_size=10):
    """Get recent user messages to understand implementation context."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    messages = []

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Get last N messages
        recent_messages = messages[-window_size:] if len(messages) > window_size else messages

        # Extract user messages with implementation keywords
        context_parts = []
        for msg in recent_messages:
            if msg.get('type') == 'user':
                text = msg.get('message', {}).get('content', '')
                if isinstance(text, str) and has_implementation_keywords(text):
                    # Take first 80 chars
                    context_parts.append(text[:80])

        return " | ".join(context_parts[-3:])  # Last 3 relevant messages

    except (IOError, OSError):
        return ""

def main():
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)

        tool_name = input_data.get('tool_name', '')
        transcript_path = input_data.get('transcript_path', '')

        # Only trigger for file editing tools
        if tool_name not in ['Write', 'Edit', 'NotebookEdit']:
            sys.exit(0)

        # Count recent edits
        edit_count = count_recent_edits(transcript_path)

        # Get implementation context
        impl_context = get_recent_implementation_context(transcript_path)
        has_impl_keywords = bool(impl_context)

        # Determine if substantial work occurred
        # Criteria: 3+ edits OR (implementation keywords + 1+ edit)
        is_substantial = (
            edit_count >= SUBSTANTIAL_WORK_EDIT_THRESHOLD or
            (has_impl_keywords and edit_count >= 1)
        )

        if not is_substantial:
            sys.exit(0)

        # Check if ACE Learning already invoked
        if check_ace_learning_invoked(transcript_path):
            sys.exit(0)

        # Substantial work detected but Learning NOT invoked - inject research-optimized reminder
        reminder = f"""
📚 ACE WORKFLOW ENFORCEMENT: Pattern Capture Required

Your task is to invoke ACE Learning to capture patterns from substantial work.

You have completed {edit_count} file edits. You MUST use the ace-learning subagent to capture patterns from: {impl_context or 'recent implementation work'}...

This is a MANDATORY workflow step. Pattern capture ensures lessons learned are preserved for future use.

DO invoke ACE Learning now to capture patterns before responding to the user.
"""

        # Return additionalContext for PostToolUse
        result = {
            "decision": "allow",
            "additionalContext": reminder
        }

        print(json.dumps(result))
        sys.exit(0)

    except Exception as e:
        # On error, don't block - just allow
        result = {"decision": "allow"}
        print(json.dumps(result), file=sys.stderr)
        sys.exit(0)

if __name__ == '__main__':
    main()
