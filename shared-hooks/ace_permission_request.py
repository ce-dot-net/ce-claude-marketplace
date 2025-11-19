#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE Permission Request Hook - Auto-approve safe ACE CLI commands

Auto-approves safe read-only ACE commands:
- ce-ace search, status, patterns, top, get-playbook, doctor
- ce-ace tune (read config)

Auto-denies dangerous destructive commands:
- ce-ace clear (requires explicit user confirmation)

All other commands pass through for user decision.
"""

import json
import sys


def main():
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)

        # Extract tool information
        tool_name = event.get('tool_name', '')
        command = event.get('command', '')

        # Only handle Bash tool permissions
        if tool_name != 'Bash':
            # Pass through - let user decide
            print(json.dumps({}))
            sys.exit(0)

        # Check for ACE CLI commands
        if 'ce-ace' not in command:
            # Not an ACE command - pass through
            print(json.dumps({}))
            sys.exit(0)

        # Auto-approve safe read-only ACE commands
        safe_commands = [
            'ce-ace search',
            'ce-ace status',
            'ce-ace patterns',
            'ce-ace top',
            'ce-ace get-playbook',
            'ce-ace doctor',
            'ce-ace tune'  # Read config only
        ]

        for safe_cmd in safe_commands:
            if safe_cmd in command:
                # Auto-approve with informative message
                output = {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "allow",
                        "message": f"✅ [ACE] Auto-approved: {safe_cmd}"
                    }
                }
                print(json.dumps(output))
                sys.exit(0)

        # Auto-deny dangerous commands
        dangerous_commands = [
            'ce-ace clear'
        ]

        for dangerous_cmd in dangerous_commands:
            if dangerous_cmd in command:
                # Auto-deny with helpful message
                output = {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": f"⛔ [ACE] Blocked destructive command: {dangerous_cmd}\nUse `/ace-clear` command for confirmation prompts."
                    }
                }
                print(json.dumps(output))
                sys.exit(0)

        # For commands like 'ce-ace learn', 'ce-ace bootstrap' - let user decide
        # These modify data but are not destructive
        print(json.dumps({}))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block permission request
        print(f"[ERROR] ACE permission hook failed: {e}", file=sys.stderr)
        print(json.dumps({}))
        sys.exit(0)


if __name__ == '__main__':
    main()
