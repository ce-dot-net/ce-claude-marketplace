#!/bin/bash
# Publish to GitHub Packages
# Usage: ./scripts/publish-github.sh

set -e

echo "📦 Publishing to GitHub Packages"
echo "=================================="

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Error: GITHUB_TOKEN environment variable not set"
    echo ""
    echo "Get a token from: https://github.com/settings/tokens"
    echo "Required scopes: write:packages, read:packages, delete:packages"
    echo ""
    echo "Set it with: export GITHUB_TOKEN=ghp_xxxxx"
    exit 1
fi

# Check if on correct directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: Not in package directory"
    echo "Run from: mcp-clients/ce-ai-ace-client/"
    exit 1
fi

# Verify version
VERSION=$(node -p "require('./package.json').version")
echo "📌 Version: $VERSION"

# Build
echo ""
echo "🔨 Building..."
npm run build

# Test
echo ""
echo "🧪 Running tests..."
npm test

# Configure registry for GitHub Packages
echo ""
echo "⚙️  Configuring GitHub Packages registry..."
cat > .npmrc.temp <<EOF
registry=https://npm.pkg.github.com
@ce-dot-net:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
EOF

# Backup existing .npmrc if exists
if [ -f ".npmrc" ]; then
    mv .npmrc .npmrc.backup
    echo "💾 Backed up existing .npmrc to .npmrc.backup"
fi

# Use temporary .npmrc
mv .npmrc.temp .npmrc

# Publish
echo ""
echo "🚀 Publishing @ce-dot-net/ace-client@$VERSION to GitHub Packages..."
npm publish

# Cleanup
rm .npmrc
if [ -f ".npmrc.backup" ]; then
    mv .npmrc.backup .npmrc
    echo "♻️  Restored original .npmrc"
fi

echo ""
echo "✅ Successfully published to GitHub Packages!"
echo ""
echo "View at: https://github.com/orgs/ce-dot-net/packages?repo_name=ce-claude-marketplace"
echo ""
echo "Users can install with:"
echo "  npm install @ce-dot-net/ace-client"
echo ""
echo "After configuring .npmrc:"
echo "  @ce-dot-net:registry=https://npm.pkg.github.com"
echo "  //npm.pkg.github.com/:_authToken=\${GITHUB_TOKEN}"
