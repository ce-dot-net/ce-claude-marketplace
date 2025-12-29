#!/usr/bin/env bash
# ACE PreToolUse Hook - Continuous Auto-Search
# v5.4.7: Flag file check + ace-cli/ace-cli detection
#
# When Claude enters a new domain (e.g., reading cache files after working on auth),
# this hook automatically searches for domain-specific patterns and injects them.
#
# Key insight: PreToolUse fires BEFORE the tool runs, allowing Claude to have
# domain-specific patterns available BEFORE reading unfamiliar code.

set -eo pipefail

ACE_PLUGIN_VERSION="5.4.7"

# ACE disable flag check (set by SessionStart if CLI issues detected)
# Official Claude Code pattern: flag file coordination between hooks
SESSION_ID_FOR_FLAG="${SESSION_ID:-default}"
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID_FOR_FLAG}.flag"
if [ -f "$ACE_DISABLED_FLAG" ]; then
  # ACE is disabled for this session - exit silently
  exit 0
fi

# CLI command detection (ace-cli preferred, ace-cli fallback)
if command -v ace-cli >/dev/null 2>&1; then
  CLI_CMD="ace-cli"
elif command -v ace-cli >/dev/null 2>&1; then
  CLI_CMD="ce-ace"
else
  exit 0  # No CLI available - exit silently
fi

# Dynamic domain matching - no hardcoded lists!
# Splits hyphenated domains into words and matches each word against path segments
# Examples:
# - "ace-platform-system" domain → words: "ace", "platform", "system"
# - Path "/ace/scripts/foo.ts" → segments: "ace", "scripts", "foo", "ts"
# - Match: "ace" = "ace" (exact word match) ✓
# - Also supports 4-char prefix matching for partial matches

