#!/usr/bin/env bash
# ACE SessionStart Hook - CLI Detection & Migration
# v5.4.7: Flag-based hook disable + daily update check
# Command: ace-cli (new) or ce-ace (deprecated)
#
# Official Claude Code Hook Pattern:
# - Exit 0 with systemMessage for warnings (session continues)
# - Set ACE_DISABLED flag file when CLI issues detected
# - Other hooks check flag file and silently exit
# - Never use continue:false (blocks entire Claude Code session)

set -eo pipefail

# Flag file to disable other ACE hooks (per-session, temp directory)
SESSION_ID="${SESSION_ID:-default}"
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID}.flag"
CACHE_FILE="/tmp/ace-update-check-$(date +%Y%m%d).txt"
MIN_VERSION="3.4.1"

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

# Clear any previous disable flag (new session)
rm -f "$ACE_DISABLED_FLAG" 2>/dev/null || true

# 1. Check if ace-cli exists (new command name)
if ! command -v ace-cli >/dev/null 2>&1; then
  # Fallback: Check old ce-ace command
  if command -v ce-ace >/dev/null 2>&1; then
    # Old command found - warn but allow (transition period)
    output_warning "⚠️ [ACE] Deprecated command 'ce-ace' detected. Upgrade: npm uninstall -g @ce-dot-net/ce-ace-cli && npm install -g @ace-sdk/cli"
    CLI_CMD="ce-ace"
  else
    # No CLI at all - disable ACE hooks
    disable_ace_hooks "CLI not installed"
    output_warning "⛔ [ACE] ace-cli not found. Install: npm install -g @ace-sdk/cli. ACE hooks DISABLED."
    exit 0  # Exit 0 to not disrupt Claude Code (flag file disables other hooks)
  fi
else
  CLI_CMD="ace-cli"
fi

# 2. Detect old deprecated package (causes 422 errors)
# Use grep -q for boolean check instead of grep -c which can have parsing issues
if npm list -g @ce-dot-net/ce-ace-cli 2>/dev/null | grep -q "@ce-dot-net"; then
  # Old package detected - disable ACE hooks and show migration instructions
  disable_ace_hooks "Deprecated package @ce-dot-net/ce-ace-cli"
  output_warning "⛔ [ACE] DEPRECATED: @ce-dot-net/ce-ace-cli causes 422 API errors. Migrate: npm uninstall -g @ce-dot-net/ce-ace-cli && npm install -g @ace-sdk/cli. ACE hooks DISABLED."
  exit 0
fi

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

# Success - ACE hooks can proceed (no flag file = enabled)
exit 0
