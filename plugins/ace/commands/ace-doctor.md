---
disable-model-invocation: true
model: claude-haiku-4-5
description: Comprehensive ACE installation and health diagnostic
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(jq:*), Bash(npm:*), Bash(uname:*), Bash(bash:*), Bash(node:*), Bash(ls:*), Bash(test:*), Bash(claude:*), Bash(cat:*), Bash(tail:*), Bash(sort:*), Bash(python3:*), Read
---

# ACE Doctor - Installation & Health Diagnostic

Comprehensive diagnostic tool that checks your entire ACE setup and identifies issues.

## Instructions for Claude

When the user runs `/ace:ace-doctor`, perform a complete health check of the ACE system.

### Diagnostic Flow

Run all checks in parallel for speed, then present organized results.

---

## 🏥 Diagnostic Checks

### Check 0: Environment, Claude Code Version and Plugin Data

**What to Check**:
```bash
# One screen a remote user can paste back: OS, shells, runtimes
uname -sm
bash --version | head -1
python3 --version
node --version
# Windows is not supported (macOS, Linux and WSL2 only): the hook shims are exec-form .sh files

# Claude Code floor is 2.1.311 (SubagentStop double-fire fix)
claude --version
# Compare against 2.1.311: older => WARN, ACE pauses itself (SessionStart writes disabled.flag and says so)

# Plugin data layout (v8): Claude Code substitutes the exact token below (cc_hooks_reference.md:480).
# Other plugins export THEIR CLAUDE_PLUGIN_DATA into the shared env file: only a data dir whose NAME starts with ace is ours.
DATA="${CLAUDE_PLUGIN_DATA}"
case "${DATA##*/}" in ace*) ;; *) DATA="$HOME/.claude/plugins/data/ace-ce-dot-net-marketplace" ;; esac
ls -la "$DATA"
test -r "$DATA/python_path" && cat "$DATA/python_path"   # written by SessionStart
test -r "$DATA/cli_version.json" && cat "$DATA/cli_version.json"   # version of a GLOBAL ace-cli (fallback only)
test -f "$DATA/logs/ace-hook-errors.log" && tail -5 "$DATA/logs/ace-hook-errors.log"   # non-empty => hook errors
# Active chain (newest session dir): mod-active = the mod searches/injects; mod-classic = its classic.* hooks run
# (absent while mod-active is fresh = a managed-settings guard filters them: the Python hooks learn and set the title)
S=$(ls -td "$DATA"/projects/*/sessions/* 2>/dev/null | head -1)
for m in mod-active mod-classic; do test -f "$S/$m" && python3 -c 'import os,sys,time; print(sys.argv[1], "age_s=%d" % (time.time() - os.path.getmtime(sys.argv[2])))' "$m" "$S/$m" || echo "$m absent"; done
# Full render share (§31) and its source: env ACE_RENDER_FULL_PCT > server render_full_pct (render-full-pct.json, < 7 days) > default 50
CLAUDE_PLUGIN_DATA="$DATA" python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from ace_pattern_render import full_pct_source; print("render full share = %d%% (source: %s)" % full_pct_source())' "${CLAUDE_PLUGIN_ROOT}/shared-hooks/utils"
```

