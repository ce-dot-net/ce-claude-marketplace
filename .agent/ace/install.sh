#!/usr/bin/env bash
# ACE CLI Installer

set -e

if command -v ace-cli >/dev/null 2>&1; then
  echo "✅ ace-cli is already installed."
  exit 0
fi

echo "⚠️  ace-cli not found."
echo "📦 Installing @ace-sdk/cli..."

if npm install -g @ace-sdk/cli; then
  echo "✅ Installed successfully!"
else
  echo "❌ Installation failed. Please try running: npm install -g @ace-sdk/cli"
  exit 1
fi
