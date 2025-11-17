#!/usr/bin/env python3
"""
ACE After Task Hook - PreCompact Event Handler

Reminds user to capture learning from completed work.
Future: Could auto-call ce-ace learn --stdin with transcript summary.
"""

import json
import sys


def main():
    try:
        # Read hook event from stdin (currently unused but available for future)
        event = json.load(sys.stdin)

        # Simple reminder for now
        # Future: Could analyze transcript and auto-call ce-ace learn
        print()
        print("📚 [ACE] Reminder: If you completed substantial work, capture it:")
        print("   /ace-learn")
        print()

        sys.exit(0)

    except Exception as e:
        # Log error but don't block compaction
        print(f"[ERROR] ACE after-task hook failed: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
