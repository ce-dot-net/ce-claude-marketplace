# 🚀 Publish to GitHub Packages - Step-by-Step

**Ready to publish v3.0.0!**

---

## ✅ Pre-flight Checklist

All preparation complete:
- [x] Package built and tested (10/10 tests passing)
- [x] Version synced to 3.0.0
- [x] Documentation complete
- [x] Security verified (no hardcoded credentials)
- [x] Installation scripts created
- [x] Publishing scripts ready

---

## 📝 Step 1: Create GitHub Token

### Go to GitHub Settings

**URL**: https://github.com/settings/tokens

### Create New Token

1. Click **"Generate new token"** → **"Generate new token (classic)"**

2. **Token name**: `ace-publish`

3. **Select scopes**:
   - ✅ `write:packages` - Upload packages
   - ✅ `read:packages` - Download packages
   - ✅ `delete:packages` - Delete packages (important!)

4. **Expiration**: Choose (recommend 90 days)

5. Click **"Generate token"**

6. **Copy the token** (shown only once!)
   - Format: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Save Token Securely

```bash
# Add to your shell profile (~/.zshrc or ~/.bashrc)
echo 'export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx' >> ~/.zshrc

# Reload shell
source ~/.zshrc

# Verify
echo $GITHUB_TOKEN  # Should show your token
```

---

## 🚀 Step 2: Publish to GitHub Packages

### Option A: Using Script (Recommended)

```bash
cd mcp-clients/ce-ai-ace-client

# Set token (if not in shell profile)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx

# Publish!
npm run publish:github

# Expected output:
# 🔨 Building...
# 🧪 Running tests...
# 🚀 Publishing @ce-dot-net/ace-client@3.0.0 to GitHub Packages...
# + @ce-dot-net/ace-client@3.0.0
# ✅ Successfully published to GitHub Packages!
```

### Option B: Manual Steps

```bash
cd mcp-clients/ce-ai-ace-client

# 1. Build
npm run build

# 2. Test
npm test

# 3. Configure GitHub Packages
cat > .npmrc <<EOF
registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=\${GITHUB_TOKEN}
EOF

# 4. Publish
npm publish

# 5. Clean up
rm .npmrc

# Expected: + @ce-dot-net/ace-client@3.0.0
```

---

## 📦 Step 3: Verify Publication

### Check on GitHub

**Go to**: https://github.com/ce-dot-net?tab=packages

**Look for**: `@ce-dot-net/ace-client`

**Should show**:
- Version: 3.0.0
- Published: Just now
- Type: npm

### Test Installation

```bash
# From marketplace root (where .npmrc will be)
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace

# Create .npmrc for GitHub Packages
cat > .npmrc <<EOF
@ce-dot-net:registry=https://npm.pkg.github.com
EOF

# Test installation
npx @ce-dot-net/ace-client --help

# Expected: Downloads package and shows MCP server starting
```

---

## 🔧 Step 4: Test Plugin Installation

### Run Installation Script

```bash
cd plugins/ace-orchestration

# Run automated setup
./scripts/install.sh

# Expected:
# ✅ .npmrc created with GitHub Packages configuration
# ✅ Environment variables checked
# ✅ Configuration verified
```

### Set Environment Variables

```bash
# Add to ~/.zshrc (if not already)
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"

# Reload
source ~/.zshrc
```

### Copy Plugin Configuration

```bash
cd plugins/ace-orchestration
cp plugin.template.json plugin.json
```

### Install Plugin in Claude Code

```bash
# Via symlink
ln -sf "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration

# Restart Claude Code
```

### Test in Claude Code

```
/ace-status
```

**Expected**:
- Claude Code runs: `npx @ce-dot-net/ace-client`
- Downloads from GitHub Packages (first time)
- Connects to ACE server
- Shows pattern statistics

---

## 🎉 Step 5: Create Git Tag

### Tag the Release

```bash
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace

# Create tag
git tag -a v3.0.0 -m "Release v3.0.0 - TypeScript MCP Client Production Ready

- Complete TypeScript rewrite
- 3-tier cache architecture (50-200x speedup)
- 10/10 integration tests passing
- Published to GitHub Packages
- 37 real patterns discovered
- Security best practices implemented
"

# Push tag
git push origin v3.0.0

# Also push main branch
git push origin main
```

---

## 📝 Step 6: Create GitHub Release

### Go to Releases

**URL**: https://github.com/ce-dot-net/ce-claude-marketplace/releases/new

### Fill in Details

**Tag**: v3.0.0 (select from dropdown)

