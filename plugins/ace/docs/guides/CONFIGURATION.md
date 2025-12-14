# ACE Plugin Configuration Guide

**Version**: v5.1.19
**Architecture**: Hooks + ce-ace CLI (no MCP server)

---

## 🎯 Overview

The ACE plugin uses **two configuration files**:

1. **`~/.config/ace/config.json`** - Global ce-ace CLI configuration (server URL, API token, org ID)
2. **`.claude/settings.json`** - Per-project configuration (project ID)

**No MCP configuration needed!** The plugin uses hooks + subprocess calls to `ce-ace`, not MCP tools.

---

## 🚀 Quick Configuration

### Interactive Wizard (Recommended)

Run the configuration wizard in Claude Code:

```bash
/ace:ace-configure
```

**What it does:**

1. Prompts for ACE server URL (or uses default)
2. Requests your API token
3. Auto-fetches your organization ID from server
4. Lists available projects for selection
5. Creates `~/.config/ace/config.json` (global)
6. Creates `.claude/settings.json` (project-specific)

**Done in 60 seconds!**

---

## 📝 Manual Configuration

If you prefer manual setup or need to troubleshoot:

### Step 1: Global Configuration

Create `~/.config/ace/config.json`:

```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_your_token_here",
  "orgId": "org_your_org_id_here"
}
```

**Fields:**