# Get common prefix length between two strings
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

  # Extract path segments (split by / and other separators)
  local segments=$(echo "$path" | tr '/._-' ' ')

  # Extract domain words (split by -)
  # e.g., "ace-platform-system-diagnostics" → "ace platform system diagnostics"
  local domain_words=$(echo "$domain" | tr '-' ' ')

  for segment in $segments; do
    # Skip very short segments
    [ ${#segment} -lt 3 ] && continue

    # Check against each word in the domain
    for word in $domain_words; do
      # Skip very short words
      [ ${#word} -lt 3 ] && continue

      # Exact match (case-insensitive comparison already done upstream)
      if [ "$segment" = "$word" ]; then
        return 0  # Exact word match
      fi

      # Check common prefix length (min 4 chars for semantic match)
      local prefix_len=$(common_prefix_len "$word" "$segment")
      if [ "$prefix_len" -ge 4 ]; then
        return 0  # Strong semantic match
      fi
    done
  done

  return 1  # No match
}

# Read hook input from stdin
INPUT_JSON=$(cat)

# Extract tool name and file path
TOOL_NAME=$(echo "$INPUT_JSON" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT_JSON" | jq -r '.tool_input.file_path // .tool_input.path // .tool_input.pattern // empty')

# Only process file read operations (Read, Glob, Grep)
if [[ ! "$TOOL_NAME" =~ ^(Read|Glob|Grep)$ ]]; then
  exit 0
fi

# Skip if no file path
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Get project context
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
if [ -z "$PROJECT_ID" ]; then
  exit 0
fi

# Read stored domains from LAST search (server-provided, not hardcoded!)
# This file is written by UserPromptSubmit hook (ace_before_task.py)
DOMAINS_FILE="/tmp/ace-domains-${PROJECT_ID}.json"
if [ ! -f "$DOMAINS_FILE" ]; then
  exit 0  # No domains stored yet - first search hasn't happened
fi

# Extract all domain names (keys are in format "domain-name:source")
# Get unique domain names by splitting on ":"
ALL_DOMAINS=$(jq -r 'keys[]' "$DOMAINS_FILE" 2>/dev/null | cut -d':' -f1 | sort -u | tr '[:upper:]' '[:lower:]')

if [ -z "$ALL_DOMAINS" ]; then
  exit 0  # No domains found
fi

# Extract keywords from path (lowercase for matching)
PATH_LOWER=$(echo "$FILE_PATH" | tr '[:upper:]' '[:lower:]')

# Find first matching domain in the file path using dynamic matching
MATCHED_DOMAIN=""
for domain in $ALL_DOMAINS; do
  if match_domain_to_path "$domain" "$PATH_LOWER"; then
    MATCHED_DOMAIN="$domain"
    break
  fi
done

# No domain match in path - exit silently
if [ -z "$MATCHED_DOMAIN" ]; then
  exit 0
fi

# Track domain shifts
DOMAIN_FILE="/tmp/ace-domain-${PROJECT_ID}.txt"
LAST_DOMAIN=""
if [ -f "$DOMAIN_FILE" ]; then
  LAST_DOMAIN=$(cat "$DOMAIN_FILE" 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "")
fi

# Update current domain
echo "$MATCHED_DOMAIN" > "$DOMAIN_FILE"

# Only take action on domain SHIFT (not first time or same domain)
if [ "$MATCHED_DOMAIN" != "$LAST_DOMAIN" ] && [ -n "$LAST_DOMAIN" ]; then
  # Domain shift detected! AUTO-SEARCH and inject patterns

  # 0. Get org context for search
  ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  if [ -z "$ORG_ID" ]; then
    # No org context - fallback to reminder
    jq -n --arg d "$MATCHED_DOMAIN" --arg p "$LAST_DOMAIN" \
      '{"systemMessage": "💡 [ACE] Domain shift: \($p) → \($d). Consider: /ace:ace-search \($d)"}'
    exit 0
  fi

  # 1. Build search query for the new domain
  # Use first word of domain + "patterns" for best semantic match
  # "troubleshooting-and-pitfalls" → "troubleshooting patterns"
  FIRST_WORD=$(echo "$MATCHED_DOMAIN" | cut -d'-' -f1)
  SEARCH_QUERY="${FIRST_WORD} patterns"

  # 2. Call ace-cli search with domain filter (env vars for context)
  export ACE_ORG_ID="$ORG_ID"
  export ACE_PROJECT_ID="$PROJECT_ID"

  # CLI already verified by flag file check above

  SEARCH_RESULT=$(echo "$SEARCH_QUERY" | $CLI_CMD search --stdin --json \
    --allowed-domains "$MATCHED_DOMAIN" 2>/dev/null | \
    iconv -f UTF-8 -t UTF-8 -c 2>/dev/null || echo "")  # Sanitize Unicode

  # 3. Check if search succeeded
  PATTERN_COUNT=$(echo "$SEARCH_RESULT" | jq -r '.count // 0' 2>/dev/null || echo "0")

  if [ "$PATTERN_COUNT" != "0" ] && [ "$PATTERN_COUNT" != "null" ] && [ -n "$SEARCH_RESULT" ]; then
    # 4. Build ace-patterns context (same format as UserPromptSubmit)
    ACE_CONTEXT="<ace-patterns-domain-shift domain=\"${MATCHED_DOMAIN}\">
${SEARCH_RESULT}
</ace-patterns-domain-shift>"

    # 4.5: Log domain shift metrics (v5.4.2)
    LOG_DIR=".claude/data/logs"
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // "unknown"')
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    jq -n --arg ts "$TIMESTAMP" \
          --arg hook "PreToolUse" \
          --arg sid "$SESSION_ID" \
          --arg pid "$PROJECT_ID" \
          --arg from "$LAST_DOMAIN" \
          --arg to "$MATCHED_DOMAIN" \
          --arg path "$FILE_PATH" \
          --argjson count "$PATTERN_COUNT" \
          --argjson success true \
      '{
        timestamp: $ts,
        event: "domain_shift",
        hook: $hook,
        session_id: $sid,
        project_id: $pid,
        from_domain: $from,
        to_domain: $to,
        file_path: ($path | if length > 200 then .[:200] else . end),
        patterns_found: $count,
        search_succeeded: $success
      }' >> "$LOG_DIR/ace-relevance.jsonl" 2>/dev/null || true

    # 5. Output with additionalContext (patterns injected into Claude's context)
    jq -n \
      --arg old "$LAST_DOMAIN" \
      --arg new "$MATCHED_DOMAIN" \
      --arg count "$PATTERN_COUNT" \
      --arg ctx "$ACE_CONTEXT" \
      '{
        "systemMessage": "🔄 [ACE] Domain shift: \($old) → \($new). Auto-loaded \($count) patterns.",
        "hookSpecificOutput": {
          "hookEventName": "PreToolUse",
          "additionalContext": $ctx
        }
      }'
  else
    # Fallback: Search failed or no patterns - log failure and show reminder
    LOG_DIR=".claude/data/logs"
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // "unknown"')
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    jq -n --arg ts "$TIMESTAMP" \
          --arg hook "PreToolUse" \
          --arg sid "$SESSION_ID" \
          --arg pid "$PROJECT_ID" \
          --arg from "$LAST_DOMAIN" \
          --arg to "$MATCHED_DOMAIN" \
          --arg path "$FILE_PATH" \
          --argjson count 0 \
          --argjson success false \
      '{
        timestamp: $ts,
        event: "domain_shift",
        hook: $hook,
        session_id: $sid,
        project_id: $pid,
        from_domain: $from,
        to_domain: $to,
        file_path: ($path | if length > 200 then .[:200] else . end),
        patterns_found: $count,
        search_succeeded: $success
      }' >> "$LOG_DIR/ace-relevance.jsonl" 2>/dev/null || true

    jq -n \
      --arg old "$LAST_DOMAIN" \
      --arg new "$MATCHED_DOMAIN" \
      '{
        "systemMessage": "💡 [ACE] Domain shift: \($old) → \($new). Consider: /ace:ace-search \($new)"
      }'
  fi
fi
