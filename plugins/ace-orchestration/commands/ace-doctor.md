---
description: Comprehensive ACE installation and health diagnostic
---

# ACE Doctor - Installation & Health Diagnostic

Comprehensive diagnostic tool that checks your entire ACE setup and identifies issues.

## Instructions for Claude

When the user runs `/ace-orchestration:ace-doctor`, perform a complete health check of the ACE system.

### Diagnostic Flow

Run all checks in parallel for speed, then present organized results.

---

## 🏥 Diagnostic Checks

### Check 1: Plugin Installation

**What to Check**:
```bash
# Verify plugin directory structure
ls -la ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/
```

**Expected Structure**:
```
ace-orchestration/
├── skills/
│   ├── ace-playbook-retrieval/
│   └── ace-learning/
├── commands/
├── hooks/
│   └── hooks.json
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
   ln -s /path/to/ace-orchestration ~/.claude/plugins/ace-orchestration
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
1. Run: /ace-orchestration:ace-configure --global
2. Provide:
   - Server URL (https://ace-api.code-engine.app)
   - API Token (starts with ace_)
```

**If Incomplete**:
```
⚠️ Global Configuration: INCOMPLETE

Missing fields: apiToken, cacheTtlMinutes

Recommended Actions:
1. Run: /ace-orchestration:ace-configure --global
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
jq -e '.env.ACE_PROJECT_ID' "$PROJECT_ROOT/.claude/settings.json"
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

**Note**: MCP server is registered in plugin `.mcp.json`, not in project config.

**If Failed**:
```
❌ Project Configuration: MISSING

Recommended Actions:
1. Run: /ace-orchestration:ace-configure --project
2. Provide your project ID (starts with prj_)
```

**If Using @latest**:
```
⚠️ Project Configuration: USING @latest

Current: "@ce-dot-net/ace-client@latest"
Recommended: "@ce-dot-net/ace-client@3.7.2"

Issue: @latest causes npx caching - updates won't install automatically

Recommended Actions:
1. Run: /ace-orchestration:ace-configure --project
2. This will update to pinned version 3.7.0
```

---

### Check 4: MCP Client Connectivity

**What to Check**:
```bash
# Try to call ace_status tool
mcp__plugin_ace-orchestration_ace-pattern-learning__ace_status
```

**Report**:
- ✅ MCP client connected and responding
- ⚠️ MCP client connected but returning errors
- ❌ MCP client not responding

**If Failed**:
```
❌ MCP Client: NOT RESPONDING

Possible Causes:
1. MCP server not started
2. Global config missing or invalid
3. Network issues
4. npm package not installed

Recommended Actions:
1. Restart Claude Code (Cmd+Q, then reopen)
2. Check global config: cat ~/.config/ace/config.json
3. Verify network access to npm registry
4. Manual test: npx @ce-dot-net/ace-client@3.7.2 --version
```

---

### Check 5: ACE Server Connectivity

**What to Check**:
```bash
# Read serverUrl and apiToken from global config
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
SERVER_URL=$(jq -r '.serverUrl' "$XDG_HOME/ace/config.json")
API_TOKEN=$(jq -r '.apiToken' "$XDG_HOME/ace/config.json")
PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID' .claude/settings.json)

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
3. Run: /ace-orchestration:ace-configure --global
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
3. Run: /ace-orchestration:ace-configure --project
4. Create new project in ACE dashboard
```

---

### Check 6: Skills Loaded

**What to Check**:
```bash
# Check if skills are available in current session
# This can be verified by checking skill descriptions
```

**Expected Skills**:
- `ace-orchestration:ace-playbook-retrieval`
- `ace-orchestration:ace-learning`

**Report**:
- ✅ Both skills loaded and available
- ⚠️ Only one skill loaded
- ❌ No skills loaded

**If Failed**:
```
❌ Skills: NOT LOADED

Expected Skills:
- ace-orchestration:ace-playbook-retrieval (before tasks)
- ace-orchestration:ace-learning (after tasks)

Recommended Actions:
1. Verify plugin installation (Check 1)
2. Check skills/ directory exists in plugin
3. Restart Claude Code
4. Check Claude Code logs for skill loading errors
```

---

### Check 7: CLAUDE.md Status

**What to Check**:
```bash
# Check if CLAUDE.md exists in project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
test -f "$PROJECT_ROOT/CLAUDE.md" && echo "EXISTS" || echo "MISSING"

# If exists, check for ACE section
grep -q "ACE_SECTION_START" "$PROJECT_ROOT/CLAUDE.md" && echo "HAS_ACE" || echo "NO_ACE"

# Extract version
grep -oP 'ACE_SECTION_START v\K[\d.]+' "$PROJECT_ROOT/CLAUDE.md"
```

**Report**:
- ✅ CLAUDE.md exists with ACE instructions (v3.3.2)
- ⚠️ CLAUDE.md exists but no ACE section
- ⚠️ CLAUDE.md exists but outdated version (v3.3.1)
- ❌ CLAUDE.md missing

**If Missing**:
```
❌ CLAUDE.md: NOT FOUND

