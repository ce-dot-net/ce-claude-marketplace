---
description: Verify ACE Agent Skill is loaded and show its current configuration
argument-hint:
---

# ACE Test

Verify that the ACE Agent Skill (`ace-orchestration:ace-learning`) is loaded and operational.

## What This Command Does

1. **Checks if the Agent Skill is loaded**
   - Verifies `ace-orchestration:ace-learning` is available
   - Confirms automatic learning is enabled

2. **Shows current configuration**
   - Displays MCP server connection status
   - Shows playbook statistics
   - Lists available ACE tools

3. **Provides diagnostic information**
   - Helpful for troubleshooting
   - Confirms plugin setup is correct

## How to Use

Simply run:
```
/ace-test
```

## Verification Steps

### Step 1: Check Agent Skill Availability

Look for the `ace-orchestration:ace-learning` skill in the available skills list.

**Expected**: The skill should be present and marked as available.

**If Missing**: The ACE plugin may not be properly installed or the skill configuration may be incorrect. Check:
- Plugin is installed: `~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/`
- Skill file exists: Check the plugin's skills directory
- Claude Code plugins are properly loaded

**Error Handling**:
- Gracefully handle missing skill files
- Provide clear diagnostic messages
- Suggest recovery steps

### Step 2: Check MCP Server Status

```
Use the mcp__ace-pattern-learning__ace_status tool to verify connectivity.
```

**Expected Output**:
```json
{
  "total_bullets": 0,
  "by_section": {
    "strategies_and_hard_rules": 0,
    "useful_code_snippets": 0,
    "troubleshooting_and_pitfalls": 0,
    "apis_to_use": 0
  },
  "avg_confidence": 0.0,
  "top_helpful": [],
  "top_harmful": []
}
```

**Error Handling**:

1. **Connection Refused**
   ```
   Error: ECONNREFUSED
   → MCP server not running
   → Action: Check server is running at configured URL
   → Fallback: Suggest running /ace-orchestration:ace-configure
   ```

2. **Timeout**
   ```
   Error: Request timeout
   → Network issues or server overloaded
   → Action: Retry with exponential backoff
   → Fallback: Check ~/.config/ace/config.json for correct serverUrl
   ```

3. **Authentication Failed**
   ```
   Error: 401 Unauthorized
   → Invalid or missing API token
   → Action: Run /ace-orchestration:ace-configure to set up credentials
   → Fallback: Check ~/.config/ace/config.json for valid apiToken
   ```

4. **Invalid Project**
   ```
   Error: 404 Project not found
   → Project ID doesn't exist
   → Action: Verify projectId in .claude/settings.json
   → Fallback: Create new project or use existing one
   ```

5. **Server Error**
   ```
   Error: 500 Internal Server Error
   → ACE server malfunction
   → Action: Check server logs
   → Fallback: Restart ACE server
   ```

6. **Malformed Response**
   ```
   Error: Invalid JSON response
   → Server returned unexpected format
   → Action: Log raw response for debugging
   → Fallback: Check server version compatibility
   ```

7. **Missing Configuration**
   ```
   Error: Config file not found
   → ~/.config/ace/config.json or .claude/settings.json missing
   → Action: Run /ace-orchestration:ace-configure to create config files
   → Fallback: Provide default configuration template
   ```

### Step 3: List Available ACE Tools

Display all ACE-related MCP tools that should be available:

**Expected Tools**:
- `mcp__ace-pattern-learning__ace_learn` - Core learning function
- `mcp__ace-pattern-learning__ace_status` - Get playbook stats
- `mcp__ace-pattern-learning__ace_get_playbook` - View playbook
- `mcp__ace-pattern-learning__ace_clear` - Clear playbook
- `mcp__ace-pattern-learning__ace_init` - Initialize from git
- `mcp__ace-pattern-learning__ace_save_config` - Save configuration

**Error Handling**:

1. **Tool Not Found**
   ```
   Error: Tool mcp__ace-pattern-learning__ace_* not available
   → MCP server not registered or not running
   → Action: Check .claude/settings.json for MCP server definition
   → Fallback: Restart Claude Code to reload MCP servers
   ```

2. **Tool Execution Failed**
   ```
   Error: Tool execution error
   → Tool exists but fails on invocation
   → Action: Check tool parameters and server logs
   → Fallback: Try with minimal parameters or default values
   ```

3. **Partial Tool Availability**
   ```
   Warning: Some ACE tools missing
   → Incomplete MCP server setup
   → Action: List available vs expected tools
   → Fallback: Reinstall plugin or check .claude/settings.json
   ```

### Step 4: Show Configuration Summary

