#!/usr/bin/env bash
set -euo pipefail

# Export context for CLI
_ace_setting() {  # $1 settings key, $2 env-block key; stdlib JSON read, no jq
  python3 -c 'import json,sys
try: s=json.load(open(".claude/settings.json"))
except Exception: s={}
print(s.get(sys.argv[1]) or (s.get("env") or {}).get(sys.argv[2]) or "")' "$1" "$2" 2>/dev/null || true
}
export ACE_ORG_ID="$(_ace_setting orgId ACE_ORG_ID)"
export ACE_PROJECT_ID="$(_ace_setting projectId ACE_PROJECT_ID)"

if [ -z "$ACE_ORG_ID" ] || [ -z "$ACE_PROJECT_ID" ]; then
  echo "❌ Run /ace-configure first"
  exit 1
fi

# Delegate to the ace-cli wrapper (tune) with all arguments
exec "$(dirname "${BASH_SOURCE[0]}")/ace-cli" tune "$@"
