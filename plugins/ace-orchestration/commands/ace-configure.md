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

---

## Helper Functions (v3.8.1 Multi-Org Support)

### verify_token() - Verify API Token and Fetch Organization Info

```bash
verify_token() {
  local TOKEN=$1
  local SERVER_URL=$2

  echo "🔍 Verifying token with ACE server..."

  VERIFY_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$SERVER_URL/api/v1/config/verify")

  HTTP_CODE=$(echo "$VERIFY_RESPONSE" | tail -n1)
  BODY=$(echo "$VERIFY_RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -eq 200 ]; then
    ORG_ID=$(echo "$BODY" | jq -r '.org_id')
    ORG_NAME=$(echo "$BODY" | jq -r '.org_name')
    PROJECTS_JSON=$(echo "$BODY" | jq '.projects')
    PROJECT_IDS=$(echo "$PROJECTS_JSON" | jq -r '.[].project_id')

    echo "✅ Verified! Organization: $ORG_NAME ($ORG_ID)"
    echo "📋 Available projects:"
    echo "$PROJECTS_JSON" | jq -r '.[] | "  • \(.project_name) (\(.project_id))"'
    echo ""

    # Return as JSON for script to use
    echo "$BODY"
    return 0
  else
    echo "❌ Token verification failed (HTTP $HTTP_CODE)"
    echo "Response: $BODY"
    echo "Please check your token and try again."
    return 1
  fi
}
```

### validate_project_in_orgs() - Validate Project Belongs to Organization

```bash
validate_project_in_orgs() {
  local PROJECT_ID=$1
  local GLOBAL_CONFIG_JSON=$2

  # Find which org contains this project
  MATCHING_ORG=$(echo "$GLOBAL_CONFIG_JSON" | jq -r \
    ".orgs | to_entries[] | select(.value.projects | contains([\"$PROJECT_ID\"])) | .key" \
    | head -n1)

  if [ -n "$MATCHING_ORG" ]; then
    ORG_NAME=$(echo "$GLOBAL_CONFIG_JSON" | jq -r ".orgs[\"$MATCHING_ORG\"].orgName")
    echo "✅ Project validated in organization: $ORG_NAME ($MATCHING_ORG)"
    return 0
  else
    echo "⚠️  Warning: Project ID not found in any configured organization"
    echo "   The project will use the fallback token (root apiToken)"
    echo ""
    return 1
  fi
}
```

---

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

    # Move backup to new location (not in old .ace folder!)
    BACKUP_NAME=$(basename "$MIGRATION_SOURCE").v3.3.2.bak
    BACKUP_PATH="$XDG_HOME/ace/$BACKUP_NAME"
    mv "$MIGRATION_SOURCE" "$BACKUP_PATH"

    # Remove empty legacy directories
    if [ "$MIGRATION_SOURCE" = "$LEGACY_PROJECT_CONFIG" ]; then
      # Remove .ace folder if empty (project-level migration)
      if [ -d "$PROJECT_ROOT/.ace" ] && [ -z "$(ls -A "$PROJECT_ROOT/.ace")" ]; then
        rmdir "$PROJECT_ROOT/.ace"
        echo "   🗑️  Removed empty legacy folder: $PROJECT_ROOT/.ace"
      fi
    elif [ "$MIGRATION_SOURCE" = "$LEGACY_GLOBAL_CONFIG" ]; then
      # Remove ~/.ace folder if empty (global migration)
      if [ -d "$HOME/.ace" ] && [ -z "$(ls -A "$HOME/.ace")" ]; then
        rmdir "$HOME/.ace"
        echo "   🗑️  Removed empty legacy folder: $HOME/.ace"
      fi
    fi

    echo "✅ Migration complete!"
    echo "   New config: $GLOBAL_CONFIG"
    echo "   Backup: $BACKUP_PATH"
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

### Step 3: Read Existing Configuration and Detect Multi-Org Mode

