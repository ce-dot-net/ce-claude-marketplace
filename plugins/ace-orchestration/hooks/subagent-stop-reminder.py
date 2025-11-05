#!/usr/bin/env python3
import json
import sys

# Read hook input from stdin
try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError:
    # If no input, just exit successfully
    sys.exit(0)

# Only show reminder if a subagent just finished (stop_hook_active might be True)
# This prevents infinite loops

output = {
    "systemMessage": "📚 ACE Learning: Capture lessons after subagent completion",
    "decision": "approve"  # Allow the subagent to stop normally
}

print(json.dumps(output))
sys.exit(0)
