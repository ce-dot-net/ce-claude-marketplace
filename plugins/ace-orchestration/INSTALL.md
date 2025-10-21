# ACE Plugin Installation Guide

**Version**: 3.0.0
**Package**: @ce-dot-net/ace-client (GitHub Packages)

---

## 🚀 Quick Install (Automated)

### Step 1: Clone Repository

```bash
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace
```

### Step 2: Run Installation Script

```bash
cd plugins/ace-orchestration

# Run automated setup
./scripts/install.sh

# Or using Node.js
node scripts/setup.js
```

**What it does**:
- ✅ Creates `.npmrc` for GitHub Packages registry
- ✅ Checks environment variables
- ✅ Verifies configuration files
- ✅ Shows next steps

### Step 3: Set Environment Variables

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_REDACTED_TOKEN"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"
```

Then reload:

```bash
source ~/.zshrc  # or ~/.bashrc
```

### Step 4: Configure Plugin

```bash
cd plugins/ace-orchestration
cp plugin.template.json plugin.json
```

### Step 5: Install Plugin in Claude Code

```bash
# Via symlink (recommended)
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration

# Or via Claude Code UI
# Plugins → Install from Filesystem → Select this directory
```

### Step 6: Restart Claude Code

Restart Claude Code to load the plugin.

### Step 7: Test Installation

In Claude Code:

```
/ace-status
```

**Expected**: Shows ACE system status (may download @ce-dot-net/ace-client first)

---

## 📋 Manual Install (Step-by-Step)

### 1. Configure npm Registry

Create `.npmrc` in the marketplace root:

```bash
cd ce-claude-marketplace

cat > .npmrc <<EOF
# ACE Plugin - GitHub Packages Configuration
@ce-dot-net:registry=https://npm.pkg.github.com
EOF
```

**Why**: Tells npm/npx to download `@ce-dot-net/ace-client` from GitHub Packages

### 2. Set Environment Variables

```bash
# Add to ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="your-token-here"
export ACE_PROJECT_ID="your-project-id"

# Reload shell
source ~/.zshrc
```

### 3. Copy Plugin Configuration

```bash
cd plugins/ace-orchestration
cp plugin.template.json plugin.json
```

### 4. Install Plugin

```bash
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration
```

### 5. Restart Claude Code

### 6. Test

```
/ace-status
```

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
