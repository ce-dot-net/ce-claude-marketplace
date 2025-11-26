# ACE Configure Command - Research Summary

## Current Implementation Status

### Overview
The `/ace:ace-configure` command is already **designed and documented** with full AskUserQuestion interactive forms support. The command spec exists in `/plugins/ace/commands/ace-configure.md` but the actual implementation (the executable command that Claude runs) has **not yet been created**.

---

## Current Implementation Approach

### Design Pattern (from ace-configure.md)
The command uses a **5-step bash + AskUserQuestion hybrid approach**:

1. **Version Check**: Verify ce-ace CLI >= 1.0.2 is installed
2. **Scope Detection**: Auto-detect global/project/both based on arguments and git status
3. **Global Configuration** (if needed): 
   - Collect server URL via AskUserQuestion
   - Collect API token via AskUserQuestion
   - Validate token and fetch org/project info
   - Select project via AskUserQuestion
   - Save to `~/.config/ace/config.json`
4. **Project Configuration** (if needed):
   - Read global config
   - Handle single-org vs multi-org modes
   - Select org/project via AskUserQuestion
   - Write `.claude/settings.json`
5. **Summary**: Display completion status

---

## Fields to Collect from User

### Global Configuration (Global Config File)

**Server URL** (via AskUserQuestion)
- **Options**: Production, Localhost, Other
- Maps to:
  - Production → `https://ace-api.code-engine.app`
  - Localhost → `http://localhost:9000`
  - Other → Custom input field

**API Token** (via AskUserQuestion)
- **Format**: `ace_` followed by 48 alphanumeric characters
- **Example**: `ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU`
- **Input**: Text field for user-provided token
- **Validation**: Token validated against server with `ce-ace config validate --json`

**Organization** (via AskUserQuestion, if multi-org)
- **Options**: Dynamically built from validation response
- **Source**: `ce-ace config validate` returns `projects` array
- **Selection**: User chooses org, system fetches projects for that org

**Project** (via AskUserQuestion)
- **Options**: Dynamically built from org's project list
- **Format**: `prj_` followed by 16 hexadecimal characters
- **Example**: `prj_d3a244129d62c198`
- **Source**: Returned from `ce-ace config validate --json`

### Project Configuration (.claude/settings.json)

After collecting org/project info, write to `.claude/settings.json`:

**Multi-Org Mode**:
```json
{
  "env": {
    "ACE_ORG_ID": "org_xxxxx",
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

**Single-Org Mode**:
```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

---

## ce-ace CLI Reference

### Version Check
```bash
ce-ace --version  # Should return >= 1.0.2 (current is 1.0.9)
```

### Configuration Commands
```bash
# Validate token and fetch org/project info
ce-ace config validate --json

# Save configuration
ce-ace config \
  --server-url "$SERVER_URL" \
  --api-token "$API_TOKEN" \
  --project-id "$PROJECT_ID" \
  --json

# Display current config
ce-ace config show

# Environment variable support (for validation)
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_xxxxx"
ce-ace config validate --json
```

### Output Format (ce-ace config validate --json)
```json
{
  "org_id": "org_34fYIlitYk4nyFuTvtsAzA6uUJF",
  "org_name": "Organization Name",
  "projects": [
    {
      "project_id": "prj_d3a244129d62c198",
      "project_name": "My Project"
    },
    {
      "project_id": "prj_another_project_id",
      "project_name": "Another Project"
    }
  ]
}
```

---

## What Needs to Be Updated

### 1. Implementation Needed
The command spec exists but Claude needs to implement it as an executable. The ace-configure.md file contains all the detailed instructions for what Claude should do step-by-step.

