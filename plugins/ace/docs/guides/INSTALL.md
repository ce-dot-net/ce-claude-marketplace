# ACE Plugin Installation Guide

**Version**: v5.1.15
**Architecture**: Hooks + ce-ace CLI (no MCP server)

---

## 🎯 Overview

The ACE plugin uses a **hooks-based architecture** with the `ce-ace` CLI tool. No MCP server configuration needed!

**Architecture:**
```
Claude Code → Hooks → ce-ace CLI → ACE Server
```

**What you need:**
- ✅ ce-ace CLI (npm package)
- ✅ Claude Code with marketplace support
- ❌ No MCP server setup required
- ❌ No plugin.json MCP configuration

---

## 🚀 Quick Install (3 Steps)

### Step 1: Install ce-ace CLI

```bash
npm install -g @ce-dot-net/ce-ace-cli
```

**Verify installation:**
```bash
ce-ace --version
# Should show: v1.0.14 or higher
```

**Alternative**: Use the interactive installer:
```bash
# In Claude Code:
/ace:ace-install-cli
```

### Step 2: Enable ACE Plugin

The ACE plugin is part of the **ce-dot-net marketplace**:

**Option A - Via Marketplace** (Recommended):
```bash
# In Claude Code:
/plugin enable ce-dot-net-marketplace
```

The ACE plugin auto-loads when the marketplace is enabled.

**Option B - Manual Install**:
```bash
# Clone marketplace
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace

# Symlink marketplace
ln -s "$(pwd)" ~/.config/claude-code/marketplaces/ce-dot-net-marketplace

# Restart Claude Code
```

### Step 3: Configure ACE

Run the interactive configuration wizard:

```bash
# In Claude Code:
/ace:ace-configure
```

This will:
- Prompt for your ACE server URL
- Request your API token
- Auto-fetch your organization ID
- List available projects for selection
- Create `.claude/settings.json` in your project

**Done!** ACE is now ready to use.

---

## 📋 Requirements

**System Requirements:**
- Node.js v18+ (for npm)
- Claude Code v2.0+
- Git (for marketplace installation)

**ACE Requirements:**
- ce-ace CLI >= v1.0.14
- ACE server access (API token)
- Organization and project on ACE server

---

## 🔄 Migration from v4.x (MCP-based)

If you're upgrading from the old MCP-based architecture:

### Breaking Changes

- ❌ **MCP server removed** - No more `mcp__ace-pattern-learning__*` tools
- ❌ **Subagent invocations removed** - No more Task tool calls to ACE subagents
- ✅ **Hooks + CLI** - All ACE operations now via hooks and slash commands

### Migration Steps

1. **Uninstall old MCP server** (if configured):
   ```bash
   # Edit ~/.claude/mcp/config.json
   # Remove "ace-pattern-learning" entry
   ```

2. **Install ce-ace CLI**:
   ```bash
   npm install -g @ce-dot-net/ce-ace-cli
   ```

3. **Update plugin**:
   ```bash
   cd ~/.config/claude-code/marketplaces/ce-dot-net-marketplace
   git pull
   ```

4. **Reconfigure**:
   ```bash
   # In Claude Code:
   /ace:ace-configure
   ```

5. **Restart Claude Code**

6. **Verify**:
   ```bash
   # In Claude Code:
   /ace:ace-status
   ```

Your playbook data is preserved on the server - no data loss during migration!

---

## 🔧 Troubleshooting

### "ce-ace not found"

**Problem**: `ce-ace` command not in PATH.

**Solution**:
```bash
# Reinstall globally
npm install -g @ce-dot-net/ce-ace-cli

# Verify installation
which ce-ace
ce-ace --version

# If still not found, check npm global bin path
npm bin -g
# Add to PATH if needed
```

### "ACE authentication failed"

**Problem**: Invalid or expired API token.

**Solution**:
```bash
# Reconfigure with new token
/ace:ace-configure

# Or manually update ~/.config/ace/config.json
```

### "No .claude/settings.json"

**Problem**: Project not configured.

**Solution**:
```bash
# Run configuration wizard
/ace:ace-configure

# Wizard creates .claude/settings.json automatically
```

### Hooks not firing

**Problem**: Hook scripts not executable or wrong permissions.

**Solution**:
```bash
# Check hook wrapper scripts
ls -la ~/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/*.sh

# Make executable if needed
chmod +x ~/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/*.sh

# Restart Claude Code
```

### SessionStart shows "ce-ace not found" every session

**Problem**: ce-ace not installed.

**Solution**:
```bash
npm install -g @ce-dot-net/ce-ace-cli

# Or use interactive installer
/ace:ace-install-cli
```

---

## 🧪 Verify Installation

After installation, verify everything works:

```bash
# Check CLI version
ce-ace --version

# Check plugin status
/ace:ace-status

# Test pattern search
/ace:ace-search authentication

# View configuration
cat ~/.config/ace/config.json
cat .claude/settings.json
```

**Expected behavior:**
- ✅ ce-ace shows version >= v1.0.14
- ✅ `/ace:ace-status` shows playbook stats
- ✅ `/ace:ace-search` returns results
- ✅ Config files exist with valid credentials

---

## 📚 Next Steps

Once installed:

1. **Bootstrap playbook** (optional):
   ```bash
   /ace:ace-bootstrap
   ```
   Analyzes your codebase and creates initial patterns.

2. **Start coding**:
   - Type prompts with keywords like "implement", "fix", "debug"
   - Hooks automatically inject relevant patterns
   - Learning captured automatically after work completion

3. **Explore commands**:
   ```bash
   /ace:ace-patterns        # View all patterns
   /ace:ace-search auth     # Search for patterns
   /ace:ace-learn           # Manual learning capture
   /ace:ace-doctor          # Run diagnostics
   ```

---

## 🔗 Additional Resources

- **ACE Server**: https://github.com/ce-dot-net/ce-ace-server
- **CE-ACE CLI**: https://github.com/ce-dot-net/ce-ace-cli
- **Marketplace**: https://github.com/ce-dot-net/ce-claude-marketplace
- **Configuration Guide**: See `CONFIGURATION.md`
- **Troubleshooting**: See `TROUBLESHOOTING.md`

---

**Questions?** File an issue on the [marketplace repository](https://github.com/ce-dot-net/ce-claude-marketplace/issues).
