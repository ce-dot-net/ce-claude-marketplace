---
model: claude-haiku-4-5
description: Verify ACE plugin is properly configured and operational
argument-hint:
allowed-tools: Bash(ace-cli:*), Bash(jq:*), Bash(npm:*), Read
---

# ACE Test

Verify that the ACE plugin is properly configured and operational with ace-cli.

## What This Command Does

1. **Checks if ace-cli is installed**
   - Verifies `ace-cli` command is available
   - Shows installed version

2. **Tests ACE server connectivity**
   - Runs `ace-cli doctor` diagnostics
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
echo "[1/4] Checking ace-cli installation..."
if command -v ace-cli >/dev/null 2>&1; then
  VERSION=$(ace-cli --version 2>&1 | head -1)
  echo "✅ ace-cli found: $VERSION"
else
  echo "❌ ace-cli not found"
  echo "   Install: npm install -g @ace-sdk/cli"
  exit 1
fi
echo ""
```

### Step 2: Test ACE Server Connectivity

```bash
# Test 2: Server Connectivity
echo "[2/4] Testing ACE server connectivity..."

export ACE_ORG_ID=$(jq -r '.env.ACE_ORG_ID // .orgId // empty' .claude/settings.json 2>/dev/null || echo "")
export ACE_PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // .projectId // empty' .claude/settings.json 2>/dev/null || echo "")

if [ -z "$ACE_PROJECT_ID" ]; then
  echo "❌ No project configured"
  echo "   Run: /ace:ace-configure"
  exit 1
fi

# Run doctor command - CLI reads org/project from env vars automatically
# Filter out CLI update notifications (💡 lines) that break JSON parsing
RAW_DOCTOR=$(ace-cli doctor --json 2>&1)
DOCTOR_EXIT_CODE=$?
DOCTOR_RESULT=$(echo "$RAW_DOCTOR" | grep -v '^💡' | grep -v '^$')

