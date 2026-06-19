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
# PR-review B2: ERR trap so an internal failure doesn't propagate to CC.
# PreToolUse fires BEFORE the tool runs — a non-zero exit here blocks the
# user's tool call. We must NEVER block user work because of an ACE bug.
trap 'echo "[ERROR] ACE hook failed: $(basename $0) line $LINENO" >&2; exit 0' ERR

source "${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/scripts/_ace_env.sh"

# ACE disable flag check (set by SessionStart if CLI issues detected)
# Official Claude Code pattern: flag file coordination between hooks
SESSION_ID_FOR_FLAG="${SESSION_ID:-default}"
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID_FOR_FLAG}.flag"
if [ -f "$ACE_DISABLED_FLAG" ]; then
  # ACE is disabled for this session - exit silently
  exit 0
fi

# CLI command detection
if ! command -v ace-cli >/dev/null 2>&1; then
  exit 0  # No CLI available - exit silently
fi
CLI_CMD="ace-cli"

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

# Extract the agent identity ONCE. agent_id is empty for the main agent and the
# child UUID for a subagent (v6.4.0 contract). AGENT_SUFFIX keys per-agent state
# files so each agent (main + each subagent) owns its OWN domain history.
AGENT_ID=$(echo "$INPUT_JSON" | jq -r '.agent_id // empty' 2>/dev/null || echo "")
AGENT_SUFFIX="${AGENT_ID:-main}"

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

# Track domain shifts — PER-AGENT so a subagent entering main's domain is a
# 'first entry' for THAT agent (main's history no longer suppresses it).
DOMAIN_FILE="/tmp/ace-domain-${PROJECT_ID}-${AGENT_SUFFIX}.txt"
LAST_DOMAIN=""
if [ -f "$DOMAIN_FILE" ]; then
  LAST_DOMAIN=$(cat "$DOMAIN_FILE" 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "")
fi

# Update current domain
echo "$MATCHED_DOMAIN" > "$DOMAIN_FILE"

# Take action on domain ENTRY or SHIFT. LAST_DOMAIN is empty on an agent's FIRST
# touch (per-agent history) — Option B: the first domain per agent now searches,
# giving every subagent a guaranteed recall for ITS OWN task under ITS OWN id.
if [ "$MATCHED_DOMAIN" != "$LAST_DOMAIN" ]; then
  # Domain entry/shift detected! AUTO-SEARCH and inject patterns

  # 0. Get org context for search
  ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  if [ -z "$ORG_ID" ]; then
    # No org context - fallback to reminder
    jq -n --arg d "$MATCHED_DOMAIN" --arg p "$LAST_DOMAIN" \
      '{"systemMessage": "💡 [ACE] Domain shift: \($p) → \($d). Consider: /ace:ace-search \($d)"}'
    exit 0
  fi

  # 1. Build query from file basename only (no domain token — server-team confirmed
  # domain_match ANTI-predicts relevance; cross-domain patterns are more useful;
  # let de-confounded bandit_rank order an unfiltered set).
  FILE_BASENAME=$(basename "$FILE_PATH" 2>/dev/null | sed 's/\.[^.]*$//' || echo "")
  # Edge case: if FILE_BASENAME is empty there is no usable query — skip entirely.
  if [ -z "$FILE_BASENAME" ]; then
    exit 0
  fi
  SEARCH_QUERY="${FILE_BASENAME}"

  # 2. Call ace-cli search with domain filter (env vars for context)
  export ACE_ORG_ID="$ORG_ID"
  export ACE_PROJECT_ID="$PROJECT_ID"

  # CLI already verified by flag file check above

  # Change A (v7.1.2): Session pinning — reuse existing task_session_id from state
  # file so all domain-shift searches within the SAME task pin to the SAME bucket.
  # If no task_session_id stored yet, generate a fresh uuid4 (matches before_task pattern).
  SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // "unknown"')
  EXISTING_TSID=$(python3 "${_ACE_PLUGIN_ROOT}/shared-hooks/utils/patterns_used_state.py" \
    --session "$SESSION_ID" --agent-id "$AGENT_ID" \
    --read-task-session-id 2>/dev/null || echo "")
  if [ -z "$EXISTING_TSID" ]; then
    EXISTING_TSID=$(python3 -c 'import uuid; print(uuid.uuid4())' 2>/dev/null || echo "")
  fi

  # Build search command: pass --pin-session if we have a task_session_id.
  # --top-k 8: server-side count bound for domain-shift (hot path, per-tool-call).
  # The server SELECTS the top-8 patterns; the client does NOT cap client-side.
  if [ -n "$EXISTING_TSID" ]; then
    SEARCH_RESULT=$(echo "$SEARCH_QUERY" | $CLI_CMD search --stdin --json \
      --top-k 8 --pin-session "$EXISTING_TSID" 2>/dev/null | \
      iconv -f UTF-8 -t UTF-8 -c 2>/dev/null || echo "")  # Sanitize Unicode
  else
    SEARCH_RESULT=$(echo "$SEARCH_QUERY" | $CLI_CMD search --stdin --json \
      --top-k 8 2>/dev/null | \
      iconv -f UTF-8 -t UTF-8 -c 2>/dev/null || echo "")  # Sanitize Unicode
  fi

  # 3. Check if search succeeded
  PATTERN_COUNT=$(echo "$SEARCH_RESULT" | jq -r '.count // 0' 2>/dev/null || echo "0")

  if [ "$PATTERN_COUNT" != "0" ] && [ "$PATTERN_COUNT" != "null" ] && [ -n "$SEARCH_RESULT" ]; then
    # 4. Strip server-internal fields AND apply v15 quality gate (Change B: v7.1.2).
    # Uses --strip-and-gate mode of patterns_used_state.py so ALL inject paths
    # share the SAME USEFUL_FIELDS set + quality gate as ace_before_task.py.
    STRIPPED=$(echo "$SEARCH_RESULT" | python3 "${_ACE_PLUGIN_ROOT}/shared-hooks/utils/patterns_used_state.py" \
      --strip-and-gate 2>/dev/null || echo "$SEARCH_RESULT")

    # After gate: if all patterns were filtered, fallback to reminder
    GATED_COUNT=$(echo "$STRIPPED" | jq -r '.count // 0' 2>/dev/null || echo "0")
    if [ "$GATED_COUNT" = "0" ]; then
      jq -n \
        --arg old "$LAST_DOMAIN" \
        --arg new "$MATCHED_DOMAIN" \
        '{"systemMessage": "💡 [ACE] Domain shift: \($old) → \($new). Consider: /ace:ace-search \($new)"}'
      exit 0
    fi

    # Build ace-patterns context (same format as UserPromptSubmit)
    ACE_CONTEXT="<ace-patterns-domain-shift domain=\"${MATCHED_DOMAIN}\">
