#!/usr/bin/env bash
# ace_stop_wrapper.sh - Stop hook with comprehensive logging
# v5.4.7: Flag file check + ace-cli/ace-cli detection
set -euo pipefail
trap 'exit 0' ERR

# Read stdin early (can only be read once) for session_id
INPUT_JSON=$(cat)
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
SESSION_ID="${SESSION_ID:-default}"

# ACE disable flag check (set by SessionStart if CLI issues detected)
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID}.flag"
if [ -f "$ACE_DISABLED_FLAG" ]; then
  exit 0
fi

# CLI command detection
if ! command -v ace-cli >/dev/null 2>&1; then
  exit 0  # No CLI available - exit silently
fi
CLI_CMD="ace-cli"

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOGGER="${PLUGIN_ROOT}/shared-hooks/ace_event_logger.py"
HOOK_SCRIPT="${PLUGIN_ROOT}/shared-hooks/ace_after_task.py"

# Export plugin version for logger
export ACE_PLUGIN_VERSION="6.2.1"

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

# PRE-CHECK: CLI already verified by flag file check above

# PRE-CHECK: Verify configuration exists
GLOBAL_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/ace/config.json"
if [[ ! -f "$GLOBAL_CONFIG" ]]; then
  # No global config - skip learning capture gracefully
  # Don't show error, just exit silently (user can configure later)
  exit 0
fi

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

# stdin already read at top for session_id

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
# v5.4.5: Disabled by default to prevent 42GB log growth
# Enable with: export ACE_EVENT_LOGGING=1
if [[ "${ACE_EVENT_LOGGING:-0}" == "1" ]] && [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$INPUT_JSON" | uv run "$LOGGER" --event-type Stop --phase start >/dev/null 2>&1 || {
    echo "[WARN] Failed to log start event" >&2
  }
fi

# Record start time (cross-platform milliseconds)
START_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')

# CRITICAL: Inject hook_event_name into event JSON
# v5.3.0: ace_after_task.py queries accumulated tools from SQLite
INPUT_JSON=$(echo "$INPUT_JSON" | jq '. + {"hook_event_name": "Stop"}')

# ── Self-Evaluation: Check BEFORE learning (which deletes patterns-used file) ──
PATTERNS_FILE=".claude/data/logs/ace-patterns-used-${SESSION_ID}.json"
EVAL_FLAG="/tmp/ace-eval-requested-${SESSION_ID}.flag"
REVIEW_FILE=".claude/data/logs/ace-review-result.json"
HAS_PATTERNS=false
if [ -f "$PATTERNS_FILE" ] || [ -f "$EVAL_FLAG" ]; then
  HAS_PATTERNS=true
fi

# Check if async mode is enabled (Issue #3 fix)
ACE_ASYNC_LEARNING="${ACE_ASYNC_LEARNING:-1}"  # Default: enabled

if [[ "$ACE_ASYNC_LEARNING" == "1" ]]; then
  # === ASYNC MODE (Issue #3 fix) ===
  # Launch ace_after_task.py in background and return immediately

  # Create temp files (cleanup handled by subshell)
  TEMP_INPUT=$(mktemp)
  TEMP_OUTPUT=$(mktemp)

  # Write INPUT_JSON to temp file (prevents injection)
  printf '%s\n' "$INPUT_JSON" > "$TEMP_INPUT"

  # Create log directory for background errors
  LOG_DIR="${HOME}/.claude/logs"
  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/ace-background-$(date +%Y%m%d-%H%M%S)-$$.log"

  # Launch in background with proper error logging
  (
    uv run "${HOOK_SCRIPT}" < "$TEMP_INPUT" 2>&1 > "$TEMP_OUTPUT"
    LEARN_EXIT=$?
    if [[ $LEARN_EXIT -ne 0 ]]; then
      echo "[ERROR] Background learning failed with exit code $LEARN_EXIT" >> "$LOG_FILE"
      cat "$TEMP_OUTPUT" >> "$LOG_FILE"
    fi
    rm -f "$TEMP_INPUT" "$TEMP_OUTPUT"
  ) &

  # Return immediate feedback
  RESULT='{"continue": true, "systemMessage": "✅ [ACE] Learning started in background"}'
  EXIT_CODE=0

  # Calculate execution time (should be <1s)
  END_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')
  EXECUTION_TIME=$((END_TIME - START_TIME))

