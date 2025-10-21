# ACE Plugin Troubleshooting Guide

**Problem**: MCP server not appearing in `/mcp` command

---

## Quick Fix Checklist

✅ **90% of issues are solved by restarting Claude Code**

According to [official Claude Code documentation](https://docs.claude.com/en/docs/claude-code/mcp#plugin-provided-mcp-servers):

> **You must restart Claude Code to apply MCP server changes (enabling or disabling)**

---

## Step-by-Step Diagnostic

### 1. Verify Plugin Installation

```bash
# Check symlink exists
ls -la ~/.config/claude-code/plugins/ace-orchestration

# Should show:
# lrwxr-xr-x  ... ace-orchestration -> /path/to/ce-claude-marketplace/plugins/ace-orchestration
```

**Fix if missing:**
```bash
cd ~/repos/.../ce-claude-marketplace/plugins/ace-orchestration
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration
```

---

### 2. Verify plugin.json Exists

```bash
cat ~/.config/claude-code/plugins/ace-orchestration/plugin.json | grep -A 5 mcpServers
```

**Should show:**
```json
"mcpServers": {
  "ace-pattern-learning": {
    "command": "npx",
    "args": ["--package=@ce-dot-net/ace-client", "ace-client"],
```

**Fix if missing:**
```bash
cd ~/repos/.../ce-claude-marketplace/plugins/ace-orchestration
cp plugin.template.json plugin.json
```

---

### 3. Verify .npmrc Configuration

```bash
# Check marketplace root has .npmrc
cd ~/repos/.../ce-claude-marketplace
cat .npmrc
```

**Should show:**
```
@ce-dot-net:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=ghp_xxxxx
```

**Fix if missing:**
```bash
cd ~/repos/.../ce-claude-marketplace/plugins/ace-orchestration
./scripts/install.sh
```

---

### 4. Test Package Download

```bash
cd ~/repos/.../ce-claude-marketplace
npx --package=@ce-dot-net/ace-client@3.0.3 ace-client
```

**Should show:**
```
💾 Local cache: ...
🔗 ACE Server: http://localhost:9000
🚀 ACE Client MCP started (v3.0.3 - Full ACE Paper Implementation)
```

**If fails:**
- Check .npmrc exists in marketplace root
- Check GITHUB_TOKEN in ~/.npmrc or .env file
- Try: `rm -rf ~/.npm/_npx` to clear cache

---

### 5. Verify Environment Variables

```bash
echo "ACE_SERVER_URL: $ACE_SERVER_URL"
echo "ACE_API_TOKEN: ${ACE_API_TOKEN:0:10}..."
echo "ACE_PROJECT_ID: $ACE_PROJECT_ID"
```

**Should show:**
```
ACE_SERVER_URL: http://localhost:9000
ACE_API_TOKEN: ace_wFIuXz...
ACE_PROJECT_ID: prj_5bc0b560221052c1
```

**Fix if missing:**
```bash
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"

# Add to ~/.zshrc or ~/.bashrc to persist
```

---

### 6. ⭐ RESTART CLAUDE CODE ⭐

**This is the most important step!**

1. **Completely quit** Claude Code (Cmd+Q on Mac)
2. Wait 5 seconds
3. Start Claude Code again
4. Navigate to your project directory
5. Run: `/mcp`

---

### 7. Check MCP Server Status

In Claude Code:
```
/mcp
```

**Expected output:**
```
Found X MCP servers:

ace-pattern-learning: connected
  - ace_status: Get ACE system status
  - ace_init: Initialize patterns for a project
  - ace_clear: Clear pattern database
  - ace_patterns: List learned patterns
  - ace_playbook: Get playbook for domain
```

**If shows "failed" or "connecting":**
- Check environment variables are set
- Check ACE server is running at http://localhost:9000
- Check Claude Code logs (see below)

---

## Known Issues

### Issue: MCP Server Shows as "Failed"

**Possible causes:**
1. Environment variables not set in Claude Code's environment
2. ACE server not running
3. Network connectivity issues

**Solutions:**
```bash
# 1. Check if variables are in Claude Code's environment
# Add to ~/.zshrc or ~/.bashrc:
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="your-token"
export ACE_PROJECT_ID="your-project-id"

# 2. Restart terminal AND Claude Code

# 3. Test ACE server manually:
curl http://localhost:9000/api/health
```

---

### Issue: Package Download Fails (404)

**Cause:** npm can't find package on GitHub Packages

**Solution:**
```bash
# 1. Verify .npmrc exists at marketplace root
cat ~/repos/.../ce-claude-marketplace/.npmrc

# 2. If missing auth token, run install script:
cd plugins/ace-orchestration
./scripts/install.sh

# 3. Clear npm cache:
rm -rf ~/.npm/_npx
npm cache clean --force

# 4. Test again:
npx --package=@ce-dot-net/ace-client@3.0.3 ace-client
```

---

### Issue: "Connection Closed" or "Timeout"

**Cause:** MCP server fails to start

**Check logs:**
```bash
# View Claude Code logs
ls -lt ~/.config/claude-code/logs/ | head -5
tail -50 ~/.config/claude-code/logs/server-*.log
```

**Common issues:**
- `npx` command fails (check .npmrc)
- Environment variables not accessible
- Port conflicts (9000 already in use)

---

## Official Documentation References

- [Claude Code MCP - Plugin-provided MCP servers](https://docs.claude.com/en/docs/claude-code/mcp#plugin-provided-mcp-servers)
- [Claude Code Plugins Reference](https://docs.claude.com/en/docs/claude-code/plugins-reference#mcp-servers)

---

## Known Claude Code Bugs

As of 2025, there are open issues with MCP servers in Claude Code:

- [Issue #2156](https://github.com/anthropics/claude-code/issues/2156): Project Scoped MCP Server not detected
- [Issue #1611](https://github.com/anthropics/claude-code/issues/1611): MCP servers fail to connect
- [Issue #467](https://github.com/anthropics/claude-code/issues/467): MCP tool calls not working

If you've followed all steps above and MCP server still doesn't appear, it may be a Claude Code bug.

---

## Automated Diagnostic

Run our diagnostic script:
```bash
cd ~/repos/.../ce-claude-marketplace/plugins/ace-orchestration
./scripts/diagnose.sh
```

This checks all requirements automatically.

---

## Getting Help

1. **Check diagnostic output**: `./scripts/diagnose.sh`
2. **Check Claude Code logs**: `~/.config/claude-code/logs/`
3. **Report issue**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

Include:
- Output of `./scripts/diagnose.sh`
- Output of `/mcp` command
- Recent Claude Code logs
