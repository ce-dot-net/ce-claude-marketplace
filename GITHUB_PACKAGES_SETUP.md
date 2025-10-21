# GitHub Packages Setup - Alternative to npm

**Why GitHub Packages?**
- ✅ Can DELETE packages anytime (no restrictions!)
- ✅ Full control over your package lifecycle
- ✅ Private or public packages
- ✅ Integrated with GitHub authentication
- ✅ Free for public repositories

---

## 🚀 Setup: Publish to GitHub Packages

### Step 1: Update package.json

Add GitHub Package registry configuration:

```json
{
  "name": "@ce-dot-net/ace-client",
  "version": "3.0.0",
  "publishConfig": {
    "registry": "https://npm.pkg.github.com"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/ce-dot-net/ce-claude-marketplace.git"
  }
}
```

### Step 2: Create GitHub Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Name: `npm-publish`
4. Select scopes:
   - ✅ `write:packages` - Upload packages
   - ✅ `read:packages` - Download packages
   - ✅ `delete:packages` - Delete packages
5. Click "Generate token"
6. **Copy the token** (shown only once!)

### Step 3: Configure npm Authentication

```bash
# Create or edit ~/.npmrc
echo "//npm.pkg.github.com/:_authToken=YOUR_GITHUB_TOKEN" >> ~/.npmrc

# Or for this package only:
npm login --registry=https://npm.pkg.github.com
# Username: your-github-username
# Password: your-github-token
# Email: your-email@example.com
```

### Step 4: Publish to GitHub Packages

```bash
cd mcp-clients/ce-ai-ace-client

# Publish
npm publish

# Expected output:
# + @ce-dot-net/ace-client@3.0.0
# Published to GitHub Packages!
```

---

## 📥 Installation from GitHub Packages

### For Users: Configure .npmrc

Users need to tell npm to use GitHub Packages for @ce-dot-net packages:

**Option 1: Project-level** (Recommended)

Create `.npmrc` in project root:

```
@ce-dot-net:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

**Option 2: User-level**

```bash
npm config set @ce-dot-net:registry https://npm.pkg.github.com
npm config set //npm.pkg.github.com/:_authToken YOUR_GITHUB_TOKEN
```

### Install the Package

```bash
# Now npm will use GitHub Packages for @ce-dot-net packages
npm install @ce-dot-net/ace-client

# Or with npx
npx @ce-dot-net/ace-client
```

---

## 🔧 Plugin Configuration for GitHub Packages

### Update plugin.template.json

**No changes needed!** npx works the same way:

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": ["@ce-dot-net/ace-client"],
      "env": {
        "ACE_SERVER_URL": "${env:ACE_SERVER_URL}",
        "ACE_API_TOKEN": "${env:ACE_API_TOKEN}",
        "ACE_PROJECT_ID": "${env:ACE_PROJECT_ID}"
      }
    }
  }
}
```

npx will automatically use the registry configured in `.npmrc`!

---

## 🗑️ DELETE Package (GitHub Packages Advantage!)

### Delete Entire Package

```bash
# Via GitHub CLI
gh api -X DELETE /user/packages/npm/ace-client

# Or via web UI:
# 1. Go to: https://github.com/ce-dot-net?tab=packages
# 2. Click on package
# 3. Click "Package settings"
# 4. Scroll down → "Delete this package"
```

### Delete Specific Version

```bash
# Via GitHub CLI
gh api -X DELETE /user/packages/npm/ace-client/versions/VERSION_ID

# Or via web UI:
# 1. Go to package page
# 2. Click on version
# 3. Click "Delete"
```

**This is the BIG advantage over npm!** No 72-hour restriction!

---

## 📊 Comparison: npm vs GitHub Packages

| Feature | npm (public) | GitHub Packages |
|---------|--------------|-----------------|
| **Delete after 72h** | ❌ No (only deprecate) | ✅ Yes (anytime) |
| **Delete specific version** | ❌ No | ✅ Yes |
| **Unpublish restrictions** | ❌ Many | ✅ None |
| **Authentication** | npm account | GitHub token |
| **Cost** | Free (public) | Free (public repos) |
| **Discovery** | npmjs.com | github.com/packages |
| **CI/CD Integration** | Good | Excellent (GitHub Actions) |
| **Private packages** | $7/month | Free (with GitHub) |

---

## 🎯 Recommended Approach: Use Both!

### Publish to BOTH npm AND GitHub Packages

**Why?**
- npm: Better discovery, more users
- GitHub Packages: Full control, can delete

**How?**

#### 1. Publish to GitHub Packages First (Testing)

```bash
cd mcp-clients/ce-ai-ace-client

# Configure for GitHub Packages
cat > .npmrc <<EOF
registry=https://npm.pkg.github.com
EOF

# Publish
npm publish

# Test with users
# If something goes wrong → DELETE and fix!
```

