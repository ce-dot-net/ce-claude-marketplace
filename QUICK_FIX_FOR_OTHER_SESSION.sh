#!/bin/bash
# Quick fix for the other Claude session

echo "🔧 Quick Fix: MCP Not Appearing"
echo "================================"
echo ""

cd "$(dirname "$0")"

echo "1. Checking if .npmrc exists..."
if [ -f .npmrc ]; then
  echo "✅ .npmrc exists"
else
  echo "❌ .npmrc missing - creating it now..."
  cd plugins/ace
  ./scripts/install.sh
  cd ../..
fi

echo ""
echo "2. Testing package download..."
npx --package=@ce-dot-net/ace-client@3.0.4 ace-client 2>&1 | head -15

echo ""
echo "================================"
echo "✅ If you see 'ACE Client MCP started' above, it works!"
echo ""
echo "Next steps:"
echo "1. RESTART Claude Code (Cmd+Q, then start again)"
echo "2. Run: /mcp"
echo "3. You should see 'ace-pattern-learning: connected'"
echo ""
