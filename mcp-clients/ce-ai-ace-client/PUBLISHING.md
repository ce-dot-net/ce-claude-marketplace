# Publishing Guide - @ce-dot-net/ace-client

**Version**: 3.0.0
**Package**: https://www.npmjs.com/package/@ce-dot-net/ace-client

---

## Pre-publish Checklist

### 1. Version Check ✅

Ensure all versions are synced:

```bash
# package.json
"version": "3.0.0"

# plugin.json
"version": "3.0.0"

# CHANGELOG.md
## [3.0.0] - 2025-01-21
```

### 2. Build & Test ✅

```bash
cd mcp-clients/ce-ai-ace-client

# Clean build
rm -rf dist/ node_modules/
npm install
npm run build

# Run all tests
npm test

# Verify dist/ contains:
ls dist/
# Expected: index.js, types/, services/, tests/
```

### 3. Package Verification ✅

```bash
# Preview what will be published
npm pack --dry-run

# Check package size
npm pack
tar -tzf ce-dot-net-ace-client-3.0.0.tgz

# Expected files:
# - package/dist/**/*.js
# - package/README.md
# - package/LICENSE
# - package/package.json

# Clean up
rm *.tgz
```

### 4. Documentation ✅

- [ ] README.md is up to date
- [ ] CHANGELOG.md includes v3.0.0
- [ ] All links work
- [ ] Installation instructions tested

---

## Publishing to npm

### First Time Setup

```bash
# Login to npm (if not already)
npm login

# Verify account
npm whoami
```

### Publish Package

```bash
cd mcp-clients/ce-ai-ace-client

# Final check
npm run prepublishOnly

# Publish (dry run first)
npm publish --dry-run

# Actually publish
npm publish --access public

# Expected output:
# + @ce-dot-net/ace-client@3.0.0
```

### Verify Publication

```bash
# Check npm registry
npm view @ce-dot-net/ace-client

# Test installation
cd /tmp
npm install @ce-dot-net/ace-client
npx ace-client --help  # Should show MCP server starting
```

---

## Post-publish Tasks

### 1. Create Git Tag

```bash
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace

# Tag the release
git tag -a v3.0.0 -m "Release v3.0.0 - TypeScript MCP Client with 3-tier cache"

# Push tag
git push origin v3.0.0
```

### 2. Update Plugin Configuration

**For Published Package** (plugins/ace-orchestration/plugin.json):

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

**For Local Development** (plugins/ace-orchestration/plugin.local.json):

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/../../mcp-clients/ce-ai-ace-client/dist/index.js"],
      "env": {
        "ACE_SERVER_URL": "${env:ACE_SERVER_URL}",
        "ACE_API_TOKEN": "${env:ACE_API_TOKEN}",
        "ACE_PROJECT_ID": "${env:ACE_PROJECT_ID}"
      }
    }
  }
}
```

### 3. Test End-to-End Installation

```bash
# 1. Install plugin from template
cp plugins/ace-orchestration/plugin.template.json plugins/ace-orchestration/plugin.json

# 2. Set environment variables
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"

# 3. Update plugin.json to use npx
# Edit to use: "command": "npx", "args": ["@ce-dot-net/ace-client"]

# 4. Install plugin in Claude Code
ln -sf "$(pwd)/plugins/ace-orchestration" ~/.config/claude-code/plugins/ace-orchestration

# 5. Restart Claude Code

# 6. Test in Claude Code
/ace-status
```

### 4. Create GitHub Release

```bash
# Go to: https://github.com/ce-dot-net/ce-claude-marketplace/releases/new

Tag: v3.0.0
Title: Release v3.0.0 - TypeScript MCP Client Production Ready
Body:
```

**Release v3.0.0 - TypeScript MCP Client Production Ready**

## 🎉 What's New

### Complete TypeScript Refactor
- Full TypeScript implementation (no Python dependency)
- 3-tier cache architecture (RAM → SQLite → Server)
- 50-200x performance improvement on cache hits
- 10/10 integration tests passing

### Features
- **5 MCP Tools**: ace_init, ace_reflect, ace_get_playbook, ace_status, ace_clear
- **Offline Pattern Discovery**: Learn from git history and files
- **Online Learning**: Evolve from execution feedback
- **Local Caching**: SQLite cache survives restarts
- **Multi-tenant**: Project isolation support

### Pattern Database
- 37 real patterns discovered from codebase
- 2 strategies, 28 code snippets, 7 APIs
- Ready for helpful/harmful tracking
- Authentic foundation for learning

## 📦 Installation

```bash
npm install @ce-dot-net/ace-client
# or
npx @ce-dot-net/ace-client
```

## 🔗 Links
- [npm package](https://www.npmjs.com/package/@ce-dot-net/ace-client)
- [Documentation](https://github.com/ce-dot-net/ce-claude-marketplace/tree/main/mcp-clients/ce-ai-ace-client)
- [Plugin Installation](https://github.com/ce-dot-net/ce-claude-marketplace/tree/main/plugins/ace-orchestration)

**Full Changelog**: https://github.com/ce-dot-net/ce-claude-marketplace/blob/main/CHANGELOG.md

---

## Versioning Strategy

### Semantic Versioning (SemVer)

- **Major (3.x.x)**: Breaking changes (TypeScript refactor)
- **Minor (x.1.x)**: New features (new MCP tools)
- **Patch (x.x.1)**: Bug fixes (cache issues, endpoint fixes)

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0.0 | 2025-01-21 | TypeScript refactor, 3-tier cache, 10/10 tests |
| 0.2.0 | 2025-01-20 | Python FastMCP (deprecated) |
| 0.1.0 | 2025-01-19 | Initial release (deprecated) |

---

## Troubleshooting Publication

### "Package already exists"

```bash
# Version already published
# Increment version in package.json and try again
npm version patch  # or minor, or major
npm publish
```

### "Authentication failed"

```bash
# Re-login to npm
npm logout
npm login
npm whoami  # Verify
```

### "Permission denied"

```bash
# Check organization membership
npm org ls @ce-dot-net

# Verify publishConfig
# In package.json:
"publishConfig": {
  "access": "public"
}
```

### "Build failed"

```bash
# Clean rebuild
rm -rf dist/ node_modules/
npm install
npm run build
npm test
```

### "Tests failed"

```bash
# Ensure server is running
curl http://localhost:9000/health

# Set environment variables
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"

# Run tests
npm test
```

---

## Rollback

If there's an issue with the published package:

```bash
# Deprecate the version
npm deprecate @ce-dot-net/ace-client@3.0.0 "Critical bug - use 3.0.1 instead"

# Publish fixed version
npm version patch
npm publish
```

**Note**: You cannot unpublish a version after 72 hours!

---

## Distribution Channels

### 1. npm Registry (Primary)
```bash
npm install @ce-dot-net/ace-client
```

### 2. npx (Recommended for Plugin)
```bash
npx @ce-dot-net/ace-client
```

### 3. GitHub Repository
```bash
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd mcp-clients/ce-ai-ace-client
npm install && npm run build
```

---

## Next Release

For v3.1.0:

- [ ] Monitor pattern evolution
- [ ] Gather user feedback
- [ ] Optimize performance based on usage
- [ ] Add new MCP tools if needed
- [ ] Improve error messages

---

**Remember**: Always test locally before publishing!