- `serverUrl` - Your ACE server endpoint (default: <https://ace-api.code-engine.app>)
- `apiToken` - Your personal API token (get from ACE server dashboard)
- `orgId` - Your organization ID (fetch via `/organizations` API endpoint)

**Permissions:**

```bash
chmod 600 ~/.config/ace/config.json  # Protect token
```

### Step 2: Project Configuration

Create `.claude/settings.json` in your project root:

```json
{
  "orgId": "org_your_org_id_here",
  "projectId": "prj_your_project_id_here"
}
```

**Alternative format** (environment variables):

```json
{
  "env": {
    "ACE_ORG_ID": "org_xxxxx",
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

Both formats work! The plugin supports either.

**Fields:**

- `orgId` - Same as global config (for context resolution)
- `projectId` - Specific project ID for this codebase

---

## 🔐 Security Best Practices

### Protect Your API Token

**Never commit** `.config/ace/config.json` or tokens to version control!

```bash
# Add to .gitignore
echo ".claude/settings.json" >> .gitignore
echo "~/.config/ace/config.json" >> .gitignore
```

**File permissions:**

```bash
chmod 600 ~/.config/ace/config.json       # User read/write only
chmod 644 .claude/settings.json           # Can be shared (no secrets)
```

### Environment Variables (Optional)

For CI/CD or shared environments, use environment variables:

```bash
# Add to ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_your_token_here"
export ACE_ORG_ID="org_xxxxx"
export ACE_PROJECT_ID="prj_xxxxx"
```

Then use env format in `.claude/settings.json`:

```json
{
  "env": {
    "ACE_ORG_ID": "org_xxxxx",
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

---

## 🔄 Configuration Hierarchy

The ce-ace CLI uses this priority order:

1. **Environment variables** (highest priority)
   - `ACE_SERVER_URL`
   - `ACE_API_TOKEN`
   - `ACE_ORG_ID`
   - `ACE_PROJECT_ID`
   - `ACE_ASYNC_LEARNING` - Set to `0` to disable async learning (default: `1`)

2. **Global config** (`~/.config/ace/config.json`)
   - `serverUrl`
   - `apiToken`
   - `orgId`

3. **Project config** (`.claude/settings.json`)
   - `projectId` (required per-project)
   - `orgId` (fallback if not in global)

---

## 🧪 Verify Configuration

### Check Global Config

```bash
cat ~/.config/ace/config.json
```

**Expected output:**

```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_abcd1234...",
  "orgId": "org_xyz789..."
}
```

### Check Project Config

```bash
cat .claude/settings.json
```

**Expected output:**

```json
{
  "orgId": "org_xyz789...",
  "projectId": "prj_abc123..."
}
```

### Test Connection

```bash
# In Claude Code:
/ace:ace-status
```

**Expected output:**

```
✅ Connected to ACE server
Organization: org_xyz789
Project: prj_abc123
Patterns: 42 total
- strategies_and_hard_rules: 15
- useful_code_snippets: 12
- troubleshooting_and_pitfalls: 8
- apis_to_use: 7
```

---

## 🛠️ Troubleshooting

### "ACE authentication failed"

**Problem**: Invalid or expired token.

**Solution:**

```bash
# Get new token from ACE server dashboard
# Update config
/ace:ace-configure

# Or manually edit
vim ~/.config/ace/config.json
```

### "Organization not found"

**Problem**: Invalid `orgId` or no access to organization.

**Solution:**

```bash
# Verify org ID from server
curl -H "Authorization: Bearer ace_your_token" \
  https://ace-api.code-engine.app/organizations

# Update config with correct orgId
/ace:ace-configure
```

### "Project not found"

**Problem**: Invalid `projectId` or project doesn't exist.

**Solution:**

```bash
# List available projects
curl -H "Authorization: Bearer ace_your_token" \
  https://ace-api.code-engine.app/organizations/org_xxx/projects

# Update .claude/settings.json with correct projectId
/ace:ace-configure
```

### "No .claude/settings.json"

**Problem**: Project not configured yet.

**Solution:**

```bash
# Run wizard to create settings.json
/ace:ace-configure
```

### Hooks receive wrong org/project

**Problem**: Configuration file not in expected location.

**Solution:**

```bash
# Check file locations
ls -la ~/.config/ace/config.json
ls -la .claude/settings.json

# Verify you're in correct project directory
pwd

# Re-run configuration
/ace:ace-configure
```

---

## 📂 Configuration File Locations

### Default Locations

**Global config:**

- macOS/Linux: `~/.config/ace/config.json`
- Windows: `%USERPROFILE%\.config\ace\config.json`

**Project config:**

- All platforms: `<project-root>/.claude/settings.json`

### Custom Locations (Advanced)

Override via environment variables:

```bash
export ACE_CONFIG_PATH="/custom/path/to/config.json"
export ACE_SETTINGS_PATH="/custom/path/to/settings.json"
```

---

## 🔄 Multi-Project Setup

Working with multiple projects? Each gets its own `.claude/settings.json`:

```bash
# Project 1
cd ~/projects/website
cat .claude/settings.json
# {"orgId": "org_xyz", "projectId": "prj_website"}

# Project 2
cd ~/projects/api
cat .claude/settings.json
# {"orgId": "org_xyz", "projectId": "prj_api"}

# Project 3 (different org)
cd ~/projects/client-work
cat .claude/settings.json
# {"orgId": "org_client", "projectId": "prj_client_app"}
```

**Global config** stays the same (your personal token), but each project gets its own playbook via `projectId`.

---

## 🔧 Advanced Configuration

### Custom Server URL

Using a self-hosted ACE server?

```json
{
  "serverUrl": "https://ace.your-company.com",
  "apiToken": "ace_your_token",
  "orgId": "org_your_org"
}
```

### Timeout Settings

Hooks have built-in timeouts. To adjust:

Edit `plugins/ace/hooks/hooks.json`:

```json
{
  "UserPromptSubmit": [{
    "hooks": [{
      "timeout": 15000  // 15 seconds (default)
    }]
  }]
}
```

**Recommended timeouts:**

- SessionStart: 30000ms (CLI check)
- UserPromptSubmit: 15000ms (pattern retrieval)
- PostToolUse: 10000ms (learning detection)
- Stop: 30000ms (session learning)

---

## 📚 Next Steps

After configuration:

1. **Bootstrap playbook**:

   ```bash
   /ace:ace-bootstrap
   ```

2. **Test pattern retrieval**:

   ```bash
   /ace:ace-search authentication
   ```

3. **Start coding** - Hooks auto-trigger on implementation keywords!

---

## 🔗 Related Documentation

- **Installation Guide**: See `INSTALL.md`
- **Troubleshooting Guide**: See `TROUBLESHOOTING.md`
- **ACE Server API**: <https://github.com/ce-dot-net/ce-ace-server/blob/main/docs/API.md>
- **CE-ACE CLI Docs**: <https://github.com/ce-dot-net/ce-ace-cli>

---

**Questions?** File an issue on the [marketplace repository](https://github.com/ce-dot-net/ce-claude-marketplace/issues).
