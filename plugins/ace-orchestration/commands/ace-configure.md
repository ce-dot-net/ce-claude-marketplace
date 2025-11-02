---
description: Configure ACE server connection settings interactively
argument-hint: [--global] [--project]
---

# Configure ACE Connection

Interactive configuration wizard for ACE server connection with support for global and project-level settings.

## Instructions for Claude

**IMPORTANT**: When executing bash/jq code from this file:
- Use the `Bash` tool to run commands (do NOT copy-paste into eval or subshells)
- For reading JSON values, use `Read` tool + manual parsing OR use `jq` via `Bash` tool
- Keep jq expressions simple (avoid complex nested parentheses)
- Use `AskUserQuestion` tool for interactive prompts (do NOT use bash `read` command)

When the user runs `/ace-orchestration:ace-configure`, follow these steps:

### Step 1: Detect Configuration Scope

Determine if this is global or project configuration:

```bash
# Check for scope flags
if [ "$1" == "--global" ]; then
  SCOPE="global"
elif [ "$1" == "--project" ]; then
  SCOPE="project"
else
  # Auto-detect: If in a project with git, default to project setup
  if git rev-parse --show-toplevel 2>/dev/null; then
    SCOPE="project"
  else
    SCOPE="global"
  fi
fi
```

**Configuration Scopes**:
- **Global** (`~/.config/ace/config.json`): Org-level settings (serverUrl, apiToken, cache settings)
- **Project** (`.claude/settings.json`): Project-specific environment variable ACE_PROJECT_ID

### Step 2: Detect and Migrate Legacy Configurations

**Check for Legacy Config Files** (v3.3.1 and v3.3.2):
```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
LEGACY_PROJECT_CONFIG="$PROJECT_ROOT/.ace/config.json"  # v3.3.1 and earlier
LEGACY_GLOBAL_CONFIG="$HOME/.ace/config.json"           # v3.3.2
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
GLOBAL_CONFIG="$XDG_HOME/ace/config.json"               # v3.3.3+

# Check if legacy configs exist
FOUND_LEGACY=false
MIGRATION_SOURCE=""

if [ -f "$LEGACY_PROJECT_CONFIG" ]; then
  echo "⚠️  Found legacy project config: $LEGACY_PROJECT_CONFIG"
  echo "   This was used in v3.3.1 and earlier"
  FOUND_LEGACY=true
  MIGRATION_SOURCE="$LEGACY_PROJECT_CONFIG"
elif [ -f "$LEGACY_GLOBAL_CONFIG" ]; then
  echo "⚠️  Found legacy global config: $LEGACY_GLOBAL_CONFIG"
  echo "   This was used in v3.3.2"
  FOUND_LEGACY=true
  MIGRATION_SOURCE="$LEGACY_GLOBAL_CONFIG"
fi

# If legacy config found, offer migration
if [ "$FOUND_LEGACY" = true ]; then
  echo ""
  echo "🔄 Auto-Migration Available"
  echo "   Old location: $MIGRATION_SOURCE"
  echo "   New location: $GLOBAL_CONFIG"
  echo ""

  # Ask user if they want to migrate
  read -p "Migrate config automatically? (y/n): " MIGRATE_CHOICE

  if [ "$MIGRATE_CHOICE" = "y" ] || [ "$MIGRATE_CHOICE" = "Y" ]; then
    # Create XDG directory
    mkdir -p "$XDG_HOME/ace"
    chmod 700 "$XDG_HOME/ace"

    # Copy config
    cp "$MIGRATION_SOURCE" "$GLOBAL_CONFIG"
    chmod 600 "$GLOBAL_CONFIG"

    # Backup old config
    mv "$MIGRATION_SOURCE" "${MIGRATION_SOURCE}.v3.3.2.bak"

    echo "✅ Migration complete!"
    echo "   New config: $GLOBAL_CONFIG"
    echo "   Backup: ${MIGRATION_SOURCE}.v3.3.2.bak"
    echo ""

    # If migrated from project config, also need to set up project ID
    if [ "$MIGRATION_SOURCE" = "$LEGACY_PROJECT_CONFIG" ]; then
      echo "ℹ️  Note: Project-specific ID needs to be set in .claude/settings.json"
      echo "   Run: /ace-orchestration:ace-configure --project"
      echo ""
    fi
  else
    echo "⏭️  Skipping migration (you can run this command again later)"
    echo ""
  fi
fi
```

