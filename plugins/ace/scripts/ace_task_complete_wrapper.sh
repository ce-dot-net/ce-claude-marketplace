#!/usr/bin/env bash
# ACE Task Complete Wrapper - Forwards to shared-hooks/ace_task_complete.py
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/ace_task_complete.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_task_complete.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

exec uv run "${HOOK_SCRIPT}" "$@"
