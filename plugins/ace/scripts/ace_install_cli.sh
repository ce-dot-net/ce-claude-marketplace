#!/usr/bin/env bash
# ACE SessionStart Hook - Consolidated CLI Detection, Migration & Pattern Restoration
# v6.0.1: Remove incorrect stale projectId warning (ace-cli manages its own projectId)
# v6.0.0: Consolidated SessionStart (source field routing for CC 2.1.69+)
#   - startup: Full CLI check, version validation, auth check
#   - resume: Light CLI availability check only (already validated)
#   - compact: Pattern restoration from PreCompact temp file
#   - clear: Full CLI check + pattern restoration
# v5.4.22: Deprecated config detection (old ~/.ace/config.json or apiToken format)
# v5.4.13: Token expiration check (catches 48h standby on new sessions)
# v5.4.7: Flag-based hook disable + daily update check
# Command: ace-cli
#
# Official Claude Code Hook Pattern:
# - Exit 0 with systemMessage for warnings (session continues)
# - Set ACE_DISABLED flag file when CLI issues detected
# - Other hooks check flag file and silently exit
# - Never use continue:false (blocks entire Claude Code session)

set -eo pipefail
trap 'echo "[ERROR] ACE hook failed: $(basename $0) line $LINENO" >&2; exit 0' ERR

# Resolve script directory for auto-sync statusline
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Read stdin JSON (Claude Code 2.1.69+ provides source, agent_type, agent_id)
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# ── Dependency check: jq (required before any JSON parsing) ──
if ! command -v jq >/dev/null 2>&1; then
  # Can't use output_warning or disable_ace_hooks (both need jq/SESSION_ID) — output raw JSON
  echo '{"systemMessage": "⚠️ [ACE] jq is required but not installed. Install: brew install jq (macOS) or apt install jq (Linux)"}'
  echo "jq not installed" > "/tmp/ace-disabled-default.flag"
  exit 0
fi

# Extract session_id from input (fall back to default)
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
SESSION_ID="${SESSION_ID:-default}"

# v6.0.0: Extract source field for consolidated SessionStart (CC 2.1.69+)
# source: 'startup' | 'resume' | 'compact' | 'clear'
SOURCE=$(echo "$INPUT_JSON" | jq -r '.source // "startup"' 2>/dev/null || echo "startup")

# Flag file to disable other ACE hooks (per-session, temp directory)
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID}.flag"
CACHE_FILE="/tmp/ace-update-check-$(date +%Y%m%d).txt"
MIN_VERSION="3.10.3"

# Helper: Disable ACE hooks by creating flag file
disable_ace_hooks() {
  local reason="$1"
  echo "$reason" > "$ACE_DISABLED_FLAG"
}

# Helper: Output JSON with systemMessage (official format)
output_warning() {
  local msg="$1"
  jq -n --arg msg "$msg" '{"systemMessage": $msg}'
}

# Helper: Restore patterns from PreCompact temp file (compact/clear sources)
restore_patterns_after_compact() {
  # Resolve SESSION_ID using same source as PreCompact (ace-session file)
  local PROJECT_ID
  PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  local SESSION_FILE="/tmp/ace-session-${PROJECT_ID}.txt"
  local RESTORE_SESSION_ID="$SESSION_ID"

  if [ -n "$PROJECT_ID" ] && [ -f "$SESSION_FILE" ]; then
    RESTORE_SESSION_ID=$(cat "$SESSION_FILE" 2>/dev/null || echo "$SESSION_ID")
  fi

  local TEMP_FILE="/tmp/ace-patterns-precompact-${RESTORE_SESSION_ID}.json"

  if [ ! -f "$TEMP_FILE" ]; then
    return 0
  fi

  local PATTERN_DATA PATTERNS COUNT
  PATTERN_DATA=$(cat "$TEMP_FILE" 2>/dev/null || echo "{}")
  PATTERNS=$(echo "$PATTERN_DATA" | jq -r '.patterns // ""' 2>/dev/null || echo "")
  COUNT=$(echo "$PATTERN_DATA" | jq -r '.count // "0"' 2>/dev/null || echo "0")

  rm -f "$TEMP_FILE" 2>/dev/null || true

  if [ -z "$PATTERNS" ] || [ "$COUNT" = "0" ]; then
    return 0
  fi

  jq -n \
    --arg patterns "$PATTERNS" \
    --arg session "$RESTORE_SESSION_ID" \
    --arg count "$COUNT" \
    '{
      "systemMessage": "📚 [ACE] Restored \($count) patterns after compaction",
      "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "<!-- ACE Patterns (preserved from session \($session)) -->\n<ace-patterns-recalled>\n\($patterns)\n</ace-patterns-recalled>"
      }
    }'
}

