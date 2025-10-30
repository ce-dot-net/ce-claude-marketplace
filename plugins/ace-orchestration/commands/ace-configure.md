---
description: Configure ACE server connection settings interactively
---

# Configure ACE Connection

Interactive configuration wizard for ACE server connection.

## Instructions for Claude

When the user runs `/ace-configure`, follow these steps:

1. **Use AskUserQuestion Tool for Interactive Configuration:**

   IMPORTANT: ALWAYS use the AskUserQuestion tool to create an interactive UI. DO NOT use plain text prompts.

   ```javascript
   AskUserQuestion({
     questions: [
       {
         question: "What is your ACE server URL?",
         header: "Server URL",
         multiSelect: false,
         options: [
           {
             label: "https://ace-api.code-engine.app",
             description: "Official Code Engine ACE server"
           },
           {
             label: "Custom URL",
             description: "Enter your own server URL (for enterprise/custom installations)"
           }
         ]
       },
       {
         question: "What is your ACE API token? (Get from server logs)",
         header: "API Token",
         multiSelect: false,
         options: [
           {
             label: "Enter token",
             description: "Paste your ACE API token (starts with ace_)"
           }
         ]
       },
       {
         question: "What is your ACE project ID? (Get from dashboard)",
         header: "Project ID",
         multiSelect: false,
         options: [
           {
             label: "Enter project ID",
             description: "Your project identifier (usually starts with prj_)"
           }
         ]
       }
     ]
   })
   ```

   - If user selects "Custom URL" or "Other", prompt them to enter the custom value
   - API Token must start with `ace_`
   - Project ID usually starts with `prj_`
   - If user selects "Other" for any field, ask them to provide the value

2. **Save Configuration to PROJECT ROOT (NOT user home):**
   - IMPORTANT: Save to project root, NOT `~/.ace/`!
   - Find the project root using: `git rev-parse --show-toplevel` (or use current directory if not in git)
   - Create `.ace` directory in project root if it doesn't exist: `mkdir -p .ace`
   - Write configuration to **PROJECT-LEVEL** `.ace/config.json` with the provided values:
     ```json
     {
       "serverUrl": "[provided URL]",
       "apiToken": "[provided token]",
       "projectId": "[provided project ID]"
     }
     ```
   - DO NOT write to `~/.ace/config.json` (that's the global fallback, not the primary location)
   - Use the Write tool with an absolute path like: `/path/to/project/.ace/config.json`
   - Show success message with the FULL config file path

3. **Next Steps:**
   - Configuration saved! No restart needed.
   - Suggest running `/ace-orchestration:ace-claude-init` to add ACE instructions to project CLAUDE.md
   - Suggest running `/ace-orchestration:ace-status` to verify connection
   - Optionally suggest `/ace-orchestration:ace-bootstrap` to populate initial playbook patterns

## Example Interaction

```
User: /ace-configure

Claude: I'll help you configure your ACE server connection.

[Claude finds project root]
📂 Project root: /Users/you/my-project

What is your ACE server URL? (default: http://localhost:9000)
User: [press Enter or type URL]

What is your ACE API token? (Get from your ACE server logs)
User: ace_your_api_token_here

What is your ACE project ID? (Get from your ACE server dashboard)
User: prj_your_project_id

[Claude writes config file to PROJECT ROOT - NOT user home]

✅ Configuration saved to: /Users/you/my-project/.ace/config.json

⚠️  Note: Config was saved to PROJECT root, not ~/.ace/
    This ensures your team can share the same ACE server configuration.

✅ .gitignore automatically updated: .ace/ and .ace-cache/ added automatically
    (The ACE plugin manages this via SessionStart hook)

Next steps:
1. Restart Claude Code (Cmd+Q, then reopen)
2. Run: /ace-orchestration:ace-status to verify connection
3. .gitignore is managed automatically - no manual action needed!
```

## Configuration Storage

**ACE is project-scoped:** Configuration MUST be saved to project root (`./.ace/config.json`):
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_your_api_token_here",
  "projectId": "prj_your_project_id"
}
```

**Location**: `.ace/config.json` in your git repository root (or current directory if not in a git repo)

**Why project-scoped only:**
- ✅ Each project has its own ACE playbook (learned patterns are project-specific)
- ✅ Each project can use different ACE servers or credentials
- ✅ Configuration travels with the repository
- ✅ Team members automatically share the same ACE server
- ✅ No global state - clean separation between projects

## Alternative: Environment Variables

You can also set configuration via environment variables:
```bash
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_your_api_token_here"
export ACE_PROJECT_ID="prj_your_project_id"
```

Add to `~/.zshrc` or `~/.bashrc` to persist across sessions.

## Alternative: Claude Code Settings

You can add to `~/.config/claude-code/settings.json`:
```json
{
  "env": {
    "ACE_SERVER_URL": "https://ace-api.code-engine.app",
    "ACE_API_TOKEN": "ace_your_api_token_here",
    "ACE_PROJECT_ID": "prj_your_project_id"
  }
}
```

## Configuration Priority

**IMPORTANT:** ACE is **project-scoped only**. Each project has its own ACE configuration and playbook.

The MCP client checks for configuration in this order:
1. Environment variables (`ACE_SERVER_URL`, `ACE_API_TOKEN`, `ACE_PROJECT_ID`) - highest priority
2. **Project-level config**: `<project-root>/.ace/config.json` - **REQUIRED for file-based config**
3. Claude Code settings.json (`~/.config/claude-code/settings.json`)
4. Default values (lowest priority)

**There is NO global `~/.ace/config.json` fallback.** ACE is designed to be project-scoped - each repository has its own configuration and learned patterns.

## Getting Your Credentials

### Server URL
Your ACE server URL:
- **Production (recommended)**: `https://ace-api.code-engine.app`
- **Local development**: `http://localhost:9000`
- **Custom**: Your own ACE server instance

