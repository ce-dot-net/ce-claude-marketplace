---
disable-model-invocation: true
model: claude-haiku-4-5
description: Report which ace-cli ACE uses and repair a missing or broken install
argument-hint:
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(jq:*), Bash(npm:*), Bash(node:*), Bash(claude:*), Bash(test:*), Bash(ls:*), Read
---

# ACE CLI Repair

Each plugin version runs exactly the ace-cli it was tested with: the exact pin in `${CLAUDE_PLUGIN_ROOT}/package.json`,
installed by Claude Code into `${CLAUDE_PLUGIN_ROOT}/node_modules` when the plugin is installed or updated.
Node.js is required. Run the steps in order and stop at the first one that fixes it.

## Step 1: Report

```bash
PIN=$(jq -r '.dependencies["@ace-sdk/cli"]' "${CLAUDE_PLUGIN_ROOT}/package.json")
echo "pinned in package.json: $PIN"
if test -f "${CLAUDE_PLUGIN_ROOT}/node_modules/@ace-sdk/cli/dist/cli.js"; then
  echo "source: plugin-local $(jq -r .version "${CLAUDE_PLUGIN_ROOT}/node_modules/@ace-sdk/cli/package.json")"
else
  echo "source: none plugin-local (packages not installed)"
fi
GLOBAL_CLI="$(command -v 'ace-cli')"
test -n "$GLOBAL_CLI" && echo "global: $GLOBAL_CLI $("$GLOBAL_CLI" --version 2>/dev/null)"
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version
```

Tell the user which source is used (plugin-local wins over global). A global CLI older than the pin is not used;
a different one works but is untested with this plugin version. If plugin-local is present and the version equals the
pin, stop: nothing to repair.

## Step 2: Packages missing - update the plugin

```bash
claude plugin update ace@ce-dot-net-marketplace
```

Then restart Claude Code. If the packages are still missing, show the likely reason: no `npm` or `node` on PATH,
no network, or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set (Claude Code skips the package install then).

## Step 3: Install the packages by hand

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && npm ci --ignore-scripts && npm rebuild better-sqlite3
```

`npm ci` installs exactly the locked pin; the rebuild gives the CLI its local cache (otherwise SessionStart does it once).
Show npm's error if it fails.

## Last resort: global install

Only if step 3 cannot work (for example a read-only plugin directory), tell the user: `npm install -g @ace-sdk/cli@<pin>`
with the pin from step 1. A global CLI works as a fallback but stays untested against this plugin version.

After any fix, run `/ace:ace-doctor`.
