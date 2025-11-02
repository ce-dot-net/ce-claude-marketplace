# ACE MCP Setup Guide for Claude Code CLI

Complete guide for setting up the ACE MCP server for Claude Code CLI with per-project `projectID` and global API credentials.

## 🎯 Goal

Each project uses its own `projectID`, while the ACE API credentials (server URL + token) remain shared globally (stored in the user's home directory).

This setup ensures:
- One consistent MCP plugin config for all projects
- Project-specific IDs via environment variables
- Secure global storage of sensitive data (URL/token)

---

## 1️⃣ Prerequisites

- Claude Code CLI installed
- Node.js ≥ 18
- `@ce-dot-net/ace-client` available (from npm or your private registry)

**Latest version**: v3.7.2 (requires plugin v3.3.3+)

---

## 2️⃣ Plugin Configuration (global)

The plugin automatically provides `.mcp.json` which registers the MCP server:

**`plugins/ace-orchestration/.mcp.json`**:
```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": [
        "--yes",
        "@ce-dot-net/ace-client@3.7.2",
        "--config",
        "${XDG_CONFIG_HOME:-${HOME}/.config}/ace/config.json",
        "--projectID",
        "${ACE_PROJECT_ID}"
      ]
    }
  }
}
```

### How It Works

Claude Code:
1. Reads `.mcp.json` from plugin directory
2. Expands environment variables (`${ACE_PROJECT_ID}`, `${HOME}`, etc.)
3. Starts MCP server with expanded arguments

**Key Points**:
- `${XDG_CONFIG_HOME:-${HOME}/.config}` - Uses XDG_CONFIG_HOME if set, otherwise `~/.config`
- `${ACE_PROJECT_ID}` - Expanded from `.claude/settings.json` in project root
- Plugin is global, but receives different `projectID` per workspace

---

## 3️⃣ Global Configuration Setup

**Scope**: User-level (shared across ALL projects)

**Location**: `~/.config/ace/config.json` (XDG standard)

### Option A: Interactive Setup (Recommended)

Run the configuration wizard:

```bash
/ace-orchestration:ace-configure --global
```

You'll be prompted for:
- **Server URL**: `https://ace-api.code-engine.app` (default)
- **API Token**: Your organization's token (starts with `ace_`)
- **Cache TTL**: 120 minutes (default)
- **Auto-update**: Enable automatic CLAUDE.md updates

### Option B: Manual Setup

Create `~/.config/ace/config.json`:

```bash
# Create directory
mkdir -p ~/.config/ace

# Create config file
cat > ~/.config/ace/config.json <<'EOF'
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_gJ3XjvJK907TLbkKqrwgG8a1YH8wc3BLI9YAcuc0pso",
  "cacheTtlMinutes": 120,
  "autoUpdateEnabled": true
}
EOF

# Set secure permissions (IMPORTANT!)
chmod 600 ~/.config/ace/config.json
chmod 700 ~/.config/ace
```

### Getting Your API Token

1. Contact your ACE server administrator
2. Or generate via ACE dashboard (if available)
3. Token format: `ace_` followed by base64-encoded string
4. **Keep it secret!** Never commit to git

---

## 4️⃣ Project Configuration Setup

**Scope**: Project-specific (DIFFERENT for each repository)

**Location**: `<project-root>/.claude/settings.json`

### Option A: Interactive Setup (Recommended)

Navigate to your project directory and run:

```bash
cd /path/to/your/project
/ace-orchestration:ace-configure --project
```

You'll be prompted for:
- **Project ID**: Your unique project identifier (e.g., `prj_d3a244129d62c198`)

### Option B: Manual Setup

Create or edit `.claude/settings.json` in project root:

```bash
# Navigate to project
cd /path/to/your/project

# Create .claude directory if needed
mkdir -p .claude

# Add or merge ACE_PROJECT_ID env var
cat > .claude/settings.json <<'EOF'
{
  "env": {
    "ACE_PROJECT_ID": "prj_d3a244129d62c198"
  }
}
EOF
```

**If `.claude/settings.json` already exists**, merge the env var:

```bash
# Read existing settings
EXISTING=$(cat .claude/settings.json)

# Merge ACE_PROJECT_ID using jq
echo "$EXISTING" | jq \
  --arg projectId "prj_d3a244129d62c198" \
  '.env.ACE_PROJECT_ID = $projectId' > .claude/settings.json.tmp

mv .claude/settings.json.tmp .claude/settings.json
```

### Getting Your Project ID

1. Contact your ACE server administrator
2. Or create via ACE dashboard (if available)
3. Format: `prj_` followed by hex string
4. **Unique per project/repository**

### Should I Commit `.claude/settings.json`?

**YES** - Commit this file to git!

**Why?**:
- Contains project-specific configuration (not secrets)
- Shared across team members
- Each developer still uses their own API token (from global config)

**What to ignore**:
- ❌ `~/.config/ace/config.json` - NEVER commit (contains API token)
- ✅ `.claude/settings.json` - COMMIT (contains project ID)

---

## 5️⃣ Verification

### Step 1: Check MCP Server Registration

```bash
# In Claude Code CLI
/ace-orchestration:ace-status
```

**Expected output**:
```
✅ ACE MCP Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MCP Server: ace-pattern-learning ✓ CONNECTED
Project ID: prj_d3a244129d62c198
Server URL: https://ace-api.code-engine.app
Playbook Size: 42 patterns (4 sections)
Cache Status: ACTIVE (TTL: 120 minutes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 2: Test Connection

```bash
# Run comprehensive diagnostic
/ace-orchestration:ace-doctor
```

This checks:
- Plugin installation
- Global configuration
- Project configuration
- MCP client connectivity
- ACE server connectivity
- Skills loaded
- CLAUDE.md status
- Cache status
- Version status

### Step 3: Test Retrieval

```bash
# Retrieve playbook patterns
/ace-orchestration:ace-patterns strategies_and_hard_rules
```

**Expected**: Returns patterns from your project's playbook.

---

## 6️⃣ Architecture Overview

### Configuration Scopes

| Item | Scope | Description | Location |
|------|-------|-------------|----------|
| **serverUrl** | 🌍 Global | ACE backend endpoint | `~/.config/ace/config.json` |
| **apiToken** | 🌍 Global | Personal access token | `~/.config/ace/config.json` |
| **projectID** | 🧩 Project | Unique per repository | `.claude/settings.json` (env var) |

### How Claude Code Resolves Configuration

**When Claude launches a workspace:**

1. **Reads plugin config**: `.mcp.json` from plugin directory
2. **Expands placeholders**:
   - `${ACE_PROJECT_ID}` from `.claude/settings.json` (project scope)
   - `${HOME}`, `${XDG_CONFIG_HOME}` from shell environment
3. **Starts MCP server**: Calls `npx @ce-dot-net/ace-client@3.7.2` with:
   - `--config ~/.config/ace/config.json` (global credentials)
   - `--projectID prj_xxxxx` (project-specific ID)

**MCP Client reads global config:**
1. Loads `~/.config/ace/config.json`
2. Extracts `serverUrl` and `apiToken`
3. Combines with `projectID` from CLI arg
4. Connects to ACE server with full context

### Example: Different Projects

| Project | `.claude/settings.json` | Effective Command |
|---------|------------------------|-------------------|
| `/projects/recrible-preview` | `ACE_PROJECT_ID=recrible-preview` | `ace-client --projectID recrible-preview --config ~/.config/ace/config.json` |
| `/projects/recrible-prod` | `ACE_PROJECT_ID=recrible-prod` | `ace-client --projectID recrible-prod --config ~/.config/ace/config.json` |

**Result**: Same MCP binary, same credentials, different project contexts!

---

## 7️⃣ Usage

### Automatic Learning Cycle

ACE uses two Agent Skills that auto-invoke:

#### Before Tasks: Playbook Retrieval
```
User: "Implement JWT authentication"
↓
ACE Skill: ace-orchestration:ace-playbook-retrieval (AUTO-INVOKES)
↓
Retrieves: Learned patterns from previous sessions
↓
Claude: Implements using organizational knowledge
```

#### After Tasks: Pattern Learning
```
Claude: Completes substantial work
↓
ACE Skill: ace-orchestration:ace-learning (AUTO-INVOKES)
↓
Captures: Task + trajectory + lessons learned
↓
Server: Updates playbook with new patterns
```

**You don't need to do anything!** Skills auto-invoke based on task context.

### Manual Commands

While skills handle automation, manual commands are available:

- `/ace-patterns [section]` - View playbook
- `/ace-status` - Check statistics
- `/ace-configure` - Update configuration
- `/ace-bootstrap` - Bootstrap from codebase
- `/ace-clear` - Clear playbook
- `/ace-doctor` - Run health diagnostic

---

## 8️⃣ Troubleshooting

### Problem: "MCP server not responding"

**Symptoms**:
```
Error: No such tool available: mcp__ace-pattern-learning__ace_status
```

**Causes**:
1. Plugin not installed
2. Global config missing
3. MCP client not installed

**Solutions**:
```bash
# Check plugin installation
ls -la ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/

# Check global config
cat ~/.config/ace/config.json

# Test MCP client manually
npx @ce-dot-net/ace-client@3.7.2 --version

# Restart Claude Code
# Press Cmd+Q (macOS) or Ctrl+Q (Linux), then reopen
```

### Problem: "HTTP 401 Unauthorized"

**Symptoms**:
```
Error: ACE server authentication failed
HTTP Status: 401
```

**Causes**:
- Invalid API token
- Expired token
- Incorrect token format

**Solutions**:
```bash
# Verify token format (starts with ace_)
jq -r '.apiToken' ~/.config/ace/config.json

# Reconfigure
/ace-orchestration:ace-configure --global

# Get new token from ACE admin
```

### Problem: "HTTP 404 Project not found"

**Symptoms**:
```
Error: Project not found
HTTP Status: 404
```

**Causes**:
- Project ID doesn't exist
- No access to project
- Typo in project ID

**Solutions**:
```bash
# Check project ID
jq -r '.env.ACE_PROJECT_ID' .claude/settings.json

# Verify with ACE admin
# Reconfigure project
/ace-orchestration:ace-configure --project
```

### Problem: "Cache always stale"

**Symptoms**:
- Every retrieval hits server (slow)
- No cache benefit

**Causes**:
- Cache directory not writable
- Cache TTL too low
- Cache corruption

**Solutions**:
```bash
# Check cache directory
ls -la ~/.ace-cache/

# Clear and rebuild cache
rm -rf ~/.ace-cache/
/ace-orchestration:ace-patterns

# Adjust TTL
/ace-orchestration:ace-configure --global
# Set Cache TTL to 120 minutes
```

### Problem: "Different project IDs across team"

**Symptoms**:
- Team members see different playbooks
- Patterns not shared

**Causes**:
- `.claude/settings.json` not committed
- Each developer using personal project ID

**Solutions**:
```bash
# Verify .claude/settings.json is committed
git status .claude/settings.json

# Should show:
#   modified:   .claude/settings.json
# OR
#   (nothing to commit - already committed)

# Ensure ALL team members use SAME project ID
# Coordinate with team to agree on project ID

# Check .gitignore doesn't ignore settings
grep -v "^#" .gitignore | grep ".claude/settings.json"
# Should return nothing (file NOT ignored)
```

### Problem: "Skills not auto-invoking"

**Symptoms**:
- Playbook retrieval doesn't happen before tasks
- Learning doesn't happen after tasks

**Causes**:
- Skills not loaded
- Plugin not installed correctly
- CLAUDE.md not initialized

**Solutions**:
```bash
# Initialize CLAUDE.md in project
/ace-orchestration:ace-claude-init

# Restart Claude Code
# Cmd+Q (macOS) or Ctrl+Q (Linux), then reopen

# Run diagnostic
/ace-orchestration:ace-doctor
# Check "Skills Loaded" section
```

---

## 9️⃣ Migration from v3.3.2 and Earlier

### Changes in v3.3.3

**Configuration locations changed:**

| Version | Global Config | Project Config |
|---------|---------------|----------------|
| v3.3.2 and earlier | `~/.ace/config.json` | `.claude/settings.local.json` |
| v3.3.3+ | `~/.config/ace/config.json` | `.claude/settings.json` |

**Why the change?**
- XDG Base Directory Specification (Linux/macOS standard)
- Clearer separation: global vs. project
- `.claude/settings.json` can be committed safely

### Automatic Migration

MCP client v3.7.2 includes automatic migration:

```bash
# First run with v3.7.2 will detect legacy config
# Migrates: ~/.ace/config.json → ~/.config/ace/config.json
# Creates backup: ~/.ace/config.json.bak
```

### Manual Migration

If needed, migrate manually:

```bash
# Step 1: Migrate global config
mkdir -p ~/.config/ace
cp ~/.ace/config.json ~/.config/ace/config.json
chmod 600 ~/.config/ace/config.json
mv ~/.ace/config.json ~/.ace/config.json.bak

# Step 2: Migrate project config (per project)
cd /path/to/project

# Read old config
OLD_PROJECT_ID=$(jq -r '.mcpServers."ace-pattern-learning".args[-1]' .claude/settings.local.json 2>/dev/null)

# If found, migrate
if [ -n "$OLD_PROJECT_ID" ]; then
  # Create or merge into .claude/settings.json
  if [ -f .claude/settings.json ]; then
    # Merge
    jq --arg id "$OLD_PROJECT_ID" '.env.ACE_PROJECT_ID = $id' .claude/settings.json > .claude/settings.json.tmp
    mv .claude/settings.json.tmp .claude/settings.json
  else
    # Create new
    cat > .claude/settings.json <<EOF
{
  "env": {
    "ACE_PROJECT_ID": "$OLD_PROJECT_ID"
  }
}
EOF
  fi

  # Backup old file
  mv .claude/settings.local.json .claude/settings.local.json.bak
fi

# Step 3: Verify migration
/ace-orchestration:ace-doctor
```

### Post-Migration Cleanup

After verifying everything works:

```bash
# Remove old global config backup (optional)
rm ~/.ace/config.json.bak

# Remove old project config backup (per project, optional)
cd /path/to/project
rm .claude/settings.local.json.bak

# Update .gitignore (remove old entries)
# Old entry: .claude/settings.local.json
# New entry: (none - .claude/settings.json should be committed)
```

---

## 🔟 Security Best Practices

### What to Commit

✅ **COMMIT** these files:
- `.claude/settings.json` - Contains project ID (not secrets)
- `.gitignore` - Ensures config files are not committed

❌ **NEVER COMMIT** these files:
- `~/.config/ace/config.json` - Contains API token (secrets!)
- `~/.ace-cache/` - Local cache directory

### File Permissions

Global config must be secure:

```bash
# Check permissions
ls -l ~/.config/ace/config.json
# Should show: -rw------- (600) - readable/writable by owner only

# Fix if needed
chmod 600 ~/.config/ace/config.json
chmod 700 ~/.config/ace
```

### Token Management

- **Rotate tokens regularly** - Change API token every 90 days
- **Revoke compromised tokens** - If leaked, revoke immediately via ACE dashboard
- **Use separate tokens per team** - Don't share personal tokens
- **Audit token usage** - Check ACE server logs periodically

---

## 1️⃣1️⃣ FAQ

### Q: Can I use different API tokens for different projects?

**A**: No. The global config (`~/.config/ace/config.json`) is shared across all projects.

**Why?**: The API token authenticates YOU as a user, not a specific project. The `projectID` distinguishes projects.

**If needed**: Create separate user accounts with different tokens and switch global configs.

### Q: Can I override the global config per project?

**A**: Not recommended, but possible via `.claude/settings.local.json` (personal overrides):

```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_custom",
    "ACE_SERVER_URL": "https://custom-ace-server.example.com",
    "ACE_API_TOKEN": "ace_custom_token"
  }
}
```

MCP client v3.7.2 respects environment variables from this file.

**Warning**: This bypasses the global config and is not team-shareable.

### Q: What happens if I don't set ACE_PROJECT_ID?

**A**: MCP client will error:

```
Error: Project ID is required (use --projectID or set ACE_PROJECT_ID)
```

**Solution**: Run `/ace-orchestration:ace-configure --project`

### Q: Can I use the same project ID across multiple repositories?

**A**: Yes, but **not recommended**.

**Why?**: All repositories would share the same playbook, mixing patterns from different codebases.

**Best practice**: One project ID per repository/workspace.

### Q: How do I share playbooks across team?

**A**: Commit `.claude/settings.json` with the shared `ACE_PROJECT_ID`.

All team members must:
1. Have their own API token (global config)
2. Use the same project ID (project config)
3. Have access to the project on ACE server

### Q: Can I test ACE without an API token?

**A**: No. ACE requires authentication to the server.

**For local development**: Run your own ACE server instance (see ACE server documentation).

---

## 1️⃣2️⃣ Next Steps

1. ✅ **Complete setup** using this guide
2. ✅ **Initialize CLAUDE.md**: Run `/ace-orchestration:ace-claude-init`
3. ✅ **Bootstrap playbook**: Run `/ace-orchestration:ace-bootstrap` (optional)
4. ✅ **Test skills**: Try implementing a small feature and observe auto-retrieval/learning
5. ✅ **Commit project config**: `git add .claude/settings.json && git commit -m "Configure ACE"`

---

## 📚 Additional Resources

- [ACE Plugin README](../README.md) - Full plugin documentation
- [ACE Plugin ARCHITECTURE](../ARCHITECTURE.md) - Technical architecture details
- [ACE Client MCP Implementation](../docs/MCP_CLIENT_IMPLEMENTATION.md) - MCP client specification
- [MCP Team Requirements](/tmp/MCP_V3.7.2_REQUIREMENTS.md) - Technical requirements for MCP v3.7.2
- [Claude Code Documentation](https://docs.claude.com) - Official Claude Code docs
- [GitHub Issues](https://github.com/ce-dot-net/ce-claude-marketplace/issues) - Report bugs

---

**Questions or issues?** Open an issue on [GitHub](https://github.com/ce-dot-net/ce-claude-marketplace/issues).
