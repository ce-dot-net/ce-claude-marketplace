#!/usr/bin/env bash
# ACE SessionEnd Hook - Per-session temp file cleanup
# v6.0.0: Clean up per-session temp files when session ends
# Pure bash (no Python) for fast execution
#
# SessionEnd provides: session_id, reason ('clear'|'logout'|'prompt_input_exit'|'other')
set -eo pipefail
trap 'exit 0' ERR

# Read stdin JSON
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# Extract session_id from input
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")

if [ -z "$SESSION_ID" ]; then
  # No session_id — nothing to clean up
  exit 0
fi

# Best-effort cleanup of session-keyed temp files only
# NOTE: Project-keyed files (ace-session-{project}, ace-domains-{project}, ace-domain-{project})
# are intentional cross-task shared state — NOT cleaned here.
# session_id is task-based: each task has its own session_id, trajectory, and steps.
rm -f "/tmp/ace-disabled-${SESSION_ID}.flag" 2>/dev/null || true
rm -f "/tmp/ace-patterns-precompact-${SESSION_ID}.json" 2>/dev/null || true
rm -f "/tmp/ace-eval-requested-${SESSION_ID}.flag" 2>/dev/null || true
# Clean fire-and-forget eval state files (ace-eval-request.json, ace-review-result.json)
rm -f .claude/data/logs/ace-eval-request.json 2>/dev/null || true

# Always exit 0 — cleanup is best-effort
exit 0
