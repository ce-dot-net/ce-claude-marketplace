---
description: Verify ACE plugin is properly configured and operational
argument-hint:
---

# ACE Test

Verify that the ACE plugin is properly configured and operational with ce-ace CLI.

## What This Command Does

1. **Checks if ce-ace CLI is installed**
   - Verifies `ce-ace` command is available
   - Shows installed version

2. **Tests ACE server connectivity**
   - Runs `ce-ace doctor` diagnostics
   - Shows connection status

3. **Verifies hooks configuration**
   - Checks if hook wrapper scripts exist
   - Confirms hooks.json is properly configured

4. **Provides diagnostic information**
   - Helpful for troubleshooting
   - Confirms plugin setup is correct

## How to Use

Simply run:
```
/ace-test
```

## Verification Steps

### Step 1: Check CLI Installation

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "🔍 ACE Plugin Test"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Test 1: CLI Installation
echo "[1/4] Checking ce-ace CLI installation..."
if command -v ce-ace >/dev/null 2>&1; then
  VERSION=$(ce-ace --version 2>&1 | head -1)
  echo "✅ ce-ace CLI found: $VERSION"
else
  echo "❌ ce-ace CLI not found"
  echo "   Install: npm install -g @ce-dot-net/ce-ace-cli"
  exit 1
fi
echo ""
```

### Step 2: Test ACE Server Connectivity

```bash
# Test 2: Server Connectivity
echo "[2/4] Testing ACE server connectivity..."

ORG_ID=$(jq -r '.orgId // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // empty' .claude/settings.json 2>/dev/null || echo "")

