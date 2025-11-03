#!/bin/bash

# ACE PostToolUse Hook for ExitPlanMode
# Injects context to trigger ace-playbook-retrieval skill after exiting plan mode

cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "🚨 CRITICAL ACE INSTRUCTION: You have just exited plan mode and are transitioning to execution mode. The user has approved your plan and expects implementation to begin. BEFORE using any Edit, Write, or Bash tools for implementation, you MUST invoke the ace-playbook-retrieval skill to retrieve learned patterns from the ACE playbook. This is NOT optional - implementation requires organizational knowledge from the ACE playbook. Syntax: Skill: ace-orchestration:ace-playbook-retrieval"
  }
}
EOF
