# CE AI ACE Client - Installation Guide

## 📦 What Is This?

A **thin MCP client** that connects Claude Code to a remote ACE pattern learning server.

- **Purpose**: Proxy requests from Claude Code plugin to remote server
- **Code**: 150 lines of forwarding logic (NO secret algorithms)
- **Security**: Uses API tokens for authentication

## 🚀 Installation Methods

### Method 1: From PyPI (Coming Soon)
```bash
# Install globally
pip install ce-ai-ace-client

# Or use with uvx (recommended)
uvx ce-ai-ace-client
```

### Method 2: From Source (Development)
```bash
# Clone marketplace repo
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace/mcp-clients/ce-ai-ace-client

# Install in development mode
pip install -e .

# Test it works
python -m ace_client --help
```

## 🔧 Configuration

### For Claude Code Plugin

Add to your plugin's `plugin.json`:

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "uvx",
      "args": ["ce-ai-ace-client"],
      "env": {
        "ACE_SERVER_URL": "https://ace.your-server.com/mcp",
        "ACE_API_TOKEN": "${ACE_API_TOKEN}",
        "ACE_STORAGE_PATH": "${CLAUDE_PLUGIN_ROOT}/.ace-memory/patterns.db"
      }
    }
  }
}
```

### Environment Variables

**Required**:
- `ACE_SERVER_URL` - URL of your remote ACE server
- `ACE_API_TOKEN` - Your API authentication token

**Optional**:
- `ACE_STORAGE_PATH` - Local pattern database path (default: `.ace-memory/patterns.db`)

### Get Your API Token

1. Sign up at: https://ace.your-domain.com (coming soon)
2. Create account
3. Generate API token
4. Set environment variable:
```bash
export ACE_API_TOKEN="your-token-here"
```

## 🧪 Testing

### Test Client Locally

```bash
# Start local test
python -m ace_client

# Should show:
# ✅ ACE Client initialized
# 🔗 Connecting to: https://ace.your-server.com/mcp
```

### Test with Plugin

1. Install plugin: `plugins/ace-orchestration/`
2. Configure with remote mode: `plugin.json`
3. Run command: `/ace-status`
4. Should connect to remote server

## 🏗️ Architecture

```
Claude Code
    ↓
ACE Plugin (plugin.json)
    ↓
Thin Client (ce-ai-ace-client) ← YOU ARE HERE
    ↓ HTTPS
Remote Server (your cloud)
    ↓
Pattern Database
```

**What this client does**:
1. Receives MCP tool calls from Claude Code
2. Forwards to remote server via HTTPS
3. Returns results to Claude Code
4. **Does NOT contain any secret algorithms!**

## 📝 Available MCP Tools

This client proxies these tools to the remote server:

1. `ace_reflect` - Pattern discovery from code
2. `ace_train_offline` - Git history training
3. `ace_get_patterns` - Pattern retrieval
4. `ace_get_playbook` - Playbook generation
5. `ace_status` - Database statistics
6. `ace_clear` - Reset database

## 🔐 Security

### API Token
- Required for all requests
- Stored securely in environment variables
- Never logged or exposed
- Rotatable via dashboard

### HTTPS
- All communication encrypted in transit
- TLS 1.3 required
- Certificate validation enforced

### Data Privacy
- Client only forwards requests
- No data stored locally (except pattern DB cache)
- Server validates all requests
- Rate limiting applied

## 🐛 Troubleshooting

### Connection Errors

```bash
# Check server URL
echo $ACE_SERVER_URL

# Test connectivity
curl -I https://ace.your-server.com/mcp

# Check API token
echo $ACE_API_TOKEN
```

### Authentication Errors

```bash
# Verify token is valid
# Check token hasn't expired
# Regenerate token if needed
```

### Import Errors

```bash
# Reinstall dependencies
pip install -e .

# Check Python version (3.11+ required)
python --version
```

## 📊 Publishing to PyPI (For Maintainers)

```bash
# 1. Update version in pyproject.toml
# 2. Build package
python -m build

# 3. Upload to PyPI
twine upload dist/*

# 4. Test installation
pip install ce-ai-ace-client
```

## 🔗 Links

- **Plugin**: `plugins/ace-orchestration/`
- **Server**: Private repo (algorithms protected)
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

## 📄 License

MIT License - See LICENSE file
