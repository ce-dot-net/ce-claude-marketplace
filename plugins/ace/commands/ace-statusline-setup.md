---
description: Wire the ACE statusline into the current project
argument-hint:
---

# ACE Statusline Setup

This command wires the ACE statusline script into your current project so Claude Code displays ACE session metrics in its status bar.

## Instructions for Claude

When the user invokes this command, follow these steps **in order**. Announce each step to the user before running it (e.g., "Checking prerequisites..."). Do not skip steps or combine them out of order.

---

### Step 1: Check Prerequisites

Tell the user: "Checking prerequisites..."

Run this single bash command:

```bash
command -v jq && jq --version || echo "JQ_NOT_FOUND"
```

**Decision**:
- Output contains `JQ_NOT_FOUND`: Tell the user jq is required and is not installed. Provide platform-specific install instructions (`brew install jq` on macOS, `apt install jq` / `yum install jq` on Linux). **Stop. Do not proceed.**
- Output contains a jq version line: jq is present. Continue to Step 2.

---

### Step 2: Locate ace-statusline.sh

Tell the user: "Locating ace-statusline.sh..."

Run each check in order. Stop at the first that prints `FOUND:`.

**Step 2.1** — Plugin root (works when the ACE plugin is active in this session):
```bash
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/ace-statusline.sh" ]; then
  echo "FOUND: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-statusline.sh"
else
  echo "NOT_FOUND"
fi
```

**Step 2.2** — Only run this if Step 2.1 printed `NOT_FOUND`. XDG config path:
```bash
_p="$HOME/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh"
if [ -f "$_p" ]; then echo "FOUND: $_p"; else echo "NOT_FOUND"; fi
```

**Step 2.3** — Only run this if Step 2.2 printed `NOT_FOUND`. macOS Application Support:
```bash
_p="$HOME/Library/Application Support/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh"
if [ -f "$_p" ]; then echo "FOUND: $_p"; else echo "NOT_FOUND"; fi
```

**Decision**:
- At least one step printed `FOUND: <path>`: Record the path after `FOUND: ` as `STATUSLINE_PATH`. Continue to Step 3.
- All three printed `NOT_FOUND`: Show the error block below and **stop**:

```
Could not find ace-statusline.sh in any expected location.

Searched:
  1. ${CLAUDE_PLUGIN_ROOT}/scripts/ace-statusline.sh  (plugin root env var)
  2. ~/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh
  3. ~/Library/Application Support/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh

To wire a custom location manually:
  1. Create .claude/statusline-command.sh containing:
       #!/usr/bin/env bash
       exec "/absolute/path/to/ace-statusline.sh" "$@"
  2. chmod +x .claude/statusline-command.sh
  3. Add to .claude/settings.local.json: {"statusLine":{"command":".claude/statusline-command.sh"}}
```

---

### Step 3: Check Idempotency

Tell the user: "Checking if statusline is already configured..."

Run this command, substituting the literal resolved `STATUSLINE_PATH` for `<STATUSLINE_PATH>`:

```bash
grep -qF "<STATUSLINE_PATH>" .claude/statusline-command.sh 2>/dev/null && echo "ALREADY_WIRED" || echo "NEEDS_WIRING"
```

**Decision**:
- Output is `ALREADY_WIRED`: The statusline is already pointing to this exact script. Tell the user:
  ```
  ACE statusline is already wired.
    Script:  <STATUSLINE_PATH>
    Wrapper: .claude/statusline-command.sh
  No changes made.
  ```
  Then skip to Step 5 (run the verification checks only — do not recreate files).
- Output is `NEEDS_WIRING`: Continue to Step 4.

---

### Step 4: Create and Configure

Tell the user: "Wiring statusline..."

**Step 4.1** — Ensure `.claude` directory exists:
```bash
mkdir -p .claude
```

**Step 4.2** — Write `.claude/statusline-command.sh`.

CRITICAL: You must write the file with the literal resolved path substituted into the `exec` line. Do NOT write the placeholder text `<STATUSLINE_PATH>` or any variable reference. The exec line must be a hard-coded absolute path string.

