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

# Build query from file basename only (no domain token — server-team confirmed
# domain_match ANTI-predicts relevance; cross-domain patterns are more useful;
# let de-confounded bandit_rank order an unfiltered set).
FILE_BASENAME=$(basename "$FILE_PATH" 2>/dev/null | sed 's/\.[^.]*$//' || echo "")
# Edge case: if FILE_BASENAME is empty there is no usable query — skip entirely.
[ -z "$FILE_BASENAME" ] && exit 0
SEARCH_QUERY="${FILE_BASENAME}"

if command -v ace-cli >/dev/null 2>&1; then
  # Change A (v7.1.2): Session pinning — reuse existing task_session_id from state
  # file so all domain-shift searches within the SAME task pin to the SAME bucket.
  # Mirrors ace_pretooluse_wrapper.sh: read EXISTING_TSID, pass --pin-session, and
  # pass --task-session-id on the append call (idempotent storage).
  _ACE_PLUGIN_ROOT_PDI="${ACE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
  _PDI_SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // "unknown"' 2>/dev/null || echo "unknown")
  _PDI_AGENT_ID=$(echo "$INPUT_JSON" | jq -r '.agent_id // ""' 2>/dev/null || echo "")
  EXISTING_TSID=$(python3 "${_ACE_PLUGIN_ROOT_PDI}/shared-hooks/utils/patterns_used_state.py" \
    --session "$_PDI_SESSION_ID" --agent-id "$_PDI_AGENT_ID" \
    --read-task-session-id 2>/dev/null || echo "")
  if [ -z "$EXISTING_TSID" ]; then
    EXISTING_TSID=$(python3 -c 'import uuid; print(uuid.uuid4())' 2>/dev/null || echo "")
  fi

  # Build ace-cli search command with --pin-session if we have a task_session_id.
  # --top-k 8: server-side count bound for domain-shift (hot path, per-tool-call).
  # The server SELECTS the top-8 patterns; the client does NOT cap client-side.
  if [ -n "$EXISTING_TSID" ]; then
    RESULT=$(echo "$SEARCH_QUERY" | ace-cli search --stdin --json \
      --top-k 8 --pin-session "$EXISTING_TSID" 2>/dev/null || echo "")
  else
    RESULT=$(echo "$SEARCH_QUERY" | ace-cli search --stdin --json \
      --top-k 8 2>/dev/null || echo "")
  fi
  if [ -n "$RESULT" ] && echo "$RESULT" | jq -e '.similar_patterns | length > 0' >/dev/null 2>&1; then
    # Strip server-internal fields AND apply v15 quality gate (Change B: v7.1.2).
    # Uses --strip-and-gate mode of patterns_used_state.py so ALL inject paths
    # share the SAME USEFUL_FIELDS set + _quality_gate logic as ace_before_task.py.
    STRIPPED=$(echo "$RESULT" | python3 "${_ACE_PLUGIN_ROOT_PDI}/shared-hooks/utils/patterns_used_state.py" --strip-and-gate 2>/dev/null || echo "$RESULT")

    # After gate: if all patterns were filtered, skip injection
    GATED_COUNT=$(echo "$STRIPPED" | jq -r '.count // 0' 2>/dev/null || echo "0")
    if [ "$GATED_COUNT" = "0" ]; then
      exit 0
    fi

    CONTEXT="<ace-patterns-domain-shift domain=\"${MATCHED_DOMAIN}\">${STRIPPED}</ace-patterns-domain-shift>"

    # Change A (v7.1.2): Track injected patterns for RL + store task_session_id.
    # Pass --task-session-id so the state file stores the same EXISTING_TSID
    # (idempotent — if before_task already wrote it, this is a no-op for that field).
    # F-080: extract retrieval_id from RESULT top-level field.
    _PDI_RETRIEVAL_ID=$(echo "$RESULT" | jq -r 'if .retrieval_id != null and .retrieval_id != "" then .retrieval_id else empty end' 2>/dev/null || true)
    _PDI_TSID_FLAG=""
    if [ -n "$EXISTING_TSID" ]; then
      _PDI_TSID_FLAG="--task-session-id $EXISTING_TSID"
    fi
    if [ -n "$_PDI_RETRIEVAL_ID" ] && [ "$_PDI_RETRIEVAL_ID" != "null" ]; then
      # shellcheck disable=SC2086
      echo "$RESULT" | python3 "${_ACE_PLUGIN_ROOT_PDI}/shared-hooks/utils/patterns_used_state.py" \
        --session "$_PDI_SESSION_ID" --agent-id "$_PDI_AGENT_ID" \
        --retrieval-id "$_PDI_RETRIEVAL_ID" \
        $_PDI_TSID_FLAG >/dev/null 2>&1 || true
    else
      # shellcheck disable=SC2086
      echo "$RESULT" | python3 "${_ACE_PLUGIN_ROOT_PDI}/shared-hooks/utils/patterns_used_state.py" \
        --session "$_PDI_SESSION_ID" --agent-id "$_PDI_AGENT_ID" \
        $_PDI_TSID_FLAG >/dev/null 2>&1 || true
    fi

    jq -n --arg ctx "$CONTEXT" '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
    exit 0
  fi
fi

exit 0