**Report**:
- PASS: Claude Code >= 2.1.311, python_path present, ace-hook-errors.log empty or absent
- WARN: Claude Code older than 2.1.311, or python_path missing (start a new session), or errors in ace-hook-errors.log
- INFO: render full share = N% (source: env | server | default); server = the ACE server set `render_full_pct` in a search response (0 = full off for everyone)
- INFO: chain = mod (mod-active younger than 15 s for UserPromptSubmit/Agent stash/SubagentStart/Stop/SubagentStop, 120 s for the hooks after a tool: domain shift, tool accumulation; `plugin_data_dir.MOD_HANDOFF_S` / `MOD_AFTER_TOOL_S`), Python (absent or older), or mod + Python learn (mod-active fresh, mod-classic absent or older: the managed-settings guard filters the mod's classic hooks)

---

### Check 1: Plugin Installation

**What to Check**:
```bash
# Verify plugin directory structure (installPath from installed_plugins.json is authoritative)
ls -la "${CLAUDE_PLUGIN_ROOT:-$(jq -r '.plugins["ace@ce-dot-net-marketplace"][0].installPath // empty' ~/.claude/plugins/installed_plugins.json 2>/dev/null)}"
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
│   ├── ace_posttooluse_wrapper.sh
│   ├── ace_posttooluse_domain_inject.sh
│   ├── ace_pretooluse_agent_stash.sh
│   ├── ace_posttoolusefailure_wrapper.sh
│   ├── ace_sessionstart_compact.sh
│   ├── ace_permission_denied_wrapper.sh
│   ├── ace_stop_wrapper.sh
│   ├── ace_sessionend_wrapper.sh
│   ├── ace_subagent_start_wrapper.sh
│   └── ace_subagent_stop_wrapper.sh
├── shared-hooks/       # Python hook utilities
└── .claude-plugin/plugin.json
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
1. Run: /ace:ace-login    (completes device-code auth and writes ~/.config/ace/config.json)
2. Then run: /ace:ace-configure --global   (writes org/project IDs to plugin config)
```

**If Incomplete**:
```
⚠️ Global Configuration: INCOMPLETE

The config file exists but is missing required v4.x fields (e.g. auth.token).
This usually means a stale v1.x config is present.

Recommended Actions:
1. Run: /ace:ace-login    (re-authenticates via device-code and refreshes config)
2. Then run: /ace:ace-configure --global   (re-writes org/project IDs)
```

---

### Check 3: Project Configuration

**What to Check** (the one core: `scripts/ace-context`, the same resolver every hook uses):
```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --json; echo "exit: $?"
```

**Report**:
- ✅ exit 0: bound. Show `projectId`, `orgId`, `source` (`repo_file` = tracked `.ace/config.json`, `settings_file` =
  legacy `.claude/settings.json` env, `env`, `remote_map`) and `path`.
- ⚠️ `source: settings_file`: legacy binding; it is adopted into `.ace/config.json` automatically (commit it).
- ⚠️ `warnings` contains `global_project_id_ignored`: the global ace-cli config has a top-level `projectId`. It is
  never used; bind each repo with `.ace/config.json` (/ace:ace-configure) and remove it from the global config.
- ❌ exit 5, `reason: no_binding`: not bound; show the `tried` paths. Fix: /ace:ace-configure
- ❌ `reason: config_refused` (`warnings: repo_file_contains_secret`): `.ace/config.json` holds `apiToken`/`serverUrl`.
  Rewrite it with only `orgId`/`projectId` and revoke the token; it is in git history.
- ❌ `reason: config_invalid`: the named file is not valid JSON.

**Note**: ace-cli is used for all ACE operations.

**If Failed**:
```
❌ Project Configuration: MISSING

Recommended Actions:
1. Run: /ace:ace-configure --project
2. Provide your project ID (starts with prj_)
```

---

### Check 4: CLI Availability (plugin-local pin)

Each plugin version runs exactly the ace-cli it was tested with: the exact pin in `package.json`, installed by
Claude Code into `${CLAUDE_PLUGIN_ROOT}/node_modules` on plugin install/update. A global ace-cli is only a fallback.

**What to Check**:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(jq -r '.plugins["ace@ce-dot-net-marketplace"][0].installPath // empty' ~/.claude/plugins/installed_plugins.json 2>/dev/null)}"
PIN=$(jq -r '.dependencies["@ace-sdk/cli"]' "$PLUGIN_ROOT/package.json")
echo "pinned (package.json): $PIN"

# CLI source: plugin-local first
LOCAL="$PLUGIN_ROOT/node_modules/@ace-sdk/cli"
if test -f "$LOCAL/dist/cli.js"; then
  echo "CLI source: plugin-local $(jq -r .version "$LOCAL/package.json")"
else
  echo "packages not installed in $PLUGIN_ROOT/node_modules"
fi
# sqlite binary (without it the CLI runs RAM-only: no pins, empty graph cache until SessionStart rebuilds it)
test -f "$PLUGIN_ROOT/node_modules/better-sqlite3/build/Release/better_sqlite3.node" && echo "sqlite binary: present" || echo "sqlite binary: missing"

