#!/bin/bash
# ACE Plugin Diagnostic Script
# Checks all requirements for plugin to work

echo "🔍 ACE Plugin Diagnostic"
echo "========================"
echo ""

# Get paths
PLUGIN_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
MARKETPLACE_ROOT="$( cd "$PLUGIN_DIR/../.." && pwd )"

echo "📁 Paths:"
echo "  Plugin: $PLUGIN_DIR"
echo "  Marketplace: $MARKETPLACE_ROOT"
echo ""

# Check 1: Plugin installed in Claude Code
echo "1️⃣  Checking Claude Code plugin installation..."
if [ -L ~/.config/claude-code/plugins/ace-orchestration ]; then
    LINK_TARGET=$(readlink ~/.config/claude-code/plugins/ace-orchestration)
    echo "  ✅ Plugin symlinked at: ~/.config/claude-code/plugins/ace-orchestration"
    echo "     → Points to: $LINK_TARGET"
elif [ -d ~/.config/claude-code/plugins/ace-orchestration ]; then
    echo "  ✅ Plugin directory exists at: ~/.config/claude-code/plugins/ace-orchestration"
else
    echo "  ❌ Plugin NOT installed in Claude Code"
    echo "     Install with: ln -s $PLUGIN_DIR ~/.config/claude-code/plugins/ace-orchestration"
    exit 1
fi
echo ""

# Check 2: plugin.json exists
echo "2️⃣  Checking plugin.json..."
if [ -f "$PLUGIN_DIR/.claude-plugin/plugin.json" ]; then
    echo "  ✅ plugin.json exists"

    # Check if it has mcpServers
    if grep -q "mcpServers" "$PLUGIN_DIR/.claude-plugin/plugin.json"; then
        echo "  ✅ mcpServers configuration found"

        # Show the command
        echo ""
        echo "  MCP Server Configuration:"
        cat "$PLUGIN_DIR/.claude-plugin/plugin.json" | grep -A 10 '"mcpServers"' | head -15
    else
        echo "  ⚠️  No mcpServers configuration in plugin.json"
    fi
else
    echo "  ❌ plugin.json does NOT exist"
    echo "     Create from template: cp $PLUGIN_DIR/.claude-plugin/plugin.template.json $PLUGIN_DIR/.claude-plugin/plugin.json"
    exit 1
fi
echo ""

# Check 3: .npmrc configuration
echo "3️⃣  Checking .npmrc configuration..."
if [ -f "$MARKETPLACE_ROOT/.npmrc" ]; then
    echo "  ✅ .npmrc exists at marketplace root"

    if grep -q "@ce-dot-net:registry=https://npm.pkg.github.com" "$MARKETPLACE_ROOT/.npmrc"; then
        echo "  ✅ GitHub Packages registry configured"
    else
        echo "  ⚠️  GitHub Packages registry NOT configured"
    fi

    if grep -q "//npm.pkg.github.com/:_authToken=" "$MARKETPLACE_ROOT/.npmrc"; then
        echo "  ✅ Authentication token present"
    else
        echo "  ⚠️  Authentication token missing (needed for private packages)"
    fi
else
    echo "  ⚠️  .npmrc does NOT exist"
    echo "     Run: $PLUGIN_DIR/scripts/install.sh"
fi

if [ -f ~/.npmrc ]; then
    echo "  ✅ ~/.npmrc exists (checked by npm)"

    if grep -q "@ce-dot-net:registry" ~/.npmrc; then
        echo "     Contains @ce-dot-net registry config"
    fi
fi
echo ""

# Check 4: Environment variables
echo "4️⃣  Checking environment variables..."
if [ -n "$ACE_SERVER_URL" ]; then
    echo "  ✅ ACE_SERVER_URL: $ACE_SERVER_URL"
else
    echo "  ⚠️  ACE_SERVER_URL not set"
fi

if [ -n "$ACE_API_TOKEN" ]; then
    echo "  ✅ ACE_API_TOKEN: ${ACE_API_TOKEN:0:10}..."
else
    echo "  ⚠️  ACE_API_TOKEN not set"
fi

if [ -n "$ACE_PROJECT_ID" ]; then
    echo "  ✅ ACE_PROJECT_ID: $ACE_PROJECT_ID"
else
    echo "  ⚠️  ACE_PROJECT_ID not set"
fi
echo ""

# Check 5: Test package download
echo "5️⃣  Testing package download..."
echo "  Attempting to download @ce-dot-net/ace-client..."

# Change to marketplace root for .npmrc
cd "$MARKETPLACE_ROOT"

if npx --package=@ce-dot-net/ace-client@3.0.3 ace-client --help 2>&1 | head -5; then
    echo "  ✅ Package can be downloaded and executed"
else
    echo "  ❌ Failed to download/execute package"
    echo "     Check .npmrc configuration and GitHub token"
fi
echo ""

# Check 6: Claude Code settings
echo "6️⃣  Checking Claude Code settings..."
if [ -f ~/.config/claude-code/settings.json ]; then
    echo "  ✅ Claude Code settings.json exists"

    if grep -q "mcpServers" ~/.config/claude-code/settings.json 2>/dev/null; then
        echo "  ⚠️  User has custom MCP servers in settings.json"
        echo "     Plugin MCP servers should still appear separately"
    fi
else
    echo "  ℹ️  No custom settings.json (this is normal)"
fi
echo ""

# Summary
echo "================================"
echo "📊 Diagnostic Summary"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Fix any ❌ items above"
echo "2. Restart Claude Code completely"
echo "3. Run: /mcp"
echo "4. Look for 'ace-pattern-learning' server"
echo ""
echo "If MCP server still doesn't appear:"
echo "- Check Claude Code logs: ~/.config/claude-code/logs/"
echo "- Try: claude --debug"
echo ""
