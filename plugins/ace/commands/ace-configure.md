---
disable-model-invocation: true
description: Configure ACE server connection settings interactively
argument-hint: "[--global] [--project]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(jq:*), Bash(npm:*), Bash(mkdir:*), Bash(cat:*), Bash(git:*), Read
---

# Configure ACE Connection (8.1.0)

Interactive configuration wizard. Where mods run, the ACE mod answers this command itself (a name-matched
suggestion and one [Verbinden] button); this markdown is the fallback.

**IMPORTANT**: This command requires prior authentication via `/ace-login`.

## What This Does

1. Verifies user is authenticated (via `ace-cli whoami`)
2. **Shows current configuration** (if exists)
3. **Fetches FRESH** organization and project lists (not cached)
4. Lets user select organization and project
5. Writes the tracked binding `.ace/config.json` (`{orgId, projectId}`, nothing else) at the MAIN checkout root,
   fixing `.gitignore` (`.ace/*` + `!.ace/config.json`) only after the user confirmed the shown diff.
   `.claude/settings.json` is never written.

**v5.4.18 Changes**:
- Always shows current config before prompting
- Fetches fresh org/project lists (shows newly created projects)

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
if ! ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version >/dev/null 2>&1; then
  echo "ACE CLI not found"
  echo ""
  echo "Installation required:"
  echo "  /ace:ace-install-cli"
  exit 1
fi

VERSION=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
echo "ACE CLI found (version: $VERSION)"
echo ""
```

### Step 2: Check Authentication Status (CRITICAL)

```bash
AUTH_STATUS=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli whoami --json 2>&1 || echo '{"authenticated": false}')
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

### Step 3: Fetch FRESH Organizations (Always From Server)

**v5.4.18**: Always fetch fresh data to show newly added orgs/projects.

```bash
# Fetch FRESH organization list from server (not cached)
ORGS_JSON=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli orgs --json 2>&1)
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

### Step 5: Fetch FRESH Projects for Selected Org

**v5.4.18**: Always fetch fresh project list (shows newly created projects).

```bash
# Fetch FRESH project list from server (not cached)
PROJECTS_JSON=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli projects --org "$SELECTED_ORG_ID" --json 2>&1)
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

### Step 7: Preview the binding (nothing written yet)

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --bind "$SELECTED_ORG_ID" "$SELECTED_PROJECT_ID"
```

Show the user the output (the file and, when `.gitignore` ignores it, the diff) and **use AskUserQuestion**:
"Write this binding?" with "Write" / "Cancel".

### Step 8: Write it (only after "Write")

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --bind "$SELECTED_ORG_ID" "$SELECTED_PROJECT_ID" --yes
```

Nothing is staged or committed. Tell the user to commit `.ace/config.json`: then every clone and worktree is bound.

It writes through `ace-cli init --json --fix-gitignore` (in a linked worktree: the MAIN checkout's file). Show every
`ACE ▼` line it prints. When it names a worktree-local `.ace/config.json` that overrides the main checkout's binding
(`--remove-shadow <path>`), **use AskUserQuestion** "Remove that file?" with "Entfernen" / "Keep"; only after
"Entfernen":

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --remove-shadow "$SHADOW_PATH"
```

### Step 10: Verify Configuration

```bash
echo ""
echo "Verifying configuration..."

CTX="$("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --shell)" || exit 1  # 8.1.0: the one binding lookup
eval "$CTX"
STATUS=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli status --json --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" 2>&1 || echo '{"error": true}')
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

## Handling Existing Configuration (Step 2.5 - After Auth Check)

**v5.4.18**: Always show current config, then proceed to selection.

**Show the current binding (from the one core):**

1. Read and display it:
```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --json
```
(`source` says where it came from: `repo_file`, `settings_file` (legacy), `env`, `remote_map`; exit 5 = not bound.)

2. **Use AskUserQuestion** to ask what to do:
```javascript
{
  questions: [
    {
      question: "What would you like to do?",
      header: "Config Action",
      multiSelect: false,
      options: [
        {
          label: "Reconfigure (recommended)",
          description: "Fetch fresh org/project lists and select new settings"
        },
        {
          label: "Keep existing configuration",
          description: "No changes - use current org and project settings"
        }
      ]
    }
  ]
}
```

3. If "Keep existing", show current config and exit:
```
Keeping existing configuration:
  Organization: $EXISTING_ORG
  Project: $EXISTING_PROJECT

Run /ace-status to verify connection.
```

4. If "Reconfigure", continue to Step 3 (fetch fresh data)

## Project Config Format

The tracked `.ace/config.json` at the repo's main checkout root:

```json
{"orgId": "org_xxxxx", "projectId": "prj_xxxxx"}
```

Nothing else: a file with `apiToken` / `serverUrl` is refused. `.gitignore` must not ignore it (`.ace/*` plus
`!.ace/config.json`; a bare `.ace/` rule blocks the negation). Legacy `.claude/settings.json` `env.ACE_*` bindings
still resolve and are adopted into `.ace/config.json` automatically (opt out: `ACE_AUTO_ADOPT=0`).

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
1. ace-cli is installed: /ace:ace-install-cli
2. You're authenticated: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli whoami
3. Network connectivity to ACE server
```

## See Also

- `/ace-login` - Authenticate before configuring
- `/ace-status` - Verify configuration
- `/ace-bootstrap` - Initialize playbook from codebase
- `ace-cli whoami --json` - View authentication status
- `ace-cli orgs --json` - List organizations
- `ace-cli projects --org <id> --json` - List projects