### API Token
Generated by your ACE server on first start. Check:
- Server logs: Look for "API Token: ace_xxxxx"
- Server admin panel
- Ask your team's ACE administrator

### Project ID
Your project identifier in ACE. Check:
- ACE dashboard
- Server admin panel
- Ask your team's ACE administrator

## Troubleshooting

### "Cannot connect to ACE server"
1. Check server URL is correct: `curl https://ace-api.code-engine.app/api/health`
2. Verify ACE server is running (or use official production server)
3. Check firewall/network settings

### "Authentication failed"
1. Verify API token is correct
2. Check token hasn't expired
3. Generate new token from ACE server

### "Project not found"
1. Verify project ID exists in ACE server
2. Check you have access to the project
3. Create new project in ACE dashboard

## See Also

- `/ace-orchestration:ace-status` - Check current ACE connection status
- `/ace-init` - Initialize pattern discovery
- Plugin installation guide: `INSTALL.md`

## Running the Configuration

This command runs an interactive wizard that prompts for your ACE server details and saves the configuration to your project directory.

## Testing the Configuration

After saving, test your connection:

```bash
/ace-orchestration:ace-status
```

This will show if ACE server is reachable and authenticated.

## Manual Configuration

If you prefer to configure manually, create `.ace/config.json` in your project root:

```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxxxxxxxxxx",
  "projectId": "prj_xxxxxxxxxxxxx"
}
```

## Getting Your Credentials

### 1. Server URL

Your ACE server URL. Common values:
- **Production (recommended)**: `https://ace-api.code-engine.app`
- Local development: `http://localhost:9000`
- Custom server: Your own instance URL

### 2. API Token

Generated by ACE server. Find it in:
- Server startup logs: `"API Token: ace_xxxxx"`
- Server dashboard under Settings > API Keys
- Ask your team's ACE administrator

### 3. Project ID

Your project identifier. Find it in:
- ACE dashboard project list
- Server admin panel
- Ask your team's ACE administrator

## Troubleshooting

### "Cannot save configuration"

**If saving to project root fails:**
```bash
# Check write permissions
ls -la .ace/

# Create directory manually if needed
mkdir -p .ace
chmod 755 .ace
```

**Note:** There is NO global `~/.ace/config.json` file in ACE's design. If you have one, it's likely a leftover from testing or incorrect configuration. ACE is project-scoped only - each project must have its own `.ace/config.json` file.

### "Connection test failed"

1. Verify server URL: `curl https://ace-api.code-engine.app/api/health`
2. Check ACE server is running (production server is always online)
3. Verify firewall/network allows HTTPS connections

### "Authentication failed"

1. Check API token is correct (no extra spaces)
2. Token may have expired - generate new one
3. Verify token has correct permissions

## See Also

- `/ace-orchestration:ace-status` - Test your current configuration
- `/ace-init` - Initialize pattern discovery
- Installation guide: `plugins/ace-orchestration/INSTALL.md`
