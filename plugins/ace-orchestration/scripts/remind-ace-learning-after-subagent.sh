#!/bin/bash

# ACE SubagentStop Hook
# Reminds parent agent to invoke ace-learning after subagent completes substantial work

# Get the stop_hook_active flag to prevent infinite loops
STOP_HOOK_ACTIVE="${stop_hook_active:-false}"

# Only proceed if not already in a stop hook cycle
if [ "$STOP_HOOK_ACTIVE" = "false" ]; then
  cat <<'EOF'
{
  "decision": "block",
  "reason": "⚠️ SUBAGENT TASK COMPLETED: A subagent has finished substantial technical work. Before responding to the user, you MUST invoke ace-learning skill to capture patterns and lessons learned from this subagent's execution. This is part of the mandatory ACE training cycle. Syntax: Skill: ace-orchestration:ace-learning",
  "hookSpecificOutput": {
    "hookEventName": "SubagentStop",
    "additionalContext": "Subagent completed - invoke ace-learning skill to capture organizational knowledge from this execution."
  }
}
EOF
else
  # Already in stop hook, don't block again
  cat <<'EOF'
{
  "continue": true
}
EOF
fi
