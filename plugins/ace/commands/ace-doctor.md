---
description: Comprehensive ACE installation and health diagnostic
allowed-tools: Bash(ace-cli:*), Bash(jq:*), Bash(npm:*), Bash(curl:*), Bash(ls:*), Bash(test:*), Read
---

# ACE Doctor - Installation & Health Diagnostic

Comprehensive diagnostic tool that checks your entire ACE setup and identifies issues.

## Instructions for Claude

When the user runs `/ace:ace-doctor`, perform a complete health check of the ACE system.

### Diagnostic Flow

Run all checks in parallel for speed, then present organized results.

---

## 🏥 Diagnostic Checks

### Check 1: Plugin Installation

**What to Check**:
```bash
# Verify plugin directory structure
ls -la ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace/
```

**Expected Structure**:
```
ace/
├── commands/           # Slash commands (/ace-search, /ace-patterns, etc.)
├── hooks/
│   └── hooks.json     # Hook definitions
├── scripts/           # Hook wrapper scripts
│   ├── ace_install_cli.sh
│   ├── ace_before_task_wrapper.sh
│   ├── ace_task_complete_wrapper.sh
│   └── ace_after_task_wrapper.sh
├── plugin.json
└── CLAUDE.md
```

**Report**:
- ✅ Plugin installed correctly
- ⚠️ Plugin directory missing components
- ❌ Plugin not installed

**If Failed**:
```
❌ Plugin Installation: NOT FOUND

Recommended Actions:
1. Install plugin via Claude Code marketplace
2. OR install via symlink:
   ln -s /path/to/ace ~/.claude/plugins/ace
3. Restart Claude Code after installation
```

---

### Check 2: Global Configuration

**What to Check**:
```bash
# Check global config exists (XDG standard path)
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_PATH="$XDG_HOME/ace/config.json"
test -f "$CONFIG_PATH" && echo "EXISTS" || echo "MISSING"

# If exists, validate JSON and check required fields
jq -e '.serverUrl, .apiToken, .cacheTtlMinutes, .autoUpdateEnabled' "$CONFIG_PATH"
```

**Expected**:
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxx",
  "cacheTtlMinutes": 120,
  "autoUpdateEnabled": true
}
```

**Report**:
- ✅ Global config valid
- ⚠️ Global config exists but incomplete
- ❌ Global config missing

**If Failed**:
```
❌ Global Configuration: MISSING

Recommended Actions:
1. Run: /ace:ace-configure --global
2. Provide:
   - Server URL (https://ace-api.code-engine.app)
   - API Token (starts with ace_)
```

**If Incomplete**:
```
⚠️ Global Configuration: INCOMPLETE

Missing fields: apiToken, cacheTtlMinutes

Recommended Actions:
1. Run: /ace:ace-configure --global
2. This will preserve existing values and fill missing fields
```

---

### Check 3: Project Configuration

**What to Check**:
```bash
# Get project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

# Check project settings
test -f "$PROJECT_ROOT/.claude/settings.json" && echo "EXISTS" || echo "MISSING"

# If exists, validate ACE_PROJECT_ID env var
jq -e '.projectId' "$PROJECT_ROOT/.claude/settings.json"
```

**Expected**:
```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_xxxxx"
  }
}
```

**Report**:
- ✅ Project config valid with ACE_PROJECT_ID set
- ⚠️ Project config exists but ACE_PROJECT_ID missing
- ❌ Project config missing

**Note**: ace-cli is used for all ACE operations.

**If Failed**:
```
❌ Project Configuration: MISSING

Recommended Actions:
1. Run: /ace:ace-configure --project
2. Provide your project ID (starts with prj_)
```

**If Using @latest**:
```
⚠️ Project Configuration: USING @latest

Current: "@ce-dot-net/ace-client@latest"
Recommended: "@ce-dot-net/ace-client@3.7.2"

Issue: @latest causes npx caching - updates won't install automatically

