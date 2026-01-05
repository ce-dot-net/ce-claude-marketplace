#!/usr/bin/env bash
# install-bats.sh - Install Bats and supporting libraries
set -euo pipefail

echo "🔧 Installing Bats testing framework..."

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
  # macOS
  if command -v brew >/dev/null 2>&1; then
    echo "📦 Installing via Homebrew..."
    brew install bats-core bats-support bats-assert bats-file
  else
    echo "❌ Homebrew not found. Install from https://brew.sh"
    exit 1
  fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
  # Linux
  if command -v apt-get >/dev/null 2>&1; then
    echo "📦 Installing via apt..."
    sudo apt-get update
    sudo apt-get install -y bats
  elif command -v dnf >/dev/null 2>&1; then
    echo "📦 Installing via dnf..."
    sudo dnf install -y bats
  else
    echo "⚠️ Package manager not detected. Installing from Git..."
    git clone https://github.com/bats-core/bats-core.git /tmp/bats-core
    cd /tmp/bats-core
    sudo ./install.sh /usr/local
    cd -
    rm -rf /tmp/bats-core
  fi
else
  echo "❌ Unsupported OS: $OSTYPE"
  exit 1
fi

# Verify installation
if command -v bats >/dev/null 2>&1; then
  echo "✅ Bats installed successfully!"
  bats --version
else
  echo "❌ Bats installation failed"
  exit 1
fi

echo ""
echo "📚 Bats installed. Run tests with:"
echo "   cd tests && bun test"
