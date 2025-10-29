#!/bin/bash
# ACE Version Check - Runs on SessionStart
# Compares project CLAUDE.md ACE version with plugin version

PLUGIN_CLAUDE="${CLAUDE_PLUGIN_ROOT}/CLAUDE.md"
PROJECT_CLAUDE="./CLAUDE.md"
VERSION_CACHE="$HOME/.ace/version_check_cache"

# Only check if project CLAUDE.md exists
if [ ! -f "$PROJECT_CLAUDE" ]; then
  exit 0
fi

# Check if ACE content exists in project
if ! grep -q "ACE Orchestration Plugin" "$PROJECT_CLAUDE" 2>/dev/null; then
  exit 0
fi

# Extract versions
PROJECT_VERSION=$(grep -m 1 "Complete Automatic Learning Cycle (v" "$PROJECT_CLAUDE" 2>/dev/null | sed -n 's/.*v\([0-9]\+\.[0-9]\+\.[0-9]\+\).*/\1/p')
PLUGIN_VERSION=$(grep -m 1 "Complete Automatic Learning Cycle (v" "$PLUGIN_CLAUDE" 2>/dev/null | sed -n 's/.*v\([0-9]\+\.[0-9]\+\.[0-9]\+\).*/\1/p')

# If versions couldn't be extracted, skip
if [ -z "$PROJECT_VERSION" ] || [ -z "$PLUGIN_VERSION" ]; then
  exit 0
fi

# If versions match, skip
if [ "$PROJECT_VERSION" = "$PLUGIN_VERSION" ]; then
  exit 0
fi

# Check if we already notified in this session (debounce)
CACHE_KEY="${PROJECT_VERSION}_${PLUGIN_VERSION}"
if [ -f "$VERSION_CACHE" ] && grep -q "$CACHE_KEY" "$VERSION_CACHE" 2>/dev/null; then
  exit 0
fi

# Create cache directory if needed
mkdir -p "$HOME/.ace"

# Mark as notified
echo "$CACHE_KEY" > "$VERSION_CACHE"

# Output notification message (will be shown to Claude)
cat << EOF
⚠️ ACE Update Available!

Your project's ACE instructions are outdated:
  Current: v${PROJECT_VERSION}
  Latest:  v${PLUGIN_VERSION}

Run \`/ace-claude-init\` to update and get the latest features!

This check runs once per session. Disable by removing hooks/ace-version-check.sh
EOF
