#!/usr/bin/env bash
# thin shim: resolve python once (cached by SessionStart), exec the python hook with stdin untouched
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PY=""; [ -r "${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ace-ce-dot-net-marketplace}/python_path" ] && read -r PY < "${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ace-ce-dot-net-marketplace}/python_path"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || exit 0
exec "$PY" "$ROOT/shared-hooks/ace_domain_shift.py" "$@"