Recommended Actions:
1. Run: /ace:ace-configure --project
2. This will update to pinned version 3.7.0
```

---

### Check 4: CLI Availability

**What to Check**:
```bash
# Check if ace-cli is installed and working
command -v ace-cli >/dev/null 2>&1 && echo "INSTALLED" || echo "NOT FOUND"

# If installed, check version
ace-cli --version
```

**Report**:
- ✅ ace-cli installed and accessible
- ⚠️ ace-cli installed but old version
- ❌ ace-cli not found

**If Failed**:
```
❌ CLI: NOT FOUND

Possible Causes:
1. ace-cli not installed globally
2. npm global bin path not in PATH

Recommended Actions:
1. Install: npm install -g @ace-sdk/cli
2. Check version: ace-cli --version
3. Verify PATH includes npm global bin: npm bin -g
```

---

### Check 5: ACE Server Connectivity

**What to Check**:
```bash
# Read serverUrl and apiToken from global config
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
SERVER_URL=$(jq -r '.serverUrl' "$XDG_HOME/ace/config.json")
API_TOKEN=$(jq -r '.apiToken' "$XDG_HOME/ace/config.json")
PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // .projectId // empty' .claude/settings.json)

# Test connection to ACE server
curl -s -X GET \
  -H "Authorization: Bearer $API_TOKEN" \
  "$SERVER_URL/api/projects/$PROJECT_ID/playbook" \
  -w "\nHTTP: %{http_code}\n" \
  -o /tmp/ace-doctor-response.json
```

**Report**:
- ✅ ACE server reachable and authenticated (HTTP 200)
- ⚠️ Server reachable but authentication failed (HTTP 401)
- ⚠️ Project not found (HTTP 404)
- ❌ Server unreachable (connection timeout/refused)

**If Failed**:
```
❌ ACE Server: UNREACHABLE

Server URL: https://ace-api.code-engine.app
HTTP Status: Connection refused

Possible Causes:
1. Network connectivity issues
2. Firewall blocking HTTPS
3. Incorrect server URL

Recommended Actions:
1. Test connection: curl https://ace-api.code-engine.app/api/health
2. Check firewall settings
3. Try different network (WiFi vs. Ethernet)
4. Verify serverUrl in ~/.config/ace/config.json
```

**If 401 Unauthorized**:
```
⚠️ ACE Server: AUTHENTICATION FAILED

Server URL: https://ace-api.code-engine.app
HTTP Status: 401 Unauthorized

Recommended Actions:
1. Verify API token is correct
2. Check token hasn't expired
3. Run: /ace:ace-configure --global
4. Get new token from ACE server admin
```

**If 404 Not Found**:
```
⚠️ ACE Server: PROJECT NOT FOUND

Project ID: prj_xxxxx
HTTP Status: 404 Not Found

Recommended Actions:
1. Verify project ID exists in ACE server
2. Check you have access to this project
3. Run: /ace:ace-configure --project
4. Create new project in ACE dashboard
```

---

### Check 6: Hooks Registered

**What to Check**:
```bash
# Check if hook scripts exist
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PLUGIN_ROOT="$HOME/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace"

# Check hook wrappers in scripts/
test -f "$PLUGIN_ROOT/scripts/ace_before_task_wrapper.sh" && echo "before_task: EXISTS"
test -f "$PLUGIN_ROOT/scripts/ace_task_complete_wrapper.sh" && echo "task_complete: EXISTS"
test -f "$PLUGIN_ROOT/scripts/ace_after_task_wrapper.sh" && echo "after_task: EXISTS"
test -f "$PLUGIN_ROOT/scripts/ace_install_cli.sh" && echo "install_cli: EXISTS"