Display the current ACE configuration:
- Server URL (from `~/.config/ace/config.json` or environment)
- Project ID (from `.claude/settings.json`)
- API token status (present/missing, don't show actual token)
- Plugin version
- Learning mode (automatic/manual)

**Error Handling**:

1. **Configuration File Read Error**
   ```
   Error: Cannot read ~/.config/ace/config.json or .claude/settings.json
   → Permission denied or file corrupted
   → Action: Check file permissions (global config should be 600)
   → Fallback: Recreate config with /ace-orchestration:ace-configure
   ```

2. **Invalid JSON in Config**
   ```
   Error: Malformed configuration file
   → JSON parse error
   → Action: Show line/column of error
   → Fallback: Backup corrupted file, create new config
   ```

3. **Missing Required Fields**
   ```
   Warning: Configuration incomplete
   → serverUrl, apiToken, or projectId missing
   → Action: List missing fields
   → Fallback: Run /ace-orchestration:ace-configure to complete setup
   ```

4. **Invalid URL Format**
   ```
   Error: Invalid serverUrl format
   → URL doesn't match expected pattern
   → Action: Suggest correct format (e.g., https://ace-api.code-engine.app)
   → Fallback: Provide default URL options
   ```

## Example Success Output

```
✅ ACE Agent Skill Status

Agent Skill: ace-orchestration:ace-learning
Status: ✅ LOADED
Description: Learn from execution feedback and update ACE playbook

MCP Server Connection:
Status: ✅ CONNECTED
Server: https://ace-api.code-engine.app (or configured URL)
Project ID: prj_xxxxx

Playbook Statistics:
Total Bullets: 42
  - Strategies & Rules: 10
  - Code Snippets: 15
  - Troubleshooting: 12
  - API Patterns: 5
Average Confidence: 78%

Available ACE Tools:
✅ ace_learn - Core learning function
✅ ace_status - Get playbook stats
✅ ace_get_playbook - View playbook
✅ ace_clear - Clear playbook
✅ ace_init - Initialize from git
✅ ace_save_config - Save configuration

Configuration:
Learning Mode: Automatic (skill-based)
Plugin Version: 3.3.2
Config Files:
  - Global: ~/.config/ace/config.json (serverUrl, apiToken, cacheTtl)
  - Project: .claude/settings.json (projectId, MCP server)

🎯 Everything looks good! ACE automatic learning is ready.
```

## Example Failure Output

```
❌ ACE Agent Skill Status

Agent Skill: ace-orchestration:ace-learning
Status: ❌ NOT FOUND

The ACE Agent Skill is not loaded. Possible causes:
1. Plugin not installed in ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/
2. Skill file missing or misconfigured
3. Claude Code plugin system not initialized

Troubleshooting Steps:
1. Check plugin installation: ls ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/
2. Verify skill configuration in plugin.json
3. Restart Claude Code CLI
4. Check Claude Code logs for plugin loading errors
```

## Common Issues

### Issue: MCP Server Not Responding
**Symptom**: ace_status tool returns connection error
**Solution**:
1. Run `/ace-orchestration:ace-configure` to set up connection
2. Verify server URL is correct
3. Check server is running
4. Verify network connectivity

### Issue: No Bullets in Playbook
**Symptom**: ace_status shows 0 total bullets
**Solution**: This is normal for new installations. Bullets accumulate as you work:
- Complete substantial tasks (coding, debugging, API integration)
- Agent Skill will automatically trigger
- Patterns will be learned and stored

### Issue: Agent Skill Present but Not Triggering
**Symptom**: Skill exists but never invokes automatically
**Solution**:
1. Ensure you're doing substantial work (not simple Q&A)
2. Check skill description matches task type
3. Verify automatic invocation is enabled
4. Manual test: Use `Skill(ace-orchestration:ace-learning)` after completing work

## See Also

- `/ace-orchestration:ace-status` - View playbook statistics
- `/ace-orchestration:ace-patterns` - View learned patterns
- `/ace-orchestration:ace-configure` - Configure MCP server connection
- `/ace-init` - Initialize playbook from git history

## Technical Details

**Agent Skill Trigger Conditions**:
The skill automatically triggers after:
- Problem-solving & debugging
- Code implementation & refactoring
- API & tool integration
- Learning from failures
- Substantial multi-step tasks

**Not triggered for**:
- Simple Q&A responses
- Basic file reads
- Trivial informational queries

**Learning Pipeline**:
```
Work Completed → Agent Skill Triggers → ace_learn Called →
Reflector Analyzes → Curator Creates Updates → Playbook Updated
```

---

**Note**: This is a diagnostic command. It doesn't modify your playbook or configuration.
