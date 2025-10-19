#!/usr/bin/env bash
# PostTaskCompletion Hook - Collect pattern feedback after task completion
#
# This hook implements the Generator feedback loop from ACE research paper:
# "When solving new problems, the Generator highlights which bullets were
# useful or misleading, providing feedback that guides the Reflector"
#
# Triggered: After each successful task completion
# Purpose: Ask Claude to tag which patterns (bullets) were helpful/harmful

set -euo pipefail

# Get plugin root
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$0")/..}"
SCRIPT_DIR="$PLUGIN_ROOT/scripts"

# Only run if CLAUDE.md playbook exists (patterns have been learned)
PLAYBOOK_PATH="$(pwd)/CLAUDE.md"
if [ ! -f "$PLAYBOOK_PATH" ]; then
    # No playbook yet, skip feedback
    exit 0
fi

# Check if ace-memory exists (patterns database)
if [ ! -d "$(pwd)/.ace-memory" ]; then
    # No patterns database, skip
    exit 0
fi

# Run pattern feedback collection
python3 "$SCRIPT_DIR/collect-pattern-feedback.py" < /dev/stdin

# Always continue (don't block workflow)
echo '{"continue": true}'
exit 0
