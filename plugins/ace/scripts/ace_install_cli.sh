#!/usr/bin/env bash
# ACE SessionStart Hook - CLI Detection & Migration
# v5.4.23: Deprecated CLAUDE.md content detection + auto-cleanup
# v5.4.22: Deprecated config detection (old ~/.ace/config.json or apiToken format)
# v5.4.13: Token expiration check (catches 48h standby on new sessions)
# v5.4.11: Capture agent_type from Claude Code 2.1.2+
# v5.4.7: Flag-based hook disable + daily update check
# Command: ace-cli (new) or ce-ace (deprecated)
#
# Official Claude Code Hook Pattern:
# - Exit 0 with systemMessage for warnings (session continues)
# - Set ACE_DISABLED flag file when CLI issues detected
# - Other hooks check flag file and silently exit
# - Never use continue:false (blocks entire Claude Code session)

set -eo pipefail

# Read stdin JSON (Claude Code 2.1.2+ provides agent_type)
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# Extract session_id from input (fall back to env var or default)
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
SESSION_ID="${SESSION_ID:-${SESSION_ID:-default}}"

# v5.4.11: Extract agent_type (new in Claude Code 2.1.2)
# agent_type identifies subagent type: "main", "refactorer", "coder", etc.
AGENT_TYPE=$(echo "$INPUT_JSON" | jq -r '.agent_type // "main"' 2>/dev/null || echo "main")

# Flag file to disable other ACE hooks (per-session, temp directory)
ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID}.flag"
ACE_AGENT_TYPE_FILE="/tmp/ace-agent-type-${SESSION_ID}.txt"
CACHE_FILE="/tmp/ace-update-check-$(date +%Y%m%d).txt"
MIN_VERSION="3.10.3"

# Save agent_type for other hooks (before_task.py, after_task.py)
echo "$AGENT_TYPE" > "$ACE_AGENT_TYPE_FILE" 2>/dev/null || true

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
  # Fallback: Check old ce-ace command (deprecated)
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

# 7. v5.4.27: Deprecated CLAUDE.md content detection + auto-cleanup
# Hooks handle everything - ACE instructions in CLAUDE.md are no longer needed (any version)
cleanup_deprecated_claude() {
  local file="$1"
  local location="$2"  # "project" or "global"

  if [ ! -f "$file" ]; then
    return
  fi

  # Check for ANY ACE markers or skill references (all versions deprecated)
  if ! grep -q 'ACE_SECTION_START\|ace-orchestration:ace-\|# ACE Orchestration Plugin\|# ACE Plugin' "$file" 2>/dev/null; then
    return
  fi

  # Detected ACE content - extract version
  local version
  version=$(grep -oE 'ACE_SECTION_START v[0-9]+\.[0-9]+\.[0-9]+' "$file" 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")

  # Create backup
  local backup="${file}.ace-backup-$(date +%Y%m%d-%H%M%S)"
  cp "$file" "$backup"

  # Check if file has proper markers for safe removal
  if grep -q '<!-- ACE_SECTION_START' "$file" && grep -q '<!-- ACE_SECTION_END' "$file"; then
    # Safe removal using sed - remove lines between markers (inclusive)
    local start_line end_line
    start_line=$(grep -n '<!-- ACE_SECTION_START' "$file" | head -1 | cut -d: -f1)
    end_line=$(grep -n '<!-- ACE_SECTION_END' "$file" | head -1 | cut -d: -f1)

    if [ -n "$start_line" ] && [ -n "$end_line" ] && [ "$start_line" -lt "$end_line" ]; then
      # Remove ACE section (lines start_line through end_line) - all versions
      sed -i '' "${start_line},${end_line}d" "$file"
      # Clean up any resulting multiple blank lines
      sed -i '' '/^$/N;/^\n$/d' "$file"
      output_warning "🧹 [ACE] Removed deprecated v${version} instructions from ${location} CLAUDE.md. Hooks handle everything now. Backup: $(basename "$backup")"
    fi
  else
    # No markers - check for skill-based content without markers (warn only)
    if grep -q 'ace-orchestration:ace-\|ace:ace-' "$file" 2>/dev/null; then
      output_warning "⚠️ [ACE] Deprecated ACE instructions in ${location} CLAUDE.md. Manual removal recommended (hooks handle everything automatically)."
      # Remove backup since we didn't modify
      rm -f "$backup" 2>/dev/null || true
    fi
  fi
}

# Check global CLAUDE.md
cleanup_deprecated_claude "$HOME/CLAUDE.md" "global"

# Check project CLAUDE.md (use CLAUDE_PROJECT_DIR if set, else pwd)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
if [ -n "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/CLAUDE.md" ]; then
  cleanup_deprecated_claude "$PROJECT_DIR/CLAUDE.md" "project"
fi

# Success - ACE hooks can proceed (no flag file = enabled)
exit 0
