#!/usr/bin/env bash
# ACE CLI Auto-Checker - SessionStart Hook
# Checks if ce-ace is installed, shows helpful message if missing
# IMPORTANT: This hook must be NON-INTERACTIVE (no read/prompts)
set -euo pipefail

# Check if ce-ace is already installed
if command -v ce-ace >/dev/null 2>&1; then
  # Already installed - silent success (no noise!)
  exit 0
fi

# Not installed - show helpful message (non-interactive)
# User can run /ace-install-cli command to install interactively
echo "⚠️  [ACE] ce-ace CLI not found - install with: npm install -g @ce-dot-net/ce-ace-cli"

# Exit successfully (don't block the session from starting)
exit 0
