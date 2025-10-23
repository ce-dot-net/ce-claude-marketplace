# Pre-Publish Checklist - v3.0.0

**Before publishing to npm and creating GitHub release**

---

## ✅ Code & Build

### MCP Client

- [ ] All files synced to latest version
  ```bash
  cd mcp-clients/ce-ai-ace-client
  grep '"version"' package.json  # Should show 3.0.0
  ```

- [ ] Clean build successful
  ```bash
  rm -rf dist/ node_modules/ .ace-cache/
  npm install
  npm run build
  ls dist/  # Verify index.js exists
  ```

- [ ] All tests passing
  ```bash
  # Ensure server is running on localhost:9000
  npm test
  # Expected: 10/10 tests passing
  ```

- [ ] Package contents verified
  ```bash
  npm pack --dry-run
  # Should include: dist/**, README.md, LICENSE
  # Should exclude: src/, tests/, *.ts
  ```

### Plugin

- [ ] plugin.template.json uses npx
  ```bash
  cd plugins/ace-orchestration
  grep '"command"' plugin.template.json  # Should show "npx"
  grep '"args"' plugin.template.json     # Should show "@ce-dot-net/ace-client"
  ```

- [ ] plugin.local.json for local development
  ```bash
  grep '"command"' plugin.local.json     # Should show "node"
  grep '"args"' plugin.local.json        # Should show local path
  ```

- [ ] plugin.json is in .gitignore
  ```bash
  cd ../..
  grep 'plugin.json' .gitignore  # Should be ignored
  ```

---

## ✅ Versions Synced

All version numbers must be **3.0.0**:

- [ ] `mcp-clients/ce-ai-ace-client/package.json`
  ```bash
  grep '"version"' mcp-clients/ce-ai-ace-client/package.json
  # Expected: "version": "3.0.0"
  ```

- [ ] `plugins/ace-orchestration/plugin.template.json`
  ```bash
  grep '"version"' plugins/ace-orchestration/plugin.template.json
  # Expected: "version": "3.0.0"
  ```

- [ ] `plugins/ace-orchestration/plugin.local.json`
  ```bash
  grep '"version"' plugins/ace-orchestration/plugin.local.json
  # Expected: "version": "3.0.0"
  ```

- [ ] `CHANGELOG.md`
  ```bash
  grep '\[3.0.0\]' CHANGELOG.md
  # Expected: ## [3.0.0] - 2025-01-21
  ```

---

## ✅ Documentation

- [ ] CHANGELOG.md updated with v3.0.0
  ```bash
  head -n 200 CHANGELOG.md | grep "3.0.0"
  ```

- [ ] README.md accurate
  - Installation instructions
  - All links working
  - Version references updated

- [ ] PUBLISHING.md reviewed
  - Publication steps clear
  - npm login instructions
  - Post-publish tasks listed

- [ ] CONFIGURATION.md complete
  - Environment variable setup
  - Security warnings
  - Troubleshooting guide

- [ ] SECURITY.md reviewed
  - No credentials exposed
  - Token management documented
  - Incident response plan

---

## ✅ Security

- [ ] No hardcoded credentials
  ```bash
  grep -r "ace_wFIuXzQ" plugins/ace-orchestration/*.json 2>/dev/null
  # Expected: Only in plugin.local.json or no matches
  ```

- [ ] plugin.json not in git
  ```bash
  git status | grep "plugin.json"
  # Expected: No plugin.json in tracked files
  ```

- [ ] .gitignore includes sensitive files
  ```bash
  cat .gitignore | grep -E "(plugin.json|\.env)"
  # Expected: Both patterns present
  ```

- [ ] plugin.template.json uses ${env:*}
  ```bash
  grep '${env:' plugins/ace-orchestration/plugin.template.json
  # Expected: 3 matches (URL, TOKEN, PROJECT_ID)
  ```

---

## ✅ Git

- [ ] All changes committed
  ```bash
  git status
  # Expected: Working tree clean
  ```

- [ ] On correct branch
  ```bash
  git branch --show-current
  # Expected: main or release-3.0.0
  ```

- [ ] Remote is correct
  ```bash
  git remote -v
  # Expected: ce-dot-net/ce-claude-marketplace
  ```

- [ ] Ready to tag
  ```bash
  git log --oneline -5
  # Verify recent commits look correct
  ```

---

## ✅ NPM Preparation

- [ ] Logged in to npm
  ```bash
  npm whoami
  # Expected: Your npm username
  ```

- [ ] Organization access (if using @ce-dot-net scope)
  ```bash
  npm org ls @ce-dot-net
  # Verify you have publish permissions
  ```

- [ ] .npmignore configured
  ```bash
  cat mcp-clients/ce-ai-ace-client/.npmignore
  # Should exclude src/, tests/, *.ts
  ```

- [ ] package.json publishConfig
  ```bash
  grep 'publishConfig' mcp-clients/ce-ai-ace-client/package.json
  # Expected: "access": "public"
  ```