# Check hooks.json
test -f "$PLUGIN_ROOT/hooks/hooks.json" && echo "hooks.json: EXISTS"
```

**Expected Hooks** (5 total):
1. `SessionStart` → `ace_install_cli.sh`
2. `UserPromptSubmit` → `ace_before_task_wrapper.sh`
3. `PostToolUse` → `ace_task_complete_wrapper.sh`
4. `PreCompact` → `ace_after_task_wrapper.sh`
5. `Stop` → `ace_after_task_wrapper.sh`

**Report**:
- ✅ All hooks registered (5/5)
- ⚠️ Some hooks missing (e.g., 3/5)
- ❌ No hooks registered (0/5)

**If Failed**:
```
❌ Hooks: NOT REGISTERED

Expected Hook Scripts:
- ace_before_task_wrapper.sh (retrieves patterns before tasks)
- ace_task_complete_wrapper.sh (captures learning after tasks)
- ace_after_task_wrapper.sh (backup learning at session end)
- ace_install_cli.sh (ensures ace-cli is available)

Recommended Actions:
1. Verify plugin installation (Check 1)
2. Check scripts/ directory exists in plugin
3. Verify hooks.json exists in hooks/ directory
4. Run: /ace:ace-test to verify hook execution
5. Check Claude Code logs for hook errors
```

---

### Check 7: CLI Configuration

**What to Check**:
```bash
# Check ace-cli config
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
test -f "$XDG_HOME/ace/config.json" && echo "CONFIG: EXISTS"

# Check if multi-org format (ace-cli v1.x)
jq -e '.organizations' "$XDG_HOME/ace/config.json" >/dev/null 2>&1 && echo "FORMAT: MULTI-ORG"

# Check required fields
jq -e '.organizations[0].apiKey' "$XDG_HOME/ace/config.json" >/dev/null 2>&1 && echo "API_KEY: SET"
```

**Expected** (ace-cli v1.x multi-org format):
```json
{
  "organizations": [
    {
      "name": "ce-dot-net",
      "apiKey": "ace_xxxxx"
    }
  ],
  "activeOrg": "ce-dot-net"
}
```

**Report**:
- ✅ CLI config valid (multi-org format)
- ⚠️ CLI config exists but old format (single-org)
- ❌ CLI config missing

**If Old Format**:
```
⚠️ CLI Configuration: OLD FORMAT

Current: Single-org format (ace-cli v0.x)
Expected: Multi-org format (ace-cli v1.x+)

Recommended Actions:
1. Update ace-cli: npm install -g @ace-sdk/cli@latest
2. Run: ace-cli configure
3. Or run: /ace:ace-configure
```

---

### Check 8: Version Status

**What to Check**:
```bash
# Get plugin version
PLUGIN_JSON="$HOME/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace/plugin.json"
if [ -f "$PLUGIN_JSON" ]; then
    jq -r '.version' "$PLUGIN_JSON"
else
    echo "unknown"
fi

# Get ace-cli version
if command -v ace-cli >/dev/null 2>&1; then
    ace-cli --version 2>/dev/null || echo "unknown"
else
    echo "not installed"
fi

# Check for Python hooks (shared-hooks/)
if [ -d "shared-hooks" ]; then
    echo "Python hooks: present"
else
    echo "Python hooks: missing (required for v5.x)"
fi
```

**Expected Versions** (as of 2024-11):
- Plugin: v5.1.2+
- ace-cli: v1.0.9+
- CLAUDE.md: v5.0.3+

**Report**:
- ✅ All components up to date
- ⚠️ Plugin outdated (< v5.1.2)
- ⚠️ CLI outdated (< v1.0.9)
- ❌ Critical version mismatch

**If Updates Available**:
```
⚠️ Updates Recommended

Plugin: v5.1.1 → v5.1.2 (latest)
ace-cli: v1.0.8 → v1.0.9 (latest)

Changes in v5.1.2:
- Context passing bug fix (subprocess environment variables)
- Improved error handling in Python hooks