**For Global Config**:
```bash
# Check if ~/.config/ace/config.json exists (XDG standard)
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
GLOBAL_CONFIG="$XDG_HOME/ace/config.json"

if [ -f "$GLOBAL_CONFIG" ]; then
  # Read existing config
  EXISTING_CONFIG=$(cat "$GLOBAL_CONFIG")

  # Read existing values
  EXISTING_URL=$(echo "$EXISTING_CONFIG" | jq -r '.serverUrl // "https://ace-api.code-engine.app"')
  EXISTING_TOKEN=$(echo "$EXISTING_CONFIG" | jq -r '.apiToken // ""')
  EXISTING_TTL=$(echo "$EXISTING_CONFIG" | jq -r '.cacheTtlMinutes // 120')
  EXISTING_AUTO_UPDATE=$(echo "$EXISTING_CONFIG" | jq -r '.autoUpdateEnabled // false')

  # Check for multi-org mode (v3.8.1+)
  HAS_ORGS=$(echo "$EXISTING_CONFIG" | jq 'has("orgs")')

  if [ "$HAS_ORGS" = "true" ]; then
    ORG_COUNT=$(echo "$EXISTING_CONFIG" | jq '.orgs | length')
    echo "✓ Found existing global configuration (Multi-org mode)"
    echo "  Server URL: $EXISTING_URL"
    echo "  🌐 Organizations: $ORG_COUNT configured"
    echo "  Cache TTL: $EXISTING_TTL minutes"
    echo "  Auto-update: $EXISTING_AUTO_UPDATE"
    echo ""

    # Show org list
    echo "  Configured organizations:"
    echo "$EXISTING_CONFIG" | jq -r '.orgs | to_entries[] | "    • \(.value.orgName) (\(.key)) - \(.value.projects | length) projects"'

    MULTI_ORG_MODE=true
  else
    echo "✓ Found existing global configuration"
    echo "  Server URL: $EXISTING_URL"
    echo "  API Token: ${EXISTING_TOKEN:0:12}..." # Show first 12 chars
    echo "  Cache TTL: $EXISTING_TTL minutes"
    echo "  Auto-update: $EXISTING_AUTO_UPDATE"

    MULTI_ORG_MODE=false
  fi
else
  echo "ℹ No existing global configuration found"
  EXISTING_CONFIG="{}"
  EXISTING_URL="https://ace-api.code-engine.app"
  EXISTING_TOKEN=""
  EXISTING_TTL=120
  EXISTING_AUTO_UPDATE=false
  MULTI_ORG_MODE=false
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

#### Multi-Org Mode Decision (if MULTI_ORG_MODE=true):

If multi-org mode is detected, ask user what they want to do:

```javascript
// Only show if MULTI_ORG_MODE = true
AskUserQuestion({
  questions: [{
    question: `Multi-org mode active with ${ORG_COUNT} organization(s). What would you like to do?`,
    header: "Multi-Org",
    multiSelect: false,
    options: [
      {
        label: "Use existing org",
        description: "Select from configured organizations"
      },
      {
        label: "Add new org",
        description: "Configure a new organization"
      },
      {
        label: "Update existing org",
        description: "Modify token or settings for an org"
      },
      {
        label: "Convert to single org",
        description: "Remove multi-org configuration"
      }
    ]
  }]
})
```

Based on user's choice, proceed with:
- **"Use existing org"**: See "Step 4a: Use Existing Org Flow" below
- **"Add new org"**: Call verify_token(), add to orgs
- **"Update existing org"**: Show org list, update selected org
- **"Convert to single org"**: Remove orgs field, keep one token

### Step 4a: Use Existing Org Flow (Multi-Org Project Selection)

**When**: User selected "Use existing org" in multi-org mode decision.

**Purpose**: Let user select which org to use, fetch fresh project list from server, and configure project.

**Implementation**:

1. **Ask which organization to use**:
```javascript
// Build org options from global config
// orgs = {"org_abc": {"orgName": "XpertPulse", ...}, "org_xyz": {"orgName": "ce-dot-net", ...}}
AskUserQuestion({
  questions: [{
    question: "Which organization would you like to use for this project?",
    header: "Select Org",
    multiSelect: false,
    options: [
      {
        label: "XpertPulse",
        description: "org_34geJJ3Xr3ZmNVF6FYHLMhpAv61 - 2 projects"
      },
      {
        label: "ce-dot-net",
        description: "org_34fYIlitYk4nyFuTvtsAzA6uUJF - 5 projects"
      }
    ]
  }]
})
```

2. **Fetch fresh project list from server**:
```bash
# After user selects org (e.g., "XpertPulse" → org_34geJJ3Xr3ZmNVF6FYHLMhpAv61)
SELECTED_ORG_ID="org_34geJJ3Xr3ZmNVF6FYHLMhpAv61"
ORG_TOKEN=$(echo "$GLOBAL_CONFIG_JSON" | jq -r ".orgs[\"$SELECTED_ORG_ID\"].apiToken")

