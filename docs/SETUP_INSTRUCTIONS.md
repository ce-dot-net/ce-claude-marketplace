# ACE Orchestration Plugin - Setup Instructions

## 📋 Overview

This guide will help you install and configure the ACE Orchestration plugin for Claude Code. The plugin has two modes:

- **LOCAL MODE** (Development/Testing): Plugin connects directly to Python server running locally
- **REMOTE MODE** (Production): Plugin connects via thin client to remote HTTPS server

## 🔍 Configuration Files Status

✅ **Files Present**:
- `plugins/ace-orchestration/plugin.json` - REMOTE mode configuration
- `plugins/ace-orchestration/plugin.LOCAL.json` - LOCAL mode configuration
- `plugins/ace-orchestration/README.md` - Complete documentation
- `mcp-clients/ce-ai-ace-client/` - Thin MCP client for remote connections

❌ **Not Required**:
- `marketplace.json` - Optional file for Claude Code marketplace metadata (not needed)

## 🚀 Quick Start - LOCAL MODE (Testing)

### Prerequisites

1. **Private Server Repo** must be cloned at the correct location:
   ```bash
   # Expected location (relative to this marketplace repo):
   # ../ce-ai-ace/ce-ai-ace-server/

   # Verify it exists:
   ls -la ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server/
   ```

2. **Python Dependencies** installed in server repo:
   ```bash
   cd ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server
   pip install -e .
   ```

### Installation Steps

#### Step 1: Install Plugin Locally

```bash
# Navigate to marketplace repo
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace

# Copy LOCAL mode config
cd plugins/ace-orchestration
cp plugin.LOCAL.json plugin.json
```

#### Step 2: Install Plugin in Claude Code

```bash
# From marketplace repo root
claude-code plugin install ./plugins/ace-orchestration
```

#### Step 3: Verify Installation

```bash
# List installed plugins
claude-code plugin list

# You should see:
# ace-orchestration (2.5.0) - LOCAL MODE
```

#### Step 4: Test MCP Connection

Open Claude Code and verify the MCP server is running:

```bash
claude-code

# In Claude Code, check MCP tools are available:
# The following tools should be visible:
# - mcp__ace-pattern-learning__ace_reflect
# - mcp__ace-pattern-learning__ace_train_offline
# - mcp__ace-pattern-learning__ace_get_patterns
# - mcp__ace-pattern-learning__ace_get_playbook
# - mcp__ace-pattern-learning__ace_status
# - mcp__ace-pattern-learning__ace_clear
```

#### Step 5: Use Plugin Commands

```bash
# In Claude Code:
/ace-status              # Check ACE system status
/ace-patterns            # View learned patterns
/ace-playbook            # Generate workflow playbook
/ace-reflect             # Manually trigger reflection
/ace-train-offline       # Train from external data
/ace-clear --confirm     # Clear all patterns
```

## 🌐 Production Setup - REMOTE MODE

### Prerequisites

1. **Private Server Deployed** at your domain:
   ```bash
   # Server running at: https://ace.your-domain.com/mcp
   # With API token authentication
   ```

2. **MCP Client Published** to PyPI:
   ```bash
   cd mcp-clients/ce-ai-ace-client
   python -m build
   twine upload dist/*
   ```

### Installation Steps

#### Step 1: Install from Marketplace (Future)

```bash
# Once published to Claude Code marketplace:
claude-code plugin install ce-dot-net/ace-orchestration
```

#### Step 2: Configure API Token

```bash
# Set environment variable with your API token
export ACE_API_TOKEN="your-secret-token-here"

# Or add to your shell profile (~/.zshrc or ~/.bashrc):
echo 'export ACE_API_TOKEN="your-secret-token-here"' >> ~/.zshrc
source ~/.zshrc
```

#### Step 3: Update Server URL (if different from default)