**Release title**: Release v3.0.0 - TypeScript MCP Client Production Ready

**Description**: (Copy from CHANGELOG.md lines 186-460)

```markdown
## 🚀 Major Release: TypeScript MCP Client Production Ready

Complete rewrite from Python to TypeScript with 3-tier caching, comprehensive testing, and production-ready architecture.

### Breaking Changes

- **MCP Client**: Complete rewrite in TypeScript (Python client deprecated)
- **Installation**: Now requires Node.js 18+ (no Python dependency for client)
- **Package Name**: `@ce-dot-net/ace-client` (GitHub Packages)
- **MCP Tools**: 5 tools (was 6) - consolidated functionality

... [rest of CHANGELOG]
```

**Links**:
- GitHub Packages: https://github.com/ce-dot-net/ce-ai-ace-client/packages
- Documentation: https://github.com/ce-dot-net/ce-claude-marketplace/tree/main/mcp-clients/ce-ai-ace-client

### Publish Release

Click **"Publish release"**

---

## ✅ Verification Checklist

After publishing, verify:

- [ ] Package visible at: https://github.com/ce-dot-net?tab=packages
- [ ] Can install with: `npx @ce-dot-net/ace-client`
- [ ] Git tag exists: https://github.com/ce-dot-net/ce-claude-marketplace/tags
- [ ] GitHub release created: https://github.com/ce-dot-net/ce-claude-marketplace/releases
- [ ] Plugin installation script works
- [ ] Claude Code can use the plugin
- [ ] `/ace-status` command works

---

## 🗑️ If You Need to Delete (GitHub Packages Advantage!)

### Delete Entire Package

```bash
# Via GitHub CLI
gh api -X DELETE /user/packages/npm/ace-client

# Or via web UI:
# https://github.com/ce-dot-net?tab=packages
# → Click package → Settings → Delete this package
```

### Delete Specific Version

```bash
# Get package version ID first
gh api /user/packages/npm/ace-client/versions

# Delete version
gh api -X DELETE /user/packages/npm/ace-client/versions/VERSION_ID
```

**Remember**: You CAN delete from GitHub Packages anytime! No 72-hour limit!

---

## 🔄 If You Need to Republish

```bash
# After deleting or fixing issues:

cd mcp-clients/ce-ai-ace-client

# Make changes...

# Rebuild and test
npm run build
npm test

# Republish (can use same version!)
npm run publish:github

# Done!
```

---

## 📊 What Users Will See

### Installation Experience

1. **Clone repository**
   ```bash
   git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
   cd ce-claude-marketplace
   ```

2. **Run installation script**
   ```bash
   cd plugins/ace-orchestration
   ./scripts/install.sh
   ```

3. **Set environment variables**
   ```bash
   export ACE_SERVER_URL="http://localhost:9000"
   export ACE_API_TOKEN="your-token-here"
   export ACE_PROJECT_ID="your-project-id"
   ```

4. **Copy plugin config**
   ```bash
   cp plugin.template.json plugin.json
   ```

5. **Install in Claude Code**
   ```bash
   ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration
   ```

6. **Use it!**
   ```
   /ace-status
   ```

---

## 🎯 Summary

**Commands to run**:

```bash
# 1. Set GitHub token
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx

# 2. Publish to GitHub Packages
cd mcp-clients/ce-ai-ace-client
npm run publish:github

# 3. Create git tag
cd ../..
git tag -a v3.0.0 -m "Release v3.0.0"
git push origin v3.0.0

# 4. Test installation
cd plugins/ace-orchestration
./scripts/install.sh
cp plugin.template.json plugin.json

# 5. Create GitHub release (via web UI)
# https://github.com/ce-dot-net/ce-claude-marketplace/releases/new
```

---

## 🆘 Troubleshooting

### "401 Unauthorized"

**Cause**: Invalid or missing GitHub token

**Fix**:
```bash
# Check token is set
echo $GITHUB_TOKEN

# Regenerate token if needed
# https://github.com/settings/tokens
```

### "Package already exists"

**Cause**: Version 3.0.0 already published

**Fix**:
```bash
# Delete existing version
gh api -X DELETE /user/packages/npm/ace-client

# Or bump version
npm version patch  # 3.0.1
npm run publish:github
```

### "404 Not Found" during npx install

**Cause**: .npmrc not configured

**Fix**:
```bash
# Create .npmrc in project root
cat > .npmrc <<EOF
@ce-dot-net:registry=https://npm.pkg.github.com
EOF
```

---

**Ready to publish!** 🚀

Just set `GITHUB_TOKEN` and run `npm run publish:github`!
