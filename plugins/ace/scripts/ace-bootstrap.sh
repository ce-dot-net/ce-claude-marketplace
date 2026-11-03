#!/usr/bin/env bash
set -euo pipefail

ACE_CLI="$(dirname "${BASH_SOURCE[0]}")/ace-cli"  # the wrapper: plugin-local first, then global

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

# Parse arguments
MODE="${1:-hybrid}"  # Default: hybrid mode
THOROUGHNESS="${2:-medium}"  # Default: medium

echo "🔄 Bootstrapping ACE playbook (mode=$MODE, thoroughness=$THOROUGHNESS)..."
echo "This may take 10-30 seconds..."

# CLI reads org/project from env vars automatically
"$ACE_CLI" bootstrap \
  --mode "$MODE" \
  --thoroughness "$THOROUGHNESS"
