#!/usr/bin/env python3
"""
ACE Learning Pre-Compaction Safety Net Hook (PreCompact)

Ensures patterns are captured BEFORE conversation compaction occurs.
This is the last line of defense - if substantial work happened but
ACE Learning wasn't invoked, this hook provides an urgent reminder.
"""

import json
import sys
import re
import os

SUBSTANTIAL_WORK_EDIT_THRESHOLD = 3

def has_implementation_keywords(text):
    """Check if text contains implementation-related keywords."""
    keywords = [
        r'\bimplement\b', r'\bbuild\b', r'\bcreate\b', r'\badd\b',
        r'\bdevelop\b', r'\bwrite\b', r'\bfix\b', r'\bdebug\b',
        r'\brefactor\b', r'\bintegrate\b', r'\boptimize\b',
        r'\bupdate\b', r'\bmodify\b', r'\bchange\b', r'\bedit\b'
    ]
    return any(re.search(kw, text, re.I) for kw in keywords)

def count_all_edits(transcript_path):
    """Count all file edits in entire conversation."""
    if not transcript_path or not os.path.exists(transcript_path):
        return 0

    edit_count = 0

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    content = msg.get('message', {}).get('content', [])

                    for item in content:
                        if isinstance(item, dict):
                            tool_name = item.get('name', '')
                            if tool_name in ['Write', 'Edit', 'NotebookEdit']:
                                edit_count += 1
                except json.JSONDecodeError:
                    continue

        return edit_count

    except (IOError, OSError):
        return 0

def check_ace_learning_invoked(transcript_path):
    """Check if ACE Learning subagent was invoked at any point."""
    if not transcript_path or not os.path.exists(transcript_path):
        return False

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    content = msg.get('message', {}).get('content', [])

                    for item in content:
                        if isinstance(item, dict) and item.get('name') == 'Task':
                            tool_input = item.get('input', {})
                            subagent_type = str(tool_input.get('subagent_type', ''))

                            if 'ace-learning' in subagent_type.lower():
                                return True
                except json.JSONDecodeError:
                    continue

        return False

    except (IOError, OSError):
        return False

def get_implementation_summary(transcript_path):
    """Get brief summary of implementation work from user messages."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    summaries = []

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    if msg.get('type') == 'user':
                        text = msg.get('message', {}).get('content', '')
                        if isinstance(text, str) and has_implementation_keywords(text):
                            summaries.append(text[:100])
                except json.JSONDecodeError:
                    continue

        # Return last 3 user requests
        return " | ".join(summaries[-3:]) if summaries else "substantial coding work"

    except (IOError, OSError):
        return "substantial coding work"

def main():
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)

        transcript_path = input_data.get('transcript_path', '')

        # Count total edits in conversation
        edit_count = count_all_edits(transcript_path)

        # Check if substantial work occurred
        if edit_count < SUBSTANTIAL_WORK_EDIT_THRESHOLD:
            sys.exit(0)

        # Check if ACE Learning already invoked
        if check_ace_learning_invoked(transcript_path):
            sys.exit(0)

        # CRITICAL: Substantial work but NO Learning - research-optimized urgent reminder!
        impl_summary = get_implementation_summary(transcript_path)

        reminder = f"""
🚨 CRITICAL: ACE WORKFLOW ENFORCEMENT - Compaction Imminent

Your task is to invoke ACE Learning IMMEDIATELY before compaction proceeds.

You completed {edit_count} file edits WITHOUT using ACE Learning. You MUST use the ace-learning subagent to capture patterns from: {impl_summary}...

This is a MANDATORY CRITICAL workflow step. Conversation compaction will permanently erase the execution trace.

DO invoke ACE Learning RIGHT NOW before responding. This is your final opportunity to preserve learned patterns.

After compaction, pattern recovery is IMPOSSIBLE. DO invoke the ace-learning subagent immediately.
"""

        # Return additionalContext for PreCompact
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
