#!/usr/bin/env bash
# ace_stop_wrapper.sh - Stop hook with comprehensive logging
# v5.4.7: Flag file check + ace-cli/ace-cli detection
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
export ACE_PLUGIN_VERSION="6.1.2"

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

# v6.1.2: Background learning + sync contribution summary
# Learning (ace-cli learn, 5-30s) runs in background
# Contribution summary (JSONL read, <100ms) runs synchronously and shows at task end

# Create temp files for background learning
TEMP_INPUT=$(mktemp)
TEMP_OUTPUT=$(mktemp)
printf '%s\n' "$INPUT_JSON" > "$TEMP_INPUT"

# Create log directory for background errors
LOG_DIR="${HOME}/.claude/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/ace-background-$(date +%Y%m%d-%H%M%S)-$$.log"

# Launch learning in background (sends trace to server, updates playbook)
(
  uv run "${HOOK_SCRIPT}" < "$TEMP_INPUT" 2>&1 > "$TEMP_OUTPUT"
  LEARN_EXIT=$?
  if [[ $LEARN_EXIT -ne 0 ]]; then
    echo "[ERROR] Background learning failed with exit code $LEARN_EXIT" >> "$LOG_FILE"
    cat "$TEMP_OUTPUT" >> "$LOG_FILE"
  fi

  # Save learning results to statusline state file
  LEARN_RESULT=$(cat "$TEMP_OUTPUT" 2>/dev/null || echo "")
  STATE_DIR=".claude/data/logs"
  STATUSLINE_STATE="${STATE_DIR}/ace-statusline-state.json"
  mkdir -p "$STATE_DIR" 2>/dev/null || true
  if [[ -n "$LEARN_RESULT" ]]; then
    LEARN_MSG=$(echo "$LEARN_RESULT" | jq -r '.systemMessage // ""' 2>/dev/null || echo "")
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    EXISTING_STATE="{}"
    if [[ -f "$STATUSLINE_STATE" ]]; then
      EXISTING_STATE=$(cat "$STATUSLINE_STATE" 2>/dev/null || echo "{}")
    fi
    echo "$EXISTING_STATE" | jq \
      --arg result "$LEARN_MSG" \
      --arg timestamp "$TIMESTAMP" \
      '. + {"last_learn_result": $result, "last_learn_timestamp": $timestamp, "shown": false}' \
      > "$STATUSLINE_STATE" 2>/dev/null || true
  fi

  rm -f "$TEMP_INPUT" "$TEMP_OUTPUT"
) &

# === Sync: Build ACE contribution summary from JSONL (fast, local) ===
SESSION_ID_FROM_EVENT=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
RELEVANCE_FILE=".claude/data/logs/ace-relevance.jsonl"
CONTRIB_MSG=""

if [[ -n "$SESSION_ID_FROM_EVENT" ]] && [[ -f "$RELEVANCE_FILE" ]]; then
  # Read this session's search stats from JSONL (milliseconds, no network)
  CONTRIB_MSG=$(python3 -c "
import json, sys
session_id = '$SESSION_ID_FROM_EVENT'
searches, shifts = [], []
try:
    with open('$RELEVANCE_FILE') as f:
        for line in f:
            line = line.strip()
            if not line or session_id not in line:
                continue
            try:
                e = json.loads(line)
                if e.get('session_id') != session_id:
                    continue
                if e.get('event') == 'search':
                    searches.append(e)
                elif e.get('event') == 'domain_shift':
                    shifts.append(e)
            except: pass
except: pass

if searches:
    total_inj = sum(s.get('patterns_injected', 0) for s in searches)
    avg_conf = sum(s.get('avg_confidence', 0) for s in searches) / len(searches)
    rel_pct = int(avg_conf * 100)
    domains = set()
    for s in searches:
        domains.update(s.get('domains', []))
    hi = sum(s.get('patterns_injected', 0) for s in searches if s.get('avg_confidence', 0) > 0.5)
    est_s = hi * 30
    est = f'{est_s // 60}m {est_s % 60}s' if est_s >= 60 else f'{est_s}s'
    parts = [f'{total_inj} injected']
    if domains: parts.append(f'{len(domains)} domains')
    if shifts: parts.append(f'{len(shifts)} shifts')
    detail = ' · '.join(parts)
    msg = f'📊 [ACE] Task: {rel_pct}% relevance | {detail}'
    if est_s > 0: msg += f' | ~{est} saved'
    print(msg)
" 2>/dev/null || echo "")
fi

# Build result with contribution summary
if [[ -n "$CONTRIB_MSG" ]]; then
  RESULT=$(jq -n --arg msg "✅ [ACE] Learning in background\n${CONTRIB_MSG}" '{"continue": true, "systemMessage": $msg}')
else
  RESULT='{"continue": true, "systemMessage": "✅ [ACE] Learning in background"}'
fi
EXIT_CODE=0

END_TIME=$(python3 -c 'import time; print(int(time.time() * 1000))')
EXECUTION_TIME=$((END_TIME - START_TIME))

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

# Output result
echo "$RESULT"
exit $EXIT_CODE