# A global ace-cli (fallback)
GLOBAL_CLI="$(command -v 'ace-cli')"
test -n "$GLOBAL_CLI" && echo "global ace-cli: $GLOBAL_CLI $("$GLOBAL_CLI" --version 2>/dev/null)"

# ace_engine.py --status: which engine runs search/learn, and why ("lib" = in-process @ace-sdk/core, "cli" = ace-cli spawn)
python3 "$PLUGIN_ROOT/shared-hooks/utils/ace_engine.py" --status

# The wrapper commands use (plugin-local first, then global)
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version
```

**Report**:
- ✅ plugin-local CLI present, version == pin
- ⚠️ only a global CLI: "untested" when its version differs from the pin (works, but this plugin version was not tested with it)
- ⚠️ both present: suggest `npm rm -g @ace-sdk/cli` (the plugin-local one wins anyway)
- ⚠️ packages not installed: run `claude plugin update ace@ce-dot-net-marketplace`; if still missing, `/ace:ace-install-cli`
- ⚠️ sqlite binary missing: starts working after the next session start (SessionStart runs `npm rebuild better-sqlite3` once per plugin version)
- ❌ neither: run `/ace:ace-install-cli`
- ✅ Engine: lib (core version from the status JSON)
- ℹ️ Engine: cli, with the `reason` from the status JSON. This is a working fallback, not an error, so report it without alarm. `ACE_ENGINE=cli` forces it. `core_missing` is normal on volta, asdf and pnpm wrappers, where ace-cli itself is fine. `core_too_old`, `core_too_new`, `file_missing` and `export_missing` mean the core found does not pass the gate; to get the engine back, suggest `/ace:ace-install-cli`.

**If Failed**:
```
❌ CLI: NOT FOUND

Possible Causes:
1. Claude Code could not install the plugin packages (no npm, offline, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC set)
2. Node.js is not installed (it is required)

Recommended Actions:
1. Run: /ace:ace-install-cli
```

---

### Check 5: ACE Server Connectivity

**What to Check** (one authenticated round trip through the same ace-cli the hooks use; org and project come from
the one core, `scripts/ace-context`, the token from the device-code login):
```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --line; echo "exit: $?"
```
(One `ace-cli status` with explicit `--org`/`--project`, classified by exit code and stderr; prints the one problem
line, nothing when ok.)

**Report** (exit code first, then the error text):
- ✅ exit 0: server reachable, authenticated, project found (show the pattern count from the JSON if present)
- ⚠️ non-zero, text mentions `401`, `unauthorized`, `expired` or `login`: authentication failed
- ⚠️ non-zero, text mentions `404` or `not found`: project not found
- ❌ non-zero, text mentions `ENOTFOUND`, `ECONNREFUSED`, `ETIMEDOUT`, `fetch failed` or `timeout`: server unreachable

**If Failed**:
```
❌ ACE Server: UNREACHABLE

Server URL: https://ace-api.code-engine.app
Error: <first line of the ace-cli output>

Possible Causes:
1. Network connectivity issues
2. Firewall blocking HTTPS

Recommended Actions:
1. Re-run: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli doctor
2. Check firewall settings
3. Try different network (WiFi vs. Ethernet)
4. Confirm auth status: /ace:ace-login
```

**If authentication failed**:
```
⚠️ ACE Server: AUTHENTICATION FAILED

Error: <first line of the ace-cli output>

Recommended Actions:
1. Run: /ace:ace-login
2. Check: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli whoami
```

**If project not found**:
```
⚠️ ACE Server: PROJECT NOT FOUND

Project ID: prj_xxxxx

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
# Check if hook scripts exist (installPath from installed_plugins.json)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(jq -r '.plugins["ace@ce-dot-net-marketplace"][0].installPath // empty' ~/.claude/plugins/installed_plugins.json 2>/dev/null)}"

