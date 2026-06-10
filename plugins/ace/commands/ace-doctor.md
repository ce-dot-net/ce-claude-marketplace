---
model: claude-haiku-4-5
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
# Verify plugin directory structure (resolve via $CLAUDE_PLUGIN_ROOT or cache glob)
ls -la "${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/ce-dot-net-marketplace/ace/*/  2>/dev/null | tail -1)}"
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
│   ├── ace_pretooluse_wrapper.sh
│   ├── ace_posttooluse_wrapper.sh
│   ├── ace_posttooluse_domain_inject.sh
│   ├── ace_precompact_wrapper.sh
│   ├── ace_permission_request_wrapper.sh
│   ├── ace_permission_denied_wrapper.sh
│   ├── ace_stop_wrapper.sh
│   ├── ace_sessionend_wrapper.sh
│   ├── ace_subagent_start_wrapper.sh
│   └── ace_subagent_stop_wrapper.sh
├── shared-hooks/       # Python hook utilities
└── plugin.json
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

# If exists, check for authenticated device-code token (ace-cli 4.x format)
jq -e '.auth.token' "$CONFIG_PATH" >/dev/null 2>&1 && echo "AUTH: device-code token present" || echo "AUTH: token missing — run /ace:ace-login"

# Detect stale apiToken format (ace-cli v1.x) and warn
jq -e '.apiToken' "$CONFIG_PATH" >/dev/null 2>&1 && echo "WARN: stale apiToken field detected — run /ace:ace-login to migrate"
```

**Expected** (ace-cli 4.x device-code format):
```json
{
  "auth": {
    "token": "..."
  }
}
```

**Note**: The old `apiToken`, `serverUrl`, `cacheTtlMinutes`, and `autoUpdateEnabled` fields are from ace-cli v1.x and are no longer valid.  Run `/ace:ace-login` to migrate.

**Report**:
- ✅ Global config valid
- ⚠️ Global config exists but incomplete
- ❌ Global config missing

**If Failed**:
```
❌ Global Configuration: MISSING

Recommended Actions:
1. Run: ace-cli login    (completes device-code auth and writes ~/.ace/config.json)
2. Then run: /ace:ace-configure --global   (writes org/project IDs to plugin config)
```

**If Incomplete**:
```
⚠️ Global Configuration: INCOMPLETE

The config file exists but is missing required v4.x fields (e.g. auth.token).
This usually means a stale v1.x config is present.

Recommended Actions:
1. Run: ace-cli login    (re-authenticates via device-code and refreshes config)
2. Then run: /ace:ace-configure --global   (re-writes org/project IDs)
```

---

### Check 3: Project Configuration

**What to Check**:
```bash
# Get project root
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

# Check project settings
test -f "$PROJECT_ROOT/.claude/settings.json" && echo "EXISTS" || echo "MISSING"

