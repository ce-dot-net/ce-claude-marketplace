#!/bin/bash
# Publish to npm public registry
# Usage: ./scripts/publish-npm.sh

set -e

echo "📦 Publishing to npm"
echo "===================="

# Check npm login
echo "🔐 Checking npm authentication..."
if ! npm whoami &>/dev/null; then
    echo "❌ Error: Not logged in to npm"
    echo ""
    echo "Run: npm login"
    exit 1
fi

NPM_USER=$(npm whoami)
echo "✅ Logged in as: $NPM_USER"

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

# Verify registry is npm (not GitHub Packages)
REGISTRY=$(npm config get registry)
if [[ $REGISTRY != *"registry.npmjs.org"* ]]; then
    echo "⚠️  Warning: Registry is not npmjs.org"
    echo "Current: $REGISTRY"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Confirm publish
echo ""
echo "📋 About to publish:"
echo "   Package: @ce-dot-net/ace-client"
echo "   Version: $VERSION"
echo "   Registry: $REGISTRY"
echo ""
read -p "Proceed with publish? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Publish cancelled"
    exit 1
fi

# Publish
echo ""
echo "🚀 Publishing to npm..."
npm publish --access public

echo ""
echo "✅ Successfully published to npm!"
echo ""
echo "View at: https://www.npmjs.com/package/@ce-dot-net/ace-client"
echo ""
echo "Install with:"
echo "  npm install @ce-dot-net/ace-client"
echo "  npx @ce-dot-net/ace-client"