# Call verify_token() to get FRESH project list
echo "🔍 Fetching latest project list from server..."
VERIFY_RESPONSE=$(verify_token "$ORG_TOKEN" "$SERVER_URL")

# Extract fresh projects array
FRESH_PROJECTS=$(echo "$VERIFY_RESPONSE" | jq '.projects')
FRESH_PROJECT_IDS=$(echo "$FRESH_PROJECTS" | jq -r '.[].project_id')

echo "✅ Found $(echo "$FRESH_PROJECTS" | jq length) project(s) in organization"
echo ""
```

3. **Update global config with fresh project list**:
```bash
# Update the org's projects array in global config
UPDATED_CONFIG=$(echo "$GLOBAL_CONFIG_JSON" | jq \
  --arg orgId "$SELECTED_ORG_ID" \
  --argjson freshProjects "$(echo "$FRESH_PROJECTS" | jq '[.[].project_id]')" \
  '.orgs[$orgId].projects = $freshProjects')

echo "$UPDATED_CONFIG" > "$GLOBAL_CONFIG"
echo "✅ Updated project list in config"
echo ""
```

4. **Show project selection with fresh list**:
```javascript
// Build options from fresh project list
// FRESH_PROJECTS = [{"project_id": "prj_xxx", "project_name": "foo"}, ...]
AskUserQuestion({
  questions: [{
    question: "Which project would you like to use for lohnpulse-aws-iac?",
    header: "Project ID",
    multiSelect: false,
    options: [
      {
        label: "prj_913f898c709d9f89",
        description: "XpertPulse organization project"
      },
      {
        label: "prj_3600aeeef46e10f4",
        description: "XpertPulse organization project"
      },
      {
        label: "prj_185ba193e965e55c",  // ← NEW project fetched from server
        description: "XpertPulse organization project"
      },
      {
        label: "Enter new project ID",
        description: "Create a new project ID for this codebase"
      }
    ]
  }]
})
```

5. **Handle new project ID entry**:
```bash
# If user selected "Enter new project ID" or typed custom value
if [ "$SELECTED_PROJECT" = "Enter new project ID" ] || [ "$SELECTED_PROJECT" = "Type something" ]; then
  # Prompt for project ID
  # NEW_PROJECT_ID = user's input (e.g., "prj_abc123")

  echo "➕ Adding new project $NEW_PROJECT_ID to organization $SELECTED_ORG_ID"

  # Add to org's projects array in global config
  UPDATED_CONFIG=$(echo "$GLOBAL_CONFIG_JSON" | jq \
    --arg orgId "$SELECTED_ORG_ID" \
    --arg newProjectId "$NEW_PROJECT_ID" \
    '.orgs[$orgId].projects += [$newProjectId]')

  echo "$UPDATED_CONFIG" > "$GLOBAL_CONFIG"

  echo "✅ Added $NEW_PROJECT_ID to organization's project list"

  # Set variables for Step 5
  MATCHING_ORG="$SELECTED_ORG_ID"
  NEW_PROJECT_ID="$NEW_PROJECT_ID"
else
  # User selected existing project
  NEW_PROJECT_ID="$SELECTED_PROJECT"
  MATCHING_ORG="$SELECTED_ORG_ID"
