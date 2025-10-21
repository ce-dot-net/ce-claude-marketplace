# Publishing Strategy - npm vs GitHub Packages

**TL;DR**: Use **GitHub Packages first**, then npm later if desired.

---

## 🎯 Quick Comparison

| Feature | npm | GitHub Packages | Winner |
|---------|-----|-----------------|--------|
| **Can delete packages** | ❌ Only 72 hours | ✅ Anytime | 🏆 GitHub |
| **Delete specific versions** | ❌ No | ✅ Yes | 🏆 GitHub |
| **User discovery** | ✅ npmjs.com | ⚠️ github.com/packages | 🏆 npm |
| **Installation ease** | ✅ Easy | ⚠️ Needs .npmrc | 🏆 npm |
| **Private packages** | 💰 $7/month | ✅ Free | 🏆 GitHub |
| **Authentication** | npm account | GitHub token | 🤝 Tie |
| **CI/CD integration** | ✅ Good | ✅ Excellent | 🏆 GitHub |

---

## 🚀 Recommended Strategy

### Phase 1: GitHub Packages Only (RECOMMENDED)

**When**: Now - First 2 weeks

**Why**:
- ✅ Can delete if something goes wrong
- ✅ Full control over package
- ✅ Easy to fix mistakes
- ✅ Test with early users

**How**:
```bash
cd mcp-clients/ce-ai-ace-client

# Set GitHub token
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx

# Publish to GitHub Packages
npm run publish:github

# If you need to delete:
gh api -X DELETE /user/packages/npm/ace-client

# Fix and republish - same version!
npm run publish:github
```

---

### Phase 2: Dual Publishing (OPTIONAL)

**When**: After 1-2 weeks of testing

**Why**:
- ✅ Wider user reach (npmjs.com)
- ✅ Keep GitHub as backup/testing
- ✅ Users can choose

**How**:
```bash
# Keep GitHub Packages as primary
npm run publish:github

# Also publish to npm for wider reach
npm run publish:npm

# Now available on both!
```

---

### Phase 3: npm Primary (OPTIONAL)

**When**: After 1 month+ of stability

**Why**:
- ✅ Most users find packages on npm
- ✅ Easier installation (no .npmrc needed)
- ✅ Better ecosystem integration

**How**:
```bash
# Publish new versions to npm
npm run publish:npm

# Keep GitHub Packages in sync
npm run publish:github
```

---

## 📋 Publishing Commands

### Publish to GitHub Packages

```bash
cd mcp-clients/ce-ai-ace-client

# Set GitHub token
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx

# Publish
npm run publish:github

# Or manually:
./scripts/publish-github.sh
```

**What it does**:
1. Builds TypeScript
2. Runs all tests
3. Configures GitHub Packages registry
4. Publishes package
5. Restores original config

---

### Publish to npm

```bash
cd mcp-clients/ce-ai-ace-client

# Make sure you're logged in
npm whoami

# Publish
npm run publish:npm

# Or manually:
./scripts/publish-npm.sh
```

**What it does**:
1. Checks npm authentication
2. Builds TypeScript
3. Runs all tests
4. Asks for confirmation
5. Publishes to npm

---

## 🔐 Setup: GitHub Packages

### 1. Create GitHub Token

Go to: https://github.com/settings/tokens

**Required scopes**:
- ✅ `write:packages` - Publish packages
- ✅ `read:packages` - Download packages
- ✅ `delete:packages` - Delete packages (important!)

### 2. Set Token

```bash
# In your shell profile (~/.zshrc or ~/.bashrc)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx

# Or for this session only:
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
```

### 3. Publish

```bash
npm run publish:github
```

---

## 🔐 Setup: npm

### 1. Create npm Account

Go to: https://www.npmjs.com/signup

### 2. Login

```bash
npm login

# Username: your-npm-username
# Password: your-npm-password
# Email: your-email@example.com
```

### 3. Verify

```bash
npm whoami
# Should show your username
```

### 4. Publish

```bash
npm run publish:npm
```

---

## 📥 User Installation

### From GitHub Packages

**Users need to configure .npmrc**:

