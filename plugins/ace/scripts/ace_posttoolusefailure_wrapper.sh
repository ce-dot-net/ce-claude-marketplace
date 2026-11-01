#!/usr/bin/env bash
# thin shim (DESIGN §3.1): resolve python once (cached by SessionStart), exec the python hook, stdin untouched
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PY=""; [ -r "${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ace}/python_path" ] && read -r PY < "${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ace}/python_path"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -n "$PY" ] || exit 0
exec "$PY" "$ROOT/shared-hooks/ace_tool_accumulator.py" --failure "$@"
