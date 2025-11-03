#!/bin/bash

# ACE PostToolUse Hook for Edit/Write Operations
# Reminds to invoke ace-learning skill after code modifications

cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "⚠️ CODE MODIFICATION DETECTED: You just used Edit or Write tools to modify code. After completing this implementation task, remember to invoke ace-learning skill to capture patterns learned during this work. This ensures organizational knowledge is preserved in the ACE playbook for future tasks."
  }
}
EOF