else
  # === SYNC MODE (original behavior) ===
  # Forward to ace_after_task.py and wait for completion
  RESULT=$(echo "$INPUT_JSON" | uv run "${HOOK_SCRIPT}" 2>&1)
  EXIT_CODE=$?

  # Calculate execution time (cross-platform milliseconds)
  END_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')
  EXECUTION_TIME=$((END_TIME - START_TIME))
fi

# Log event END with result
# v5.4.5: Disabled by default to prevent 42GB log growth
if [[ "${ACE_EVENT_LOGGING:-0}" == "1" ]] && [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$RESULT" | uv run "$LOGGER" \
    --event-type Stop \
    --phase end \
    --exit-code "$EXIT_CODE" \
    --execution-time-ms "$EXECUTION_TIME" \
    >/dev/null 2>&1 || {
    echo "[WARN] Failed to log end event" >&2
  }
fi

# Optional: Save chat transcript
# v5.4.6: Disabled by default to prevent 47MB log growth per session
# Enable with: export ACE_EVENT_LOGGING=1
if [[ "${ACE_EVENT_LOGGING:-0}" == "1" ]] && [[ "$ENABLE_CHAT" == "true" ]]; then
  TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty')
  if [[ -n "$TRANSCRIPT_PATH" ]] && [[ -f "$TRANSCRIPT_PATH" ]]; then
    CHAT_FILE=".claude/data/logs/ace-chat-$(date +%Y%m%d-%H%M%S).json"
    mkdir -p "$(dirname "$CHAT_FILE")"
    cp "$TRANSCRIPT_PATH" "$CHAT_FILE" 2>/dev/null || {
      echo "[WARN] Failed to save chat transcript" >&2
    }
  fi
fi

# Optional: Notification (if TTS available)
if [[ "$ENABLE_NOTIFY" == "true" ]] && [[ $EXIT_CODE -eq 0 ]]; then
  echo "✅ ACE learning captured" >&2
fi

# ── Self-Evaluation Logic (uses HAS_PATTERNS from pre-check above) ──
if [ "$HAS_PATTERNS" = "true" ]; then
  if [ ! -f "$EVAL_FLAG" ]; then
    # First stop: block and ask for self-evaluation
    touch "$EVAL_FLAG"
    echo '{"decision": "block", "reason": "Before completing, rate how helpful the <ace-patterns> knowledge was for this task and estimate time saved. Reply with exactly: ACE_REVIEW: N% | Xm saved | brief reason"}'
    exit 0
  else
    # Second stop: eval was requested, parse last_assistant_message for ACE_REVIEW
    LAST_MSG=$(echo "$INPUT_JSON" | jq -r '.last_assistant_message // ""')
    HELPFUL_PCT=$(echo "$LAST_MSG" | grep -oE 'ACE_REVIEW:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | head -1)
    HELPFUL_PCT="${HELPFUL_PCT:-0}"
    # Parse time saved (e.g., "5m saved" or "30s saved")
    TIME_SAVED=$(echo "$LAST_MSG" | grep -oE '[0-9]+m[0-9]*s? saved|[0-9]+s saved|[0-9]+ ?min' | head -1 | sed 's/ saved//')
    TIME_SAVED="${TIME_SAVED:-}"
    # Write result to review file
    mkdir -p "$(dirname "$REVIEW_FILE")"
    jq -n --arg pct "$HELPFUL_PCT" --arg time "$TIME_SAVED" \
      '{helpful_pct: ($pct | tonumber), time_saved: $time}' > "$REVIEW_FILE" 2>/dev/null \
      || echo "{\"helpful_pct\": ${HELPFUL_PCT}, \"time_saved\": \"${TIME_SAVED}\"}" > "$REVIEW_FILE"
    # Clean up eval flag
    rm -f "$EVAL_FLAG"
    # Approve with helpfulness in systemMessage
    SYS_MSG="✅ [ACE] ${HELPFUL_PCT}% helpful"
    if [ -n "$TIME_SAVED" ]; then SYS_MSG="${SYS_MSG} | ~${TIME_SAVED} saved"; fi
    SYS_MSG="${SYS_MSG} | Learning in background"
    echo '{"decision": "approve", "systemMessage": "'"${SYS_MSG}"'"}'
    exit 0
  fi
fi

# Output result (no patterns — approve immediately)
echo "$RESULT"
exit $EXIT_CODE