### Step 3: Read Existing Configuration

**For Global Config**:
```bash
# Check if ~/.config/ace/config.json exists (XDG standard)
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
GLOBAL_CONFIG="$XDG_HOME/ace/config.json"

if [ -f "$GLOBAL_CONFIG" ]; then
  # Read existing values
  EXISTING_URL=$(jq -r '.serverUrl // "https://ace-api.code-engine.app"' "$GLOBAL_CONFIG")
  EXISTING_TOKEN=$(jq -r '.apiToken // ""' "$GLOBAL_CONFIG")
  EXISTING_TTL=$(jq -r '.cacheTtlMinutes // 120' "$GLOBAL_CONFIG")
  EXISTING_AUTO_UPDATE=$(jq -r '.autoUpdateEnabled // false' "$GLOBAL_CONFIG")

  echo "✓ Found existing global configuration"
  echo "  Server URL: $EXISTING_URL"
  echo "  API Token: ${EXISTING_TOKEN:0:12}..." # Show first 12 chars
  echo "  Cache TTL: $EXISTING_TTL minutes"
  echo "  Auto-update: $EXISTING_AUTO_UPDATE"
else
  echo "ℹ No existing global configuration found"
  EXISTING_URL="https://ace-api.code-engine.app"
  EXISTING_TOKEN=""
  EXISTING_TTL=120
  EXISTING_AUTO_UPDATE=false
fi
```

**For Project Config**:
```bash
# Check if .claude/settings.json exists
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROJECT_CONFIG="$PROJECT_ROOT/.claude/settings.json"

if [ -f "$PROJECT_CONFIG" ]; then
  # Extract existing ACE_PROJECT_ID from env vars
  EXISTING_PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // ""' "$PROJECT_CONFIG" 2>/dev/null || echo "")

  echo "✓ Found existing project configuration"
  echo "  Project ID: $EXISTING_PROJECT_ID"
else
  echo "ℹ No existing project configuration found"
  EXISTING_PROJECT_ID=""
fi
```

### Step 4: Interactive Configuration with Existing Values

**IMPORTANT**: Use the `AskUserQuestion` tool to show existing values and collect new values.

#### For Global Configuration (`--global` or auto-detected):

```javascript
AskUserQuestion({
  questions: [
    {
      question: `ACE Server URL (current: ${EXISTING_URL})?`,
      header: "Server URL",
      multiSelect: false,
      options: [
        {
          label: EXISTING_URL || "https://ace-api.code-engine.app",
          description: EXISTING_URL ? "Keep current server URL" : "Official Code Engine ACE server (recommended)"
        },
        {
          label: "http://localhost:9000",
          description: "Local development server"
        },
        {
          label: "Custom URL",
          description: "Enter your own server URL (for enterprise installations)"
        }
      ]
    },
    {
      question: `ACE API Token (current: ${EXISTING_TOKEN ? '***set***' : 'not set'})?`,
      header: "API Token",
      multiSelect: false,
      options: [
        {
          label: EXISTING_TOKEN ? "Keep current token" : "Enter new token",
          description: EXISTING_TOKEN
            ? `Current token: ${EXISTING_TOKEN.substring(0, 12)}...`
            : "Paste your ACE API token (starts with ace_)"
        },
        {
          label: "Enter new token",
          description: "Replace with a different API token"
        }
      ]
    },
    {
      question: `Cache TTL in minutes (current: ${EXISTING_TTL})?`,
      header: "Cache TTL",
      multiSelect: false,
      options: [
        {
          label: `${EXISTING_TTL} minutes`,
          description: EXISTING_TTL === 120 ? "Keep current (2 hours, recommended)" : "Keep current setting"
        },
        {
          label: "120 minutes",
          description: "2 hours (recommended for production)"
        },
        {
          label: "60 minutes",
          description: "1 hour (for active development)"
        },
        {
          label: "Custom",
          description: "Enter custom TTL value"
        }
      ]
    },
    {
      question: `Enable automatic CLAUDE.md updates (current: ${EXISTING_AUTO_UPDATE})?`,
      header: "Auto-Update",
      multiSelect: false,
      options: [
        {
          label: "Enabled",
          description: "Automatically update CLAUDE.md when plugin releases new version"
        },
        {
          label: "Disabled",
          description: "Manual updates only (run /ace-orchestration:ace-claude-init)"
        }
      ]
    }
  ]
})
```

