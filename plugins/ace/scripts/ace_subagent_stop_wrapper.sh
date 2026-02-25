#!/usr/bin/env bash
# ace_subagent_stop_wrapper.sh - SubagentStop hook with comprehensive logging
# v5.4.7: Flag file check + ace-cli/ace-cli detection
# Fires when Task agents complete - perfect for capturing learning after substantial work
set -euo pipefail
trap 'exit 0' ERR

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
LOGGER="${PLUGIN_ROOT}/shared-hooks/ace_event_logger.py"
HOOK_SCRIPT="${PLUGIN_ROOT}/shared-hooks/ace_after_task.py"

# Export plugin version for logger
export ACE_PLUGIN_VERSION="5.4.7"

# Parse arguments
ENABLE_LOG=true  # Always log by default
ENABLE_CHAT=false
ENABLE_NOTIFY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --log) ENABLE_LOG=true; shift ;;
    --no-log) ENABLE_LOG=false; shift ;;
    --chat) ENABLE_CHAT=true; shift ;;
    --notify) ENABLE_NOTIFY=true; shift ;;
    *) shift ;;
  esac
done

# Check if logger exists
[[ -f "${LOGGER}" ]] || {
  echo "[ERROR] ace_event_logger.py not found: ${LOGGER}" >&2
  exit 0
}

# Check if hook script exists
[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_after_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 0
}

# Read stdin
INPUT_JSON=$(cat)

# Extract working directory from event and cd to it
# This ensures ace_after_task.py can find .claude/settings.json
WORKING_DIR=$(echo "$INPUT_JSON" | jq -r '.cwd // .working_directory // .workingDirectory // empty')
if [[ -z "$WORKING_DIR" ]]; then
  # Fallback: Infer from transcript_path (.claude/data/transcript-*.jsonl -> project root)
  TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty')
  if [[ -n "$TRANSCRIPT_PATH" ]]; then
    # transcript_path is .claude/data/transcript-*.jsonl, so go up 2 levels
    WORKING_DIR=$(cd "$(dirname "$TRANSCRIPT_PATH")/../.." && pwd)
  fi
fi

if [[ -n "$WORKING_DIR" ]] && [[ -d "$WORKING_DIR" ]]; then
  cd "$WORKING_DIR" || {
    echo "[ERROR] Failed to change to working directory: $WORKING_DIR" >&2
    exit 0
  }
fi

# Log event START
if [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$INPUT_JSON" | uv run "$LOGGER" --event-type SubagentStop --phase start >/dev/null 2>&1 || {
    echo "[WARN] Failed to log start event" >&2
  }
fi

# Record start time (cross-platform milliseconds)
START_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')

# CRITICAL: Inject hook_event_name into event JSON
# v5.2.0: ace_after_task.py uses this to select agent_transcript_path
INPUT_JSON=$(echo "$INPUT_JSON" | jq '. + {"hook_event_name": "SubagentStop"}')

# Forward to ace_after_task.py (captures learning from subagent work)
RESULT=$(echo "$INPUT_JSON" | uv run "${HOOK_SCRIPT}" 2>&1)
EXIT_CODE=$?

# Calculate execution time (cross-platform milliseconds)
END_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')
EXECUTION_TIME=$((END_TIME - START_TIME))

# Log event END with result
if [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$RESULT" | uv run "$LOGGER" \
    --event-type SubagentStop \
    --phase end \
    --exit-code "$EXIT_CODE" \
    --execution-time-ms "$EXECUTION_TIME" \
    >/dev/null 2>&1 || {
    echo "[WARN] Failed to log end event" >&2
  }
fi

# Optional: Save subagent transcript
# v5.4.6: Disabled by default to prevent 47MB log growth per session
# Enable with: export ACE_EVENT_LOGGING=1
if [[ "${ACE_EVENT_LOGGING:-0}" == "1" ]] && [[ "$ENABLE_CHAT" == "true" ]]; then
  TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty')
  if [[ -n "$TRANSCRIPT_PATH" ]] && [[ -f "$TRANSCRIPT_PATH" ]]; then
    SUBAGENT_NAME=$(echo "$INPUT_JSON" | jq -r '.subagent_type // "unknown"')
    CHAT_FILE=".claude/data/logs/ace-subagent-${SUBAGENT_NAME}-$(date +%Y%m%d-%H%M%S).json"
    mkdir -p "$(dirname "$CHAT_FILE")"
    cp "$TRANSCRIPT_PATH" "$CHAT_FILE" 2>/dev/null || {
      echo "[WARN] Failed to save subagent transcript" >&2
    }
  fi
fi

# Optional: Notification
if [[ "$ENABLE_NOTIFY" == "true" ]] && [[ $EXIT_CODE -eq 0 ]]; then
  SUBAGENT_TYPE=$(echo "$INPUT_JSON" | jq -r '.subagent_type // "Task"')
  echo "✅ ACE learning captured from ${SUBAGENT_TYPE} agent" >&2
fi

# Output result
echo "$RESULT"
exit $EXIT_CODE