# Check all hook wrappers in scripts/
test -f "$PLUGIN_ROOT/scripts/ace_install_cli.sh" && echo "install_cli: EXISTS" || echo "install_cli: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_before_task_wrapper.sh" && echo "before_task: EXISTS" || echo "before_task: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_posttooluse_wrapper.sh" && echo "posttooluse: EXISTS" || echo "posttooluse: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_posttooluse_domain_inject.sh" && echo "posttooluse_domain_inject: EXISTS" || echo "posttooluse_domain_inject: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_posttoolusefailure_wrapper.sh" && echo "posttoolusefailure: EXISTS" || echo "posttoolusefailure: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_sessionstart_compact.sh" && echo "sessionstart_compact: EXISTS" || echo "sessionstart_compact: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_permission_denied_wrapper.sh" && echo "permission_denied: EXISTS" || echo "permission_denied: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_stop_wrapper.sh" && echo "stop: EXISTS" || echo "stop: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_sessionend_wrapper.sh" && echo "sessionend: EXISTS" || echo "sessionend: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_subagent_start_wrapper.sh" && echo "subagent_start: EXISTS" || echo "subagent_start: MISSING"
test -f "$PLUGIN_ROOT/scripts/ace_subagent_stop_wrapper.sh" && echo "subagent_stop: EXISTS" || echo "subagent_stop: MISSING"

# Check hooks.json
test -f "$PLUGIN_ROOT/hooks/hooks.json" && echo "hooks.json: EXISTS"
```

**Expected Hooks** (v8 round 2: PostToolBatch + PreToolUse(Agent) included incl. the async row: orphan sweep + one-time sqlite rebuild):
1. `SessionStart` → `ace_install_cli.sh` (startup|clear|resume; plus the async row, flag `--update-check`)
2. `SessionStart` (compact) → `ace_sessionstart_compact.sh`
3. `UserPromptSubmit` (sync) → `ace_before_task_wrapper.sh`
4. `PostToolBatch` (async, one event per parallel tool batch) → accumulator script (`ace_posttooluse_wrapper.sh --batch`)
4b. `PreToolUse` (matcher `Agent` only, sync) → `ace_pretooluse_agent_stash.sh`: prompt stash into `agent-prompts/` for SubagentStart (the only PreToolUse hook in v8)
5. `PostToolUse` (Read|Glob|Grep) → `ace_posttooluse_domain_inject.sh`
6. `PostToolUseFailure` (async, matcher `*`) → `ace_posttoolusefailure_wrapper.sh`
7. `SubagentStart` → `ace_subagent_start_wrapper.sh`
8. `Stop` (sync, timeout 15; only dispatches a detached learn) → `ace_stop_wrapper.sh`
9. `SubagentStop` (sync, timeout 15; only dispatches a detached learn) → `ace_subagent_stop_wrapper.sh`
10. `PermissionDenied` (async) → `ace_permission_denied_wrapper.sh`
11. `SessionEnd` → `ace_sessionend_wrapper.sh`

**Report**:
- ✅ All hooks registered (11/11)
- ⚠️ Some hooks missing (e.g., 7/10)
- ❌ No hooks registered (0/11)

**If Failed**:
```
❌ Hooks: NOT REGISTERED

Expected Hook Scripts:
- ace_install_cli.sh (checks the Claude Code version and that a CLI is present)
- ace_before_task_wrapper.sh (retrieves patterns before tasks)
- ace_posttooluse_wrapper.sh (captures tool use after each tool call)
- ace_posttooluse_domain_inject.sh (domain injection on Read/Glob/Grep)
- ace_pretooluse_agent_stash.sh (PreToolUse Agent prompt stash)
- ace_posttoolusefailure_wrapper.sh (failed Bash calls into the learn trajectory)
- ace_sessionstart_compact.sh (re-inject patterns after compaction)
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
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli whoami --json 2>/dev/null | jq -e '.authenticated == true' >/dev/null 2>&1 \
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

Current: organizations/apiKey format (v1.x — deprecated)
Expected: device-code token format (ace-cli 4.x)