**Handle "Other" responses**:
- If user selects "Custom URL", prompt for URL input
- If user selects "Enter new token", prompt for token input (validate starts with "ace_")
- If user selects "Custom" TTL, prompt for number input
- Validate all inputs before saving

#### For Project Configuration (`--project` or in git repo):

```javascript
AskUserQuestion({
  questions: [
    {
      question: `ACE Project ID (current: ${EXISTING_PROJECT_ID || 'not set'})?`,
      header: "Project ID",
      multiSelect: false,
      options: [
        {
          label: EXISTING_PROJECT_ID || "Enter project ID",
          description: EXISTING_PROJECT_ID
            ? `Keep current: ${EXISTING_PROJECT_ID}`
            : "Your project identifier (usually starts with prj_)"
        },
        {
          label: "Enter new project ID",
          description: "Replace with a different project ID"
        }
      ]
    }
  ]
})
```

### Step 5: Save Configuration (Merge, Don't Overwrite)

#### For Global Config (`~/.config/ace/config.json`):

```bash
# Create XDG config directory if it doesn't exist
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
mkdir -p "$XDG_HOME/ace"
GLOBAL_CONFIG="$XDG_HOME/ace/config.json"

# Merge with existing config (preserve other fields)
if [ -f "$GLOBAL_CONFIG" ]; then
  # Read existing config
  EXISTING=$(cat "$GLOBAL_CONFIG")

  # Merge new values using jq
  echo "$EXISTING" | jq \
    --arg url "$NEW_SERVER_URL" \
    --arg token "$NEW_API_TOKEN" \
    --argjson ttl "$NEW_CACHE_TTL" \
    --argjson autoUpdate "$NEW_AUTO_UPDATE" \
    '. + {
      serverUrl: $url,
      apiToken: $token,
      cacheTtlMinutes: $ttl,
      autoUpdateEnabled: $autoUpdate
    }' > "$GLOBAL_CONFIG.tmp"

  mv "$GLOBAL_CONFIG.tmp" "$GLOBAL_CONFIG"
else
  # Create new config
  cat > "$GLOBAL_CONFIG" <<EOF
{
  "serverUrl": "$NEW_SERVER_URL",
  "apiToken": "$NEW_API_TOKEN",
  "cacheTtlMinutes": $NEW_CACHE_TTL,
  "autoUpdateEnabled": $NEW_AUTO_UPDATE
}
EOF
fi

# Set secure permissions (readable only by user)
chmod 600 "$GLOBAL_CONFIG"

echo "✅ Global configuration saved to: $GLOBAL_CONFIG"
```

#### For Project Config (`.claude/settings.json`):

```bash
# Get project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROJECT_CONFIG="$PROJECT_ROOT/.claude/settings.json"

# Create .claude directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/.claude"

# Merge with existing settings (preserve other env vars)
if [ -f "$PROJECT_CONFIG" ]; then
  # Read existing settings
  EXISTING=$(cat "$PROJECT_CONFIG")

  # Merge ACE_PROJECT_ID env var using jq
  echo "$EXISTING" | jq \
    --arg projectId "$NEW_PROJECT_ID" \
    '.env.ACE_PROJECT_ID = $projectId' > "$PROJECT_CONFIG.tmp"

  mv "$PROJECT_CONFIG.tmp" "$PROJECT_CONFIG"
else
  # Create new settings file with ACE_PROJECT_ID
  cat > "$PROJECT_CONFIG" <<EOF
{
  "env": {
    "ACE_PROJECT_ID": "$NEW_PROJECT_ID"
  }
}
EOF
fi

echo "✅ Project configuration saved to: $PROJECT_CONFIG"
```

### Step 6: Show Configuration Summary

