#!/bin/bash
set -eo pipefail
trap 'echo "[ERROR] ACE PostToolUse domain inject: $(basename $0) line $LINENO" >&2; exit 0' ERR

INPUT_JSON=$(cat 2>/dev/null || echo "{}")
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID:-default}.flag"
[ -f "$ACE_DISABLED_FLAG" ] && exit 0

# Extract file path from Read tool input
FILE_PATH=$(echo "$INPUT_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[ -z "$FILE_PATH" ] && exit 0

# Quick domain detection from file path
# Read known domains from project file
CWD=$(echo "$INPUT_JSON" | jq -r '.cwd // empty' 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // .projectId // empty' "${CWD}/.claude/settings.json" 2>/dev/null || echo "")
DOMAINS_FILE="/tmp/ace-domains-${PROJECT_ID}.json"
[ ! -f "$DOMAINS_FILE" ] && exit 0

# Match file path against known domains (simple word matching)
FILE_WORDS=$(echo "$FILE_PATH" | tr '/._-' '\n' | tr '[:upper:]' '[:lower:]' | sort -u)
MATCHED_DOMAIN=""
for domain in $(jq -r 'keys[]' "$DOMAINS_FILE" 2>/dev/null); do
  DOMAIN_WORDS=$(echo "$domain" | tr '-' '\n')
  for dw in $DOMAIN_WORDS; do
    [ ${#dw} -lt 3 ] && continue
    echo "$FILE_WORDS" | grep -q "^${dw}$" && MATCHED_DOMAIN="$domain" && break 2
  done
done

[ -z "$MATCHED_DOMAIN" ] && exit 0

# Check if different from last domain
LAST_DOMAIN_FILE="/tmp/ace-domain-${PROJECT_ID}.txt"
LAST_DOMAIN=$(cat "$LAST_DOMAIN_FILE" 2>/dev/null || echo "")
[ "$MATCHED_DOMAIN" = "$LAST_DOMAIN" ] && exit 0

# Update last domain
echo "$MATCHED_DOMAIN" > "$LAST_DOMAIN_FILE"

# Search for domain-specific patterns
FILE_BASENAME=$(basename "$FILE_PATH" 2>/dev/null | sed 's/\.[^.]*$//' || echo "")
SEARCH_QUERY="${MATCHED_DOMAIN} ${FILE_BASENAME}"

if command -v ace-cli >/dev/null 2>&1; then
  RESULT=$(echo "$SEARCH_QUERY" | ace-cli search --stdin --json --allowed-domains "$MATCHED_DOMAIN" 2>/dev/null || echo "")
  if [ -n "$RESULT" ] && echo "$RESULT" | jq -e '.similar_patterns | length > 0' >/dev/null 2>&1; then
    # Strip metadata (same as ace_before_task.py spec-05)
    STRIPPED=$(echo "$RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
useful={'id','domain','content','confidence','helpful','harmful','section','evidence'}
if 'similar_patterns' in d:
    d['similar_patterns']=[{k:v for k,v in p.items() if k in useful} for p in d['similar_patterns']]
print(json.dumps(d))
" 2>/dev/null || echo "$RESULT")

    CONTEXT="<ace-patterns-domain-shift domain=\"${MATCHED_DOMAIN}\">${STRIPPED}</ace-patterns-domain-shift>"
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"$(echo "$CONTEXT" | sed 's/"/\\"/g')\"}}"
    exit 0
  fi
fi

exit 0
