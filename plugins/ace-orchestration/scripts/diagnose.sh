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

    PLUGIN_VERSION=$(grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' "$PLUGIN_DIR/.claude-plugin/plugin.json" | cut -d'"' -f4)
    echo "  📦 Plugin version: $PLUGIN_VERSION"

    # v3.3.2+: mcpServers moved to .claude/settings.json
    if grep -q "mcpServers" "$PLUGIN_DIR/.claude-plugin/plugin.json"; then
        echo "  ⚠️  Old config format detected (v3.3.1 or earlier)"
        echo "     Run /ace-configure to migrate to dual-config"
    else
        echo "  ✅ Using v3.3.2+ dual-config architecture"
    fi
else
    echo "  ❌ plugin.json does NOT exist"
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

# Check 4: Dual-Config Architecture (v3.3.2+)
echo "4️⃣  Checking dual-config architecture..."

# Check global config
if [ -f ~/.config/ace/config.json ]; then
    echo "  ✅ Global config exists: ~/.config/ace/config.json"

    if command -v jq &> /dev/null; then
        SERVER_URL=$(jq -r '.serverUrl // "not set"' ~/.config/ace/config.json)
        API_TOKEN=$(jq -r '.apiToken // "not set"' ~/.config/ace/config.json)
        CACHE_TTL=$(jq -r '.cacheTtlMinutes // "not set"' ~/.config/ace/config.json)

        echo "     Server URL: $SERVER_URL"
        echo "     API Token: ${API_TOKEN:0:12}..."
        echo "     Cache TTL: $CACHE_TTL minutes"
    else
        echo "     (Install jq to see config details)"
    fi
else
    echo "  ❌ Global config missing: ~/.config/ace/config.json"
    echo "     Run: /ace-configure --global"
fi

# Check project config
PROJECT_ROOT=$(pwd)
if [ -f "$PROJECT_ROOT/.claude/settings.json" ]; then
    echo "  ✅ Project config exists: .claude/settings.json"

    if command -v jq &> /dev/null; then
        if jq -e '.mcpServers."ace-pattern-learning"' "$PROJECT_ROOT/.claude/settings.json" &> /dev/null; then
            echo "  ✅ MCP server configured"
            PROJECT_ID=$(jq -r '.mcpServers."ace-pattern-learning".args[] | select(startswith("prj_"))' "$PROJECT_ROOT/.claude/settings.json" 2>/dev/null || echo "not found")
            echo "     Project ID: $PROJECT_ID"
        else
            echo "  ⚠️  MCP server not configured in settings.local.json"
        fi
    fi
else
    echo "  ⚠️  Project config missing: .claude/settings.json"
    echo "     Run: /ace-configure --project"
fi

# Environment variables (fallback/override)
echo ""
echo "  Environment Variables (fallback/override):"
if [ -n "$ACE_SERVER_URL" ]; then
    echo "  ✅ ACE_SERVER_URL: $ACE_SERVER_URL (overrides global config)"
else
    echo "  ℹ️  ACE_SERVER_URL not set (using ~/.config/ace/config.json)"
fi

if [ -n "$ACE_API_TOKEN" ]; then
    echo "  ✅ ACE_API_TOKEN: ${ACE_API_TOKEN:0:10}... (overrides global config)"
else
    echo "  ℹ️  ACE_API_TOKEN not set (using ~/.config/ace/config.json)"
fi

if [ -n "$ACE_PROJECT_ID" ]; then
    echo "  ✅ ACE_PROJECT_ID: $ACE_PROJECT_ID (overrides .claude/settings.json)"
else
    echo "  ℹ️  ACE_PROJECT_ID not set (using .claude/settings.json)"
fi
echo ""

# Check 5: Test package download
echo "5️⃣  Testing MCP client package..."
echo "  Attempting to download @ce-dot-net/ace-client@3.7.2..."

# Change to marketplace root for .npmrc
cd "$MARKETPLACE_ROOT"

if npx --yes @ce-dot-net/ace-client@3.7.2 --help 2>&1 | head -5; then
    echo "  ✅ MCP client v3.7.2 can be downloaded and executed"
else
    echo "  ❌ Failed to download/execute MCP client"
    echo "     Check .npmrc configuration and GitHub token"
    echo "     Required for v3.3.2+ dual-config architecture"
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
echo "ACE Plugin v3.3.2 - Dual-Config Architecture"
echo ""
echo "Required Configuration:"
echo "  1. Global:  ~/.config/ace/config.json (org credentials)"
echo "  2. Project: .claude/settings.json (MCP server + project ID)"
echo "  3. MCP Client: @ce-dot-net/ace-client@3.7.2"
echo ""
echo "Next steps:"
echo "1. Fix any ❌ items above"
echo "2. Run /ace-configure to set up dual-config (if missing)"
echo "3. Restart Claude Code completely"
echo "4. Run /ace-status to verify connection"
echo ""
echo "If issues persist:"
echo "- Check Claude Code logs: ~/.config/claude-code/logs/"
echo "- Run: /ace-doctor (enhanced diagnostics)"
echo "- Try: claude --debug"
echo ""