# ── Dependency check: python3 (required for shared hooks) ──
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
fi
if [ -z "$PYTHON_CMD" ]; then
  output_warning "⚠️ [ACE] python3 is required but not installed. Install Python 3.11+ from python.org"
  disable_ace_hooks "python3 not installed"
  exit 0
fi

# ======================================================================
# Source-based routing (v6.0.0: consolidated SessionStart)
# ======================================================================

case "$SOURCE" in
  compact)
    # After compaction: restore patterns only (CLI already validated)
    # ACE disable flag check
    if [ -f "$ACE_DISABLED_FLAG" ]; then
      exit 0
    fi
    restore_patterns_after_compact
    exit 0
    ;;

  resume)
    # Resumed session: light CLI check only (skip version/auth/config)
    rm -f "$ACE_DISABLED_FLAG" 2>/dev/null || true
    if ! command -v ace-cli >/dev/null 2>&1; then
      disable_ace_hooks "CLI not installed"
      output_warning "⛔ [ACE] ace-cli not found. Install: npm install -g @ace-sdk/cli. ACE hooks DISABLED."
    fi
    exit 0
    ;;

  clear)
    # User cleared context: full CLI check + restore patterns
    rm -f "$ACE_DISABLED_FLAG" 2>/dev/null || true
    # Fall through to full CLI check below, then restore patterns at the end
    ;;

  *)
    # startup or unknown: full CLI check
    rm -f "$ACE_DISABLED_FLAG" 2>/dev/null || true
    ;;
esac

# ======================================================================
# Full CLI check (startup + clear sources)
# ======================================================================

# 1. Check if ace-cli exists
if ! command -v ace-cli >/dev/null 2>&1; then
  disable_ace_hooks "CLI not installed"
  output_warning "⛔ [ACE] ace-cli not found. Install: npm install -g @ace-sdk/cli. ACE hooks DISABLED."
  exit 0
fi
CLI_CMD="ace-cli"

# 3. Check version meets minimum
CURRENT_VERSION=$($CLI_CMD --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "0.0.0")
if ! printf '%s\n' "$MIN_VERSION" "$CURRENT_VERSION" | sort -V -C 2>/dev/null; then
  # Version too old - disable ACE hooks
  disable_ace_hooks "CLI version $CURRENT_VERSION < $MIN_VERSION"
  output_warning "⛔ [ACE] Outdated CLI: v$CURRENT_VERSION (requires >= v$MIN_VERSION). Upgrade: npm install -g @ace-sdk/cli. ACE hooks DISABLED."
  exit 0
fi

# 4. Daily update check (cached, non-blocking)
if [ ! -f "$CACHE_FILE" ]; then
  LATEST=$(npm show @ace-sdk/cli version 2>/dev/null || echo "")
  echo "$LATEST" > "$CACHE_FILE" 2>/dev/null || true
fi
LATEST=$(cat "$CACHE_FILE" 2>/dev/null || echo "")

if [ -n "$LATEST" ] && [ "$LATEST" != "$CURRENT_VERSION" ]; then
  output_warning "💡 [ACE] Update available: v$CURRENT_VERSION → v$LATEST. Run: npm install -g @ace-sdk/cli"
fi

# 5. v5.4.22: Deprecated config detection (migration warning)
OLD_CONFIG="$HOME/.ace/config.json"
NEW_CONFIG="$HOME/.config/ace/config.json"

