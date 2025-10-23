#!/bin/bash
# ACE Plugin - Auto-inject Instructions
# Automatically adds reference to ACE plugin CLAUDE.md in project CLAUDE.md files
# This ensures plugin instructions are automatically loaded without manual intervention

set -e

# Plugin CLAUDE.md reference path (this gets installed to ~/.claude/plugins)
PLUGIN_CLAUDE_MD_REF="@~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md"

# Project CLAUDE.md possible locations
PROJECT_CLAUDE_MD="./CLAUDE.md"
ALT_PROJECT_CLAUDE_MD="./.claude/CLAUDE.md"

# Marker to identify our injection (so we don't duplicate)
MARKER_START="# ACE Plugin Instructions (auto-injected)"
MARKER_END="# End ACE Plugin Instructions"

# Function to check if reference already exists
has_reference() {
  local file="$1"
  if [ -f "$file" ]; then
    grep -q "$PLUGIN_CLAUDE_MD_REF" "$file" 2>/dev/null && return 0
    grep -q "$MARKER_START" "$file" 2>/dev/null && return 0
  fi
  return 1
}

# Function to add reference to CLAUDE.md
add_reference() {
  local target_file="$1"

  # Skip if file doesn't exist
  [ ! -f "$target_file" ] && return 0

  # Skip if reference already exists
  has_reference "$target_file" && return 0

  # Add reference with markers
  cat >> "$target_file" <<EOF

$MARKER_START
$PLUGIN_CLAUDE_MD_REF
$MARKER_END
EOF

  return 0
}

# Main execution (silent - no output unless error)
{
  # Try to add to ./CLAUDE.md first
  add_reference "$PROJECT_CLAUDE_MD"

  # Then try ./.claude/CLAUDE.md
  add_reference "$ALT_PROJECT_CLAUDE_MD"
} 2>/dev/null

# Exit successfully (SessionStart hooks should not block)
exit 0
