#!/usr/bin/env bash
# ace_posttooluse_wrapper.sh - PostToolUse hook with tool accumulation
# v5.4.7: Flag file check + ace-cli/ace-cli detection
set -Eeuo pipefail

# ACE disable flag check (set by SessionStart if CLI issues detected)
# Official Claude Code pattern: flag file coordination between hooks
SESSION_ID="${SESSION_ID:-default}"
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID}.flag"
if [ -f "$ACE_DISABLED_FLAG" ]; then
  # ACE is disabled for this session - exit silently
  exit 0
fi

# CLI command detection (ace-cli preferred, ace-cli fallback)
if command -v ace-cli >/dev/null 2>&1; then
  CLI_CMD="ace-cli"
elif command -v ace-cli >/dev/null 2>&1; then
  CLI_CMD="ce-ace"
else
  exit 0  # No CLI available - exit silently
fi

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ACCUMULATOR="${PLUGIN_ROOT}/shared-hooks/ace_tool_accumulator.py"
LOGGER="${PLUGIN_ROOT}/shared-hooks/ace_event_logger.py"

# Export plugin version for logger
export ACE_PLUGIN_VERSION="5.4.7"

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
# Sanitize invalid UTF-8 sequences (e.g., unpaired surrogates) to prevent jq parse errors
# iconv with -c silently discards invalid characters
INPUT_JSON=$(cat | iconv -f UTF-8 -t UTF-8 -c 2>/dev/null || cat)

# Extract working directory from event (with error handling for malformed JSON)
WORKING_DIR=$(echo "$INPUT_JSON" | jq -r '.cwd // .working_directory // .workingDirectory // empty' 2>/dev/null || echo "")
if [[ -z "$WORKING_DIR" ]]; then
  # Fallback: Infer from transcript_path
  TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty' 2>/dev/null || echo "")
  if [[ -n "$TRANSCRIPT_PATH" ]]; then
    WORKING_DIR=$(cd "$(dirname "$TRANSCRIPT_PATH")/../.." 2>/dev/null && pwd) || WORKING_DIR=""
  fi
fi

if [[ -n "$WORKING_DIR" ]] && [[ -d "$WORKING_DIR" ]]; then
  cd "$WORKING_DIR" || true
fi

# Extract tool data from PostToolUse event (with error handling)
# Per Claude Code docs: PostToolUse provides tool_name, tool_input, tool_response, tool_use_id
TOOL_NAME=$(echo "$INPUT_JSON" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
TOOL_INPUT=$(echo "$INPUT_JSON" | jq -c '.tool_input // {}' 2>/dev/null || echo "{}")
TOOL_RESPONSE=$(echo "$INPUT_JSON" | jq -c '.tool_response // {}' 2>/dev/null || echo "{}")
TOOL_USE_ID=$(echo "$INPUT_JSON" | jq -r '.tool_use_id // empty' 2>/dev/null || echo "")
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")

# Skip if missing required fields
if [[ -z "$SESSION_ID" ]] || [[ -z "$TOOL_NAME" ]] || [[ -z "$TOOL_USE_ID" ]]; then
  echo "{\"systemMessage\": \"\"}"
  exit 0
fi

# Log PostToolUse event (for debugging/analysis)
# v5.4.5: Disabled by default to prevent 42GB log growth
# Enable with: export ACE_EVENT_LOGGING=1
if [[ "${ACE_EVENT_LOGGING:-0}" == "1" ]] && [[ "$ENABLE_LOG" == "true" ]] && [[ -f "${LOGGER}" ]]; then
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
