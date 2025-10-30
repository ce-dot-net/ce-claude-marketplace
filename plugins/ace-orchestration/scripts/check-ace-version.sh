#!/usr/bin/env bash

# ACE Plugin - Version Check Hook
# Runs on SessionStart to detect if project CLAUDE.md has outdated ACE instructions
# Creates notification if update is available
# Silent operation (no output to avoid cluttering session start)

set -e

# Use CLAUDE_PROJECT_DIR if available (set by Claude Code for hooks)
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Silently exit if we can't determine project root
if [ -z "$PROJECT_ROOT" ] || [ ! -d "$PROJECT_ROOT" ]; then
    exit 0
fi

# Fallback to detect plugin root if CLAUDE_PLUGIN_ROOT not set
if [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
    # Script is at: plugins/ace-orchestration/scripts/check-ace-version.sh
    # Plugin root is: plugins/ace-orchestration/
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
    PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
fi

# Get plugin version from plugin.json
PLUGIN_JSON="${PLUGIN_ROOT}/.claude-plugin/plugin.json"
if [ ! -f "$PLUGIN_JSON" ]; then
    exit 0  # Can't determine plugin version, exit silently
fi

PLUGIN_VERSION=$(grep '"version"' "$PLUGIN_JSON" | head -1 | sed 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')

if [ -z "$PLUGIN_VERSION" ]; then
    exit 0  # Failed to extract version, exit silently
fi

# Check if project CLAUDE.md exists
PROJECT_CLAUDE="${PROJECT_ROOT}/CLAUDE.md"
if [ ! -f "$PROJECT_CLAUDE" ]; then
    exit 0  # No CLAUDE.md in project, nothing to check
fi

# Check if CLAUDE.md contains ACE content
if ! grep -q "# ACE Orchestration Plugin" "$PROJECT_CLAUDE" 2>/dev/null; then
    exit 0  # ACE not initialized in this project yet
fi

# Extract existing ACE version from project CLAUDE.md
# Look for pattern: v3.2.36 in the content
EXISTING_VERSION=$(grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' "$PROJECT_CLAUDE" 2>/dev/null | head -1 | tr -d 'v')

if [ -z "$EXISTING_VERSION" ]; then
    exit 0  # No version found, might be old format without version markers
fi

# Compare versions
if [ "$EXISTING_VERSION" != "$PLUGIN_VERSION" ]; then
    # Versions differ - create notification
    mkdir -p ~/.ace

    NOTIFICATION_FILE=~/.ace/update-notification.txt
    echo "ACE update available: v${EXISTING_VERSION} → v${PLUGIN_VERSION}" > "$NOTIFICATION_FILE"
    echo "Run /ace-orchestration:ace-claude-init to update your project's ACE instructions." >> "$NOTIFICATION_FILE"
    echo "" >> "$NOTIFICATION_FILE"
    echo "Why update?" >> "$NOTIFICATION_FILE"
    echo "- New plugin features may require updated instructions" >> "$NOTIFICATION_FILE"
    echo "- Improved trigger keywords for better skill activation" >> "$NOTIFICATION_FILE"
    echo "- Bug fixes and performance improvements" >> "$NOTIFICATION_FILE"
    echo "" >> "$NOTIFICATION_FILE"
    echo "Project: ${PROJECT_ROOT}" >> "$NOTIFICATION_FILE"
    echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$NOTIFICATION_FILE"

    # Optional: Log to metrics file for tracking
    if [ -f ~/.ace/metrics.jsonl ]; then
        echo "{\"event\":\"version_check\",\"existing\":\"${EXISTING_VERSION}\",\"plugin\":\"${PLUGIN_VERSION}\",\"project\":\"${PROJECT_ROOT}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" >> ~/.ace/metrics.jsonl
    fi
fi

# Exit successfully (always non-blocking)
exit 0
