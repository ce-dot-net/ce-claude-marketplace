#!/usr/bin/env bash
# ACE After Task Wrapper - Forwards to shared-hooks/ace_after_task.py
set -euo pipefail
trap 'exit 0' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOOK_SCRIPT="${PLUGIN_ROOT}/shared-hooks/ace_after_task.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_after_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 0
}

exec uv run "${HOOK_SCRIPT}" "$@"