---

## ✅ Testing End-to-End

### Local Build Test

- [ ] Local build works
  ```bash
  cd mcp-clients/ce-ai-ace-client
  cp ../../../plugins/ace-orchestration/plugin.local.json \
     ../../../plugins/ace-orchestration/plugin.json
  # Restart Claude Code
  # /ace-status should work
  ```

### Package Test (Dry Run)

- [ ] npm pack succeeds
  ```bash
  cd mcp-clients/ce-ai-ace-client
  npm pack
  # Creates ce-dot-net-ace-client-3.0.0.tgz
  ```

- [ ] Tarball contents correct
  ```bash
  tar -tzf ce-dot-net-ace-client-3.0.0.tgz
  # Verify: package/dist/, package/README.md, package/LICENSE
  ```

- [ ] Test installation from tarball
  ```bash
  cd /tmp
  npm install /path/to/ce-dot-net-ace-client-3.0.0.tgz
  npx @ce-dot-net/ace-client --help
  # Should start MCP server
  ```

- [ ] Clean up
  ```bash
  rm /path/to/ce-dot-net-ace-client-3.0.0.tgz
  ```

---

## ✅ Server Verification

- [ ] ACE server running
  ```bash
  curl http://localhost:9000/health
  # Expected: {"status":"healthy"}
  ```

- [ ] Server has patterns
  ```bash
  curl http://localhost:9000/playbook \
    -H "Authorization: Bearer ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU" \
    -H "X-ACE-Project: prj_5bc0b560221052c1" | jq .total_bullets
  # Expected: 37
  ```

---

## 📝 Publication Steps (After All Checks Pass)

### 1. Publish to npm

```bash
cd mcp-clients/ce-ai-ace-client

# Final test
npm run prepublishOnly

# Publish (do dry run first!)
npm publish --dry-run

# If dry run looks good:
npm publish --access public

# Verify publication
npm view @ce-dot-net/ace-client
```

### 2. Create Git Tag

```bash
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace

# Tag release
git tag -a v3.0.0 -m "Release v3.0.0 - TypeScript MCP Client Production Ready"

# Push tag
git push origin v3.0.0

# Push main branch (if needed)
git push origin main
```

### 3. Create GitHub Release

Go to: https://github.com/ce-dot-net/ce-claude-marketplace/releases/new

- **Tag**: v3.0.0
- **Title**: Release v3.0.0 - TypeScript MCP Client Production Ready
- **Description**: Copy from CHANGELOG.md section for v3.0.0
- **Attach**: Link to npm package

### 4. Update Plugin for Published Package

```bash
cd plugins/ace-orchestration

# Copy template to create plugin.json
cp plugin.template.json plugin.json

# Verify it uses npx
grep '"command"' plugin.json  # Should show "npx"
grep '"args"' plugin.json     # Should show "@ce-dot-net/ace-client"

# Test installation
# (Restart Claude Code and run /ace-status)
```

### 5. Test End-to-End Installation

```bash
# 1. Fresh directory
cd /tmp
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git test-install
cd test-install

# 2. Set environment variables
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"

# 3. Copy template
cd plugins/ace-orchestration
cp plugin.template.json plugin.json

# 4. Install plugin
ln -sf "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration

# 5. Restart Claude Code

# 6. Test
# /ace-status should work and download @ce-dot-net/ace-client from npm

# 7. Clean up
cd ~
rm -rf /tmp/test-install
```

---

## 🚨 Rollback Plan

If something goes wrong after publishing:

### npm Package Issue

```bash
# Deprecate the version
npm deprecate @ce-dot-net/ace-client@3.0.0 "Critical bug - use 3.0.1 instead"

# Fix the issue
# ... make changes ...

# Publish patch version
npm version patch  # Bumps to 3.0.1
npm publish

# Update documentation
```

### Git Tag Issue

```bash
# Delete local tag
git tag -d v3.0.0

# Delete remote tag (CAREFUL!)
git push origin :refs/tags/v3.0.0

# Fix issue and re-tag
git tag -a v3.0.0 -m "Fixed release v3.0.0"
git push origin v3.0.0
```

---

## ✅ Final Checklist Before Publishing

I confirm that:

- [ ] All code is tested and working
- [ ] All versions are synced to 3.0.0
- [ ] CHANGELOG.md is complete and accurate
- [ ] No credentials are hardcoded anywhere
- [ ] .gitignore prevents credential commits
- [ ] Documentation is complete and accurate
- [ ] I have tested the package locally
- [ ] I have npm publish permissions
- [ ] Server is running and accessible
- [ ] I understand the rollback procedure
- [ ] I'm ready to publish to npm
- [ ] I'm ready to create GitHub release
- [ ] I've backed up any important data

---

**Signature**: _________________ **Date**: _________________

**Once published, there's no going back for 72 hours! Make sure everything is perfect.**
