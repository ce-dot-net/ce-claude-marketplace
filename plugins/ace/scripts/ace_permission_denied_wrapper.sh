#!/usr/bin/env bash
# ACE PermissionDenied Hook (v6.5.0 Item #15)
#
# Fires when CC auto-mode classifier denies a tool call.
# Forwards to ace_permission_denied.py which submits a boundary-signal trace
# to ace-cli learn (agent_type="permission_gate", domain="permission-boundary").
#
# Per ACE-SDK-team guidance (Q2): boundary signal, NOT anti-pattern.
# Server filters minimum-token traces, so single-step Denials become telemetry only.
# Client-side debounce caps to 1 trace per (tool_name, session) per 60s.

set -eo pipefail
trap 'echo "[ERROR] ACE hook failed: $(basename $0) line $LINENO" >&2; exit 0' ERR

# Load shared env (ACE_PLUGIN_VERSION, ACE_CLIENT_ID)
source "${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/scripts/_ace_env.sh"

# Read CC event JSON from stdin
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# Disable-flag check
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
SESSION_ID_FOR_FLAG="${SESSION_ID:-default}"
if [ -f "/tmp/ace-disabled-${SESSION_ID_FOR_FLAG}.flag" ]; then
  exit 0
fi

# CLI availability check (no point logging denials if we can't send them)
if ! command -v ace-cli >/dev/null 2>&1; then
  exit 0
fi

# Forward to Python handler
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HANDLER="${PLUGIN_ROOT}/shared-hooks/ace_permission_denied.py"

if [ ! -f "$HANDLER" ]; then
  exit 0  # Silent fail — never block CC operation on missing handler
fi

# Execute handler (synchronously — short operation, debounced)
printf '%s' "$INPUT_JSON" | python3 "$HANDLER" 2>/dev/null || true

# Always emit a valid empty JSON response so CC doesn't choke
echo '{}'
exit 0
