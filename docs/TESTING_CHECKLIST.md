# Testing Checklist

Quick reference for testing your marketplace and plugin setup.

## ✅ Pre-Testing Setup

- [ ] Local MCP server is running (separate terminal)
- [ ] MCP client installed: `cd mcp-clients/ce-ai-ace-client && pip install -e .`
- [ ] Claude Code CLI v2.0.12+ installed
- [ ] Repository cloned locally

## ✅ Marketplace Setup

```bash
# Add marketplace
/plugin marketplace add /Users/ptsafaridis/repos/github_com/ce-dot-net/ce-claude-marketplace

# Verify it's added
/plugin marketplace list
```

Expected output: Should show `ce-dot-net-marketplace`

## ✅ Plugin Installation

```bash
# Browse plugins
/plugin

# Install plugin
/plugin install ace-orchestration@ce-dot-net-marketplace

# Verify installation
/plugin list
```

Expected output: Should show `ace-orchestration` in installed plugins

## ✅ Command Testing

Test each slash command:

```bash
# 1. Check status
/ace-status

# 2. View patterns (should be empty initially)
/ace-patterns

# 3. View patterns for specific domain
/ace-patterns python

# 4. View high-confidence patterns
/ace-patterns error-handling 0.7
```

## ✅ Hook Testing

1. **Create or edit a file** using Claude Code
2. **PostToolUse hook should fire** automatically
3. **Check MCP server logs** for reflection activity
4. **Run `/ace-status`** to see if patterns increased

## ✅ MCP Tools Testing

Ask Claude to:

```
Can you check the ACE pattern database status?
```

Claude should use the `ace_status` MCP tool.

```
Can you generate a playbook for error handling?
```

Claude should use the `ace_get_playbook` MCP tool.

## ✅ Offline Training

```bash
/ace-train-offline
```

This should:
- Analyze git history
- Discover patterns from commits
- Update pattern database

## ✅ Agent Testing

The Reflector agent should be available. Ask Claude:

```
Can you analyze this code and discover patterns?
```

Claude should automatically invoke the Reflector agent.

## ✅ Connection Verification

### MCP Server Running?

```bash
# Check if server is listening
lsof -i :8000
# or
curl http://localhost:8000/health
```

### MCP Client Working?

```bash
# Test client directly
python -m ace_client --help
```

### Plugin MCP Server Started?

Check Claude Code debug logs:

```bash
claude --debug
```

Look for: `Starting MCP server: ace-pattern-learning`

## ✅ Error Scenarios

Test error handling:

### Server Not Running

1. Stop MCP server
2. Try `/ace-status`
3. Expected: Clear error message about connection

### Invalid Token

1. Edit plugin.json, set invalid token
2. Try `/ace-status`
3. Expected: Authentication error

## ✅ Production Readiness

Before going to production:

- [ ] All commands work locally
- [ ] Hooks fire correctly
- [ ] MCP tools accessible
- [ ] Patterns stored successfully
- [ ] Offline training works
- [ ] Playbook generation works
- [ ] Error handling is clear
- [ ] Documentation is complete

## 🚀 Next Steps

Once all checks pass:

1. **Switch to production config**:
   ```bash
   cp plugins/ace-orchestration/plugin.PRODUCTION.json plugins/ace-orchestration/plugin.json
   ```

2. **Publish MCP client to PyPI**:
   ```bash
   cd mcp-clients/ce-ai-ace-client
   python -m build
   twine upload dist/*
   ```

3. **Update server URL** in plugin.json

4. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "🚀 Production-ready marketplace"
   git push origin main
   ```

5. **Test GitHub installation**:
   ```bash
   /plugin marketplace add ce-dot-net/ce-claude-marketplace
   ```

## 🐛 Troubleshooting

See `docs/LOCAL_TESTING.md` for detailed troubleshooting guide.

### Quick Fixes

**Plugin not loading**: `claude plugin validate .`

**MCP client not found**: `pip install -e mcp-clients/ce-ai-ace-client`

**Connection refused**: Check if MCP server is running

**Hook not firing**: Check `hooks/hooks.json` syntax and permissions
