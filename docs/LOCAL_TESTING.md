# Local Testing Guide

Complete guide for testing the ACE Orchestration plugin and MCP client locally before production deployment.

## Prerequisites

- Claude Code CLI v2.0.12 or higher
- Python 3.10+ installed
- Local ACE MCP server running
- Git repository cloned locally

## Setup Steps

### 1. Install MCP Client in Development Mode

```bash
cd mcp-clients/ce-ai-ace-client
pip install -e .
```

This installs the client in "editable" mode, so changes are immediately available without reinstalling.

### 2. Verify Client Installation

```bash
python -m ace_client --help
# or
ce-ai-ace-client --help
```

You should see the client help output.

### 3. Start Your Local MCP Server

In a separate terminal window:

```bash
# Navigate to your MCP server directory
cd /path/to/your/mcp-server

# Start the server (adjust command as needed)
python -m ace_server
# or
uvx run ace-server
```

The server should be running on `http://localhost:8000/mcp` (or your configured port).

### 4. Add the Marketplace Locally

In Claude Code CLI:

```bash
/plugin marketplace add /Users/ptsafaridis/repos/github_com/ce-dot-net/ce-claude-marketplace
```

Replace the path with your actual repository path. You can also use relative paths:

```bash
/plugin marketplace add ~/repos/github_com/ce-dot-net/ce-claude-marketplace
```

### 5. Verify Marketplace Installation

```bash
/plugin marketplace list
```

You should see `ce-dot-net-marketplace` in the list.

### 6. Browse Available Plugins

```bash
/plugin
```

This opens the interactive plugin browser. You should see `ace-orchestration` available.

### 7. Install the Plugin

```bash
/plugin install ace-orchestration@ce-dot-net-marketplace
```

Claude Code will:
1. Copy the plugin to its installation directory
2. Register commands, agents, and hooks
3. Start the MCP server (connecting to localhost:8000)

### 8. Verify Plugin Installation

```bash
/plugin list
```

You should see `ace-orchestration` in the installed plugins list.

### 9. Test Plugin Commands

Try the plugin's slash commands:

```bash
/ace-status
```

This should connect to your local MCP server and return pattern database statistics.

## Configuration Details

### Current Local Configuration

The `plugin.json` is configured for local testing:

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "python",
      "args": ["-m", "ace_client"],
      "env": {
        "ACE_SERVER_URL": "http://localhost:8000/mcp",
        "ACE_API_TOKEN": "local-dev-token",
        "ACE_STORAGE_PATH": "${CLAUDE_PLUGIN_ROOT}/.ace-memory/patterns.db"
      }
    }
  }
}
```

### Adjusting the Server URL

If your local server runs on a different port, update `plugin.json`:

```json
"ACE_SERVER_URL": "http://localhost:3000/mcp"
```

### Environment Variables

- `ACE_SERVER_URL`: Your local server endpoint
- `ACE_API_TOKEN`: Token for authentication (use any value for local testing)
- `ACE_STORAGE_PATH`: Where patterns are stored (auto-created)
- `${CLAUDE_PLUGIN_ROOT}`: Automatically resolves to plugin installation directory

## Testing Workflow

### Complete End-to-End Test

1. **Start local MCP server** (Terminal 1)
2. **Install and load plugin** (Claude Code)
3. **Write some code** using Edit/Write tools
4. **Verify PostToolUse hook** fires (check MCP server logs)
5. **Check patterns** with `/ace-patterns`
6. **Test offline training** with `/ace-train-offline`
7. **Test playbook generation** (ask Claude to generate a playbook)

### Debug Mode

Run Claude Code with debug logging:

```bash
claude --debug
```

This shows:
- Plugin loading process
- MCP server initialization
- Hook execution
- Command registration

### Common Issues

#### Plugin Not Loading

**Symptom**: Plugin doesn't appear in `/plugin list`

**Solutions**:
1. Check `marketplace.json` syntax with `claude plugin validate .`
2. Verify plugin.json exists at `plugins/ace-orchestration/plugin.json`
3. Check Claude Code debug logs

#### MCP Client Not Found

**Symptom**: `Error: python: No module named ace_client`

**Solutions**:
1. Re-install client: `pip install -e mcp-clients/ce-ai-ace-client`
2. Check Python path: `which python`
3. Try full path: `python3 -m ace_client`

#### Connection Refused

**Symptom**: `Connection refused to localhost:8000`

**Solutions**:
1. Verify MCP server is running
2. Check server port matches plugin.json
3. Test server manually: `curl http://localhost:8000/health`

#### Hook Not Firing

**Symptom**: PostToolUse hook doesn't trigger

**Solutions**:
1. Check `hooks/hooks.json` syntax
2. Verify hook script is executable: `chmod +x hooks/PostTaskCompletion.sh`
3. Check hook matcher pattern
4. Review Claude Code debug logs

## Transitioning to Production

Once local testing is successful:

### 1. Publish MCP Client to PyPI

```bash
cd mcp-clients/ce-ai-ace-client
python -m build
twine upload dist/*
```

### 2. Update Plugin Configuration

Copy production config:

```bash
cp plugins/ace-orchestration/plugin.PRODUCTION.json plugins/ace-orchestration/plugin.json
```

### 3. Update Server URL

Edit `plugin.json` and set your production URL:

```json
"ACE_SERVER_URL": "https://ace.your-domain.com/mcp"
```

### 4. Set API Token

Configure the environment variable for production:

```bash
export ACE_API_TOKEN="your-production-token"
```

### 5. Push to GitHub

```bash
git add .
git commit -m "✅ Ready for production deployment"
git push origin main
```

### 6. Test GitHub Installation

```bash
/plugin marketplace add ce-dot-net/ce-claude-marketplace
/plugin install ace-orchestration@ce-dot-net-marketplace
```

## File Structure Reference

```
ce-claude-marketplace/
├── .claude-plugin/
│   └── marketplace.json          # Marketplace configuration
├── plugins/
│   └── ace-orchestration/
│       ├── plugin.json            # LOCAL config (default)
│       ├── plugin.PRODUCTION.json # Production config template
│       ├── commands/              # Slash commands
│       ├── agents/                # Specialized agents
│       └── hooks/                 # Event hooks
└── mcp-clients/
    └── ce-ai-ace-client/
        ├── pyproject.toml         # Package config
        ├── ace_client/            # Client code
        │   ├── __init__.py
        │   ├── __main__.py
        │   └── client.py
        └── README.md
```

## Next Steps

After successful local testing:

1. ✅ Verify all commands work
2. ✅ Test hooks trigger correctly
3. ✅ Confirm MCP tools are accessible
4. ✅ Check pattern storage works
5. ✅ Test offline training
6. ✅ Validate playbook generation
7. 🚀 Deploy to production
8. 📦 Publish to PyPI
9. 🌐 Share marketplace with community

## Support

For issues or questions:
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues
- **Discussions**: https://github.com/ce-dot-net/ce-claude-marketplace/discussions
- **Email**: ace@ce-dot-net.com