fi
```

6. **Proceed to Step 5** (Save Project Config) with:
   - `NEW_PROJECT_ID` = selected or entered project ID
   - `MATCHING_ORG` = selected org ID
   - This ensures `.claude/settings.json` gets both `ACE_PROJECT_ID` and `ACE_ORG_ID`

**Benefits**:
- ✅ Always shows fresh project list from server
- ✅ Can add new projects to existing orgs
- ✅ Updates global config automatically
- ✅ Properly sets ACE_ORG_ID in project config

#### Single-Org Mode Decision (if MULTI_ORG_MODE=false AND config exists):

If single-org config exists (no multi-org), ask user what they want to do:

```javascript
// Only show if MULTI_ORG_MODE = false AND EXISTING_TOKEN is not empty
AskUserQuestion({
  questions: [{
    question: `Found existing single-org configuration. What would you like to do?`,
    header: "Configuration",
    multiSelect: false,
    options: [
      {
        label: "Keep current config",
        description: "No changes, use existing configuration"
      },
      {
        label: "Update settings",
        description: "Update server URL, token, cache TTL, or auto-update"
      },
      {
        label: "Add another organization",
        description: "Convert to multi-org mode by adding a second organization"
      },
      {
        label: "Reconfigure from scratch",
        description: "Replace entire configuration with new values"
      }
    ]
  }]
})
```

Based on user's choice, proceed with:
- **"Keep current config"**: Exit, show summary of current config
- **"Update settings"**: Show interactive form with current values pre-filled
- **"Add another organization"**: Call verify_token() for new org, convert to multi-org format
- **"Reconfigure from scratch"**: Proceed to full interactive configuration

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
  - **IMPORTANT**: After collecting new token, call `verify_token(NEW_TOKEN, SERVER_URL)`
  - This auto-populates org_id, org_name, and project list from server
  - If verify fails, don't save the config and allow retry
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

**Multi-Org Mode (if verify_token() was called and returned org info)**:

```bash
# After verify_token() returns org info:
# ORG_ID, ORG_NAME, PROJECTS_ARRAY are available

# Create XDG config directory if it doesn't exist
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
mkdir -p "$XDG_HOME/ace"
GLOBAL_CONFIG="$XDG_HOME/ace/config.json"

# Read existing config or create empty object
EXISTING=$(cat "$GLOBAL_CONFIG" 2>/dev/null || echo '{}')

# Add org to orgs object (preserves other orgs and root-level fields)
UPDATED=$(echo "$EXISTING" | jq \
  --arg url "$NEW_SERVER_URL" \
  --arg orgId "$ORG_ID" \
  --arg orgName "$ORG_NAME" \
  --arg token "$NEW_API_TOKEN" \
  --argjson projects "$PROJECTS_ARRAY" \
  --argjson ttl "$NEW_CACHE_TTL" \
  --argjson autoUpdate "$NEW_AUTO_UPDATE" \
  '. + {
    serverUrl: $url,
    cacheTtlMinutes: $ttl,
    autoUpdateEnabled: $autoUpdate
  } | .orgs[$orgId] = {
    orgName: $orgName,
    apiToken: $token,
    projects: $projects
  }')

echo "$UPDATED" > "$GLOBAL_CONFIG"
chmod 600 "$GLOBAL_CONFIG"

echo "✅ Organization added: $ORG_NAME ($ORG_ID)"
echo "   Projects: $(echo "$PROJECTS_ARRAY" | jq length)"
```

**Single-Org Mode (backward compatible - no verify_token() call)**:

```bash
# Create XDG config directory if it doesn't exist
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
mkdir -p "$XDG_HOME/ace"
GLOBAL_CONFIG="$XDG_HOME/ace/config.json"

# Merge with existing config (preserve other fields including orgs!)
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

# If multi-org mode, validate project belongs to an org
if [ "$MULTI_ORG_MODE" = "true" ]; then
  GLOBAL_CONFIG_JSON=$(cat "$GLOBAL_CONFIG")

  # Call validate_project_in_orgs()
  if validate_project_in_orgs "$NEW_PROJECT_ID" "$GLOBAL_CONFIG_JSON"; then
    # Project validated - get org info for display
    MATCHING_ORG=$(echo "$GLOBAL_CONFIG_JSON" | jq -r \
      ".orgs | to_entries[] | select(.value.projects | contains([\"$NEW_PROJECT_ID\"])) | .key" \
      | head -n1)
    ORG_NAME=$(echo "$GLOBAL_CONFIG_JSON" | jq -r ".orgs[\"$MATCHING_ORG\"].orgName")

    # ACE_ORG_ID will be set in project config
    echo ""
    echo "ℹ️  Note: ACE_ORG_ID will be set automatically for multi-org projects"
    echo "   Project belongs to: $ORG_NAME ($MATCHING_ORG)"
  else
    echo "⚠️  New project ID detected: $NEW_PROJECT_ID"
    echo "   This project doesn't exist in any configured organization yet."
    echo ""

    # Ask user which org this new project belongs to
    # Build org list from global config for AskUserQuestion
