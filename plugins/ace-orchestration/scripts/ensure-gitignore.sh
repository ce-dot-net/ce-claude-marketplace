#!/usr/bin/env bash

# ACE Plugin - Automatic .gitignore Management
# Ensures .ace/ and .ace-cache/ are in project .gitignore
# Runs on SessionStart (beginning of each Claude Code session)

set -e

# Use CLAUDE_PROJECT_DIR if available (set by Claude Code for hooks)
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Silently exit if we can't determine project root
if [ -z "$PROJECT_ROOT" ] || [ ! -d "$PROJECT_ROOT" ]; then
    exit 0
fi

GITIGNORE_PATH="$PROJECT_ROOT/.gitignore"

# Function to check if a pattern exists in .gitignore
pattern_exists() {
    local pattern="$1"
    local file="$2"

    if [ ! -f "$file" ]; then
        return 1
    fi

    # Check for exact match or pattern with trailing slash
    grep -qE "^${pattern}/?$" "$file" 2>/dev/null
}

# Function to add pattern to .gitignore
add_to_gitignore() {
    local pattern="$1"
    local comment="$2"
    local file="$3"

    # Create .gitignore if it doesn't exist
    if [ ! -f "$file" ]; then
        echo "# ACE Plugin - Automatic Pattern Learning" >> "$file"
        echo "$comment" >> "$file"
        echo "$pattern" >> "$file"
        return 0
    fi

    # Add pattern if not already present
    if ! pattern_exists "$pattern" "$file"; then
        # Add blank line if file doesn't end with one
        if [ -s "$file" ] && [ "$(tail -c 1 "$file" | wc -l)" -eq 0 ]; then
            echo "" >> "$file"
        fi

        echo "$comment" >> "$file"
        echo "$pattern" >> "$file"
    fi
}

# Check and add .ace/ pattern (project-level config)
if ! pattern_exists ".ace" "$GITIGNORE_PATH"; then
    add_to_gitignore ".ace/" "# ACE project config (may contain sensitive tokens)" "$GITIGNORE_PATH"
fi

# Check and add .ace-cache/ pattern (local SQLite cache)
if ! pattern_exists ".ace-cache" "$GITIGNORE_PATH"; then
    add_to_gitignore ".ace-cache/" "# ACE local cache (SQLite database)" "$GITIGNORE_PATH"
fi

# Exit successfully (no output to avoid cluttering session start)
exit 0
