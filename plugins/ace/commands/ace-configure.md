---
description: Configure ACE server connection settings interactively
argument-hint: [--global] [--project]
---

# Configure ACE Connection

Interactive configuration wizard using ace-cli v1.0.2+ features with Claude Code native UI.

## What This Does

**Two-step configuration:**
1. **Global Config**: Uses `ace-cli config validate` + `ace-cli config` with flags
2. **Project Config**: Creates `.claude/settings.json` with orgId and projectId

## Instructions for Claude

When the user runs `/ace:configure`, follow these steps:

### Step 1: Check ace-cli Version and Dependencies

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check for jq (required for JSON parsing)
if ! command -v jq >/dev/null 2>&1; then
  echo "❌ jq not found (required for JSON parsing)"
  echo ""
  echo "Installation instructions:"
  echo "  macOS:   brew install jq"
  echo "  Linux:   apt-get install jq  or  yum install jq"
  echo "  Windows: Download from https://stedolan.github.io/jq/download/"
  echo ""
  exit 1
fi

# Check for ace-cli
if ! command -v ace-cli >/dev/null 2>&1; then
  echo "❌ ace-cli not found"
  echo ""
  echo "Installation required:"
  echo "  npm install -g @ace-sdk/cli"
  echo ""
  exit 1
fi

