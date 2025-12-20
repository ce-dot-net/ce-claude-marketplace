#!/usr/bin/env bash
# ACE PreToolUse Hook - Domain-Aware Reminders
# v5.3.0: Detects domain shifts and reminds Claude to search for relevant patterns
#
# When Claude enters a new domain (e.g., reading cache files after working on auth),
# this hook shows a reminder BEFORE the file read to suggest searching for patterns.
#
# Key insight: PreToolUse fires BEFORE the tool runs, giving Claude a chance to
# search for domain-specific patterns before diving into unfamiliar code.

set -euo pipefail

ACE_PLUGIN_VERSION="5.3.0"

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

# Find first matching domain in the file path
MATCHED_DOMAIN=""
for domain in $ALL_DOMAINS; do
  # Check if domain keyword appears in the path
  if [[ "$PATH_LOWER" == *"$domain"* ]]; then
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

# Only show reminder on domain SHIFT (not first time or same domain)
if [ "$MATCHED_DOMAIN" != "$LAST_DOMAIN" ] && [ -n "$LAST_DOMAIN" ]; then
  # Domain shift detected! Show reminder to Claude
  jq -n \
    --arg domain "$MATCHED_DOMAIN" \
    --arg prev "$LAST_DOMAIN" \
    --arg path "$FILE_PATH" \
    '{
      "systemMessage": "💡 [ACE] Domain shift: \($prev) → \($domain). Consider: /ace-search \($domain) patterns --allowed-domains \($domain)"
    }'
fi
