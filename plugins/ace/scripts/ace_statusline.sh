#!/usr/bin/env bash
# ACE Statusline Script - Reads CC JSON from stdin + ACE state files
# No network calls — all from local files only
set -eo pipefail

# Read CC JSON from stdin (model, context_window, cost, etc.)
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# Extract CC fields from stdin
display_name=$(echo "$INPUT_JSON" | jq -r '.display_name // .model // "unknown"' 2>/dev/null || echo "unknown")
context_window=$(echo "$INPUT_JSON" | jq -r '.context_window // 0' 2>/dev/null || echo "0")
used_percentage=$(echo "$INPUT_JSON" | jq -r '.used_percentage // 0' 2>/dev/null || echo "0")
remaining=$(echo "$INPUT_JSON" | jq -r '.remaining // 0' 2>/dev/null || echo "0")

# ACE state file paths
USAGE_DIR="${HOME}/.claude/usage-data"
STATE_FILE="${USAGE_DIR}/ace-statusline-state.json"
RELEVANCE_FILE="${USAGE_DIR}/ace-relevance.jsonl"

# Default values
patterns_total=0
helpful_total=0
last_learn_result=""
last_learn_timestamp=""
session_searches=0
session_patterns_injected=0

# Read ACE state file (handle missing gracefully)
if [ -f "$STATE_FILE" ]; then
  patterns_total=$(jq -r '.patterns_total // 0' "$STATE_FILE" 2>/dev/null || echo "0")
  helpful_total=$(jq -r '.helpful_total // 0' "$STATE_FILE" 2>/dev/null || echo "0")
  last_learn_result=$(jq -r '.last_learn_result // ""' "$STATE_FILE" 2>/dev/null || echo "")
  last_learn_timestamp=$(jq -r '.last_learn_timestamp // ""' "$STATE_FILE" 2>/dev/null || echo "")
  session_searches=$(jq -r '.session_searches // 0' "$STATE_FILE" 2>/dev/null || echo "0")
  session_patterns_injected=$(jq -r '.session_patterns_injected // 0' "$STATE_FILE" 2>/dev/null || echo "0")
fi

# Read live search stats from ace-relevance.jsonl
if [ -f "$RELEVANCE_FILE" ]; then
  live_searches=$(wc -l < "$RELEVANCE_FILE" 2>/dev/null || echo "0")
  session_searches="${live_searches}"
fi

# Build status output
STATUS="ACE: ${patterns_total}p"
if [ -n "$last_learn_result" ] && [ "$last_learn_result" != "null" ]; then
  STATUS="${STATUS} | learn: ${last_learn_result}"
fi
STATUS="${STATUS} | ${display_name} | ctx: ${used_percentage}%"

echo "$STATUS"