# Try env wrapper format
if [ -z "$ORG_ID" ] || [ -z "$PROJECT_ID" ]; then
  ORG_ID=$(jq -r '.env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
fi

if [ -z "$PROJECT_ID" ]; then
  echo "❌ No project configured"
  echo "   Run: /ace:ace-configure"
  exit 1
fi

# Run doctor command
if [ -n "$ORG_ID" ]; then
  DOCTOR_RESULT=$(ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" doctor 2>&1)
else
  DOCTOR_RESULT=$(ce-ace --json --project "$PROJECT_ID" doctor 2>&1)
fi

# Parse results
PASSED=$(echo "$DOCTOR_RESULT" | jq -r '.summary.passed // 0')
FAILED=$(echo "$DOCTOR_RESULT" | jq -r '.summary.failed // 0')

if [ "$FAILED" -eq 0 ]; then
  echo "✅ Server connectivity: $PASSED/$((PASSED + FAILED)) checks passed"
else
  echo "⚠️  Server connectivity: $FAILED checks failed"
  echo "$DOCTOR_RESULT" | jq -r '.results[] | select(.status != "pass") | "   - \(.check): \(.message)"'
fi
echo ""
```

### Step 3: Verify Hooks Configuration

```bash
# Test 3: Hooks Configuration
echo "[3/4] Checking hooks configuration..."

PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace"

# Check hook wrappers
HOOKS_FOUND=0
if [ -f "$PLUGIN_DIR/scripts/ace_before_task_wrapper.sh" ]; then
  HOOKS_FOUND=$((HOOKS_FOUND + 1))
fi
if [ -f "$PLUGIN_DIR/scripts/ace_after_task_wrapper.sh" ]; then
  HOOKS_FOUND=$((HOOKS_FOUND + 1))
fi

if [ "$HOOKS_FOUND" -eq 2 ]; then
  echo "✅ Hook wrappers: 2/2 found"
else
  echo "⚠️  Hook wrappers: $HOOKS_FOUND/2 found"
fi

# Check hooks.json
if [ -f "$PLUGIN_DIR/hooks/hooks.json" ]; then
  HOOK_COUNT=$(jq -r '.hooks | length' "$PLUGIN_DIR/hooks/hooks.json")
  echo "✅ hooks.json: $HOOK_COUNT hooks registered"
else
  echo "❌ hooks.json not found"
fi
echo ""
```

### Step 4: Test Basic ACE Operations

```bash
# Test 4: Basic Operations
echo "[4/4] Testing basic ACE operations..."

# Test status command
if [ -n "$ORG_ID" ]; then
  STATUS_RESULT=$(ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" status 2>&1)
else
  STATUS_RESULT=$(ce-ace --json --project "$PROJECT_ID" status 2>&1)
fi

TOTAL_BULLETS=$(echo "$STATUS_RESULT" | jq -r '.total_bullets // 0')
echo "✅ Status command: Playbook has $TOTAL_BULLETS patterns"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All tests passed!"
echo ""
echo "Next steps:"
echo "  - Bootstrap playbook: /ace:ace-bootstrap"
echo "  - Search patterns: /ace:ace-search <query>"
echo "  - Capture learning: /ace:ace-learn"
```

**Error Handling**:

1. **CLI Not Found**
   ```
   ❌ ce-ace CLI not found
   → Install: npm install -g @ce-dot-net/ce-ace-cli
   ```

2. **Server Connection Failed**
   ```
   ⚠️  Server connectivity: checks failed
   → Run: /ace:ace-doctor for detailed diagnostics
   → Or: /ace:ace-configure to reconfigure
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
   → Action: Run /ace:ace-configure to set up credentials
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
   → Action: Run /ace:ace-configure to create config files
   → Fallback: Provide default configuration template
   ```

## Available ACE Commands

All ACE operations use ce-ace CLI:

**Core Commands**:
- `ce-ace status` - Get playbook statistics
- `ce-ace patterns` - View playbook patterns
- `ce-ace search --stdin` - Search for patterns
- `ce-ace learn` - Capture learning (via /ace:ace-learn)
- `ce-ace bootstrap` - Initialize from codebase
- `ce-ace clear` - Clear playbook
- `ce-ace export` - Export playbook to JSON
- `ce-ace import` - Import playbook from JSON
- `ce-ace top` - Get top-rated patterns
- `ce-ace doctor` - Run diagnostics
- `ce-ace config` - Manage configuration

**Error Handling**:

1. **CLI Not Found**
   ```
   Error: ce-ace command not found
   → ce-ace CLI not installed
   → Action: npm install -g @ce-dot-net/ce-ace-cli
   → Fallback: Check npm global bin is in PATH
   ```

2. **Tool Execution Failed**
   ```
   Error: Tool execution error
   → Tool exists but fails on invocation
   → Action: Check tool parameters and server logs
   → Fallback: Try with minimal parameters or default values
   ```

3. **Partial Setup**
   ```
   Warning: Some ACE components missing
   → Incomplete plugin installation
   → Action: Check hook wrappers and scripts exist
   → Fallback: Reinstall plugin from marketplace
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
   → Fallback: Recreate config with /ace:ace-configure
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
   → Fallback: Run /ace:ace-configure to complete setup
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

Agent Skill: ace:ace-learning
Status: ✅ LOADED
Description: Learn from execution feedback and update ACE playbook

ACE Server Connection:
Status: ✅ CONNECTED
Server: https://ace-api.code-engine.app
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
Learning Mode: Automatic (hook-based)
Plugin Version: 5.0.0
Config Files:
  - Global: ~/.config/ace/config.json (serverUrl, apiToken, cacheTtl)
  - Project: .claude/settings.json (projectId, orgId)

🎯 Everything looks good! ACE automatic learning is ready.
```

## Example Failure Output

```
❌ ACE Agent Skill Status

Agent Skill: ace:ace-learning
Status: ❌ NOT FOUND

The ACE Agent Skill is not loaded. Possible causes:
1. Plugin not installed in ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace/
2. Skill file missing or misconfigured
3. Claude Code plugin system not initialized

Troubleshooting Steps:
1. Check plugin installation: ls ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace/
2. Verify skill configuration in plugin.json
3. Restart Claude Code CLI
4. Check Claude Code logs for plugin loading errors
```

## Common Issues

### Issue: MCP Server Not Responding
**Symptom**: ace_status tool returns connection error
**Solution**:
1. Run `/ace:ace-configure` to set up connection
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
4. Manual test: Use `Skill(ace:ace-learning)` after completing work

## See Also

- `/ace:ace-status` - View playbook statistics
- `/ace:ace-patterns` - View learned patterns
- `/ace:ace-configure` - Configure ACE server connection
- `/ace:ace-bootstrap` - Initialize playbook from codebase

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
