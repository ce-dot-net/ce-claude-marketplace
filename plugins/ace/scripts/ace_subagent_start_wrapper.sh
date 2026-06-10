#!/usr/bin/env bash
# ace_subagent_start_wrapper.sh - SubagentStart hook
# Fires ACE search keyed to each subagent's own agent_id + task text.
# This gives the subagent its own retrieval rows so SubagentStop crediting works.
# Never blocks the subagent — exits 0 on any error.
set -eo pipefail
trap 'echo "[ERROR] ACE hook failed: $(basename $0) line $LINENO" >&2; exit 0' ERR

# ACE disable flag check
SESSION_ID="${SESSION_ID:-default}"
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID}.flag"
if [ -f "$ACE_DISABLED_FLAG" ]; then
  exit 0
fi

# CLI availability check
if ! command -v ace-cli >/dev/null 2>&1; then
  exit 0
fi

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOOK_SCRIPT="${PLUGIN_ROOT}/shared-hooks/ace_subagent_start.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_subagent_start.py not found: ${HOOK_SCRIPT}" >&2
  exit 0
}

# Read stdin; extract cwd for context resolution (same pattern as ace_before_task_wrapper.sh)
INPUT_JSON=$(cat)

WORKING_DIR=$(echo "$INPUT_JSON" | jq -r '.cwd // .working_directory // .workingDirectory // empty')
if [[ -z "$WORKING_DIR" ]]; then
  TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty')
  if [[ -n "$TRANSCRIPT_PATH" ]]; then
    WORKING_DIR=$(cd "$(dirname "$TRANSCRIPT_PATH")/../.." && pwd)
  fi
fi

if [[ -n "$WORKING_DIR" ]] && [[ -d "$WORKING_DIR" ]]; then
  cd "$WORKING_DIR" || {
    echo "[ERROR] Failed to change to working directory: $WORKING_DIR" >&2
    exit 0
  }
fi

# Forward to Python hook
echo "$INPUT_JSON" | exec python3 "${HOOK_SCRIPT}" "$@"
