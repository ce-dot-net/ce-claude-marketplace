#!/usr/bin/env bash
# ace_stop_wrapper.sh - Stop hook with comprehensive logging
# v5.4.7: Flag file check + ace-cli/ace-cli detection
set -eo pipefail
trap 'echo "[ERROR] ACE hook failed: $(basename $0) line $LINENO" >&2; exit 0' ERR

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
export ACE_PLUGIN_VERSION="6.2.13"

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
  echo "$INPUT_JSON" | python3 "$LOGGER" --event-type Stop --phase start >/dev/null 2>&1 || {
    echo "[WARN] Failed to log start event" >&2
  }
fi

# Record start time (cross-platform milliseconds)
START_TIME=$(($(date +%s) * 1000))

# CRITICAL: Inject hook_event_name into event JSON
# v5.3.0: ace_after_task.py queries accumulated tools from SQLite
INPUT_JSON=$(echo "$INPUT_JSON" | jq '. + {"hook_event_name": "Stop"}')

# ── Fire-and-Forget Self-Evaluation ──
# Stop hook writes eval request to state file (NO blocking, NO decision:block)
# Next UserPromptSubmit reads eval request, injects via additionalContext (silent)
# Claude evaluates previous task's patterns naturally in its response
# Stop hook parses ACE_REVIEW from last_assistant_message and writes review file
EVAL_REQUEST_FILE=".claude/data/logs/ace-eval-request.json"
REVIEW_FILE=".claude/data/logs/ace-review-result.json"
RELEVANCE_FILE=".claude/data/logs/ace-relevance.jsonl"

# Check if last_assistant_message contains ACE_REVIEW (from previous eval injection)
LAST_MSG=$(echo "$INPUT_JSON" | jq -r '.last_assistant_message // ""')
if echo "$LAST_MSG" | grep -qE 'ACE_REVIEW:'; then
  HELPFUL_PCT=$(echo "$LAST_MSG" | grep -oE 'ACE_REVIEW:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | head -1)
  HELPFUL_PCT="${HELPFUL_PCT:-0}"
  TIME_SAVED=$(echo "$LAST_MSG" | grep -oE '[0-9]+m[0-9]*s? saved|[0-9]+s saved|[0-9]+ ?min' | head -1 | sed 's/ saved//')
  TIME_SAVED="${TIME_SAVED:-}"
  mkdir -p "$(dirname "$REVIEW_FILE")"
  jq -n --arg pct "$HELPFUL_PCT" --arg time "$TIME_SAVED" \
    '{helpful_pct: ($pct | tonumber), time_saved: $time}' > "$REVIEW_FILE" 2>/dev/null \
    || echo "{\"helpful_pct\": ${HELPFUL_PCT}, \"time_saved\": \"${TIME_SAVED}\"}" > "$REVIEW_FILE"
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
    python3 "${HOOK_SCRIPT}" < "$TEMP_INPUT" 2>&1 > "$TEMP_OUTPUT"
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
  END_TIME=$(($(date +%s) * 1000))
  EXECUTION_TIME=$((END_TIME - START_TIME))

else
  # === SYNC MODE (original behavior) ===
  # Forward to ace_after_task.py and wait for completion
  RESULT=$(echo "$INPUT_JSON" | python3 "${HOOK_SCRIPT}" 2>&1)
  EXIT_CODE=$?

  # Calculate execution time (cross-platform milliseconds)
  END_TIME=$(($(date +%s) * 1000))
  EXECUTION_TIME=$((END_TIME - START_TIME))
fi

# Log event END with result
# v5.4.5: Disabled by default to prevent 42GB log growth
if [[ "${ACE_EVENT_LOGGING:-0}" == "1" ]] && [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$RESULT" | python3 "$LOGGER" \
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

# ── Write eval request for next task (fire-and-forget, no blocking) ──
# Check if patterns were injected this task (from JSONL) and write eval request
# Next UserPromptSubmit will read this and inject eval via additionalContext

HAS_PATTERNS=false
INJECTED=0
AVG_REL=0
DOMAINS_COUNT=0
TOOLS_EXECUTED=0

if [ -f "$RELEVANCE_FILE" ]; then
  METRICS=$(python3 -c "
import json
events = []
with open('$RELEVANCE_FILE') as f:
    for line in f:
        line = line.strip()
        if line:
            try: events.append(json.loads(line))
            except: pass
last_exec = -1
for i, e in enumerate(events):
    if e.get('event') == 'execution': last_exec = i
current = events[last_exec + 1:] if last_exec >= 0 else events
searches = [e for e in current if e.get('event') == 'search']
execs = [e for e in current if e.get('event') == 'execution']
inj = sum(s.get('patterns_injected', 0) for s in searches)
rel = int(sum(s.get('avg_confidence', 0) for s in searches) / len(searches) * 100) if searches else 0
doms = len(set(d for s in searches for d in s.get('domains', [])))
tools = sum(e.get('tools_executed', 0) for e in execs) if execs else 0
print(f'INJECTED={inj}')
print(f'AVG_REL={rel}')
print(f'DOMAINS_COUNT={doms}')
print(f'TOOLS_EXECUTED={tools}')
" 2>/dev/null || echo "")
  INJECTED=$(echo "$METRICS" | grep '^INJECTED=' | cut -d= -f2)
  AVG_REL=$(echo "$METRICS" | grep '^AVG_REL=' | cut -d= -f2)
  DOMAINS_COUNT=$(echo "$METRICS" | grep '^DOMAINS_COUNT=' | cut -d= -f2)
  TOOLS_EXECUTED=$(echo "$METRICS" | grep '^TOOLS_EXECUTED=' | cut -d= -f2)
  if [ "$INJECTED" -gt 0 ] 2>/dev/null; then
    HAS_PATTERNS=true
  fi
fi

if [ "$HAS_PATTERNS" = "true" ]; then
  # Write eval request for next UserPromptSubmit to pick up
  mkdir -p "$(dirname "$EVAL_REQUEST_FILE")"
  jq -n \
    --arg pi "$INJECTED" \
    --arg ar "$AVG_REL" \
    --arg dc "$DOMAINS_COUNT" \
    --arg te "$TOOLS_EXECUTED" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{patterns_injected: ($pi | tonumber), avg_relevance: ($ar | tonumber), domains: ($dc | tonumber), tools_executed: ($te | tonumber), success: true, timestamp: $ts}' \
    > "$EVAL_REQUEST_FILE" 2>/dev/null || true
fi

if [ -f "$REVIEW_FILE" ]; then
  # Review was parsed — show result
  REVIEW_PCT=$(jq -r '.helpful_pct // 0' "$REVIEW_FILE" 2>/dev/null || echo "0")
  REVIEW_TIME=$(jq -r '.time_saved // ""' "$REVIEW_FILE" 2>/dev/null || echo "")
  SYS_MSG="✅ [ACE] ${REVIEW_PCT}% helpful"
  if [ -n "$REVIEW_TIME" ] && [ "$REVIEW_TIME" != "null" ] && [ "$REVIEW_TIME" != "" ]; then SYS_MSG="${SYS_MSG} | ~${REVIEW_TIME} saved"; fi
  SYS_MSG="${SYS_MSG} | Learning in background"
  echo "{\"continue\": true, \"systemMessage\": \"${SYS_MSG}\"}"
else
  echo "$RESULT"
fi
exit $EXIT_CODE