```bash
# Create .npmrc in project root
cat > .npmrc <<EOF
@ce-dot-net:registry=https://npm.pkg.github.com
EOF

# For private packages, also set:
export GITHUB_TOKEN=ghp_xxxxx

# Install
npm install @ce-dot-net/ace-client
```

**In Claude Code plugin.json**:
- No changes needed!
- `npx @ce-dot-net/ace-client` respects .npmrc automatically

---

### From npm (Public Registry)

**No configuration needed!**

```bash
# Just install
npm install @ce-dot-net/ace-client

# Or use directly
npx @ce-dot-net/ace-client
```

**In Claude Code plugin.json**:
- Works out of the box!
- No .npmrc required

---

## 🗑️ Delete Package

### GitHub Packages (Easy!)

```bash
# Delete entire package
gh api -X DELETE /user/packages/npm/ace-client

# Or via web UI:
# https://github.com/ce-dot-net?tab=packages
# → Click package → Settings → Delete
```

**Can do this ANYTIME!** No restrictions!

---

### npm (Very Limited!)

```bash
# Only within 72 hours:
npm unpublish @ce-dot-net/ace-client@3.0.0 --force

# After 72 hours:
# ❌ Cannot unpublish
# ✅ Can only deprecate:
npm deprecate @ce-dot-net/ace-client@3.0.0 "Use 3.0.1 instead"
```

**Version number is burned forever after unpublish!**

---

## 💡 Best Practices

### For Testing Phase (Now)

✅ **DO**: Use GitHub Packages
✅ **DO**: Test with a few users first
✅ **DO**: Be ready to delete and fix
✅ **DO**: Keep version flexible

❌ **DON'T**: Publish to npm yet
❌ **DON'T**: Rush to production
❌ **DON'T**: Skip testing phase

---

### For Production Phase (Later)

✅ **DO**: Consider npm for wider reach
✅ **DO**: Keep both registries in sync
✅ **DO**: Document installation for both
✅ **DO**: Have rollback plan

❌ **DON'T**: Delete from npm after 72h
❌ **DON'T**: Ignore deprecation notices
❌ **DON'T**: Forget to test both sources

---

## 🎯 Recommendation for You

**Start with GitHub Packages ONLY**

```bash
# Week 1-2: GitHub Packages only
npm run publish:github

# Can delete anytime if needed!
gh api -X DELETE /user/packages/npm/ace-client

# After 2 weeks of stability: Add npm
npm run publish:npm

# Now users can choose, and you have full control!
```

**Why this strategy?**

1. **Safety**: Can delete from GitHub anytime
2. **Testing**: Early users help catch issues
3. **Flexibility**: Can fix without version burn
4. **Control**: Full package lifecycle control
5. **Future**: Can add npm when stable

---

## 📊 Cost Comparison

### npm

- **Public packages**: Free
- **Private packages**: $7/month (first package)
- **Teams**: $7/user/month
- **No delete after 72h**: Priceless 😅

### GitHub Packages

- **Public packages**: Free
- **Private packages**: Free (with GitHub account)
- **Storage**: 500MB free, $0.25/GB after
- **Bandwidth**: 1GB free, $0.50/GB after
- **Can delete anytime**: Priceless! 😎

**For this package (38 KB)**: Both are **FREE**!

---

## 🚀 Quick Start

```bash
cd mcp-clients/ce-ai-ace-client

# GitHub Packages (recommended first)
export GITHUB_TOKEN=ghp_xxxxx
npm run publish:github

# npm (after testing)
npm login
npm run publish:npm

# Users install from either:
# GitHub: (with .npmrc configured)
npm install @ce-dot-net/ace-client

# npm: (no config needed)
npm install @ce-dot-net/ace-client
```

---

## 🎉 Final Verdict

**Use GitHub Packages first!**

You get:
- ✅ Full control (delete anytime)
- ✅ Free private packages
- ✅ Excellent CI/CD
- ✅ Easy testing phase
- ✅ Can add npm later

**Later add npm if you want**:
- ✅ Wider discovery
- ✅ Easier for users
- ✅ Better ecosystem
- ✅ Both registries available

**Best of both worlds!** 🌍
