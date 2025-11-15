#!/usr/bin/env python3
"""
ACE Retrieval Enforcement Hook (UserPromptSubmit)

Ensures ACE Retrieval subagent is invoked BEFORE implementation work begins.
Reads transcript to check if ACE Retrieval was already invoked, and injects
strong reminder if not.
"""

import json
import sys
import re
import os

def has_implementation_keywords(prompt):
    """Check if prompt contains implementation-related keywords."""
    keywords = [
        r'\bimplement\b', r'\bbuild\b', r'\bcreate\b', r'\badd\b',
        r'\bdevelop\b', r'\bwrite\b', r'\bfix\b', r'\bdebug\b',
        r'\brefactor\b', r'\bintegrate\b', r'\boptimize\b',
        r'\bupdate\b', r'\bmodify\b', r'\bchange\b', r'\bedit\b'
    ]
    return any(re.search(kw, prompt, re.I) for kw in keywords)

def check_ace_retrieval_invoked(transcript_path):
    """Check if ACE Retrieval subagent was already invoked in this session."""
    if not transcript_path or not os.path.exists(transcript_path):
        return False

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    content = msg.get('message', {}).get('content', [])

                    # Check for Task tool use with ace-retrieval subagent
                    for item in content:
                        if isinstance(item, dict) and item.get('name') == 'Task':
                            tool_input = item.get('input', {})
                            subagent_type = str(tool_input.get('subagent_type', ''))

                            if 'ace-retrieval' in subagent_type.lower():
                                return True
                except json.JSONDecodeError:
                    continue
    except (IOError, OSError):
        pass

    return False

def main():
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)

        prompt = input_data.get('prompt', '')
        transcript_path = input_data.get('transcript_path', '')

        # Skip if not implementation work
        if not has_implementation_keywords(prompt):
            sys.exit(0)

        # Skip if ACE Retrieval already invoked
        if check_ace_retrieval_invoked(transcript_path):
            sys.exit(0)

        # ACE Retrieval NOT invoked - inject research-optimized reminder
        reminder = f"""
🚨 ACE WORKFLOW ENFORCEMENT

Your task is to invoke ACE Retrieval BEFORE proceeding with implementation.

You MUST use the ace-retrieval subagent to search for patterns about: {prompt[:80]}...

This is a MANDATORY workflow step. Retrieval provides proven patterns from past similar work.

DO invoke ACE Retrieval now before proceeding with implementation.
"""

        # Output using simple stdout (UserPromptSubmit special case)
        print(reminder)
        sys.exit(0)

    except Exception as e:
        # On error, don't block - just log and continue
        print(f"ACE hook error: {e}", file=sys.stderr)
        sys.exit(0)

if __name__ == '__main__':
    main()