Recommended Actions:
1. Update ace-cli: npm install -g @ace-sdk/cli@latest
2. Update plugin from marketplace (if available)
3. Restart Claude Code
```

---

## 📊 Final Report Format

After running all checks, present results in this format:

```
🩺 ACE Doctor - Health Diagnostic Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] Plugin Installation................... ✅ PASS
[2] Global Configuration................. ✅ PASS
[3] Project Configuration................ ✅ PASS
[4] CLI Availability..................... ✅ PASS (v1.0.9)
[5] ACE Server Connectivity.............. ✅ PASS (HTTP 200)
[6] Hooks Registered..................... ✅ PASS (5/5)
[7] CLI Configuration.................... ✅ PASS (multi-org)
[8] Version Status....................... ✅ PASS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Overall Health: 🟢 HEALTHY

✅ All systems operational!

ACE is properly configured and ready to use.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

System Information:

Plugin Version: v5.1.2
CLI Version: v1.0.9
Architecture: Hook-based (v5.x)
Project ID: prj_d3a244129d62c198
Organization: org_34fYIlitYk4nyFuTvtsAzA6uUJF

Registered Hooks:
• SessionStart → ace_install_cli.sh
• UserPromptSubmit → ace_before_task_wrapper.sh
• PostToolUse → ace_task_complete_wrapper.sh
• PreCompact → ace_after_task_wrapper.sh
• Stop → ace_after_task_wrapper.sh

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For detailed troubleshooting, see:
- README.md (section: 🐛 Troubleshooting)
- /ace:ace-test (hook execution test)

Report issues: https://github.com/ce-dot-net/ce-claude-marketplace/issues
```

### Example with Warnings

```
🩺 ACE Doctor - Health Diagnostic Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] Plugin Installation................... ✅ PASS
[2] Global Configuration................. ✅ PASS
[3] Project Configuration................ ⚠️  WARN
[4] CLI Availability..................... ✅ PASS (v1.0.9)
[5] ACE Server Connectivity.............. ✅ PASS (HTTP 200)
[6] Hooks Registered..................... ⚠️  WARN (3/5)
[7] CLI Configuration.................... ✅ PASS
[8] Version Status....................... ⚠️  WARN

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Overall Health: 🟡 NEEDS ATTENTION (3 warnings)

⚠️  Warnings Found:

[3] Project Configuration
    Issue: projectId missing in .claude/settings.json
    Impact: Hooks cannot determine which project to use
    Fix: Run /ace:ace-configure

[6] Hooks Registered
    Issue: Some hook scripts missing (3/5 found)
    Missing: ace_task_complete_wrapper.sh, ace_after_task_wrapper.sh
    Impact: Learning capture won't work after tasks
    Fix: Reinstall plugin or check scripts/ directory

[8] Version Status
    Issue: Updates available
    Plugin: v5.1.1 → v5.1.2
    CLI: v1.0.8 → v1.0.9
    Fix: See recommended actions below

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Quick Fix All Issues:

Run these commands in order:
1. /ace:ace-configure
2. npm install -g @ace-sdk/cli@latest
3. Restart Claude Code

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

System Information:

Plugin Version: v5.1.1
CLI Version: v1.0.8
Architecture: Hook-based (v5.x)
Project ID: (not configured)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For detailed troubleshooting, see:
- README.md (section: 🐛 Troubleshooting)
- /ace:ace-test (hook execution test)

Report issues: https://github.com/ce-dot-net/ce-claude-marketplace/issues
```

## Color Coding Legend

Use these status indicators:
- ✅ **PASS** - Everything working correctly
- ⚠️  **WARN** - Non-critical issue, system still functional
- ❌ **FAIL** - Critical issue, system may not work properly

## Performance

Run all checks in **parallel** for speed (< 5 seconds total).

Use Promise.all() or concurrent bash commands where possible.

## Error Handling

If any check throws an error:
1. Catch the error gracefully
2. Report as ❌ FAIL with error message
3. Continue with remaining checks
4. Include error details in final report

## Exit Codes

This is a diagnostic command - NEVER exit with error code.
Always complete all checks and present full report.

## See Also

- `/ace:ace-test` - Plugin-specific tests
- `/ace:ace-status` - Playbook statistics
- `/ace:ace-configure` - Configuration wizard
- README.md - Full troubleshooting guide
