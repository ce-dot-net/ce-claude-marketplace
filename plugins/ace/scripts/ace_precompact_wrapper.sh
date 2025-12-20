#!/usr/bin/env bash
# ACE PreCompact Hook - Pattern Preservation
# v5.3.0: Recalls session patterns before context compaction so they survive
#
# When context gets compacted, injected patterns are lost. This hook:
# 1. Reads the session ID from UserPromptSubmit
# 2. Calls ce-ace cache recall to get pinned patterns
# 3. Re-injects them as additionalContext (survives compaction)

set -euo pipefail

ACE_PLUGIN_VERSION="5.3.0"

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

# Check if ce-ace CLI is available
if ! command -v ce-ace >/dev/null 2>&1; then
  exit 0  # CLI not installed, skip silently
fi

# Recall patterns from session cache (fast SQLite lookup, ~10ms)
# Filter out CLI update notifications that break JSON parsing
RAW_PATTERNS=$(ce-ace cache recall --session "$SESSION_ID" --json 2>&1) || true
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