#### 2. Once Stable, Publish to npm

```bash
# Remove GitHub-specific config
rm .npmrc

# Publish to npm
npm publish --access public

# Now it's on both!
```

---

## 🔐 User Authentication Options

### Option 1: Public Package (No Auth Required)

Make package public on GitHub:

1. Go to package settings
2. Change visibility to "Public"
3. Users can install without token!

```bash
# No authentication needed for public packages
npm install @ce-dot-net/ace-client
```

### Option 2: Private Package (Auth Required)

Users need GitHub token:

```bash
# Users set their token
export GITHUB_TOKEN=ghp_xxxxx

# Install
npm install @ce-dot-net/ace-client
```

---

## 🚀 Complete Workflow

### 1. Initial Setup (One-time)

```bash
cd mcp-clients/ce-ai-ace-client

# Add publishConfig to package.json
npm pkg set publishConfig.registry=https://npm.pkg.github.com

# Login to GitHub Packages
npm login --registry=https://npm.pkg.github.com
```

### 2. Publish to GitHub Packages

```bash
# Build and test
npm run build
npm test

# Publish
npm publish

# Verify
# Go to: https://github.com/ce-dot-net?tab=packages
```

### 3. Update Plugin Documentation

Add to CONFIGURATION.md:

```markdown
## Using GitHub Packages

Create `.npmrc` in your project:

\`\`\`
@ce-dot-net:registry=https://npm.pkg.github.com
\`\`\`

For private packages, add your GitHub token:

\`\`\`bash
export GITHUB_TOKEN=ghp_xxxxx
\`\`\`

Then install normally:

\`\`\`bash
npm install @ce-dot-net/ace-client
\`\`\`
```

### 4. Users Install

```bash
# User creates .npmrc
echo "@ce-dot-net:registry=https://npm.pkg.github.com" > .npmrc

# Install plugin
cd plugins/ace-orchestration
cp plugin.template.json plugin.json

# Use it
# Claude Code will use npx which respects .npmrc
```

---

## 🔄 Migration Strategy

### Phase 1: GitHub Packages Only (Now - Week 1)

- ✅ Full control
- ✅ Can delete/fix anytime
- ✅ Test with early users
- ✅ Gather feedback

### Phase 2: Dual Publishing (Week 2+)

- ✅ Stable version confirmed
- ✅ Publish to npm for wider reach
- ✅ Keep GitHub Packages as backup
- ✅ Users can choose

### Phase 3: npm Primary (Month 1+)

- ✅ Most users use npm
- ✅ GitHub Packages for testing new versions
- ✅ Both stay in sync

---

## 📝 User Installation Guide (GitHub Packages)

Create this in your README:

```markdown
## Installation from GitHub Packages

### 1. Configure npm registry

Create `.npmrc` in your project root:

\`\`\`
@ce-dot-net:registry=https://npm.pkg.github.com
\`\`\`

### 2. Set GitHub token (if private package)

\`\`\`bash
export GITHUB_TOKEN=ghp_YOUR_TOKEN_HERE
\`\`\`

### 3. Install

\`\`\`bash
npm install @ce-dot-net/ace-client
\`\`\`

Or use directly:

\`\`\`bash
npx @ce-dot-net/ace-client
\`\`\`
```

---

## ✅ Benefits Summary

### What You Get with GitHub Packages

1. **Full Control**: Delete anytime, no restrictions
2. **Better CI/CD**: Integrated with GitHub Actions
3. **Private packages**: Free with GitHub
4. **Version management**: Easy to manage all versions
5. **Access control**: GitHub teams and permissions
6. **Backup strategy**: Use both npm and GitHub

### What You Avoid

1. ❌ npm's 72-hour unpublish limit
2. ❌ Permanent version numbers
3. ❌ Can't delete after mistakes
4. ❌ Less control over package lifecycle

---

## 🎯 My Recommendation

**Start with GitHub Packages!**

```bash
# 1. Publish to GitHub Packages first
npm publish  # (with GitHub registry configured)

# 2. Test with a few users for 1 week

# 3. Once stable, ALSO publish to npm
npm publish --registry=https://registry.npmjs.org

# 4. Now users can choose:
#    - GitHub Packages (more control for you)
#    - npm (easier for users)
```

This gives you:
- ✅ Safety net (can delete from GitHub Packages)
- ✅ Wider reach (also on npm)
- ✅ Best of both worlds!

---

## 🚀 Quick Start Commands

```bash
# Setup GitHub Packages
cd mcp-clients/ce-ai-ace-client
npm pkg set publishConfig.registry=https://npm.pkg.github.com
npm login --registry=https://npm.pkg.github.com

# Publish
npm publish

# If you need to delete:
gh api -X DELETE /user/packages/npm/ace-client

# Re-publish fixed version:
npm publish
```

**No more stress about the 72-hour limit!** 🎉