fi

# If we need to ask for org selection (new project), do it here:
if [ "$MULTI_ORG_MODE" = "true" ] && [ -z "$MATCHING_ORG" ]; then
  # Use AskUserQuestion to select org
  # Example:
  # AskUserQuestion({
  #   questions: [{
  #     question: "Which organization does project $NEW_PROJECT_ID belong to?",
  #     header: "Select Org",
  #     multiSelect: false,
  #     options: [
  #       {label: "XpertPulse", description: "org_34geJJ3Xr3ZmNVF6FYHLMhpAv61"},
  #       {label: "ce-dot-net", description: "org_34fYIlitYk4nyFuTvtsAzA6uUJF"}
  #     ]
  #   }]
  # })

  # After user answers, extract org ID from their selection
  # SELECTED_ORG_ID = org ID corresponding to selected label

  # Add project to org's projects array
  UPDATED_CONFIG=$(cat "$GLOBAL_CONFIG" | jq \
    --arg orgId "$SELECTED_ORG_ID" \
    --arg newProjectId "$NEW_PROJECT_ID" \
    '.orgs[$orgId].projects += [$newProjectId]')

  echo "$UPDATED_CONFIG" > "$GLOBAL_CONFIG"

  ORG_NAME=$(echo "$UPDATED_CONFIG" | jq -r ".orgs[\"$SELECTED_ORG_ID\"].orgName")
  echo "✅ Added $NEW_PROJECT_ID to $ORG_NAME organization"
  echo ""

  # Set MATCHING_ORG for .claude/settings.json creation below
  MATCHING_ORG="$SELECTED_ORG_ID"
fi

# Create .claude directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/.claude"

# Merge with existing settings (preserve other env vars)
if [ -f "$PROJECT_CONFIG" ]; then
  # Read existing settings
  EXISTING=$(cat "$PROJECT_CONFIG")

  # Merge ACE_PROJECT_ID (and ACE_ORG_ID if multi-org) using jq
  if [ -n "$MATCHING_ORG" ]; then
    # Multi-org mode: set both ACE_PROJECT_ID and ACE_ORG_ID
    echo "$EXISTING" | jq \
      --arg projectId "$NEW_PROJECT_ID" \
      --arg orgId "$MATCHING_ORG" \
      '.env.ACE_PROJECT_ID = $projectId | .env.ACE_ORG_ID = $orgId' > "$PROJECT_CONFIG.tmp"
  else
    # Single-org or no org: only set ACE_PROJECT_ID
    echo "$EXISTING" | jq \
      --arg projectId "$NEW_PROJECT_ID" \
      '.env.ACE_PROJECT_ID = $projectId' > "$PROJECT_CONFIG.tmp"
  fi

  mv "$PROJECT_CONFIG.tmp" "$PROJECT_CONFIG"
else
  # Create new settings file
  if [ -n "$MATCHING_ORG" ]; then
    # Multi-org mode: include both ACE_PROJECT_ID and ACE_ORG_ID
    cat > "$PROJECT_CONFIG" <<EOF
{
  "env": {
    "ACE_PROJECT_ID": "$NEW_PROJECT_ID",
    "ACE_ORG_ID": "$MATCHING_ORG"
  }
}
EOF
  else
    # Single-org or no org: only ACE_PROJECT_ID
    cat > "$PROJECT_CONFIG" <<EOF
{
  "env": {
    "ACE_PROJECT_ID": "$NEW_PROJECT_ID"
  }
}
EOF
  fi
fi