Recommended Actions:
1. Update the plugin: claude plugin update ace@ce-dot-net-marketplace
2. Run: /ace:ace-login
```

---

### Check 8: Version Status

**What to Check**:
```bash
# Get plugin version (installPath from installed_plugins.json)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(jq -r '.plugins["ace@ce-dot-net-marketplace"][0].installPath // empty' ~/.claude/plugins/installed_plugins.json 2>/dev/null)}"
PLUGIN_JSON="$PLUGIN_ROOT/.claude-plugin/plugin.json"
if [ -f "$PLUGIN_JSON" ]; then
    jq -r '.version' "$PLUGIN_JSON"
else
    echo "unknown"
fi

# ace-cli: the pin this plugin version was tested with, and the one that actually runs
jq -r '.dependencies["@ace-sdk/cli"]' "$PLUGIN_ROOT/package.json"
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version 2>/dev/null || echo "not installed"

# Check for Python hooks (shared-hooks/)
if [ -d "${PLUGIN_ROOT}/shared-hooks" ]; then
    echo "Python hooks: present"
else
    echo "Python hooks: missing"
fi
# The fallback hooks need Python >= 3.10 (8.1.0)
"${PLUGIN_ROOT}/scripts/ace-python" || echo "Python >= 3.10 needed for the fallback hooks; the mod chain is unaffected"
```

**Expected Versions**:
- Plugin: the installed marketplace version
- ace-cli: exactly the pin in `package.json` (plugin and CLI go hand in hand; a new CLI reaches you with the next plugin update)

**Report**:
- ✅ CLI version == pin
- ⚠️ CLI differs from the pin (untested combination)
- ❌ No CLI

**If Updates Are Wanted**:
```
Update the plugin: claude plugin update ace@ce-dot-net-marketplace
(the bundled ace-cli is installed with it), then restart Claude Code.
```

---

### Check 8b: Local Session Cache Health (sessions.db)

`~/.ace-cache/sessions.db` is a 24 h-TTL local cache of `ace-cli`. When it grows large, concurrent `ace-cli`
processes hit `database is locked` and hooks time out. Run:

```bash
python3 - <<'PY'
# ace-doctor: sessions-db-health
import os, json, time
from datetime import datetime, timezone

