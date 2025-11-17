#!/usr/bin/env bash
# ACE CLI Auto-Installer - SessionStart Hook
# Checks if ce-ace is installed, prompts to install if missing
set -euo pipefail

# Check if ce-ace is already installed
if command -v ce-ace >/dev/null 2>&1; then
  # Already installed, show version
  VERSION=$(ce-ace --version 2>/dev/null || echo "unknown")
  echo "✅ [ACE] ce-ace CLI installed (v${VERSION})"
  exit 0
fi

# Not installed - show installation prompt
echo ""
echo "⚠️  [ACE] ce-ace CLI not found!"
echo ""
echo "The ACE plugin requires the ce-ace CLI tool."
echo "Install it with:"
echo ""
echo "  npm install -g @ce-dot-net/ce-ace-cli"
echo ""
echo "Or auto-install now? (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
  echo ""
  echo "📦 Installing @ce-dot-net/ce-ace-cli..."

  if npm install -g @ce-dot-net/ce-ace-cli; then
    echo "✅ [ACE] ce-ace CLI installed successfully!"
    echo "   Run /ace-configure to set up your ACE server connection"
  else
    echo "❌ [ACE] Installation failed"
    echo "   Try manually: npm install -g @ce-dot-net/ce-ace-cli"
    exit 1
  fi
else
  echo "ℹ️  [ACE] Skipped installation. Install later with:"
  echo "   npm install -g @ce-dot-net/ce-ace-cli"
fi

echo ""