echo "✅ Project configuration saved to: $PROJECT_CONFIG"
```

### Step 6: Configure Startup Announcements (Automatic)

**This step runs automatically after global configuration** to add ACE version check reminders to Claude Code's startup announcements.

```bash
# Only configure announcements if global config was updated
if [ "$SCOPE" = "global" ] || [ "$SCOPE" = "both" ]; then
  echo ""
  echo "🔔 Configuring startup announcements..."

  # Path to Claude Code user-level settings.json
  CLAUDE_SETTINGS="$HOME/.claude/settings.json"

  # Check if companyAnnouncements already exists
  if [ -f "$CLAUDE_SETTINGS" ]; then
    HAS_ANNOUNCEMENTS=$(jq 'has("companyAnnouncements")' "$CLAUDE_SETTINGS" 2>/dev/null || echo "false")

    if [ "$HAS_ANNOUNCEMENTS" = "true" ]; then
      echo "   ℹ️  Startup announcements already configured - skipping"
    else
      echo "   ➕ Adding ACE announcements to ~/.claude/settings.json"

      # Read existing settings
      EXISTING=$(cat "$CLAUDE_SETTINGS")

      # Add companyAnnouncements array (preserve other settings)
      echo "$EXISTING" | jq '. + {
        "companyAnnouncements": [
          "ACE Plugin: Check for updates with /ace-orchestration:ace-status",
          "ACE Plugin: Run /ace-claude-init after updating to refresh project instructions"
        ]
      }' > "$CLAUDE_SETTINGS.tmp"

      mv "$CLAUDE_SETTINGS.tmp" "$CLAUDE_SETTINGS"
      echo "   ✅ Startup announcements configured"
    fi
  else
    # Create new settings.json with announcements
    echo "   ➕ Creating ~/.claude/settings.json with ACE announcements"

    mkdir -p "$HOME/.claude"
    cat > "$CLAUDE_SETTINGS" <<'EOF'
{
  "companyAnnouncements": [
    "ACE Plugin: Check for updates with /ace-orchestration:ace-status",
    "ACE Plugin: Run /ace-claude-init after updating to refresh project instructions"
  ]
}
EOF

    echo "   ✅ Startup announcements configured"
  fi

  echo ""
fi
```

**What This Does**:
- Adds ACE-related announcements to `~/.claude/settings.json` (user-level global)
- These announcements appear randomly on Claude Code startup (v2.0.32+)
- Reminds users to check for plugin updates and refresh instructions
- **Only adds if not already present** (won't overwrite existing announcements)
- Preserves all other settings in the file

### Step 7: Show Configuration Summary

**Single-Org Mode**:
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
  📦 MCP Client: @ce-dot-net/ace-client@3.8.1 (registered in plugin .mcp.json)

Startup Announcements (~/.claude/settings.json):
  🔔 Configured to show ACE update reminders on startup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Next steps:
1. Run: /ace-orchestration:ace-status to verify connection
2. Run: /ace-orchestration:ace-claude-init to add ACE instructions to CLAUDE.md
3. Optional: /ace-orchestration:ace-bootstrap to populate initial playbook patterns

ℹ️  No restart needed - configuration is active immediately!
   Startup announcements will appear on next Claude Code restart.
```

**Multi-Org Mode**:
```
✅ ACE Configuration Complete!

Configuration saved:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Global Config (~/.config/ace/config.json):
  📍 Server URL: https://ace-api.code-engine.app
  🌐 Multi-org mode: 2 organization(s) configured
  ⏱️  Cache TTL: 120 minutes (2 hours)
  🔄 Auto-update: enabled

  Organizations:
    • ce-dot-net (org_34fYIl...JF) - 3 projects
    • client-corp (org_xyz789) - 1 project

Project Config (.claude/settings.json):
  📂 Project Root: /Users/you/my-project
  🆔 Project ID: prj_d3a244129d62c198
  🎯 Active Org: ce-dot-net (auto-resolved from project ID)
  📦 MCP Client: @ce-dot-net/ace-client@3.8.1 (registered in plugin .mcp.json)

Startup Announcements (~/.claude/settings.json):
  🔔 Configured to show ACE update reminders on startup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Next steps:
1. Run: /ace-orchestration:ace-status to verify connection
2. Run: /ace-orchestration:ace-claude-init to add ACE instructions to CLAUDE.md
3. Optional: /ace-orchestration:ace-bootstrap to populate initial playbook patterns

ℹ️  No restart needed - configuration is active immediately!
   Startup announcements will appear on next Claude Code restart.
   🌐 Multi-org: Token auto-resolved from project ID (prj_d3a244129d62c198)
```

### Step 8: Validation (Optional but Recommended)

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
