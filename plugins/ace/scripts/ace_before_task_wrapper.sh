#!/usr/bin/env bash
# ACE Before Task Wrapper - Forwards to shared-hooks/ace_before_task.py
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/ace_before_task.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_before_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

# Extract working directory from stdin and cd to it
# This ensures ace_before_task.py can find .claude/settings.json
INPUT_JSON=$(cat)

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

# Pass INPUT_JSON to ace_before_task.py via stdin
echo "$INPUT_JSON" | exec uv run "${HOOK_SCRIPT}" "$@"