${STRIPPED}
</ace-patterns-domain-shift>"

    # 4.5: Log domain shift metrics (v5.4.2)
    LOG_DIR=".claude/data/logs"
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    jq -nc --arg ts "$TIMESTAMP" \
          --arg hook "PreToolUse" \
          --arg sid "$SESSION_ID" \
          --arg pid "$PROJECT_ID" \
          --arg from "$LAST_DOMAIN" \
          --arg to "$MATCHED_DOMAIN" \
          --arg path "$FILE_PATH" \
          --arg aid "$AGENT_ID" \
          --argjson count "$GATED_COUNT" \
          --argjson success true \
      '{
        timestamp: $ts,
        event: "domain_shift",
        hook: $hook,
        session_id: $sid,
        project_id: $pid,
        agent_id: $aid,
        from_domain: $from,
        to_domain: $to,
        file_path: ($path | if length > 200 then .[:200] else . end),
        patterns_found: $count,
        search_succeeded: $success
      }' >> "$LOG_DIR/ace-relevance.jsonl" 2>/dev/null || true

    # 4.6: Track injected patterns for reinforcement learning (close subagent gap).
    # Subagents search here (domain-shift) but never fire UserPromptSubmit, so the
    # patterns-used state file was never written for them. Append the injected IDs
    # under THIS agent's id (AGENT_ID, extracted once at the top) so
    # ace_after_task.py (SubagentStop/Stop) reports them in playbook_used.
    # Guarded, non-fatal, stdout-suppressed — MUST NOT corrupt the hook's JSON.
    # F-080: extract retrieval_id from SEARCH_RESULT (top-level field) and pass via --retrieval-id
    # Change A: also pass --task-session-id so the merge keeps it idempotent.
    _RETRIEVAL_ID=$(echo "$SEARCH_RESULT" | jq -r 'if .retrieval_id != null and .retrieval_id != "" then .retrieval_id else empty end' 2>/dev/null || true)
    _TSID_FLAG=""
    if [ -n "$EXISTING_TSID" ]; then
      _TSID_FLAG="--task-session-id $EXISTING_TSID"
    fi
    if [ -n "$_RETRIEVAL_ID" ] && [ "$_RETRIEVAL_ID" != "null" ]; then
      # shellcheck disable=SC2086
      echo "$SEARCH_RESULT" | python3 "${_ACE_PLUGIN_ROOT}/shared-hooks/utils/patterns_used_state.py" \
        --session "$SESSION_ID" --agent-id "$AGENT_ID" --retrieval-id "$_RETRIEVAL_ID" \
        $_TSID_FLAG >/dev/null 2>&1 || true
    else
      # shellcheck disable=SC2086
      echo "$SEARCH_RESULT" | python3 "${_ACE_PLUGIN_ROOT}/shared-hooks/utils/patterns_used_state.py" \
        --session "$SESSION_ID" --agent-id "$AGENT_ID" \
        $_TSID_FLAG >/dev/null 2>&1 || true
    fi

    # 5. Output with additionalContext (patterns injected into Claude's context)
    jq -n \
      --arg old "$LAST_DOMAIN" \
      --arg new "$MATCHED_DOMAIN" \
      --arg count "$GATED_COUNT" \
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
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    jq -nc --arg ts "$TIMESTAMP" \
          --arg hook "PreToolUse" \
          --arg sid "$SESSION_ID" \
          --arg pid "$PROJECT_ID" \
          --arg from "$LAST_DOMAIN" \
          --arg to "$MATCHED_DOMAIN" \
          --arg path "$FILE_PATH" \
          --arg aid "$AGENT_ID" \
          --argjson count 0 \
          --argjson success false \
      '{
        timestamp: $ts,
        event: "domain_shift",
        hook: $hook,
        session_id: $sid,
        project_id: $pid,
        agent_id: $aid,
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