VERSION=$(ace-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
echo "✅ ace-cli found (version: $VERSION)"

# Check version >= 1.0.2
REQUIRED_VERSION="1.0.2"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
  echo "⚠️  ace-cli v$VERSION found, but v1.0.2+ required for non-interactive config"
  echo ""
  echo "Please upgrade:"
  echo "  npm install -g @ace-sdk/cli@latest"
  echo ""
  exit 1
fi

echo ""
```

### Step 2: Detect Scope

```bash
# Parse arguments
SCOPE="both"
if [ "${1:-}" == "--global" ]; then
  SCOPE="global"
elif [ "${1:-}" == "--project" ]; then
  SCOPE="project"
else
  # Auto-detect: If in a git repo, do both; otherwise just global
  if git rev-parse --show-toplevel 2>/dev/null; then
    SCOPE="both"
  else
    SCOPE="global"
  fi
fi

echo "📋 Configuration scope: $SCOPE"
echo ""
```

### Step 3: Global Configuration (if needed)

**If SCOPE is "global" or "both", use AskUserQuestion to gather inputs, then configure:**

1. **Ask for Server URL**:
   Use AskUserQuestion tool:
   ```javascript
   {
     questions: [
       {
         question: "ACE Server URL?",
         header: "Server URL",
         multiSelect: false,
         options: [
           {
             label: "Production (ace-api.code-engine.app)",
             description: "Official ACE production server (recommended)"
           },
           {
             label: "Localhost (localhost:9000)",
             description: "Local development server"
           }
         ]
       }
     ]
   }
   ```

   Map user selection to URL:
   - "Production" → `https://ace-api.code-engine.app`
   - "Localhost" → `http://localhost:9000`
   - "Other" → Prompt for custom URL

2. **Ask for API Token**:
   Use AskUserQuestion tool:
   ```javascript
   {
     questions: [
       {
         question: "Enter your ACE API token (starts with 'ace_')?",
         header: "API Token",
         multiSelect: false,
         options: [
           {
             label: "I have a token",
             description: "Enter token in the next step"
           },
           {
             label: "I need to get a token",
             description: "Visit https://ace.code-engine.app/settings/tokens"
           }
         ]
       }
     ]
   }
   ```

   If user selects "I have a token", they'll provide it in the "Other" field.
   If "I need to get a token", show them the URL and exit.

3. **Validate Token and Get Org/Project Info**:
   ```bash
   echo "🔍 Validating token with ACE server..."
   echo "   Server: $SERVER_URL"
   echo ""

   # Use subshell to avoid polluting parent environment
   # Workaround: ace-cli config validate doesn't accept --server-url flag properly
   # Use environment variables instead
   # Filter out CLI update notifications (💡 lines) that break JSON parsing
   RAW_VALIDATION=$(
     ACE_SERVER_URL="$SERVER_URL" \
     ACE_API_TOKEN="$API_TOKEN" \
     ace-cli config validate --json 2>&1
   )
   VALIDATION_EXIT_CODE=$?
   VALIDATION_OUTPUT=$(echo "$RAW_VALIDATION" | grep -v '^💡' | grep -v '^$')

   if [ $VALIDATION_EXIT_CODE -ne 0 ]; then
     echo "❌ Token validation failed"
     echo ""
     echo "Error details:"
     echo "$VALIDATION_OUTPUT"
     echo ""
     echo "Common issues:"
     echo "  - Invalid or expired token"
     echo "  - Network connectivity problems"
     echo "  - Server URL incorrect"
     echo ""
     echo "Please verify your token at: https://ace.code-engine.app/settings"
     exit 1
   fi

   # Verify we got valid JSON back
   if ! echo "$VALIDATION_OUTPUT" | jq empty 2>/dev/null; then
     echo "❌ Invalid response from ACE server (not valid JSON)"
     echo ""
     echo "Response:"
     echo "$VALIDATION_OUTPUT"
     exit 1
   fi

   # Parse validation response
   ORG_ID=$(echo "$VALIDATION_OUTPUT" | jq -r '.org_id // empty')
   ORG_NAME=$(echo "$VALIDATION_OUTPUT" | jq -r '.org_name // empty')
   PROJECTS_JSON=$(echo "$VALIDATION_OUTPUT" | jq -c '.projects // []')

   # Verify required fields
   if [ -z "$ORG_ID" ] || [ -z "$ORG_NAME" ]; then
     echo "❌ Validation response missing required fields (org_id, org_name)"
     echo ""
     echo "Response:"
     echo "$VALIDATION_OUTPUT"
     exit 1
   fi

   # Check if user has any projects
   PROJECT_COUNT=$(echo "$PROJECTS_JSON" | jq 'length')
   if [ "$PROJECT_COUNT" -eq 0 ]; then
     echo "⚠️  No projects found for organization: $ORG_NAME"
     echo ""
     echo "Please create a project first at: https://ace.code-engine.app/projects"
     exit 1
   fi

   echo "✅ Validated! Organization: $ORG_NAME ($ORG_ID)"
   echo "   Projects available: $PROJECT_COUNT"
   echo ""
   ```

4. **Ask User to Select Project** (use AskUserQuestion):
   ```javascript
   // Parse projects from PROJECTS_JSON
   // Build options dynamically from project list
   {
     questions: [
       {
         question: "Which project should be configured?",
         header: "Project",
         multiSelect: false,
         options: [
           // For each project in PROJECTS_JSON:
           {
             label: "project.project_name",
             description: "project.project_id"
           }
           // ... more projects
         ]
       }
     ]
   }
   ```

   Extract project_id from user selection.

5. **Configure with ace-cli**:
   ```bash
   echo "💾 Saving global configuration..."

   # Determine config location (respect XDG_CONFIG_HOME)
   GLOBAL_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/ace/config.json"
   GLOBAL_CONFIG_DIR=$(dirname "$GLOBAL_CONFIG")

   # Ensure config directory exists
   if [ ! -d "$GLOBAL_CONFIG_DIR" ]; then
     echo "📁 Creating config directory: $GLOBAL_CONFIG_DIR"
     mkdir -p "$GLOBAL_CONFIG_DIR"
     if [ $? -ne 0 ]; then
       echo "❌ Failed to create config directory: $GLOBAL_CONFIG_DIR"
       exit 1
     fi
   fi

   # Save configuration
   ace-cli config \
     --server-url "$SERVER_URL" \
     --api-token "$API_TOKEN" \
     --project-id "$PROJECT_ID" \
     --json

   if [ $? -ne 0 ]; then
     echo "❌ Failed to save global configuration (ace-cli config command failed)"
     exit 1
   fi

   # Verify config file was created
   if [ ! -f "$GLOBAL_CONFIG" ]; then
     echo "❌ Global config was not created at expected location"
     echo "   Expected: $GLOBAL_CONFIG"
     echo "   Please check ace-cli logs for details"
     exit 1
   fi

   # Verify config is valid JSON
   if ! jq empty "$GLOBAL_CONFIG" 2>/dev/null; then
     echo "❌ Global config is not valid JSON"
     echo "   Location: $GLOBAL_CONFIG"
     echo "   Please check file contents"
     exit 1
   fi

   # Verify required fields are present
   if ! jq -e '.serverUrl and .apiToken' "$GLOBAL_CONFIG" >/dev/null 2>&1; then
     echo "❌ Global config is missing required fields (serverUrl, apiToken)"
     echo "   Location: $GLOBAL_CONFIG"
     exit 1
   fi

   echo "✅ Global configuration saved and verified:"
   echo "   Location: $GLOBAL_CONFIG"
   echo "   Server: $SERVER_URL"
   echo "   Project: $PROJECT_ID"
   echo ""
   ```

### Step 4: Project Configuration (if needed)

**If SCOPE is "project" or "both":**

1. **Get Project Root**:
   ```bash
   PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
   PROJECT_CONFIG="$PROJECT_ROOT/.claude/settings.json"

   echo "📂 Project root: $PROJECT_ROOT"
   echo ""
   ```

2. **Check Existing Config**:
   ```bash
   if [ -f "$PROJECT_CONFIG" ]; then
     EXISTING_ORG=$(jq -r '.env.ACE_ORG_ID // empty' "$PROJECT_CONFIG" 2>/dev/null || echo "")
     EXISTING_PROJECT=$(jq -r '.env.ACE_PROJECT_ID // empty' "$PROJECT_CONFIG" 2>/dev/null || echo "")

     if [ -n "$EXISTING_ORG" ] && [ -n "$EXISTING_PROJECT" ]; then
       echo "ℹ️  Found existing project configuration:"
       echo "  Organization ID: $EXISTING_ORG"
       echo "  Project ID: $EXISTING_PROJECT"
       echo ""
       # Ask user what they want to do - STOP HERE AND PROMPT
       EXISTING_CONFIG="true"
     fi
   fi
   ```

3. **Prompt for Action** (if existing config found):

   If existing configuration was detected, use AskUserQuestion:
   ```javascript
   {
     questions: [
       {
         question: "Found existing ACE configuration. What would you like to do?",
         header: "Config Action",
         multiSelect: false,
         options: [
           {
             label: "Keep existing configuration",
             description: "No changes - use current org and project settings"
           },
           {
             label: "Update project only",
             description: "Keep organization, select a different project"
           },
           {
             label: "Reconfigure everything",
             description: "Fresh setup - change both organization and project"
           }
         ]
       }
     ]
   }
   ```

   Based on user's choice:
   - **"Keep existing configuration"** → Exit early:
     ```bash
     echo "✅ Keeping existing configuration"
     echo "   Organization: $EXISTING_ORG"
     echo "   Project: $EXISTING_PROJECT"
     exit 0
     ```
   - **"Update project only"** → Skip to Step 5 (project selection), reuse $EXISTING_ORG
   - **"Reconfigure everything"** → Continue with Step 4 (full flow)

4. **Read Global Config**:
   ```bash
   GLOBAL_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/ace/config.json"

   if [ ! -f "$GLOBAL_CONFIG" ]; then
     echo "⚠️  No global config found at $GLOBAL_CONFIG"
     echo "   Run /ace:configure --global first"
     exit 1
   fi

   # Check if multi-org mode
   HAS_ORGS=$(jq 'has("orgs")' "$GLOBAL_CONFIG" 2>/dev/null || echo "false")
   ```

4. **Multi-Org Mode** (if HAS_ORGS is true):

   Use AskUserQuestion to select organization:
   ```javascript
   // Parse orgs from global config
   // For each org in config.orgs:
   {
     questions: [
       {
         question: "Which organization should this project use?",
         header: "Organization",
         multiSelect: false,
         options: [
           {
             label: "org.orgName",
             description: "org_id"
           }
           // ... more orgs
         ]
       }
     ]
   }
   ```

   Then ask for project from that org's project list.

5. **Single-Org Mode** (if HAS_ORGS is false):

   Just ask for project ID directly using AskUserQuestion.

6. **Ask for Verbosity Preference**:

   Use AskUserQuestion to let user choose display mode:
   ```javascript
   {
     questions: [
       {
         question: "How should ACE display learning results?",
         header: "Verbosity",
         multiSelect: false,
         options: [
           {
             label: "Detailed (recommended)",
             description: "Multi-line with full stats: 📝 new 🔄 updated ⭐ quality 📂 sections ⏱️ timing"
           },
           {
             label: "Compact",
             description: "Single line: ✅ [ACE] 📚 +2 patterns 🔄 1 merged ⭐ 85% quality"
           }
         ]
       }
     ]
   }
   ```

   Map selection:
   - "Detailed" → `VERBOSITY="detailed"`
   - "Compact" → `VERBOSITY="compact"`

7. **Write .claude/settings.json**:
   ```bash
   mkdir -p "$PROJECT_ROOT/.claude"

   if [ -n "$ORG_ID" ]; then
     # Multi-org: include ACE_ORG_ID in env
     cat > "$PROJECT_CONFIG" <<EOF
{
  "env": {
    "ACE_ORG_ID": "$ORG_ID",
    "ACE_PROJECT_ID": "$PROJECT_ID",
    "ACE_VERBOSITY": "$VERBOSITY"
  }
}
EOF
     echo "✅ Project configuration saved:"
     echo "  Organization ID: $ORG_ID"
     echo "  Project ID: $PROJECT_ID"
     echo "  Verbosity: $VERBOSITY"
   else
     # Single-org: just ACE_PROJECT_ID in env
     cat > "$PROJECT_CONFIG" <<EOF
{
  "env": {
    "ACE_PROJECT_ID": "$PROJECT_ID",
    "ACE_VERBOSITY": "$VERBOSITY"
  }
}
EOF
     echo "✅ Project configuration saved:"
     echo "  Project ID: $PROJECT_ID"
     echo "  Verbosity: $VERBOSITY"
   fi

   echo "  Location: $PROJECT_CONFIG"
   echo ""
   ```

### Step 5: Show Summary

```bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ACE Configuration Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$SCOPE" = "global" ] || [ "$SCOPE" = "both" ]; then
  GLOBAL_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/ace/config.json"
  echo "Global Config: $GLOBAL_CONFIG ✓"
fi

if [ "$SCOPE" = "project" ] || [ "$SCOPE" = "both" ]; then
  PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  echo "Project Config: $PROJECT_ROOT/.claude/settings.json ✓"
  echo "  Verbosity: $VERBOSITY"
fi

echo ""
echo "Next steps:"
echo "1. Run: /ace:status to verify connection"
echo "2. Optional: /ace:bootstrap to populate playbook from codebase"
echo "3. Start coding - hooks will auto-search patterns!"
echo ""
```

## Implementation Notes for Claude

**Key Points:**
1. **Always use AskUserQuestion** for user input (not bash read or prompts)
2. **Parse JSON responses** from `ace-cli config validate --json`
3. **Build dynamic options** from validation response (orgs/projects)
4. **Map user selections** to actual values (e.g., "Production" → URL)
5. **Handle both single-org and multi-org modes** based on global config

**Error Handling:**
- Check jq availability (required for JSON parsing)
- Check ace-cli version >= 1.0.2
- Validate token before saving (with detailed error messages)
- Verify global config file was created and is valid JSON
- Verify global config has required fields (serverUrl, apiToken)
- Check user has at least one project in organization
- Handle missing global config for project-only mode
- Use subshell for environment variables (avoid pollution)

**User Experience:**
- Show progress messages at each step
- Display org/project names (not just IDs) in selections
- Provide helpful error messages with next steps
- Summarize what was configured

## What Gets Configured

### Global Config (~/.config/ace/config.json)

**Single-Org Mode:**
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxx",
  "projectId": "prj_xxxxx",
  "cacheTtlMinutes": 120
}
```

**Multi-Org Mode:**
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "orgs": {
    "org_xxxxx": {
      "orgName": "My Organization",
      "apiToken": "ace_xxxxx",
      "projects": ["prj_123", "prj_456"]
    }
  },
  "cacheTtlMinutes": 120
}
```