Edit `plugins/ace-orchestration/plugin.json`:

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "uvx",
      "args": ["ce-ai-ace-client"],
      "env": {
        "ACE_SERVER_URL": "https://ace.YOUR-ACTUAL-DOMAIN.com/mcp",
        "ACE_API_TOKEN": "${ACE_API_TOKEN}",
        "ACE_STORAGE_PATH": "${CLAUDE_PLUGIN_ROOT}/.ace-memory/patterns.db"
      }
    }
  }
}
```

#### Step 4: Reinstall Plugin

```bash
claude-code plugin uninstall ace-orchestration
claude-code plugin install ce-dot-net/ace-orchestration
```

## 🔧 Troubleshooting

### Plugin Not Found

```bash
# Check plugin is in correct location:
ls -la plugins/ace-orchestration/plugin.json

# Verify JSON is valid:
cat plugins/ace-orchestration/plugin.json | python -m json.tool
```

### MCP Server Not Starting (LOCAL MODE)

```bash
# Check server repo exists:
ls -la ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server/

# Verify dependencies installed:
cd ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server
pip list | grep -E "fastmcp|chromadb|sentence-transformers"

# Test server manually:
cd ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server
python3 -m ace_server
```

### MCP Tools Not Available

```bash
# Check Claude Code logs:
tail -f ~/.claude/logs/claude-code.log

# Verify MCP server name matches:
# In plugin.json: "ace-pattern-learning"
# Tools will be: mcp__ace-pattern-learning__<function_name>
```

### Client Connection Failing (REMOTE MODE)

```bash
# Test client manually:
export ACE_SERVER_URL="https://ace.your-domain.com/mcp"
export ACE_API_TOKEN="your-token"
uvx ce-ai-ace-client

# Check server is accessible:
curl -H "Authorization: Bearer your-token" https://ace.your-domain.com/health
```

## 📚 References

- **Plugin Documentation**: `plugins/ace-orchestration/README.md`
- **Client Installation**: `mcp-clients/ce-ai-ace-client/INSTALL.md`
- **Server Repository**: `https://github.com/ce-dot-net/ce-ai-ace` (private)
- **ACE Research Paper**: arXiv:2510.04618v1 (Stanford/SambaNova/UC Berkeley)
- **FastMCP Framework**: `https://gofastmcp.com`
- **MCP Protocol**: `https://modelcontextprotocol.io`

## 🧪 Testing Checklist

- [ ] Plugin installed successfully
- [ ] MCP tools visible in Claude Code
- [ ] `/ace-status` command works
- [ ] `/ace-patterns` shows empty patterns initially
- [ ] Hooks trigger on workflow completion
- [ ] Patterns are learned and stored in ChromaDB
- [ ] `/ace-playbook` generates valid workflows
- [ ] `/ace-clear --confirm` clears all patterns

## 🎯 Next Steps

1. **LOCAL Testing**: Use plugin in development with local server
2. **Pattern Learning**: Let ACE observe your workflows and learn patterns
3. **Deploy Server**: Host private server at your domain
4. **Publish Client**: Release thin client to PyPI
5. **Marketplace**: Submit plugin to Claude Code marketplace
6. **Production**: Switch to REMOTE mode configuration

## 💾 Serena Memory Storage

To store ACE configuration in Serena memory for future reference:

```python
# Using Serena MCP server
mcp__serena__write_memory(
    memory_name="ace_plugin_setup",
    content="""
    ACE Plugin Configuration:
    - Local server: ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server/
    - Plugin path: ~/repos/github_com/ce-dot-net/ce-claude-marketplace/plugins/ace-orchestration/
    - MCP server name: ace-pattern-learning
    - Storage path: ${CLAUDE_PLUGIN_ROOT}/.ace-memory/patterns.db
    - Commands: /ace-status, /ace-patterns, /ace-playbook, /ace-reflect, /ace-train-offline, /ace-clear
    """
)
```

## 🔐 Security Notes

- **API Tokens**: Never commit `ACE_API_TOKEN` to git
- **Environment Variables**: Use `${ACE_API_TOKEN}` in plugin.json
- **Private Server**: Keep algorithm code in private repo
- **Public Client**: Thin client has NO secret algorithms
- **Pattern Storage**: Stored locally in `${CLAUDE_PLUGIN_ROOT}/.ace-memory/`

---

**Last Updated**: 2025-10-19
**Version**: 2.5.0
**Status**: ✅ Ready for LOCAL mode testing
