#!/usr/bin/env bash
# ACE SessionEnd Hook - Per-session temp file cleanup
# v6.0.0: Clean up per-session temp files when session ends
# Pure bash (no Python) for fast execution
#
# SessionEnd provides: session_id, reason ('clear'|'logout'|'prompt_input_exit'|'other')
set -eo pipefail
trap 'echo "[ERROR] ACE hook failed: $(basename $0) line $LINENO" >&2; exit 0' ERR

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

# Option B GC: reap per-agent patterns-used state files for this session. These are
# written by ace_before_task.py (main) and the PreToolUse wrapper (subagents) and
# reaped by ace_after_task.py on Stop/SubagentStop; this sweeps any orphan suffixes
# (e.g. a subagent that searched but never reached SubagentStop). Glob covers -main
# and every -{uuid}. Guarded + best-effort.
rm -f ".claude/data/logs/ace-patterns-used-${SESSION_ID}-"*.json 2>/dev/null || true

# Option B GC: per-agent domain-history files are project-keyed (not session-keyed),
# so derive PROJECT_ID the same way the PreToolUse wrapper does. Guarded; if PROJECT_ID
# can't be resolved we skip the tmp sweep rather than risk a too-broad glob.
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
if [ -n "$PROJECT_ID" ]; then
  rm -f "/tmp/ace-domain-${PROJECT_ID}-"*.txt 2>/dev/null || true
fi

# Always exit 0 — cleanup is best-effort
exit 0
