#!/usr/bin/env bash
# ACE PreCompact Hook - Pattern Preservation
# v5.4.7: Flag file check + ace-cli/ace-cli detection
#
# When context gets compacted, injected patterns are lost. This hook:
# 1. Reads the session ID from UserPromptSubmit
# 2. Calls ace-cli cache recall to get pinned patterns
# 3. Re-injects them as additionalContext (survives compaction)

set -euo pipefail

ACE_PLUGIN_VERSION="5.4.7"

# ACE disable flag check (set by SessionStart if CLI issues detected)
# Official Claude Code pattern: flag file coordination between hooks
SESSION_ID_FOR_FLAG="${SESSION_ID:-default}"
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID_FOR_FLAG}.flag"
if [ -f "$ACE_DISABLED_FLAG" ]; then
  # ACE is disabled for this session - exit silently
  exit 0
fi

# CLI command detection (ace-cli preferred, ace-cli fallback)
if command -v ace-cli >/dev/null 2>&1; then
  CLI_CMD="ace-cli"
elif command -v ce-ace >/dev/null 2>&1; then
  CLI_CMD="ce-ace"
else
  exit 0  # No CLI available - exit silently
fi

# Get project context
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
export ACE_ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
export ACE_PROJECT_ID="$PROJECT_ID"

# No project context - exit silently
if [ -z "$PROJECT_ID" ]; then
  exit 0
fi

# Read session ID from UserPromptSubmit hook
SESSION_FILE="/tmp/ace-session-${PROJECT_ID}.txt"
if [ ! -f "$SESSION_FILE" ]; then
  exit 0  # No session, nothing to recall
fi
SESSION_ID=$(cat "$SESSION_FILE")

# CLI already verified by flag file check above

# Recall patterns from session cache (fast SQLite lookup, ~10ms)
# Filter out CLI update notifications that break JSON parsing
RAW_PATTERNS=$($CLI_CMD cache recall --session "$SESSION_ID" --json 2>&1) || true
PATTERNS=$(echo "$RAW_PATTERNS" | grep -v "^💡" | grep -v "^$" || echo "{}")

# Parse count (default to 0 if parsing fails)
COUNT=$(echo "$PATTERNS" | jq -r '.count // 0' 2>/dev/null || echo "0")

if [ "$COUNT" = "0" ] || [ "$COUNT" = "null" ]; then
  exit 0  # No patterns to recall
fi

# Format patterns for injection
FORMATTED=$(echo "$PATTERNS" | jq -r '.similar_patterns[] | "• [\(.section // "general")] \(.content)"' 2>/dev/null || echo "")

if [ -z "$FORMATTED" ]; then
  exit 0
fi

# Output as hookSpecificOutput with additionalContext
# This survives context compaction and keeps patterns in Claude's context
jq -n \
  --arg patterns "$FORMATTED" \
  --arg session "$SESSION_ID" \
  --arg count "$COUNT" \
  '{
    "systemMessage": "📚 [ACE] Preserved \($count) patterns through compaction",
    "hookSpecificOutput": {
      "hookEventName": "PreCompact",
      "additionalContext": "<!-- ACE Patterns (preserved from session \($session)) -->\n<ace-patterns-recalled>\n\($patterns)\n</ace-patterns-recalled>"
    }
  }'