```
✅ ACE Configuration Complete!

Configuration saved:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Global Config (~/.config/ace/config.json):
  📍 Server URL: https://ace-api.code-engine.app
  🔑 API Token: ace_gJ3XjvJK907T... (saved securely)
  ⏱️  Cache TTL: 120 minutes (2 hours)
  🔄 Auto-update: enabled

Project Config (.claude/settings.json):
  📂 Project Root: /Users/you/my-project
  🆔 Project ID: prj_d3a244129d62c198 (set as ACE_PROJECT_ID env var)
  📦 MCP Client: @ce-dot-net/ace-client@3.7.2 (registered in plugin .mcp.json)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Next steps:
1. Run: /ace-orchestration:ace-status to verify connection
2. Run: /ace-orchestration:ace-claude-init to add ACE instructions to CLAUDE.md
3. Optional: /ace-orchestration:ace-bootstrap to populate initial playbook patterns

ℹ️  No restart needed - configuration is active immediately!
```

### Step 7: Validation (Optional but Recommended)

```bash
# Test connection to ACE server
echo "🔍 Testing connection to ACE server..."

curl -s -X GET \
  -H "Authorization: Bearer $NEW_API_TOKEN" \
  "$NEW_SERVER_URL/api/projects/$NEW_PROJECT_ID/playbook" \
  -w "\nHTTP Status: %{http_code}\n" \
  -o /dev/null

if [ $? -eq 0 ]; then
  echo "✅ Connection successful!"
else
  echo "⚠️  Connection test failed - please verify your credentials"
  echo "   Run /ace-orchestration:ace-status for detailed diagnostics"
fi
```

## Usage Examples

### Example 1: First-Time Global Setup

```
User: /ace-orchestration:ace-configure --global

Claude: I'll help you configure ACE global settings.

ℹ No existing global configuration found

[Interactive form appears]

Question 1: ACE Server URL?
  → https://ace-api.code-engine.app (Official Code Engine ACE server)
  → http://localhost:9000 (Local development)
  → Custom URL (Enter your own)

User selects: https://ace-api.code-engine.app

Question 2: ACE API Token?
  → Enter new token (Paste your token starting with ace_)

User enters: ace_gJ3XjvJK907TLbkKqrwgG8a1YH8wc3BLI9YAcuc0pso

Question 3: Cache TTL in minutes?
  → 120 minutes (2 hours, recommended)
  → 60 minutes (1 hour)
  → Custom

User selects: 360 minutes

Question 4: Enable automatic CLAUDE.md updates?
  → Enabled
  → Disabled

User selects: Enabled

✅ Global configuration saved to: ~/.config/ace/config.json
```

### Example 2: Update Existing Global Config

```
User: /ace-orchestration:ace-configure --global

Claude: I'll help you update ACE global settings.

✓ Found existing global configuration
  Server URL: https://ace-api.code-engine.app
  API Token: ace_gJ3XjvJK...
  Cache TTL: 360 minutes
  Auto-update: true

[Interactive form shows current values]

Question 1: ACE Server URL (current: https://ace-api.code-engine.app)?
  → https://ace-api.code-engine.app (Keep current)
  → http://localhost:9000
  → Custom URL

User selects: Keep current

Question 2: ACE API Token (current: ***set***)?
  → Keep current token (Current: ace_gJ3XjvJK...)
  → Enter new token

User selects: Keep current

[Process continues, preserving existing values when selected]
```

### Example 3: Project Setup

```
User: /ace-orchestration:ace-configure --project

Claude: I'll help you configure ACE for this project.

ℹ No existing project configuration found
📂 Project root: /Users/you/my-project

[Interactive form]

Question: ACE Project ID?
  → Enter project ID (Your project identifier)

User enters: prj_d3a244129d62c198

✅ Project configuration saved to: /Users/you/my-project/.claude/settings.json

Project Settings (env var):
{
  "env": {
    "ACE_PROJECT_ID": "prj_d3a244129d62c198"
  }
}

Note: MCP server is registered in plugin .mcp.json, which reads ACE_PROJECT_ID from environment.
```

### Example 4: Combined Setup (Auto-detect)

