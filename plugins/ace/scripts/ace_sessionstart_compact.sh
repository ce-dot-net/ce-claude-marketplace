#!/usr/bin/env bash
# ACE SessionStart(compact) Hook - Pattern Injection After Compaction
# v5.4.28: Fix Issue #17 - PreCompact → SessionStart handoff
#
# When context gets compacted, this hook fires AFTER compaction (matcher: "compact")
# and re-injects patterns that PreCompact saved to a temp file.
#
# Why this design:
# - PreCompact hooks don't support hookSpecificOutput (Claude Code limitation)
# - SessionStart hooks DO support hookSpecificOutput.additionalContext
# - This is the official pattern for preserving context through compaction

set -euo pipefail

# Read stdin JSON (SessionStart provides session_id)
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# ACE disable flag check (consistent with all other hooks)
SESSION_ID_FOR_FLAG=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
SESSION_ID_FOR_FLAG="${SESSION_ID_FOR_FLAG:-default}"
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID_FOR_FLAG}.flag"
if [ -f "$ACE_DISABLED_FLAG" ]; then
  exit 0
fi

# Resolve SESSION_ID using same source as PreCompact (ace-session file)
# PreCompact reads from /tmp/ace-session-${PROJECT_ID}.txt, so we must too
# to ensure temp file paths match. Stdin session_id is fallback only.
# NOTE: Reads .claude/settings.json from CWD (Claude Code sets CWD to project root)
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
SESSION_FILE="/tmp/ace-session-${PROJECT_ID}.txt"

if [ -n "$PROJECT_ID" ] && [ -f "$SESSION_FILE" ]; then
  # Primary: same source as PreCompact
  SESSION_ID=$(cat "$SESSION_FILE" 2>/dev/null || echo "")
fi

# Fallback: stdin session_id (if ace-session file unavailable)
if [ -z "${SESSION_ID:-}" ]; then
  SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
  SESSION_ID="${SESSION_ID:-default}"
fi

# Check for temp file created by PreCompact hook
TEMP_FILE="/tmp/ace-patterns-precompact-${SESSION_ID}.json"

if [ ! -f "$TEMP_FILE" ]; then
  # No patterns to restore - exit silently
  exit 0
fi

# Read patterns from temp file
PATTERN_DATA=$(cat "$TEMP_FILE" 2>/dev/null || echo "{}")
PATTERNS=$(echo "$PATTERN_DATA" | jq -r '.patterns // ""' 2>/dev/null || echo "")
COUNT=$(echo "$PATTERN_DATA" | jq -r '.count // "0"' 2>/dev/null || echo "0")

# Cleanup temp file
rm -f "$TEMP_FILE" 2>/dev/null || true

# If no patterns, exit silently
if [ -z "$PATTERNS" ] || [ "$COUNT" = "0" ]; then
  exit 0
fi

# Output valid hookSpecificOutput with additionalContext
# hookEventName: "SessionStart" is valid (PreCompact is not)
jq -n \
  --arg patterns "$PATTERNS" \
  --arg session "$SESSION_ID" \
  --arg count "$COUNT" \
  '{
    "systemMessage": "📚 [ACE] Restored \($count) patterns after compaction",
    "hookSpecificOutput": {
      "hookEventName": "SessionStart",
      "additionalContext": "<!-- ACE Patterns (preserved from session \($session)) -->\n<ace-patterns-recalled>\n\($patterns)\n</ace-patterns-recalled>"
    }
  }'