if [ $DOCTOR_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Doctor command failed"
  echo "$DOCTOR_RESULT"
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

# Resolve plugin root dynamically (mirrors ace-doctor)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/ce-dot-net-marketplace/ace/*/ 2>/dev/null | tail -1)}"

if [ -z "$PLUGIN_ROOT" ]; then
  echo "❌ Plugin root not found — is the ACE plugin installed?"
  echo "   Expected: ~/.claude/plugins/cache/ce-dot-net-marketplace/ace/<version>/"
else
  # Check key hook wrappers exist
  HOOKS_FOUND=0
  for WRAPPER in ace_before_task_wrapper.sh ace_stop_wrapper.sh ace_posttooluse_wrapper.sh; do
    if [ -f "$PLUGIN_ROOT/scripts/$WRAPPER" ]; then
      HOOKS_FOUND=$((HOOKS_FOUND + 1))
    fi
  done

  if [ "$HOOKS_FOUND" -eq 3 ]; then
    echo "✅ Hook wrappers: 3/3 key wrappers found"
  else
    echo "⚠️  Hook wrappers: $HOOKS_FOUND/3 found (see /ace:ace-doctor for details)"
  fi

  # Check hooks.json
  if [ -f "$PLUGIN_ROOT/hooks/hooks.json" ]; then
    HOOK_COUNT=$(jq -r '.hooks | length' "$PLUGIN_ROOT/hooks/hooks.json")
    echo "✅ hooks.json: $HOOK_COUNT hook events registered"
  else
    echo "❌ hooks.json not found at $PLUGIN_ROOT/hooks/hooks.json"
  fi
fi
echo ""
```

### Step 4: Test Basic ACE Operations

```bash
# Test 4: Basic Operations
echo "[4/4] Testing basic ACE operations..."

# Test status command - CLI reads org/project from env vars automatically
# Filter out CLI update notifications (💡 lines) that break JSON parsing
RAW_STATUS=$(ace-cli status --json 2>&1)
STATUS_EXIT_CODE=$?
STATUS_RESULT=$(echo "$RAW_STATUS" | grep -v '^💡' | grep -v '^$')

if [ $STATUS_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Status command failed"
  echo "$STATUS_RESULT"
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
   ❌ ace-cli not found
   → Install: npm install -g @ace-sdk/cli
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
   → Fallback: Confirm auth status with: ace-cli whoami --json
   ```

3. **Authentication Failed**
   ```
   Error: 401 Unauthorized
   → Device-code token missing or expired
   → Action: Run /ace:ace-login (re-authenticates via device-code)
   → Config path: ~/.config/ace/config.json (field: auth.token)
   ```

4. **Invalid Project**
   ```
   Error: 404 Project not found
   → Project ID doesn't exist or ACE_PROJECT_ID not configured
   → Action: Verify ACE_PROJECT_ID in .claude/settings.json (.env.ACE_PROJECT_ID)
   → Fallback: Run /ace:ace-configure to reconfigure
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
   → ~/.config/ace/config.json (global, device-code token) or .claude/settings.json missing
   → Action: Run /ace:ace-login (creates ~/.config/ace/config.json with auth.token)
   →         Run /ace:ace-configure (writes ACE_PROJECT_ID to .claude/settings.json)
   ```

## Available ACE Commands

All ACE operations use ace-cli:

**Core Commands**:
- `ace-cli status` - Get playbook statistics
- `ace-cli patterns` - View playbook patterns
- `ace-cli search --stdin` - Search for patterns
- `ace-cli learn` - Capture learning (via /ace:ace-learn)
- `ace-cli bootstrap` - Initialize from codebase
- `ace-cli clear` - Clear playbook
- `ace-cli export` - Export playbook to JSON
- `ace-cli import` - Import playbook from JSON
- `ace-cli top` - Get top-rated patterns
- `ace-cli doctor` - Run diagnostics
- `ace-cli config` - Manage configuration

**Error Handling**:

1. **CLI Not Found**
   ```
   Error: ace-cli command not found
   → ace-cli not installed
   → Action: npm install -g @ace-sdk/cli
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

Display the current ACE configuration (ACE 1.5 / ace-cli 4.x model):
- Auth status: verify with `ace-cli whoami --json` (device-code token at `~/.config/ace/config.json` under `auth.token`)
- Project ID: `ACE_PROJECT_ID` from `.claude/settings.json` (`.env.ACE_PROJECT_ID`)
- Server URL override (if set): `ACE_SERVER_URL` environment variable (baked into binary by default)
- Plugin version (resolved via `$CLAUDE_PLUGIN_ROOT` or `~/.claude/plugins/cache/ce-dot-net-marketplace/ace/<version>/plugin.json`)
- Learning mode (automatic/manual)

**Error Handling**:

1. **Configuration File Read Error**
   ```
   Error: Cannot read ~/.config/ace/config.json or .claude/settings.json
   → Permission denied or file corrupted
   → Action: Check file permissions (global config should be 600)
   → Fallback: Recreate config with /ace:ace-login and /ace:ace-configure
   ```

2. **Invalid JSON in Config**
   ```
   Error: Malformed configuration file
   → JSON parse error
   → Action: Show line/column of error
   → Fallback: Backup corrupted file, run /ace:ace-login to recreate
   ```

3. **Missing Required Fields**
   ```
   Warning: Configuration incomplete
   → auth.token (device-code) or ACE_PROJECT_ID missing
   → Action: List missing fields
   → Fallback: Run /ace:ace-login (auth) or /ace:ace-configure (project)
   ```

4. **Server URL Override**
   ```
   Note: Server URL is baked into the ace-cli binary (ace-cli 4.x)
   → It is NOT a user-editable field in ~/.config/ace/config.json
   → To override: set ACE_SERVER_URL environment variable
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
Plugin Version: 7.x
Config Files:
  - Global: ~/.config/ace/config.json (auth.token — device-code, ace-cli 4.x)
  - Project: .claude/settings.json (env.ACE_PROJECT_ID, env.ACE_ORG_ID)

🎯 Everything looks good! ACE automatic learning is ready.
```

## Example Failure Output

```
❌ ACE Agent Skill Status

Agent Skill: ace:ace-learning
Status: ❌ NOT FOUND

The ACE plugin is not responding as expected. Possible causes:
1. Plugin not installed — check: ls ~/.claude/plugins/cache/ce-dot-net-marketplace/ace/
2. ace-cli 4.x not installed — install: npm install -g @ace-sdk/cli
3. Not authenticated — run: ace-cli login (device-code auth)
4. ACE_PROJECT_ID not configured — run: /ace:ace-configure

Troubleshooting Steps:
1. Check plugin installation: ls ~/.claude/plugins/cache/ce-dot-net-marketplace/ace/
2. Verify CLI: ace-cli --version  (must be 4.x+)
3. Verify auth: ace-cli whoami --json
4. Run full diagnostics: /ace:ace-doctor
```

## Common Issues

### Issue: ACE Server Connection Failed
**Symptom**: ace-cli commands return connection error or authentication failed
**Solution**:
1. Verify auth: `ace-cli whoami --json` (device-code token in `~/.config/ace/config.json` under `auth.token`)
2. Re-authenticate if needed: `ace-cli login`
3. Verify project is configured: `ACE_PROJECT_ID` in `.claude/settings.json` (`.env.ACE_PROJECT_ID`)
4. Check network connectivity
5. Run full diagnostics: `/ace:ace-doctor`

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