```
User: /ace-orchestration:ace-configure

Claude: I'll set up ACE for both global and project configuration.

[Step 1: Global Config]
✓ Found existing global configuration - updating...

[Step 2: Project Config]
ℹ No project configuration found - creating...

[Runs both flows sequentially]

✅ ACE Configuration Complete!

Global Config: ~/.config/ace/config.json ✓
Project Config: /Users/you/my-project/.claude/settings.json ✓
```

## Configuration Architecture

### Global Configuration (`~/.config/ace/config.json`)

**Purpose**: Organization-level settings shared across all projects

**Location**: `~/.config/ace/config.json`

**Schema**:
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxx",
  "cacheTtlMinutes": 120,
  "autoUpdateEnabled": true
}
```

**Fields**:
- `serverUrl`: ACE server endpoint
- `apiToken`: Your organization's API token
- `cacheTtlMinutes`: Cache TTL (default: 120 = 2 hours)
- `autoUpdateEnabled`: Auto-update CLAUDE.md on version changes

### Project Configuration (`.claude/settings.json`)

**Purpose**: Project-specific environment variable for ACE_PROJECT_ID

**Location**: `<project-root>/.claude/settings.json`

**Schema**:
```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

**How It Works**:
1. Claude Code sets ACE_PROJECT_ID as environment variable from `.claude/settings.json`
2. Plugin `.mcp.json` expands `${ACE_PROJECT_ID}` when starting MCP server
3. MCP client receives `--projectID prj_xxxxx` as CLI argument
4. MCP client reads `~/.config/ace/config.json` for serverUrl, apiToken, cacheTtl
5. Combined context: projectId (from arg) + serverUrl/apiToken (from config)

## Migration from v3.3.1 and v3.3.2

Legacy configuration files are automatically detected and migrated:

**Migration Strategy:**
1. **Plugin-level** (ace-configure command):
   - Detects legacy configs at old paths (Step 2 above)
   - Prompts user to migrate interactively
   - Creates backup of old config before migration
   - Handles both v3.3.1 project configs and v3.3.2 global configs

2. **MCP Client-level** (v3.7.2):
   - Auto-migrates on first run if plugin migration was skipped
   - Migrates `~/.ace/config.json` → `~/.config/ace/config.json`
   - Creates backup: `~/.ace/config.json.bak`
   - Silent migration with console notification

**Old Files:**
- v3.3.1 and earlier: `<project>/.ace/config.json` → `~/.config/ace/config.json` + `.claude/settings.json`
- v3.3.2: `~/.ace/config.json` → `~/.config/ace/config.json`

**Best Practice**: Run `/ace-orchestration:ace-configure` after upgrading to handle migration interactively with clear feedback.

## Troubleshooting

### "Cannot save global config"

```bash
# Check ~/.ace directory permissions
ls -ld ~/.ace

# Should be: drwx------ (700)
# If not, fix with:
mkdir -p ~/.ace
chmod 700 ~/.ace
```

### "Cannot save project config"

```bash
# Check .claude directory in project root
ls -ld .claude

# Create if missing:
mkdir -p .claude
```

### "jq command not found"

The configuration command requires `jq` for JSON manipulation:

```bash
# macOS
brew install jq

# Linux (Debian/Ubuntu)
sudo apt-get install jq

# Linux (RHEL/CentOS)
sudo yum install jq
```

### "Existing values not showing"

If the interactive form doesn't show existing values, the config file may be corrupted:

```bash
# Validate JSON syntax
jq . ~/.config/ace/config.json
jq . .claude/settings.json

# If invalid, you'll see syntax errors
```

## Security Notes

- **API Token Security**: Global config is saved with `chmod 600` (readable only by user)
- **Git Ignore**: `.claude/settings.json` should be committed (contains project ID, not secrets)
- **Secret Management**: Never commit `~/.config/ace/config.json` (contains API token)

## See Also

- `/ace-orchestration:ace-status` - Verify configuration and test connection
- `/ace-orchestration:ace-claude-init` - Add ACE instructions to project CLAUDE.md
- `/ace-orchestration:ace-bootstrap` - Initialize playbook from codebase
- `docs/MCP_CLIENT_IMPLEMENTATION.md` - MCP client configuration discovery spec
