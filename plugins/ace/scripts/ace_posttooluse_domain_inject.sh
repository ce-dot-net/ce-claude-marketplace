#!/usr/bin/env bash
# thin shim: the python >= 3.10 the fallback hooks need (scripts/ace-python), exec the python hook, stdin untouched
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
. "$ROOT/scripts/ace-python"; PY="$(ace_python)" || exit 0  # Python >= 3.10 (8.1.0), else silent: the mod chain is unaffected
exec "$PY" "$ROOT/shared-hooks/ace_domain_shift.py" "$@"
