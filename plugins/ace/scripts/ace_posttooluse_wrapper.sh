#!/usr/bin/env bash
# ace_posttooluse_wrapper.sh - PostToolUse hook with tool accumulation
# v5.3.0: Appends tool data to SQLite accumulator for Stop hook processing
set -Eeuo pipefail

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ACCUMULATOR="${MARKETPLACE_ROOT}/shared-hooks/ace_tool_accumulator.py"
LOGGER="${MARKETPLACE_ROOT}/shared-hooks/ace_event_logger.py"

# Export plugin version for logger
export ACE_PLUGIN_VERSION="5.2.5"

# Parse arguments
ENABLE_LOG=true

while [[ $# -gt 0 ]]; do
  case $1 in
    --log) ENABLE_LOG=true; shift ;;
    --no-log) ENABLE_LOG=false; shift ;;
    *) shift ;;
  esac
done

# Check if accumulator exists
[[ -f "${ACCUMULATOR}" ]] || {
  echo "[ERROR] ace_tool_accumulator.py not found: ${ACCUMULATOR}" >&2
  exit 1
}

# Read stdin (PostToolUse event JSON)
INPUT_JSON=$(cat)

# Extract working directory from event
WORKING_DIR=$(echo "$INPUT_JSON" | jq -r '.cwd // .working_directory // .workingDirectory // empty')
if [[ -z "$WORKING_DIR" ]]; then
  # Fallback: Infer from transcript_path
  TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty')
  if [[ -n "$TRANSCRIPT_PATH" ]]; then
    WORKING_DIR=$(cd "$(dirname "$TRANSCRIPT_PATH")/../.." 2>/dev/null && pwd) || WORKING_DIR=""
  fi
fi

if [[ -n "$WORKING_DIR" ]] && [[ -d "$WORKING_DIR" ]]; then
  cd "$WORKING_DIR" || true
fi

# Extract tool data from PostToolUse event
# Per Claude Code docs: PostToolUse provides tool_name, tool_input, tool_response, tool_use_id
TOOL_NAME=$(echo "$INPUT_JSON" | jq -r '.tool_name // empty')
TOOL_INPUT=$(echo "$INPUT_JSON" | jq -c '.tool_input // {}')
TOOL_RESPONSE=$(echo "$INPUT_JSON" | jq -c '.tool_response // {}')
TOOL_USE_ID=$(echo "$INPUT_JSON" | jq -r '.tool_use_id // empty')
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty')

# Skip if missing required fields
if [[ -z "$SESSION_ID" ]] || [[ -z "$TOOL_NAME" ]] || [[ -z "$TOOL_USE_ID" ]]; then
  echo "{\"systemMessage\": \"\"}"
  exit 0
fi

# Log PostToolUse event (for debugging/analysis)
if [[ "$ENABLE_LOG" == "true" ]] && [[ -f "${LOGGER}" ]]; then
  echo "$INPUT_JSON" | uv run "$LOGGER" --event-type PostToolUse --phase start >/dev/null 2>&1 || true
fi

# Append tool to SQLite accumulator (fast, silent)
# This is the ONLY job of PostToolUse hook in v5.3.0
APPEND_RESULT=$(uv run "$ACCUMULATOR" append \
  --session-id "$SESSION_ID" \
  --tool-name "$TOOL_NAME" \
  --tool-input "$TOOL_INPUT" \
  --tool-response "$TOOL_RESPONSE" \
  --tool-use-id "$TOOL_USE_ID" \
  --working-dir "${WORKING_DIR:-$(pwd)}" 2>&1) || true

# Debug logging
if [[ "${ACE_DEBUG_HOOKS:-0}" == "1" ]]; then
  echo "[PostToolUse] Appended: $TOOL_NAME ($TOOL_USE_ID) -> $APPEND_RESULT" >> /tmp/ace_hook_debug.log
fi

# Output empty response (no user-facing message)
echo "{\"systemMessage\": \"\"}"
exit 0