MB = 1024 * 1024
warned = False
db = os.path.expanduser("~/.ace-cache/sessions.db")
if os.path.exists(db) and os.path.getsize(db) > 100 * MB:
    warned = True
    print("WARN: %s is %d MB (over 100 MB)" % (db, os.path.getsize(db) // MB))
import subprocess
try:
    logs = subprocess.run([os.path.join(os.environ.get("CLAUDE_PLUGIN_ROOT", ""), "scripts", "ace-context"), "--logs"],
                          capture_output=True, text=True).stdout.strip()
except OSError:
    logs = ""
logs = logs or os.path.join(os.getcwd(), ".claude", "data", "logs")
log = os.path.join(logs, "ace-relevance.jsonl")  # 8.1.0: the repo root's log (log_root)
cutoff = time.time() - 24 * 3600
locked = 0
counts = {"learn_retry": 0, "learn_failed": 0}
ctx = {}
for path in (log, os.path.join(logs, "ace-relevance.1.jsonl")):  # also the rotated file (ace-relevance.1.jsonl)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    ev = row.get("event")
                    if ev == "learn_retry":
                        counts["learn_retry"] += 1
                    elif ev == "execution" and row.get("learning_sent") is False:
                        counts["learn_failed"] += 1
                    elif ev == "context":
                        k = "%s/%s" % (row.get("source"), row.get("state"))
                        ctx[k] = ctx.get(k, 0) + 1
                    # stderr_sample is cut at 300 chars, so also count pin-drop rows
                    if not ("database is locked" in line or row.get("pin_failed") is True
                            or row.get("pin_skipped") == "backoff"):
                        continue
                    ts = row.get("timestamp", "")
                    t = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    continue
                if t >= cutoff:
                    locked += 1
    except OSError:
        pass
print("INFO: learn retries %d, failed learns %d; binding source/state: %s" % (
    counts["learn_retry"], counts["learn_failed"], ", ".join("%s %d" % kv for kv in ctx.items()) or "none"))
if locked:
    warned = True
    print("WARN: %d lock incident(s) ('database is locked' / pin_failed / pin backoff) in ace-relevance.jsonl in the last 24 h" % locked)
if warned:
    print("Fix: stop running ACE CLI processes (pkill -f 'ace-cli|@ace-sdk/cli'), then delete ~/.ace-cache/sessions.db,")
    print("     sessions.db-wal and sessions.db-shm (a 24 h-TTL cache, safe to drop) - or run")
    print("     /ace:ace-cleanup --legacy --yes --sessions-db")
else:
    print("PASS: sessions.db healthy, no recent 'database is locked' errors")
PY
```

- PASS: no WARN lines.
- WARN: sessions.db over 100 MB, or a `database is locked` row within the last 24 h. Show the remediation above.

---

### Check 9: Cache Diagnostics

ACE uses **two distinct caches** that behave differently and are cleared by different mechanisms.

#### Cache 1: In-Memory Client Cache (LRU)

- Held in the running ace-cli process memory
- Cleared by: the CLI's `cache clear` command (any `--type` flag); it only touches this in-memory cache
- Scope: per-process; lost on process exit automatically

**Important**: `cache clear` only clears the in-memory cache. It does **not** clear the SQLite graph cache on disk.

#### Cache 2: SQLite Graph Cache

- Location: `~/.ace-cache/<org>__<project>.db`
- Contains: pattern graph data with a **7-day TTL**; filled only by ace-cli >= 4.2.1 with a working better-sqlite3 binary (the pinned CLI + the SessionStart rebuild)
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
[4] CLI Availability..................... ✅ PASS (v4.3.4)
[5] ACE Server Connectivity.............. ✅ PASS (ace-cli status)
[6] Hooks Registered..................... ✅ PASS (11/11)
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
CLI Version: v4.3.4
Architecture: Hook-based (v7.x)
Project ID: prj_d3a244129d62c198
Organization: org_34fYIlitYk4nyFuTvtsAzA6uUJF

Registered Hooks:
• SessionStart → ace_install_cli.sh
• UserPromptSubmit → ace_before_task_wrapper.sh
• PreToolUse (Agent) → ace_pretooluse_agent_stash.sh
• PostToolBatch → ace_posttooluse_wrapper.sh --batch
• PostToolUse (Read|Glob|Grep) → ace_posttooluse_domain_inject.sh
• PostToolUseFailure → ace_posttoolusefailure_wrapper.sh
• SessionStart (compact) → ace_sessionstart_compact.sh
• PermissionDenied → ace_permission_denied_wrapper.sh
• Stop → ace_stop_wrapper.sh
• SessionEnd → ace_sessionend_wrapper.sh
• SubagentStart → ace_subagent_start_wrapper.sh
• SubagentStop → ace_subagent_stop_wrapper.sh

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
[4] CLI Availability..................... ✅ PASS (v4.3.4)
[5] ACE Server Connectivity.............. ✅ PASS (ace-cli status)
[6] Hooks Registered..................... ⚠️  WARN (8/11)
[7] CLI Configuration.................... ✅ PASS
[8] Version Status....................... ⚠️  WARN
[9] Cache Diagnostics.................... ✅ PASS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Overall Health: 🟡 NEEDS ATTENTION (3 warnings)

⚠️  Warnings Found:

[3] Project Configuration
    Issue: not bound (scripts/ace-context exit 5, reason no_binding)
    Impact: Hooks cannot determine which project to use
    Fix: Run /ace:ace-configure

[6] Hooks Registered
    Issue: Some hook scripts missing (8/11 found)
    Impact: Learning capture and subagent learning won't work
    Fix: Reinstall plugin or check scripts/ directory

[8] Version Status
    Issue: Updates available
    Plugin: installed → latest
    CLI: pinned version → newer plugin
    Fix: See recommended actions below

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Quick Fix All Issues:

Run these commands in order:
1. /ace:ace-configure
2. claude plugin update ace@ce-dot-net-marketplace
3. Restart Claude Code

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

System Information:

Plugin Version: v7.0.0
CLI Version: v4.3.4
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
