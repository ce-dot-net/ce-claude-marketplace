#!/usr/bin/env python3
"""
Shows the exact JSON payload sent to ace_learn via PostToolUse hook.
This is what the server receives for pattern extraction.
"""

import json
from datetime import datetime

# Simulated example based on v5.3.7 release task
execution_trace = {
    "task": "User request: use release manager subagent please :)",
    "trajectory": [
        {
            "step": 1,
            "action": "Made architectural decisions",
            "result": "Using release-manager subagent for version synchronization | Two-commit strategy for clean git history | Pattern tracking enables reinforcement learning"
        },
        {
            "step": 2,
            "action": "Completed work items",
            "result": "Updated shared-hooks/ace_before_task.py with pattern ID saving | Updated shared-hooks/ace_after_task.py with pattern ID loading | Released v5.3.7 with all files synchronized"
        }
    ],
    "result": {
        "success": True,
        "output": "I'll mark the release task as completed since v5.3.7 was successfully released. | ✅ Release v5.3.7 Completed | The pattern usage tracking fix has been successfully released | Files modified: shared-hooks/ace_before_task.py, shared-hooks/ace_after_task.py, plugins/ace/plugin.json, plugins/ace/marketplace.json, plugins/ace/CLAUDE.md"
    },
    "playbook_used": [
        "ctx-1749038481-2b49",  # Version management: two-commit strategy
        "ctx-2281764104-5985",  # MCP diagnostic strategy
        "ctx-1749038478-cca0",  # ACE skill frontmatter
        "ctx-1949337433-780a",  # Skill trigger reliability
        "ctx-3252392215-0e4f",  # Utility function design
        "ctx-3394741097-2d88",  # JWT token validation
        "ctx-3553687869-1a94",  # Auto-captured session learning
    ],
    "timestamp": datetime.now().isoformat()
}

print("=" * 80)
print("EXACT JSON SENT TO: ce-ace learn --stdin")
print("=" * 80)
print(json.dumps(execution_trace, indent=2))
print("=" * 80)
print(f"\nKey Details:")
print(f"  - Task: {len(execution_trace['task'])} chars")
print(f"  - Trajectory steps: {len(execution_trace['trajectory'])}")
print(f"  - Pattern IDs used: {len(execution_trace['playbook_used'])}")
print(f"  - Output/lessons: {len(execution_trace['result']['output'])} chars")
print(f"  - Success: {execution_trace['result']['success']}")
print("\n✅ Server receives this JSON and extracts patterns using Reflector (Sonnet 4)")
