#!/usr/bin/env python3
import json
import sys

output = {
    "systemMessage": "🔍 ACE: Use Retrieval → Work → Learning workflow",
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "\n🔍 ACE WORKFLOW REMINDER:\n\nBEFORE starting: Invoke ACE Retrieval subagent to fetch relevant patterns\nAFTER completion: Invoke ACE Learning subagent to capture new lessons\n\nSequential workflow: Retrieval → Work → Learning\n"
    }
}

print(json.dumps(output))
sys.exit(0)