Recommended Actions:
1. Run: /ace-orchestration:ace-claude-init
2. This will create CLAUDE.md with full ACE instructions
3. Commit CLAUDE.md to your repository
```

**If Outdated**:
```
⚠️ CLAUDE.md: OUTDATED VERSION

Current: v3.3.1
Latest: v3.3.2

Recommended Actions:
1. Run: /ace-orchestration:ace-claude-init
2. OR enable auto-update: /ace-orchestration:ace-enable-auto-update
3. This will update ACE instructions to latest version
```

---

### Check 8: Cache Status

**What to Check**:
```bash
# Check if cache directory exists
test -d ~/.ace-cache && echo "EXISTS" || echo "MISSING"

# Check cache database files
ls -lh ~/.ace-cache/*.db 2>/dev/null | wc -l

# Check cache age
find ~/.ace-cache -name "*.db" -mmin +120 2>/dev/null | wc -l
```

**Report**:
- ✅ Cache active and fresh (< 360 min old)
- ⚠️ Cache exists but stale (> 360 min old)
- ⚠️ Cache directory exists but no databases
- ❌ Cache directory missing

**If Stale**:
```
⚠️ Cache: STALE (> 6 hours old)

Cache TTL: 120 minutes (2 hours)
Last updated: 12 hours ago

Note: This is normal if you haven't used ACE recently.
Cache will refresh automatically on next playbook fetch.

Optional: Clear cache manually
/ace-orchestration:ace-clear-cache
```

---

### Check 9: Version Status

**What to Check**:
```bash
# Get plugin version
cat ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/plugin.json | jq -r '.version'

# Get MCP client version
npx @ce-dot-net/ace-client@3.7.2 --version 2>/dev/null

# Check GitHub for latest plugin release
curl -s https://api.github.com/repos/ce-dot-net/ce-claude-marketplace/releases/latest | jq -r '.tag_name'

# Check GitHub for latest CLAUDE.md template version
curl -s https://raw.githubusercontent.com/ce-dot-net/ce-claude-marketplace/main/plugins/ace-orchestration/CLAUDE.md | grep -oP 'ACE_SECTION_START v\K[\d.]+'
```

**Report**:
- ✅ All components up to date
- ⚠️ Plugin update available (current: v3.3.1, latest: v3.3.2)
- ⚠️ MCP client update available
- ⚠️ CLAUDE.md template update available

**If Updates Available**:
```
⚠️ Updates Available

Plugin: v3.3.1 → v3.3.2 (latest)
MCP Client: v3.6.2 → v3.7.0 (latest)
CLAUDE.md Template: v3.3.1 → v3.3.2 (latest)

Recommended Actions:
1. Update plugin from marketplace
2. Update MCP client: Edit .claude/settings.json
   Change: "@ce-dot-net/ace-client@3.6.2"
   To: "@ce-dot-net/ace-client@3.7.2"
3. Update CLAUDE.md: /ace-orchestration:ace-claude-init
4. Restart Claude Code
```

---

## 📊 Final Report Format

After running all checks, present results in this format:

```
🩺 ACE Doctor - Health Diagnostic Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] Plugin Installation................... ✅ PASS
[2] Global Configuration................. ✅ PASS
[3] Project Configuration................ ⚠️  WARN
[4] MCP Client Connectivity.............. ✅ PASS
[5] ACE Server Connectivity.............. ✅ PASS (HTTP 200)
[6] Skills Loaded........................ ✅ PASS (2/2)
[7] CLAUDE.md Status..................... ⚠️  WARN (outdated)
[8] Cache Status......................... ✅ PASS
[9] Version Status....................... ⚠️  WARN (updates available)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Overall Health: 🟡 NEEDS ATTENTION (2 warnings)

⚠️  Warnings Found:

[3] Project Configuration
    Issue: Using @latest instead of pinned version
    Impact: Updates may not install automatically due to npx caching
    Fix: /ace-orchestration:ace-configure --project

[7] CLAUDE.md Status
    Issue: Outdated version (v3.3.1, latest: v3.3.2)
    Impact: Missing latest ACE features and improvements
    Fix: /ace-orchestration:ace-claude-init

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Quick Fix All Issues:

Run these commands in order:
1. /ace-orchestration:ace-configure --project
2. /ace-orchestration:ace-claude-init
3. Restart Claude Code

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

System Information:

Plugin Version: v3.3.1
MCP Client Version: v3.6.2
Cache TTL: 120 minutes (2 hours)
Project ID: prj_d3a244129d62c198
Server URL: https://ace-api.code-engine.app

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For detailed troubleshooting, see:
- README.md (section: 🐛 Troubleshooting)
- /ace-orchestration:ace-test (plugin-specific diagnostics)

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

- `/ace-orchestration:ace-test` - Plugin-specific tests
- `/ace-orchestration:ace-status` - Playbook statistics
- `/ace-orchestration:ace-configure` - Configuration wizard
- README.md - Full troubleshooting guide
