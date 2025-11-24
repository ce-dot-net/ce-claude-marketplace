#!/usr/bin/env bash
# ace_subagent_stop_wrapper.sh - SubagentStop hook with comprehensive logging
# Fires when Task agents complete - perfect for capturing learning after substantial work
set -Eeuo pipefail

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LOGGER="${MARKETPLACE_ROOT}/shared-hooks/ace_event_logger.py"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/ace_after_task.py"

# Export plugin version for logger
export ACE_PLUGIN_VERSION="5.2.1"

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
  exit 1
}

# Check if hook script exists
[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_after_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
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
    exit 1
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
if [[ "$ENABLE_CHAT" == "true" ]]; then
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
