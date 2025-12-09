#!/usr/bin/env bash
set -euo pipefail

# ACE Permission Request Wrapper
# Auto-approves safe ACE CLI commands, denies dangerous ones

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHARED_HOOKS="$PLUGIN_ROOT/shared-hooks"

# Execute the permission request hook
"$SHARED_HOOKS/ace_permission_request.py"
