#!/usr/bin/env bash

# ACE Plugin - CLAUDE.md Initialization/Update Script
# Script-based approach for fast, token-free ACE template management
# Falls back to LLM (exit code 2) for files without HTML markers

set -e

# Source helper library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/section-parser.sh"

# Configuration
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
PROJECT_CLAUDE="${PROJECT_ROOT}/CLAUDE.md"
TEMPLATE="${PLUGIN_ROOT}/CLAUDE.md"
PLUGIN_JSON="${PLUGIN_ROOT}/.claude-plugin/plugin.json"

# Flags
AUTO_UPDATE=false
FORCE_LLM=false
UPDATE_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --auto-update)
            AUTO_UPDATE=true
            shift
            ;;
        --force-llm)
            FORCE_LLM=true
            shift
            ;;
        --update)
            UPDATE_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function: Get plugin version
get_plugin_version() {
    if [ ! -f "$PLUGIN_JSON" ]; then
        echo "ERROR: Cannot find plugin.json" >&2
        exit 1
    fi

    grep '"version"' "$PLUGIN_JSON" | head -1 | sed 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/'
}

# Function: Fallback to LLM
fallback_to_llm() {
    local reason="$1"

    if [ "$AUTO_UPDATE" = true ]; then
        # Silent fallback for auto-update mode
        exit 2
    fi

    echo "⚠️  Script cannot handle this case: $reason" >&2
    echo "Falling back to LLM-based initialization..." >&2
    exit 2
}

# Check if --force-llm flag is set
if [ "$FORCE_LLM" = true ]; then
    fallback_to_llm "User requested LLM mode (--force-llm)"
fi

# Get plugin version
PLUGIN_VERSION=$(get_plugin_version)

if [ -z "$PLUGIN_VERSION" ]; then
    fallback_to_llm "Cannot determine plugin version"
fi

# Check if project CLAUDE.md exists
if [ ! -f "$PROJECT_CLAUDE" ]; then
    # Initial setup - create new CLAUDE.md
    if [ "$AUTO_UPDATE" = false ]; then
        echo "📝 Creating new CLAUDE.md with ACE instructions..."
    fi

    cp "$TEMPLATE" "$PROJECT_CLAUDE"

    if [ "$AUTO_UPDATE" = false ]; then
        echo "✅ ACE instructions added to: $PROJECT_CLAUDE"
        echo "   Version: v${PLUGIN_VERSION}"
        echo ""
        echo "Next steps:"
        echo "1. Run /ace-orchestration:ace-configure to set up ACE server connection"
        echo "2. Run /ace-orchestration:ace-status to verify connection"
    fi

    exit 0
fi

# Check if CLAUDE.md has ACE content
if ! grep -q '# ACE Orchestration Plugin' "$PROJECT_CLAUDE"; then
    # Append ACE content to existing file
    if [ "$AUTO_UPDATE" = false ]; then
        echo "📝 Adding ACE instructions to existing CLAUDE.md..."
    fi

    echo "" >> "$PROJECT_CLAUDE"
    echo "" >> "$PROJECT_CLAUDE"
    cat "$TEMPLATE" >> "$PROJECT_CLAUDE"

    if [ "$AUTO_UPDATE" = false ]; then
        echo "✅ ACE instructions appended to: $PROJECT_CLAUDE"
        echo "   Version: v${PLUGIN_VERSION}"
    fi

    exit 0
fi

# ACE content exists - check for markers
if ! has_markers "$PROJECT_CLAUDE"; then
    # No markers - either add them or fallback to LLM
    if [ "$AUTO_UPDATE" = true ]; then
        # Auto-update mode: Add markers for next time, but don't update content
        add_markers_to_section "$PROJECT_CLAUDE" "$PLUGIN_VERSION" || fallback_to_llm "Failed to add markers"
        exit 0
    else
        fallback_to_llm "File has ACE content but no HTML markers (use LLM for complex merge)"
    fi
fi

# Validate structure
if ! validate_ace_structure "$PROJECT_CLAUDE"; then
    fallback_to_llm "Invalid ACE section structure (markers present but corrupt)"
fi

# Extract existing version
EXISTING_VERSION=$(extract_marker_version "$PROJECT_CLAUDE")

if [ -z "$EXISTING_VERSION" ]; then
    fallback_to_llm "Cannot extract version from markers"
fi

# Compare versions
if [ "$EXISTING_VERSION" = "$PLUGIN_VERSION" ]; then
    if [ "$AUTO_UPDATE" = false ]; then
        echo "✅ ACE already up-to-date (v${PLUGIN_VERSION})"
        echo "   Location: $PROJECT_CLAUDE"
    fi
    exit 0
fi

# Versions differ - update needed
if [ "$UPDATE_MODE" = false ] && [ "$AUTO_UPDATE" = false ]; then
    echo "⚠️  ACE update available: v${EXISTING_VERSION} → v${PLUGIN_VERSION}"
    echo ""
    echo "Your project has ACE v${EXISTING_VERSION}, but plugin is v${PLUGIN_VERSION}."
    echo "Run with --update flag to perform update:"
    echo ""
    echo "  /ace-orchestration:ace-claude-init --update"
    echo ""
    echo "Or use --force-llm for LLM-based update."
    exit 0
fi

# Perform update
if [ "$AUTO_UPDATE" = false ]; then
    echo "🔄 Updating ACE instructions: v${EXISTING_VERSION} → v${PLUGIN_VERSION}..."
fi

# Create backup
BACKUP_FILE="${PROJECT_CLAUDE}.backup-$(date +%Y%m%d-%H%M%S)"
cp "$PROJECT_CLAUDE" "$BACKUP_FILE"

if [ "$AUTO_UPDATE" = false ]; then
    echo "   Backup created: $BACKUP_FILE"
fi

# Create temp file for new content
TEMP_FILE=$(mktemp)

# Extract content before ACE section
extract_before_ace "$PROJECT_CLAUDE" > "$TEMP_FILE" 2>/dev/null || true

# Add new ACE content from template
cat "$TEMPLATE" >> "$TEMP_FILE"

# Extract content after ACE section
extract_after_ace "$PROJECT_CLAUDE" >> "$TEMP_FILE" 2>/dev/null || true

# Validate temp file
if [ ! -s "$TEMP_FILE" ]; then
    rm "$TEMP_FILE"
    fallback_to_llm "Generated empty file during update"
fi

# Check that temp file has ACE content
if ! grep -q '# ACE Orchestration Plugin' "$TEMP_FILE"; then
    rm "$TEMP_FILE"
    fallback_to_llm "ACE content missing after merge"
fi

# Replace original file
mv "$TEMP_FILE" "$PROJECT_CLAUDE"

if [ "$AUTO_UPDATE" = false ]; then
    echo "✅ ACE instructions updated successfully!"
    echo "   Version: v${PLUGIN_VERSION}"
    echo "   Location: $PROJECT_CLAUDE"
    echo ""
    echo "Changes:"
    echo "- Updated ACE plugin instructions to v${PLUGIN_VERSION}"
    echo "- New features and improvements available"
    echo "- Backup saved: $BACKUP_FILE"
fi

# Clean up old notification
rm -f ~/.ace/update-notification.txt 2>/dev/null || true

exit 0
