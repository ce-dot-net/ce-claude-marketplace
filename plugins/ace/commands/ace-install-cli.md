---
disable-model-invocation: true
model: claude-haiku-4-5
description: Report which ace-cli ACE uses and repair a missing or broken install
argument-hint:
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(npm:*), Bash(node:*), Bash(python3:*), Bash(claude:*), Bash(test:*), Bash(ls:*), Read
---

# ACE CLI Repair

Each plugin version runs exactly the ace-cli it was tested with: the exact pin in `${CLAUDE_PLUGIN_ROOT}/package.json`,
installed by Claude Code into `${CLAUDE_PLUGIN_ROOT}/node_modules` when the plugin is installed or updated.
Node.js is required. Run the steps in order and stop at the first one that fixes it.

## Step 1: Report

```bash
PIN=$("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --get dependencies.@ace-sdk/cli '' < "${CLAUDE_PLUGIN_ROOT}/package.json")
echo "pinned in package.json: $PIN"
if test -f "${CLAUDE_PLUGIN_ROOT}/node_modules/@ace-sdk/cli/dist/cli.js"; then
  echo "source: plugin-local $("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --get version '' < "${CLAUDE_PLUGIN_ROOT}/node_modules/@ace-sdk/cli/package.json")"
else
  echo "source: none plugin-local (packages not installed)"
fi
GLOBAL_CLI="$(command -v 'ace-cli')"
test -n "$GLOBAL_CLI" && echo "global: $GLOBAL_CLI $("$GLOBAL_CLI" --version 2>/dev/null)"
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version
```

Tell the user which source is used (plugin-local wins over global). The hooks do not use a global CLI older than the pin (the commands' wrapper runs whichever it finds);
a different one works but is untested with this plugin version. If plugin-local is present and the version equals the
pin, check the SQLite cache too (`python3 "${CLAUDE_PLUGIN_ROOT}/shared-hooks/utils/ace_cli_installer.py" --status`, field `sqlite`); `active` means stop: nothing to repair. `off (...)` means go to step 3 (it runs only the rebuild then).

## Step 2: Packages missing - update the plugin

```bash
claude plugin update ace@ce-dot-net-marketplace
```

Then restart Claude Code. If the packages are still missing, show the likely reason: no `npm` or `node` on PATH,
no network, or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set (Claude Code skips the package install then).

## Step 3: Install the packages by hand

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/shared-hooks/utils/ace_cli_installer.py" --run
```

This is the same installer SessionStart starts in the background (8.1.1; `ACE_AUTO_INSTALL=0` turns that off): in the plugin
dir only, `npm ci --ignore-scripts` from the lockfile (exactly the locked pin), then `npm rebuild better-sqlite3` (the CLI's
local cache). When the CLI already is the pin and only the better-sqlite3 binding is missing or does not load (8.1.2), it runs ONLY
`npm rebuild better-sqlite3`. It prints one JSON line `{"state": "ok"|"failed"|"running"|"unavailable", "detail": ...}`; show `detail` if it
is not `ok`. Hooks and commands pick the new CLI up on the next call, no restart.

## Last resort: global install

Only if step 3 cannot work (for example a read-only plugin directory), tell the user: `npm install -g @ace-sdk/cli@<pin>`
with the pin from step 1. A global CLI works as a fallback but stays untested against this plugin version.

After any fix, run `/ace:ace-doctor`.