### Project Config (.claude/settings.json)

**Multi-Org:**
```json
{
  "env": {
    "ACE_ORG_ID": "org_xxxxx",
    "ACE_PROJECT_ID": "prj_xxxxx",
    "ACE_VERBOSITY": "detailed"
  }
}
```

**Single-Org:**
```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_xxxxx",
    "ACE_VERBOSITY": "detailed"
  }
}
```

### Verbosity Levels

| Level | Output |
|-------|--------|
| `compact` | Single line: `✅ [ACE] 📚 +2 patterns 🔄 1 merged ⭐ 85% quality` |
| `detailed` | Full breakdown with sections, timing, helpful delta (default) |

Set via `ACE_VERBOSITY` in settings.json env block.

## Usage Examples

### First-Time Setup (Both Global + Project)

```
/ace:configure
```

**Flow:**
1. Asks for server URL (production/localhost/custom)
2. Asks for API token
3. Validates token, fetches org/projects
4. Asks which project to configure
5. Saves global config (~/.config/ace/config.json)
6. Saves project config (.claude/settings.json)

### Update Global Config Only

```
/ace:configure --global
```

**Flow:**
1. Reconfigures global settings
2. Validates token
3. Updates ~/.config/ace/config.json

### Update Project Config Only

```
/ace:configure --project
```

**Flow:**
1. Reads existing global config
2. Asks which org/project for THIS project
3. Updates .claude/settings.json

## See Also

- `/ace:status` - Verify configuration
- `/ace:bootstrap` - Initialize playbook
- `ace-cli config --help` - CLI config help
- `ace-cli config show` - View current config
