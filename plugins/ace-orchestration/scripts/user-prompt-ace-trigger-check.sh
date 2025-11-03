#!/bin/bash

# ACE UserPromptSubmit Hook
# Checks user prompt for trigger keywords and reminds to invoke skills

USER_PROMPT="$1"

# Check for ACE trigger keywords
if echo "$USER_PROMPT" | grep -qiE '(implement|build|create|add|develop|write|update|modify|change|edit|enhance|extend|revise|fix|debug|troubleshoot|resolve|diagnose|refactor|optimize|improve|restructure|integrate|connect|setup|configure|install|architect|design|plan|test|verify|validate|deploy|migrate|upgrade)'; then
  cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "additionalContext": "⚠️ ACE TRIGGER DETECTED: This user message contains ACE trigger keywords. BEFORE using any implementation tools (Edit, Write, Bash), invoke ace-playbook-retrieval skill to retrieve organizational patterns. After completing substantial work, invoke ace-learning skill to capture new patterns."
  }
}
EOF
else
  # No trigger keywords, but check for plan approval patterns
  if echo "$USER_PROMPT" | grep -qiE '^(continue|proceed|looks good|implement it|go ahead|do it|yes|approve|ok)$'; then
    cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "additionalContext": "⚠️ POSSIBLE PLAN APPROVAL: User message may be approving a plan. If you just showed a plan and are about to implement, ensure ace-playbook-retrieval skill is invoked before starting implementation."
  }
}
EOF
  fi
fi