### 2. AskUserQuestion Integration
The spec already includes full AskUserQuestion designs for:
- Server URL selection (Production/Localhost/Other)
- API token input (I have a token / I need to get a token)
- Organization selection (dynamic options from validation response)
- Project selection (dynamic options from org's projects)

### 3. Output File Format (.claude/settings.json)
Current format in repository:
```json
{
  "env": {
    "ACE_ORG_ID": "org_34fYIlitYk4nyFuTvtsAzA6uUJF",
    "ACE_PROJECT_ID": "prj_d3a244129d62c198"
  }
}
```

This matches the spec's multi-org format. For single-org, only `ACE_PROJECT_ID` is included.

---

## Structure of .claude/settings.json

### Multi-Org (Default)
```json
{
  "env": {
    "ACE_ORG_ID": "org_xxxxx",
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

**When to use**: When global config has multiple organizations
- Set by: `/ace:configure` global setup
- Detected by: Checking if `~/.config/ace/config.json` has `orgs` field

### Single-Org
```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

**When to use**: When global config has single org only
- Set by: `/ace:configure` global setup  
- Detected by: Checking if `~/.config/ace/config.json` has no `orgs` field

---

## Global Config Structure (~/.config/ace/config.json)

### Single-Org Mode
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxx",
  "projectId": "prj_xxxxx",
  "cacheTtlMinutes": 120
}
```

### Multi-Org Mode
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

---

## Implementation Checklist

### Prerequisites
- [x] ce-ace CLI >= 1.0.2 (current: 1.0.9) ✓
- [x] bash environment with jq ✓
- [x] git (for project detection) ✓

### AskUserQuestion Integration Needed
- [ ] Server URL selection form
- [ ] API token input form
- [ ] Organization selection form (multi-org)
- [ ] Project selection form
- [ ] Token retrieval guidance (if user needs token)

### Bash Integration Needed
- [ ] Version validation
- [ ] Scope detection (global/project/both)
- [ ] Token validation via ce-ace CLI
- [ ] Global config save via ce-ace CLI
- [ ] Project config file creation
- [ ] Error handling for all steps

### Output Files
- [ ] `~/.config/ace/config.json` (global config)
- [ ] `.claude/settings.json` (project config)

---

## Key Design Decisions

1. **Two-File Approach**: Separates global settings (~/.config/ace/config.json) from project settings (.claude/settings.json)

2. **Dynamic Options**: Project list is fetched from server, not hardcoded

3. **Multi-Org Support**: Detects whether user has single or multiple orgs and adjusts workflow

4. **Environment Variable Fallback**: For validation step, uses environment variables instead of CLI flags (workaround for ce-ace CLI limitations)

5. **Non-Interactive Modes**: Supports `--global` and `--project` flags for selective reconfiguration

6. **Helpful Error Messages**: Each step provides clear feedback and helpful next steps

---

## Example User Flows

### First-Time Setup (Both Global + Project)
```
User: /ace:configure
  ↓
Check ce-ace version ✓
  ↓
Ask: Server URL? → Production selected
  ↓
Ask: API token? → User provides "ace_xxxxx"
  ↓
Validate: ace_xxxxx against server ✓
  ↓
Ask: Which project? → "My Project" selected (prj_d3a244129d62c198)
  ↓
Save: ~/.config/ace/config.json ✓
  ↓
Create: .claude/settings.json ✓
  ↓
Show summary ✓
```

### Reconfigure Project Only
```
User: /ace:configure --project
  ↓
Read: ~/.config/ace/config.json (already configured)
  ↓
Detect: Multi-org mode
  ↓
Ask: Which org? → "My Org" selected
  ↓
Ask: Which project? → Different project selected
  ↓
Update: .claude/settings.json ✓
```

---

## Related Files

- **Command Spec**: `/plugins/ace/commands/ace-configure.md`
- **Current Settings**: `.claude/settings.json`
- **Plugin Config**: `/plugins/ace/plugin.PRODUCTION.json`
- **Configuration Guide**: `/plugins/ace/docs/guides/CONFIGURATION.md`
- **Hooks**: `/plugins/ace/hooks/hooks.json`
- **CE-ACE CLI**: Installed globally (v1.0.9)

---

## Summary

**Status**: Fully designed, not yet implemented

**What Exists**:
- Detailed specification in ace-configure.md
- AskUserQuestion designs for all user inputs
- ce-ace CLI with validation support
- .claude/settings.json file format

**What's Missing**:
- The actual executable command that Claude runs
- Integration of AskUserQuestion prompts
- Bash wrapper orchestrating the 5-step flow

**Scope**: Well-defined and ready to implement following the ac-configure.md specification.
