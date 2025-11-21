#!/usr/bin/env bash
# ace_posttooluse_wrapper.sh - PostToolUse hook with task completion detection
# Detects when main agent completes substantial work and captures learning
set -Eeuo pipefail

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LOGGER="${MARKETPLACE_ROOT}/shared-hooks/ace_event_logger.py"
TASK_DETECTOR="${MARKETPLACE_ROOT}/shared-hooks/ace_task_detector.py"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/ace_after_task.py"

# Export plugin version for logger
export ACE_PLUGIN_VERSION="5.3.0"

# Parse arguments
ENABLE_LOG=true  # Always log by default
ENABLE_DETECTION=true  # Always detect by default

while [[ $# -gt 0 ]]; do
  case $1 in
    --log) ENABLE_LOG=true; shift ;;
    --no-log) ENABLE_LOG=false; shift ;;
    --detect) ENABLE_DETECTION=true; shift ;;
    --no-detect) ENABLE_DETECTION=false; shift ;;
    *) shift ;;
  esac
done

# Check if required scripts exist
[[ -f "${LOGGER}" ]] || {
  echo "[ERROR] ace_event_logger.py not found: ${LOGGER}" >&2
  exit 1
}

[[ -f "${TASK_DETECTOR}" ]] || {
  echo "[ERROR] ace_task_detector.py not found: ${TASK_DETECTOR}" >&2
  exit 1
}

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_after_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

# Read stdin
INPUT_JSON=$(cat)

# Log PostToolUse event (for debugging/analysis)
if [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$INPUT_JSON" | uv run "$LOGGER" --event-type PostToolUse --phase detected >/dev/null 2>&1 || {
    echo "[WARN] Failed to log PostToolUse event" >&2
  }
fi

# Skip detection if disabled
if [[ "$ENABLE_DETECTION" == "false" ]]; then
  echo "{\"systemMessage\": \"\"}"
  exit 0
fi

# Run task completion detection
DETECTION_RESULT=$(echo "$INPUT_JSON" | uv run "${TASK_DETECTOR}" 2>&1)
DETECTOR_EXIT=$?

if [[ $DETECTOR_EXIT -ne 0 ]]; then
  echo "[WARN] Task detector failed: ${DETECTION_RESULT}" >&2
  echo "{\"systemMessage\": \"\"}"
  exit 0
fi

# Parse detection result
TASK_COMPLETE=$(echo "$DETECTION_RESULT" | jq -r '.task_complete // false')
TRIGGERED_BY=$(echo "$DETECTION_RESULT" | jq -r '.triggered_by // "none"')
CONFIDENCE=$(echo "$DETECTION_RESULT" | jq -r '.confidence // 0')

# If no task completion detected, exit early
if [[ "$TASK_COMPLETE" != "true" ]]; then
  echo "{\"systemMessage\": \"\"}"
  exit 0
fi

# Task completion detected! Log it
if [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$INPUT_JSON" | uv run "$LOGGER" \
    --event-type PostToolUse \
    --phase task_complete \
    >/dev/null 2>&1 || {
    echo "[WARN] Failed to log task completion" >&2
  }
fi

# Convert PostToolUse event to Stop event format for ace_after_task.py
# ace_after_task.py expects Stop/SubagentStop format
STOP_EVENT=$(echo "$INPUT_JSON" | jq '. + {
  "hook_event_name": "PostToolUse",
  "task_detector_triggered_by": "'$TRIGGERED_BY'",
  "task_detector_confidence": '$CONFIDENCE'
}')

# Record start time (cross-platform milliseconds)
START_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')

# Forward to ace_after_task.py (captures learning)
RESULT=$(echo "$STOP_EVENT" | uv run "${HOOK_SCRIPT}" 2>&1)
EXIT_CODE=$?

# Calculate execution time (cross-platform milliseconds)
END_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')
EXECUTION_TIME=$((END_TIME - START_TIME))

# Log learning capture result
if [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$RESULT" | uv run "$LOGGER" \
    --event-type PostToolUse \
    --phase learning_captured \
    --exit-code "$EXIT_CODE" \
    --execution-time-ms "$EXECUTION_TIME" \
    >/dev/null 2>&1 || {
    echo "[WARN] Failed to log learning capture result" >&2
  }
fi

# Output result (silent - no user-facing message)
echo "{\"systemMessage\": \"\"}"
exit 0
