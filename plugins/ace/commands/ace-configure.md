---
description: Configure ACE server connection settings interactively
argument-hint: [--global] [--project]
---

# Configure ACE Connection (v5.4.13)

Interactive configuration wizard using the new user token authentication model.

**IMPORTANT**: This command requires prior authentication via `/ace-login`.

## What This Does

1. Verifies user is authenticated (via `ace-cli whoami`)
2. Lists available organizations
3. Lets user select organization and project
4. Saves project config to `.claude/settings.json`

## Instructions for Claude

When the user runs `/ace-configure`, follow these steps:

### Step 1: Check Prerequisites

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check for jq (required for JSON parsing)
if ! command -v jq >/dev/null 2>&1; then
  echo "jq not found (required for JSON parsing)"
  echo ""
  echo "Installation instructions:"
  echo "  macOS:   brew install jq"
  echo "  Linux:   apt-get install jq  or  yum install jq"
  echo "  Windows: Download from https://stedolan.github.io/jq/download/"
  exit 1
fi

# Check for ace-cli
if ! command -v ace-cli >/dev/null 2>&1; then
  echo "ace-cli not found"
  echo ""
  echo "Installation required:"
  echo "  npm install -g @ace-sdk/cli"
  exit 1
fi

VERSION=$(ace-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
echo "ace-cli found (version: $VERSION)"
echo ""
```

### Step 2: Check Authentication Status (CRITICAL)

```bash
AUTH_STATUS=$(ace-cli whoami --json 2>&1 || echo '{"authenticated": false}')
AUTHENTICATED=$(echo "$AUTH_STATUS" | jq -r '.authenticated // false')
```

**If NOT authenticated** (most common case for new users):

Show this message and **EXIT**:
```
Not logged in to ACE.

Please run /ace-login first to authenticate, then run /ace-configure again.

The login process will:
1. Display a verification URL and code
2. You open the URL in your browser
3. Enter the code to authorize
4. Return here and run /ace-configure
```

**Do NOT continue** - user must login first.

**If authenticated**, show status and continue:
```
Authenticated as: user@example.com
Session: Expires in 10 hours

Proceeding with configuration...
```

### Step 3: Get Organizations

```bash
ORGS_JSON=$(ace-cli orgs --json 2>&1)
ORG_COUNT=$(echo "$ORGS_JSON" | jq -r '.count // 0')
```

**If no organizations** (rare edge case):
```
No organizations found for your account.

Please contact your administrator or create an organization at:
https://ace.code-engine.app/organizations
```
Exit here.

**If organizations found**, parse them for display:
```bash
# Extract organization list
ORGS=$(echo "$ORGS_JSON" | jq -r '.organizations[] | "\(.org_id)|\(.org_name)|\(.role)"')
```

### Step 4: Organization Selection

**Use AskUserQuestion** to let user select organization:

Build options dynamically from the organizations list. For example:
```javascript
{
  questions: [
    {
      question: "Which organization should this project use?",
      header: "Organization",
      multiSelect: false,
      options: [
        // For each org in ORGS:
        {
          label: "org_name (role)",
          description: "org_id"
        }
        // Example:
        // { label: "Code Engine (owner)", description: "org_34fYIlitYk4nyFuTvtsAzA6uUJF" }
      ]
    }
  ]
}
```

Extract the selected org_id from user's choice.

### Step 5: Get Projects for Selected Org

```bash
PROJECTS_JSON=$(ace-cli projects --org "$SELECTED_ORG_ID" --json 2>&1)
PROJECT_LIST=$(echo "$PROJECTS_JSON" | jq -r '.projects // []')
PROJECT_COUNT=$(echo "$PROJECT_LIST" | jq 'length')
```

**If no projects** in selected organization:
```
No projects found in this organization.

Create a new project at: https://ace.code-engine.app/projects
Or select a different organization.
```

**If projects found**, parse for display:
```bash
# Extract project list
PROJECTS=$(echo "$PROJECT_LIST" | jq -r '.[] | "\(.project_id)|\(.project_name)"')
```

### Step 6: Project Selection

**Use AskUserQuestion** to let user select project:

```javascript
{
  questions: [
    {
      question: "Which project should be configured for this codebase?",
      header: "Project",
      multiSelect: false,
      options: [
        // For each project:
        {
          label: "project_name",
          description: "project_id"
        }
        // Example:
        // { label: "ce-claude-marketplace", description: "prj_abc123" }
      ]
    }
  ]
}
```

Extract the selected project_id.

### Step 7: Set Default Organization

```bash
ace-cli switch-org "$SELECTED_ORG_ID"
echo "Default organization set: $SELECTED_ORG_ID"
```

### Step 8: Verbosity Selection (Optional)

**Use AskUserQuestion** to let user choose display mode:

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
          description: "Full stats: patterns created, updated, quality scores, timing"
        },
        {
          label: "Compact",
          description: "Single line summary"
        }
      ]
    }
  ]
}
```

Map selection:
- "Detailed" → `VERBOSITY="detailed"`
- "Compact" → `VERBOSITY="compact"`

### Step 9: Save Project Configuration

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROJECT_CONFIG="$PROJECT_ROOT/.claude/settings.json"

mkdir -p "$PROJECT_ROOT/.claude"

cat > "$PROJECT_CONFIG" <<EOF
{
  "env": {
    "ACE_ORG_ID": "$SELECTED_ORG_ID",
    "ACE_PROJECT_ID": "$SELECTED_PROJECT_ID",
    "ACE_VERBOSITY": "$VERBOSITY"
  }
}
EOF

echo "Project configuration saved:"
echo "  Location: $PROJECT_CONFIG"
echo "  Organization: $SELECTED_ORG_ID"
echo "  Project: $SELECTED_PROJECT_ID"
echo "  Verbosity: $VERBOSITY"
```

### Step 10: Verify Configuration

```bash
echo ""
echo "Verifying configuration..."

STATUS=$(ace-cli status --json 2>&1 || echo '{"error": true}')
if echo "$STATUS" | jq -e '.error' >/dev/null 2>&1; then
  echo "Configuration saved but verification failed."
  echo "This may be normal if the project is new."
else
  PATTERN_COUNT=$(echo "$STATUS" | jq -r '.playbook.total_patterns // 0')
  echo "ACE connected successfully!"
  echo "  Patterns in playbook: $PATTERN_COUNT"
fi
```

### Step 11: Show Summary

```bash
echo ""
echo "ACE Configuration Complete!"
echo ""
echo "Configured:"
echo "  Organization: $SELECTED_ORG_NAME"
echo "  Project: $SELECTED_PROJECT_NAME"
echo "  Verbosity: $VERBOSITY"
echo ""
echo "Next steps:"
echo "1. Optional: /ace-bootstrap to populate playbook from codebase"
echo "2. Start coding - hooks will auto-search patterns!"
echo ""
echo "Useful commands:"
echo "  /ace-status  - Check connection and playbook stats"
echo "  /ace-search  - Search for specific patterns"
echo "  /ace-learn   - Manually capture learning"
```

## Handling Existing Configuration

**If `.claude/settings.json` already exists with ACE config:**

1. Read existing values:
```bash
EXISTING_ORG=$(jq -r '.env.ACE_ORG_ID // empty' "$PROJECT_CONFIG" 2>/dev/null || echo "")
EXISTING_PROJECT=$(jq -r '.env.ACE_PROJECT_ID // empty' "$PROJECT_CONFIG" 2>/dev/null || echo "")
```

2. **Use AskUserQuestion** to ask what to do:
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
          label: "Reconfigure",
          description: "Choose different organization and/or project"
        }
      ]
    }
  ]
}
```

3. If "Keep existing", show current config and exit:
```
Keeping existing configuration:
  Organization: org_xxxxx
  Project: prj_xxxxx

Run /ace-status to verify connection.
```

## Project Config Format

The `.claude/settings.json` file contains environment variables for ACE hooks:

```json
{
  "env": {
    "ACE_ORG_ID": "org_xxxxx",
    "ACE_PROJECT_ID": "prj_xxxxx",
    "ACE_VERBOSITY": "detailed"
  }
}
```

**Fields:**
- `ACE_ORG_ID`: Organization identifier (from whoami)
- `ACE_PROJECT_ID`: Project identifier (from projects list)
- `ACE_VERBOSITY`: Display mode (`detailed` or `compact`)

## Error Handling

### "Not authenticated"
```
Not logged in to ACE.
Run /ace-login first to authenticate.
```

### "Token expired"
```
ACE session expired.
Run /ace-login to re-authenticate.
```

### "No organizations found"
```
No organizations found for your account.
Contact your administrator or visit https://ace.code-engine.app
```

### "No projects in organization"
```
No projects found in selected organization.
Create a project at https://ace.code-engine.app/projects
```

### "ace-cli command failed"
```
ace-cli command failed. Check:
1. ace-cli is installed: npm install -g @ace-sdk/cli
2. You're authenticated: ace-cli whoami
3. Network connectivity to ACE server
```

## See Also

- `/ace-login` - Authenticate before configuring
- `/ace-status` - Verify configuration
- `/ace-bootstrap` - Initialize playbook from codebase
- `ace-cli whoami --json` - View authentication status
- `ace-cli orgs --json` - List organizations
- `ace-cli projects --org <id> --json` - List projects
