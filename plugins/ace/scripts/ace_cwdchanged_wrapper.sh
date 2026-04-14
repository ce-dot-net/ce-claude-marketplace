#!/usr/bin/env bash
# ACE CwdChanged Hook - Domain Detection on Directory Change
# Triggered when Claude Code changes the working directory.
#
# Input (stdin): JSON with old_cwd, new_cwd, session_id, cwd
# Output (stdout): JSON with hookEventName:"CwdChanged", optional watchPaths
#
# When the new directory maps to a different ACE domain, this hook:
# 1. Detects the domain from the directory path
# 2. Updates /tmp/ace-domain-{project}.txt
# 3. Searches for domain-specific patterns via ace-cli
# 4. Logs the domain change event

set -eo pipefail
trap 'echo "[ERROR] ACE CwdChanged: $(basename $0) line $LINENO" >&2; exit 0' ERR

ACE_PLUGIN_VERSION="6.3.0"

# Read input JSON from stdin
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# Extract fields
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
OLD_CWD=$(echo "$INPUT_JSON" | jq -r '.old_cwd // empty' 2>/dev/null || echo "")
NEW_CWD=$(echo "$INPUT_JSON" | jq -r '.new_cwd // empty' 2>/dev/null || echo "")

# ACE disable flag check
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID:-default}.flag"
[ -f "$ACE_DISABLED_FLAG" ] && exit 0

# Bail if no meaningful change
[ -z "$NEW_CWD" ] && exit 0
[ "$OLD_CWD" = "$NEW_CWD" ] && exit 0

# CLI availability check
if ! command -v ace-cli >/dev/null 2>&1; then
  exit 0
fi
CLI_CMD="ace-cli"

# --- Domain matching (reuse PreToolUse logic) ---

