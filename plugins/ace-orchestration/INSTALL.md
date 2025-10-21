# ACE Plugin Installation Guide

**Version**: 3.0.4
**Type**: Bundled MCP Server (No Authentication Required)

---

## 🚀 Quick Install (3 Steps!)

### Step 1: Clone Repository

```bash
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace
```

### Step 2: Install Plugin in Claude Code

```bash
cd plugins/ace-orchestration

# Via symlink (recommended)
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration

# Or via Claude Code UI
# Plugins → Install from Filesystem → Select this directory
```

### Step 3: Restart Claude Code

Restart Claude Code to load the plugin.

### Step 4: Configure ACE Credentials

In Claude Code, run the interactive configuration wizard:

```
/ace-configure
```

**Prompts for**:
- ACE Server URL (default: http://localhost:9000)
- API Token (from your ACE server)
- Project ID (from your ACE dashboard)

**Saves to**: `~/.ace/config.json`

### Step 5: Test Installation

```
/ace-status
```

**Expected**: Shows ACE system status and connection info

---

## ✨ What's New in v3.0.4

- **Bundled MCP Server** - No package download required!
- **Zero Authentication** - Works offline, no GitHub token needed
- **Interactive Configuration** - `/ace-configure` wizard for credentials
- **Config File Support** - Saves to `~/.ace/config.json`

---

## 🎯 How It Works

**Everything is bundled!** No separate installation needed.

When you install the plugin:

1. **Plugin installed** → Claude Code finds it at `~/.config/claude-code/plugins/ace-orchestration`
2. **MCP server starts** → Automatically launched from `mcp-server/dist/index.js` (bundled!)
3. **Commands available** → All `/ace-*` commands ready to use
4. **Tools available** → MCP tools (`ace_status`, `ace_init`, etc.) ready

**What's included:**
- ✅ MCP Server (bundled in plugin)
- ✅ All dependencies (node_modules included)
- ✅ Slash commands (/ace-configure, /ace-status, etc.)
- ✅ Configuration wizard (interactive prompts)

**No external downloads, no authentication, works offline!**

---

## 📋 Alternative: Manual Configuration

If you prefer to configure manually instead of using `/ace-configure`:

### Option 1: Environment Variables

```bash
# Add to ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="your-token-here"
export ACE_PROJECT_ID="your-project-id"

# Reload shell
source ~/.zshrc

# Restart Claude Code to pick up new variables
```

### Option 2: Config File

```bash
# Create config directory
mkdir -p ~/.ace

# Create config file
cat > ~/.ace/config.json <<EOF
{
  "serverUrl": "http://localhost:9000",
  "apiToken": "your-token-here",
  "projectId": "your-project-id"
}
EOF
```

**Configuration Priority:**
1. Environment variables (highest)
2. `~/.ace/config.json`
3. Default values (lowest)

---

## 🔐 For Private Packages (Optional)

If the package is private on GitHub Packages:

### 1. Create GitHub Token

Go to: https://github.com/settings/tokens

**Required scopes**:
- ✅ `read:packages`

### 2. Add Token to .npmrc

Edit `.npmrc`:

```
@ce-dot-net:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

### 3. Set Token

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
```

---

## 🧪 Verification

### Check .npmrc Configuration

```bash
cat .npmrc

# Should show:
# @ce-dot-net:registry=https://npm.pkg.github.com
```

### Check Environment Variables

```bash
env | grep ACE_

# Should show:
# ACE_SERVER_URL=http://localhost:9000
# ACE_API_TOKEN=ace_...
# ACE_PROJECT_ID=prj_...
```

### Check Plugin Installation

```bash
ls -la ~/.config/claude-code/plugins/ace-orchestration

# Should show symlink to plugin directory
```

### Test npx Download

```bash
# From marketplace root (where .npmrc is)
cd ce-claude-marketplace
npx @ce-dot-net/ace-client --help

# Should download from GitHub Packages and show help
```

---

## 🐛 Troubleshooting

### Error: "404 Not Found" when downloading package

**Cause**: npm can't find package on GitHub Packages

**Fix**:
1. Check `.npmrc` exists in marketplace root
2. Verify `.npmrc` has: `@ce-dot-net:registry=https://npm.pkg.github.com`
3. For private packages, set `GITHUB_TOKEN`

```bash
# Verify registry
npm config get @ce-dot-net:registry

# Should show: https://npm.pkg.github.com
```

### Error: "Unauthorized" when downloading package

**Cause**: Missing or invalid GitHub token (for private packages)

**Fix**:
1. Create GitHub token: https://github.com/settings/tokens
2. Set token: `export GITHUB_TOKEN=ghp_xxxxx`
3. Add to `.npmrc`: `//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}`

### Plugin Commands Not Working

**Cause**: Environment variables not set or plugin not loaded

**Fix**:
1. Check environment variables: `env | grep ACE_`
2. Set missing variables
3. Restart Claude Code completely
4. Run `/ace-status` to verify

### "Command not found: npx"

**Cause**: Node.js not installed

**Fix**:
```bash
# Install Node.js 18+
# macOS:
brew install node

# Or download from: https://nodejs.org
```

---

## 📂 File Structure After Installation

```
ce-claude-marketplace/
├── .npmrc                          # ← Created by install script
│   └── @ce-dot-net:registry=https://npm.pkg.github.com
├── plugins/
│   └── ace-orchestration/
│       ├── plugin.json             # ← Copied from template
│       ├── plugin.template.json    # ← Original template
│       ├── scripts/
│       │   ├── install.sh          # ← Installation script
│       │   └── setup.js            # ← Node.js setup script
│       └── ...
└── ...

~/.config/claude-code/plugins/
└── ace-orchestration/              # ← Symlink to plugin directory
```

---

## 🔄 Update Plugin

```bash
cd ce-claude-marketplace

# Pull latest changes
git pull origin main

# Restart Claude Code
# Plugin updates automatically via symlink!
```

---

## 🗑️ Uninstall Plugin

```bash
# Remove symlink
rm ~/.config/claude-code/plugins/ace-orchestration

# Optionally remove .npmrc
rm ce-claude-marketplace/.npmrc

# Restart Claude Code
```

---

## 📚 Next Steps

After installation:

1. **Initialize patterns**: Run `/ace-init` to discover patterns from your codebase
2. **View status**: Run `/ace-status` to see pattern statistics
3. **Use patterns**: ACE automatically learns from your coding sessions
4. **Monitor evolution**: Check pattern growth over time

---

## 🆘 Getting Help

- **Documentation**: See `CONFIGURATION.md` for detailed setup
- **Security**: See `SECURITY.md` for security best practices
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

---

**Installation complete!** 🎉

The plugin will automatically download `@ce-dot-net/ace-client` from GitHub Packages when first used.
