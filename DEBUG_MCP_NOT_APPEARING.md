# 🔍 DEBUG: MCP Not Appearing in /mcp

## Root Cause Identified ✅

The MCP server isn't starting because **npx can't download the package from GitHub Packages**.

### Why This Happens

1. Plugin config says: `npx --package=@ce-dot-net/ace-client ace-client`
2. npx tries to download from GitHub Packages
3. GitHub Packages requires authentication
4. Authentication needs `.npmrc` file at marketplace root
5. **Your other session doesn't have `.npmrc` configured!**

## Solution (Run in the OTHER Terminal)

```bash
# Navigate to marketplace
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace

# Check if .npmrc exists
ls -la .npmrc

# If missing, run the install script
cd plugins/ace-orchestration
./scripts/install.sh

# This will:
# 1. Read GITHUB_TOKEN from mcp-clients/ce-ai-ace-client/.env
# 2. Create .npmrc at marketplace root with auth token
# 3. Verify environment variables

# After running install.sh, you should see:
# ✅ .npmrc created with authentication
```

## Verify It Worked

```bash
# Test package download manually
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace
npx --package=@ce-dot-net/ace-client@3.0.4 ace-client

# Should show:
# ✅ Loaded config from: /Users/you/.ace/config.json  (or env vars)
# 🔗 ACE Server: http://localhost:9000
# 🔑 API Token: ace_wFIuXz...
# 📂 Project: prj_5bc0b5...
# 🚀 ACE Client MCP started (v3.0.4)
```

## Then Restart Claude Code

1. **Completely quit** Claude Code (Cmd+Q)
2. Wait 5 seconds
3. Start Claude Code again
4. Navigate to your project
5. Run: `/mcp`

**Expected result:**
```
Found X MCP servers:

ace-pattern-learning: connected
  - ace_status
  - ace_init
  - ace_clear
  - ace_patterns
  - ace_playbook
```

## File Structure You Need

```
ce-claude-marketplace/
├── .npmrc                              # ← NEEDS TO EXIST (created by install.sh)
│   └── Contents:
│       @ce-dot-net:registry=https://npm.pkg.github.com
│       //npm.pkg.github.com/:_authToken=ghp_xxxxx
│
├── mcp-clients/ce-ai-ace-client/
│   └── .env                            # ← HAS THE GITHUB_TOKEN
│       └── GITHUB_TOKEN=ghp_xxxxx
│
└── plugins/ace-orchestration/
    ├── plugin.json                     # ← NEEDS TO EXIST (copy from template)
    └── scripts/install.sh              # ← RUN THIS!
```

## Checklist (Run in Other Session)

- [ ] Navigate to marketplace root
- [ ] Check `.env` exists: `ls mcp-clients/ce-ai-ace-client/.env`
- [ ] Run install script: `cd plugins/ace-orchestration && ./scripts/install.sh`
- [ ] Verify `.npmrc` created: `cat ../../.npmrc`
- [ ] Test npx download: `cd ../.. && npx --package=@ce-dot-net/ace-client@3.0.4 ace-client`
- [ ] Restart Claude Code completely
- [ ] Run: `/mcp`
- [ ] See MCP server connected!

## If Still Not Working

Check these logs:
```bash
# Claude Code logs
ls -lt ~/.config/claude-code/logs/ | head -5
tail -100 ~/.config/claude-code/logs/server-*.log | grep -i ace
```

## Quick Test Script

Run this in the other session:

```bash
#!/bin/bash
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace

echo "1. Checking .env file..."
if [ -f mcp-clients/ce-ai-ace-client/.env ]; then
  echo "✅ .env exists"
  grep "GITHUB_TOKEN=" mcp-clients/ce-ai-ace-client/.env | sed 's/=.*/=***/'
else
  echo "❌ .env missing!"
fi

echo ""
echo "2. Checking .npmrc..."
if [ -f .npmrc ]; then
  echo "✅ .npmrc exists"
  grep "@ce-dot-net:registry" .npmrc
else
  echo "❌ .npmrc missing! Run: cd plugins/ace-orchestration && ./scripts/install.sh"
fi

echo ""
echo "3. Testing package download..."
npx --package=@ce-dot-net/ace-client@3.0.4 ace-client 2>&1 | head -10
```
