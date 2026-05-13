#!/usr/bin/env bash
# ace_posttooluse_wrapper.sh - PostToolUse hook with tool accumulation
# v5.4.7: Flag file check + ace-cli/ace-cli detection
set -eo pipefail
trap 'echo "[ERROR] ACE hook failed: $(basename $0) line $LINENO" >&2; exit 0' ERR

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
ACCUMULATOR="${PLUGIN_ROOT}/shared-hooks/ace_tool_accumulator.py"
LOGGER="${PLUGIN_ROOT}/shared-hooks/ace_event_logger.py"

# Plugin version + X-ACE-Client header — loaded dynamically from plugin.json
source "${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/scripts/_ace_env.sh"

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
  exit 0
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
# v6.0.0: Capture agent_id for per-agent trajectory (CC 2.1.69+)
AGENT_ID=$(echo "$INPUT_JSON" | jq -r '.agent_id // empty' 2>/dev/null || echo "")
# v6.5.0 Item #1: Tool timing (CC 2.1.119+ delivers these natively)
TOOL_DURATION_MS=$(echo "$INPUT_JSON" | jq -r '.duration_ms // empty' 2>/dev/null || echo "")
TOOL_START_MS=$(echo "$INPUT_JSON" | jq -r '.tool_start_ms // .start_ms // empty' 2>/dev/null || echo "")
TOOL_END_MS=$(echo "$INPUT_JSON" | jq -r '.tool_end_ms // .end_ms // empty' 2>/dev/null || echo "")

# Skip if missing required fields
if [[ -z "$SESSION_ID" ]] || [[ -z "$TOOL_NAME" ]] || [[ -z "$TOOL_USE_ID" ]]; then
  exit 0
fi

# v6.5.0 Item #6: Bash-error troubleshooting injection.
# When a Bash command fails (exit_code != 0), search ACE's
# troubleshooting_and_pitfalls section for matching patterns and inject them
# inline via updatedToolOutput. Per SDK-team Q3: Plan B (Bash-only) — Plan A
# (every tool) is too latency-heavy. Uses --section filter (ace-cli >= 2.18).
INJECTED_TOOL_OUTPUT=false
if [[ "$TOOL_NAME" == "Bash" ]] && command -v ace-cli >/dev/null 2>&1; then
  EXIT_CODE_VAL=$(echo "$TOOL_RESPONSE" | jq -r '.exit_code // .exitCode // 0' 2>/dev/null || echo "0")
  if [[ -n "$EXIT_CODE_VAL" ]] && [[ "$EXIT_CODE_VAL" != "0" ]] && [[ "$EXIT_CODE_VAL" != "null" ]]; then
    # Pull error text (stderr+stdout, cap 2KB to keep search fast)
    ERROR_TEXT=$(echo "$TOOL_RESPONSE" | jq -r '((.stderr // "") + "\n" + (.stdout // ""))' 2>/dev/null | head -c 2048 | tr -d '\000' || echo "")
    if [[ -n "$ERROR_TEXT" ]] && [[ "$ERROR_TEXT" != $'\n' ]]; then
      # Call ace-cli search with timeout to protect against slow responses.
      # --section limits to troubleshooting_and_pitfalls (ace-cli 2.18+).
      TROUBLE_JSON=$(echo "$ERROR_TEXT" | timeout 3 ace-cli search --stdin \
        --section troubleshooting_and_pitfalls --top-k 3 --quiet --json 2>/dev/null || echo "")
      if [[ -n "$TROUBLE_JSON" ]]; then
        TROUBLE_COUNT=$(echo "$TROUBLE_JSON" | jq -r '.count // 0' 2>/dev/null || echo "0")
        if [[ "$TROUBLE_COUNT" != "0" ]] && [[ "$TROUBLE_COUNT" != "null" ]]; then
          TROUBLE_BLOCK=$(echo "$TROUBLE_JSON" | jq -r '
            .similar_patterns
            | map("• " + .content)
            | join("\n")
          ' 2>/dev/null || echo "")
          if [[ -n "$TROUBLE_BLOCK" ]]; then
            ORIG_OUTPUT=$(echo "$TOOL_RESPONSE" | jq -r 'tostring' 2>/dev/null || echo "")
            jq -nc \
              --arg orig "$ORIG_OUTPUT" \
              --arg tips "$TROUBLE_BLOCK" \
              '{hookSpecificOutput: {hookEventName: "PostToolUse", updatedToolOutput: ($orig + "\n\n[ACE Troubleshooting]\n" + $tips)}}'
            INJECTED_TOOL_OUTPUT=true
          fi
        fi
      fi
    fi
  fi
fi

# v6.0.0: Async output — tell Claude Code to proceed immediately
# Tool accumulation is a fire-and-forget side effect (SQLite write).
# Skip this when we already emitted hookSpecificOutput (Item #6).
if [[ "$INJECTED_TOOL_OUTPUT" != "true" ]]; then
  echo '{"async": true}'
fi

# Log PostToolUse event (for debugging/analysis)
# v5.4.5: Disabled by default to prevent 42GB log growth
# Enable with: export ACE_EVENT_LOGGING=1
if [[ "${ACE_EVENT_LOGGING:-0}" == "1" ]] && [[ "$ENABLE_LOG" == "true" ]] && [[ -f "${LOGGER}" ]]; then
  echo "$INPUT_JSON" | python3 "$LOGGER" --event-type PostToolUse --phase start >/dev/null 2>&1 || true
fi

# v6.4.0: CWD strict mode — no $(pwd) fallback.
# Build conditional --working-dir arg only when the event provided a legitimate cwd.
# This prevents state-file leaks into the hook process CWD (e.g. repo root).
WORKING_DIR_ARG=""
if [ -n "$WORKING_DIR" ]; then
  WORKING_DIR_ARG="--working-dir $WORKING_DIR"
else
  echo "[ACE WARN] No WORKING_DIR from hook event — using accumulator's default cwd" >&2
fi

# v6.5.0 Item #1: build timing arg list conditionally (only when CC provided values).
TIMING_ARGS=""
[ -n "$TOOL_START_MS" ] && TIMING_ARGS+=" --start-ms $TOOL_START_MS"
[ -n "$TOOL_END_MS" ] && TIMING_ARGS+=" --end-ms $TOOL_END_MS"
[ -n "$TOOL_DURATION_MS" ] && TIMING_ARGS+=" --duration-ms $TOOL_DURATION_MS"

# Append tool to SQLite accumulator (fast, silent)
# v6.0.0: Now runs AFTER async output — Claude Code already proceeding
APPEND_RESULT=$(python3 "$ACCUMULATOR" append \
  --session-id "$SESSION_ID" \
  --tool-name "$TOOL_NAME" \
  --tool-input "$TOOL_INPUT" \
  --tool-response "$TOOL_RESPONSE" \
  --tool-use-id "$TOOL_USE_ID" \
  --agent-id "$AGENT_ID" \
  $WORKING_DIR_ARG $TIMING_ARGS 2>&1) || true

# Debug logging
if [[ "${ACE_DEBUG_HOOKS:-0}" == "1" ]]; then
  echo "[PostToolUse] Appended: $TOOL_NAME ($TOOL_USE_ID) -> $APPEND_RESULT" >> /tmp/ace_hook_debug.log
fi

exit 0