# Check old location with apiToken (pre-device-code era)
if [ -f "$OLD_CONFIG" ] && grep -q '"apiToken"' "$OLD_CONFIG" 2>/dev/null; then
  output_warning "⚠️ [ACE] Deprecated config at ~/.ace/config.json. Run /ace-login to migrate."
fi

# Check new location with old format (apiToken but no auth object - intermediate migration state)
if [ -f "$NEW_CONFIG" ]; then
  if grep -q '"apiToken"' "$NEW_CONFIG" 2>/dev/null && ! grep -q '"auth"' "$NEW_CONFIG" 2>/dev/null; then
    output_warning "⚠️ [ACE] Old config format detected. Run /ace-login to migrate to device code auth."
  fi
fi

# 5b. projectId in global config is managed by ace-cli itself (ace-cli config --project-id)
# Per-project override via ACE_PROJECT_ID in .claude/settings.json takes precedence — no warning needed

# 6. v5.4.13: Token expiration check (catches 48h standby scenario on new sessions)
TOKEN_JSON=$($CLI_CMD whoami --json 2>/dev/null || echo '{}')
AUTHENTICATED=$(echo "$TOKEN_JSON" | jq -r '.authenticated // false' 2>/dev/null)
TOKEN_STATUS=$(echo "$TOKEN_JSON" | jq -r '.token_status // empty' 2>/dev/null)

if [ "$AUTHENTICATED" = "false" ]; then
  output_warning "⚠️ [ACE] Not authenticated. Run /ace-login to setup."
elif [ -n "$TOKEN_STATUS" ]; then
  # Check for expired or expiring soon
  if echo "$TOKEN_STATUS" | grep -qi "expired"; then
    output_warning "⚠️ [ACE] Session expired. Run /ace-login to re-authenticate."
  elif echo "$TOKEN_STATUS" | grep -qi "minutes"; then
    # Token expires in minutes - warn user
    output_warning "⚠️ [ACE] Session expires soon ($TOKEN_STATUS). Consider /ace-login."
  fi
fi

# v6.0.0: On clear source, also try to restore patterns
if [ "$SOURCE" = "clear" ]; then
  restore_patterns_after_compact
fi

# Clean stale self-eval state from previous session
# ace-eval-requested flags and ace-review-result.json should not persist across sessions
rm -f /tmp/ace-eval-requested-*.flag 2>/dev/null || true
rm -f .claude/data/logs/ace-review-result.json 2>/dev/null || true
rm -f .claude/data/logs/ace-eval-request.json 2>/dev/null || true

# Auto-sync statusline script on plugin update (if installed)
STATUSLINE_INSTALLED="$HOME/.claude/ace_statusline.sh"
STATUSLINE_SOURCE="${SCRIPT_DIR}/ace_statusline.sh"
if [ -f "$STATUSLINE_INSTALLED" ] && [ -f "$STATUSLINE_SOURCE" ]; then
  # Compare — if plugin version is newer, overwrite
  if ! cmp -s "$STATUSLINE_SOURCE" "$STATUSLINE_INSTALLED" 2>/dev/null; then
    cp "$STATUSLINE_SOURCE" "$STATUSLINE_INSTALLED" 2>/dev/null && chmod +x "$STATUSLINE_INSTALLED" 2>/dev/null || true
  fi
fi

# Set ACE_CLIENT_ID for per-extension analytics tracking (ace-sdk 2.12.0+)
# Only set if not already configured (respect user/ace-configure override)
if [ -n "$CLAUDE_ENV_FILE" ] && [ -z "${ACE_CLIENT_ID:-}" ]; then
  echo 'export ACE_CLIENT_ID="claude-code"' >> "$CLAUDE_ENV_FILE"
fi

# Clean project-keyed temp files older than 7 days
find /tmp -maxdepth 1 -name "ace-session-*.txt" -mtime +7 -delete 2>/dev/null || true
find /tmp -maxdepth 1 -name "ace-domains-*.json" -mtime +7 -delete 2>/dev/null || true
find /tmp -maxdepth 1 -name "ace-domain-*.txt" -mtime +7 -delete 2>/dev/null || true

# Success - ACE hooks can proceed (no flag file = enabled)
exit 0