common_prefix_len() {
  local s1="$1" s2="$2"
  local len1=${#s1} len2=${#s2}
  local min_len=$((len1 < len2 ? len1 : len2))
  local i=0
  while [ $i -lt $min_len ]; do
    [ "${s1:$i:1}" != "${s2:$i:1}" ] && break
    i=$((i + 1))
  done
  echo $i
}

match_domain_to_path() {
  local domain="$1"
  local path="$2"
  local segments=$(echo "$path" | tr '/._-' ' ')
  local domain_words=$(echo "$domain" | tr '-' ' ')

  for segment in $segments; do
    [ ${#segment} -lt 3 ] && continue
    for word in $domain_words; do
      [ ${#word} -lt 3 ] && continue
      if [ "$segment" = "$word" ]; then
        return 0
      fi
      local prefix_len=$(common_prefix_len "$word" "$segment")
      if [ "$prefix_len" -ge 4 ]; then
        return 0
      fi
    done
  done
  return 1
}

# --- Project context ---

# Try to get PROJECT_ID from new cwd settings first, then old cwd
PROJECT_ID=""
for dir in "$NEW_CWD" "$OLD_CWD"; do
  [ -z "$dir" ] && continue
  PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' "${dir}/.claude/settings.json" 2>/dev/null || echo "")
  [ -n "$PROJECT_ID" ] && break
done

if [ -z "$PROJECT_ID" ]; then
  exit 0
fi

# --- Domain detection from new CWD ---

DOMAINS_FILE="/tmp/ace-domains-${PROJECT_ID}.json"
if [ ! -f "$DOMAINS_FILE" ]; then
  exit 0
fi

ALL_DOMAINS=$(jq -r 'keys[]' "$DOMAINS_FILE" 2>/dev/null | cut -d':' -f1 | sort -u | tr '[:upper:]' '[:lower:]')
if [ -z "$ALL_DOMAINS" ]; then
  exit 0
fi

NEW_CWD_LOWER=$(echo "$NEW_CWD" | tr '[:upper:]' '[:lower:]')

MATCHED_DOMAIN=""
for domain in $ALL_DOMAINS; do
  if match_domain_to_path "$domain" "$NEW_CWD_LOWER"; then
    MATCHED_DOMAIN="$domain"
    break
  fi
done

# No domain match in new CWD
if [ -z "$MATCHED_DOMAIN" ]; then
  exit 0
fi

# --- Check for domain shift ---

DOMAIN_FILE="/tmp/ace-domain-${PROJECT_ID}.txt"
LAST_DOMAIN=$(cat "$DOMAIN_FILE" 2>/dev/null || echo "")

# Same domain - no action needed
if [ "$MATCHED_DOMAIN" = "$LAST_DOMAIN" ]; then
  exit 0
fi

# Update current domain
echo "$MATCHED_DOMAIN" > "$DOMAIN_FILE"

# --- Log the domain change ---

LOG_DIR=".claude/data/logs"
mkdir -p "$LOG_DIR" 2>/dev/null || true
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
jq -nc --arg ts "$TIMESTAMP" \
      --arg hook "CwdChanged" \
      --arg sid "$SESSION_ID" \
      --arg pid "$PROJECT_ID" \
      --arg from "${LAST_DOMAIN:-none}" \
      --arg to "$MATCHED_DOMAIN" \
      --arg old_cwd "$OLD_CWD" \
      --arg new_cwd "$NEW_CWD" \
  '{
    timestamp: $ts,
    event: "domain_shift",
    hook: $hook,
    session_id: $sid,
    project_id: $pid,
    from_domain: $from,
    to_domain: $to,
    old_cwd: $old_cwd,
    new_cwd: $new_cwd
  }' >> "${LOG_DIR}/ace-search-events.jsonl" 2>/dev/null || true

# --- Search for domain-specific patterns (if we have org context) ---

ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' "${NEW_CWD}/.claude/settings.json" 2>/dev/null || \
         jq -r '.orgId // .env.ACE_ORG_ID // empty' "${OLD_CWD}/.claude/settings.json" 2>/dev/null || echo "")

if [ -n "$ORG_ID" ]; then
  export ACE_ORG_ID="$ORG_ID"
  export ACE_PROJECT_ID="$PROJECT_ID"

  # Build query from domain + last directory segment
  DIR_BASENAME=$(basename "$NEW_CWD" 2>/dev/null || echo "")
  SEARCH_QUERY="${MATCHED_DOMAIN}"
  if [ -n "$DIR_BASENAME" ] && [ "$DIR_BASENAME" != "$MATCHED_DOMAIN" ]; then
    SEARCH_QUERY="${MATCHED_DOMAIN} ${DIR_BASENAME}"
  fi

  SEARCH_RESULT=$(echo "$SEARCH_QUERY" | $CLI_CMD search --stdin --json \
    --allowed-domains "$MATCHED_DOMAIN" 2>/dev/null | \
    iconv -f UTF-8 -t UTF-8 -c 2>/dev/null || echo "")

  PATTERN_COUNT=$(echo "$SEARCH_RESULT" | jq -r '.count // 0' 2>/dev/null || echo "0")

  if [ "$PATTERN_COUNT" != "0" ] && [ "$PATTERN_COUNT" != "null" ] && [ -n "$SEARCH_RESULT" ]; then
    # Strip internal metadata (same as other hooks)
    STRIPPED=$(echo "$SEARCH_RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
useful={'id','domain','content','confidence','helpful','harmful','section','evidence'}
if 'similar_patterns' in d:
    d['similar_patterns']=[{k:v for k,v in p.items() if k in useful} for p in d['similar_patterns']]
print(json.dumps(d))
" 2>/dev/null || echo "$SEARCH_RESULT")

    # Log the search result
    jq -nc --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
          --arg hook "CwdChanged" \
          --arg sid "$SESSION_ID" \
          --arg pid "$PROJECT_ID" \
          --arg domain "$MATCHED_DOMAIN" \
          --argjson count "$PATTERN_COUNT" \
      '{
        timestamp: $ts,
        event: "domain_search",
        hook: $hook,
        session_id: $sid,
        project_id: $pid,
        domain: $domain,
        count: $count
      }' >> "${LOG_DIR}/ace-search-events.jsonl" 2>/dev/null || true
  fi
fi

# CwdChanged hooks output: hookEventName + optional watchPaths
# No systemMessage or additionalContext support for this event type
jq -n '{hookEventName: "CwdChanged"}'
exit 0