For example, if `STATUSLINE_PATH` resolved to `/home/alice/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh`, the file must contain exactly:

```
#!/usr/bin/env bash
# ACE Statusline — wired by /ace-statusline-setup
exec "/home/alice/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh" "$@"
```

Construct and run a bash command that writes this file with the actual resolved path. Use double quotes around the path in the `exec` line — this is required for paths containing spaces (e.g. paths under `~/Library/Application Support/`).

A correct approach using printf:
```bash
printf '#!/usr/bin/env bash\n# ACE Statusline — wired by /ace-statusline-setup\nexec "%s" "$@"\n' "<STATUSLINE_PATH>" > .claude/statusline-command.sh
```
Replace `<STATUSLINE_PATH>` with the literal resolved path before running.

**Step 4.3** — Make it executable:
```bash
chmod +x .claude/statusline-command.sh
```

**Step 4.4** — Update `.claude/settings.local.json`.

First, check whether the file exists and whether it is valid JSON:
```bash
if [ -f .claude/settings.local.json ]; then
  jq -e . .claude/settings.local.json > /dev/null 2>&1 && echo "VALID_JSON" || echo "INVALID_JSON"
else
  echo "NOT_PRESENT"
fi
```

**Decision**:
- `NOT_PRESENT`: Create the file:
  ```bash
  printf '{\n  "statusLine": {\n    "command": ".claude/statusline-command.sh"\n  }\n}\n' > .claude/settings.local.json
  ```

- `VALID_JSON`: Merge non-destructively (preserves all existing keys):
  ```bash
  jq '.statusLine.command = ".claude/statusline-command.sh"' .claude/settings.local.json > .claude/settings.local.json.tmp \
    && mv .claude/settings.local.json.tmp .claude/settings.local.json
  ```

- `INVALID_JSON`: **Do not overwrite the file.** Tell the user:
  ```
  .claude/settings.local.json exists but contains invalid JSON and cannot be safely updated.
  Please fix or delete the file manually, then run /ace-statusline-setup again.
  ```
  **Stop.**

---

### Step 5: Verify and Report

Tell the user: "Verifying..."

Run all checks in one bash command:

```bash
echo "=== VERIFY ==="
test -f .claude/statusline-command.sh   && echo "WRAPPER_EXISTS"   || echo "WRAPPER_MISSING"
test -x .claude/statusline-command.sh   && echo "WRAPPER_EXEC"     || echo "WRAPPER_NOT_EXEC"
jq -r '.statusLine.command // "NOT_SET"' .claude/settings.local.json 2>/dev/null || echo "SETTINGS_UNREADABLE"
```

**Interpret results**:
- All three show `WRAPPER_EXISTS`, `WRAPPER_EXEC`, and `.claude/statusline-command.sh` (the command value): success. Show the summary below.
- Any line shows a failure indicator (`WRAPPER_MISSING`, `WRAPPER_NOT_EXEC`, `NOT_SET`, `SETTINGS_UNREADABLE`): tell the user which check failed and suggest running `/ace-statusline-setup` again.

**Success summary** (fill in the resolved STATUSLINE_PATH):
```
ACE statusline wired successfully.

  Source script : <STATUSLINE_PATH>
  Wrapper       : .claude/statusline-command.sh
  Settings key  : .claude/settings.local.json → statusLine.command

Restart Claude Code for the statusline to appear in the status bar.
```

This is the final step. Do not perform any additional actions after showing this summary.

---

## Notes

- This command is **idempotent** — safe to run multiple times. Re-running when already wired makes no changes.
- The wrapper script is a thin shell that delegates to the installed `ace-statusline.sh`. If the ACE plugin is later updated or moved, re-run `/ace-statusline-setup` to refresh the wiring.
- The statusline visualizes ACE session metrics (QPT score, focus, confidence, playbook health) in Claude Code's status bar.
- Requires `jq` at runtime (both for this setup command and for the statusline script itself).