# If exists, validate ACE_PROJECT_ID env var (written by ace-configure)
jq -e '.env.ACE_PROJECT_ID' "$PROJECT_ROOT/.claude/settings.json"
```

**Expected**:
```json
{
  "env": {
    "ACE_ORG_ID": "org_xxxxx",
    "ACE_PROJECT_ID": "prj_xxxxx",
    "ACE_VERBOSITY": "normal"
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
# Read auth token from global config (ace-cli 4.x device-code format)
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
API_TOKEN=$(jq -r '.auth.token // empty' "$XDG_HOME/ace/config.json")
PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // .projectId // empty' .claude/settings.json)
SERVER_URL="https://ace-api.code-engine.app"

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
4. Confirm auth status: ace-cli whoami --json
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
# Check if hook scripts exist (resolve plugin root dynamically)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/ce-dot-net-marketplace/ace/*/ 2>/dev/null | tail -1)}"

# Check all hook wrappers in scripts/
test -f "$PLUGIN_ROOT/scripts/ace_install_cli.sh" && echo "install_cli: EXISTS" || echo "install_cli: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_before_task_wrapper.sh" && echo "before_task: EXISTS" || echo "before_task: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_pretooluse_wrapper.sh" && echo "pretooluse: EXISTS" || echo "pretooluse: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_posttooluse_wrapper.sh" && echo "posttooluse: EXISTS" || echo "posttooluse: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_posttooluse_domain_inject.sh" && echo "posttooluse_domain_inject: EXISTS" || echo "posttooluse_domain_inject: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_precompact_wrapper.sh" && echo "precompact: EXISTS" || echo "precompact: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_permission_request_wrapper.sh" && echo "permission_request: EXISTS" || echo "permission_request: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_permission_denied_wrapper.sh" && echo "permission_denied: EXISTS" || echo "permission_denied: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_stop_wrapper.sh" && echo "stop: EXISTS" || echo "stop: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_sessionend_wrapper.sh" && echo "sessionend: EXISTS" || echo "sessionend: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_subagent_start_wrapper.sh" && echo "subagent_start: EXISTS" || echo "subagent_start: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_subagent_stop_wrapper.sh" && echo "subagent_stop: EXISTS" || echo "subagent_stop: MISSING"

# Check hooks.json
test -f "$PLUGIN_ROOT/hooks/hooks.json" && echo "hooks.json: EXISTS"
```

**Expected Hooks** (11 events, 12 hook entries):
1. `PreToolUse` → `ace_pretooluse_wrapper.sh`
2. `PreCompact` → `ace_precompact_wrapper.sh`
3. `SessionStart` → `ace_install_cli.sh`
4. `UserPromptSubmit` → `ace_before_task_wrapper.sh`
5. `PostToolUse` → `ace_posttooluse_wrapper.sh --log`
6. `PostToolUse` (if: `Read(*)`) → `ace_posttooluse_domain_inject.sh`
7. `PermissionRequest` → `ace_permission_request_wrapper.sh`
8. `PermissionDenied` → `ace_permission_denied_wrapper.sh`
9. `Stop` → `ace_stop_wrapper.sh --log --chat`
10. `SessionEnd` → `ace_sessionend_wrapper.sh`
11. `SubagentStart` → `ace_subagent_start_wrapper.sh`
12. `SubagentStop` → `ace_subagent_stop_wrapper.sh --log --chat --notify`

**Report**:
- ✅ All hooks registered (11/11)
- ⚠️ Some hooks missing (e.g., 7/10)
- ❌ No hooks registered (0/10)

**If Failed**:
```
❌ Hooks: NOT REGISTERED

Expected Hook Scripts:
- ace_install_cli.sh (ensures ace-cli is available)
- ace_before_task_wrapper.sh (retrieves patterns before tasks)
- ace_pretooluse_wrapper.sh (pre-tool telemetry)
- ace_posttooluse_wrapper.sh (captures tool use after each tool call)
- ace_posttooluse_domain_inject.sh (domain injection on Read(*))
- ace_precompact_wrapper.sh (pre-compact state save)
- ace_permission_request_wrapper.sh (permission request telemetry)
- ace_permission_denied_wrapper.sh (permission denied redaction)
- ace_stop_wrapper.sh (learning capture at Stop)
- ace_sessionend_wrapper.sh (session end cleanup)
- ace_subagent_start_wrapper.sh (per-subagent ACE search at spawn)
- ace_subagent_stop_wrapper.sh (subagent learning capture)

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
# Check ace-cli config (ace-cli 4.x uses device-code auth)
XDG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
test -f "$XDG_HOME/ace/config.json" && echo "CONFIG: EXISTS" || echo "CONFIG: MISSING"

# Verify authenticated via whoami
ace-cli whoami --json 2>/dev/null | jq -e '.authenticated == true' >/dev/null 2>&1 \
  && echo "AUTH: authenticated" \
  || echo "AUTH: not authenticated — run /ace:ace-login"

# Detect stale formats and warn
jq -e '.organizations' "$XDG_HOME/ace/config.json" >/dev/null 2>&1 \
  && echo "WARN: stale organizations array detected — run /ace:ace-login to migrate"
jq -e '.apiToken' "$XDG_HOME/ace/config.json" >/dev/null 2>&1 \
  && echo "WARN: stale apiToken field detected — run /ace:ace-login to migrate"
```

**Expected** (ace-cli 4.x device-code format):
```json
{
  "auth": {
    "token": "..."
  }
}
```

**Report**:
- ✅ CLI config valid (device-code authenticated)
- ⚠️ CLI config exists but stale format (organizations/apiKey from v1.x)
- ❌ CLI config missing or not authenticated

**If Stale Format**:
```
⚠️ CLI Configuration: STALE FORMAT

Current: organizations/apiKey format (ace-cli v1.x — deprecated)
Expected: device-code token format (ace-cli 4.x)

Recommended Actions:
1. Update ace-cli: npm install -g @ace-sdk/cli@latest
2. Run: ace-cli login
3. Or run: /ace:ace-login
```

---

### Check 8: Version Status

**What to Check**:
```bash
# Get plugin version (resolve dynamically via $CLAUDE_PLUGIN_ROOT or cache glob)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/ce-dot-net-marketplace/ace/*/ 2>/dev/null | tail -1)}"
PLUGIN_JSON="$PLUGIN_ROOT/plugin.json"
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
if [ -d "${PLUGIN_ROOT}/shared-hooks" ]; then
    echo "Python hooks: present"
else
    echo "Python hooks: missing (required for v7.x)"
fi
```

**Expected Versions** (as of 2026):
- Plugin: v7.0.0+
- ace-cli: v4.0.1+

**Report**:
- ✅ All components up to date
- ⚠️ Plugin outdated (< v7.0.0)
- ⚠️ CLI outdated (< v4.0.1)
- ❌ Critical version mismatch

**If Updates Available**:
```
⚠️ Updates Recommended

Plugin: v7.0.0 → latest
ace-cli: v4.0.1 → latest

Recommended Actions:
1. Update ace-cli: npm install -g @ace-sdk/cli@latest
2. Update plugin from marketplace (if available)
3. Restart Claude Code
```

---

### Check 9: Cache Diagnostics

ACE uses **two distinct caches** that behave differently and are cleared by different mechanisms.

#### Cache 1: In-Memory Client Cache (LRU)

- Held in the running ace-cli process memory
- Cleared by: `ace-cli cache clear` (any `--type` flag: `sqlite`, `ram`, or `all`)
- Scope: per-process; lost on process exit automatically

**Important (ace-cli 4.0.1)**: `cache clear` only clears the in-memory cache. It does **not** clear the SQLite graph cache on disk.

#### Cache 2: SQLite Graph Cache

- Location: `~/.ace-cache/<org>__<project>.db`
- Contains: pattern graph data with a **7-day TTL**
- **NOT cleared by `cache clear`** — must be manually removed or wait for TTL expiry
- Inspect with:

```bash
ls -lh ~/.ace-cache/
# Example:
# ~/.ace-cache/ce-dot-net__my-project.db   (graph cache, 7-day TTL)
# ~/.ace-cache/sessions.db                 (session recall DB)
```

#### Cache 3: Session Recall DB

- Location: `~/.ace-cache/sessions.db`
- Contains: per-session recall index used by the before-task hook
- **NOT cleared by `cache clear`**
- Managed automatically; safe to delete if corrupted (will be recreated)

**What to Check**:
```bash
# Inspect cache directory
ls -lh ~/.ace-cache/ 2>/dev/null || echo "~/.ace-cache not found (no cache yet)"

# Check graph DB age (warn if > 7 days)
find ~/.ace-cache -name "*.db" ! -name "sessions.db" -mtime +7 -print 2>/dev/null

# Check sessions DB exists
test -f ~/.ace-cache/sessions.db && echo "sessions.db: EXISTS" || echo "sessions.db: MISSING"
```

**Report**:
- ✅ Cache healthy (graph DB < 7 days old, sessions.db present)
- ⚠️ Graph DB stale (> 7 days — will be auto-expired on next search)
- ⚠️ sessions.db missing (will be recreated on next session start)
- ℹ️ No cache directory yet (cold start — created after first search)

**If Stale Graph Cache**:
```
⚠️ Cache: STALE GRAPH DB

File: ~/.ace-cache/<org>__<project>.db
Age: > 7 days (TTL expired)

Note: ace-cli cache clear does NOT remove this file.
To force-clear the SQLite graph cache, run:
  rm ~/.ace-cache/<org>__<project>.db

The cache will be rebuilt automatically on next search.
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
[4] CLI Availability..................... ✅ PASS (v4.1.0)
[5] ACE Server Connectivity.............. ✅ PASS (HTTP 200)
[6] Hooks Registered..................... ✅ PASS (10/10)
[7] CLI Configuration.................... ✅ PASS (device-code)
[8] Version Status....................... ✅ PASS
[9] Cache Diagnostics.................... ✅ PASS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Overall Health: 🟢 HEALTHY

✅ All systems operational!

ACE is properly configured and ready to use.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

System Information:

Plugin Version: v7.0.0
CLI Version: v4.1.0
Architecture: Hook-based (v7.x)
Project ID: prj_d3a244129d62c198
Organization: org_34fYIlitYk4nyFuTvtsAzA6uUJF

Registered Hooks:
• PreToolUse → ace_pretooluse_wrapper.sh
• PreCompact → ace_precompact_wrapper.sh
• SessionStart → ace_install_cli.sh
• UserPromptSubmit → ace_before_task_wrapper.sh
• PostToolUse → ace_posttooluse_wrapper.sh --log
• PostToolUse (if: Read(*)) → ace_posttooluse_domain_inject.sh
• PermissionRequest → ace_permission_request_wrapper.sh
• PermissionDenied → ace_permission_denied_wrapper.sh
• Stop → ace_stop_wrapper.sh --log --chat
• SessionEnd → ace_sessionend_wrapper.sh
• SubagentStart → ace_subagent_start_wrapper.sh
• SubagentStop → ace_subagent_stop_wrapper.sh --log --chat --notify

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
[4] CLI Availability..................... ✅ PASS (v4.1.0)
[5] ACE Server Connectivity.............. ✅ PASS (HTTP 200)
[6] Hooks Registered..................... ⚠️  WARN (7/10)
[7] CLI Configuration.................... ✅ PASS
[8] Version Status....................... ⚠️  WARN
[9] Cache Diagnostics.................... ✅ PASS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Overall Health: 🟡 NEEDS ATTENTION (3 warnings)

⚠️  Warnings Found:

[3] Project Configuration
    Issue: ACE_PROJECT_ID missing in .claude/settings.json (env.ACE_PROJECT_ID)
    Impact: Hooks cannot determine which project to use
    Fix: Run /ace:ace-configure

[6] Hooks Registered
    Issue: Some hook scripts missing (8/11 found)
    Missing: ace_permission_request_wrapper.sh, ace_permission_denied_wrapper.sh, ace_subagent_start_wrapper.sh, ace_subagent_stop_wrapper.sh
    Impact: Permission telemetry and subagent learning won't work
    Fix: Reinstall plugin or check scripts/ directory

[8] Version Status
    Issue: Updates available
    Plugin: v7.0.0 → latest
    CLI: v4.0.1 → latest
    Fix: See recommended actions below

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Quick Fix All Issues:

Run these commands in order:
1. /ace:ace-configure
2. npm install -g @ace-sdk/cli@latest
3. Restart Claude Code

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

System Information:

Plugin Version: v7.0.0
CLI Version: v4.1.0
Architecture: Hook-based (v7.x)
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
