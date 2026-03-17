---
description: Wire the ACE statusline into the current project
argument-hint:
---

# ACE Statusline Setup

This command wires the ACE statusline script into your current project so Claude Code displays ACE session metrics in its status bar.

## Instructions for Claude

When the user invokes this command, follow these steps in order:

### Step 1: Check Prerequisites

Use the Bash tool to check if `jq` is available:

```bash
command -v jq && echo "FOUND" || echo "NOT_FOUND"
```

**Handle results**:
- If output contains `NOT_FOUND`: Tell the user to install `jq` (e.g., `brew install jq` on macOS, `apt install jq` on Linux) and exit. Do not proceed.
- If output contains `FOUND`: continue to Step 2.

### Step 2: Locate ace-statusline.sh

Try each location in order using the Bash tool. Stop at the first one that exists.

**Step 2.1**: Check plugin root (works when ACE plugin is active):
```bash
test -f "${CLAUDE_PLUGIN_ROOT}/scripts/ace-statusline.sh" && echo "FOUND: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-statusline.sh" || echo "NOT_FOUND"
```

**Step 2.2**: If NOT_FOUND, check macOS user config:
```bash
test -f "$HOME/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh" && echo "FOUND: $HOME/.config/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh" || echo "NOT_FOUND"
```

**Step 2.3**: If NOT_FOUND, check macOS Application Support:
```bash
test -f "$HOME/Library/Application Support/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh" && echo "FOUND: $HOME/Library/Application Support/claude-code/marketplaces/ce-dot-net-marketplace/plugins/ace/scripts/ace-statusline.sh" || echo "NOT_FOUND"
```

**Handle results**:
- Use the path from the first step that returned `FOUND`. Record this as `STATUSLINE_PATH`.
- If all three returned `NOT_FOUND`, show this error and exit:
  ```
  ❌ Could not find ace-statusline.sh automatically.

  If you have it at a custom location, you can wire it manually:
  1. Create .claude/statusline-command.sh with: exec "/path/to/ace-statusline.sh" "$@"
  2. Make it executable: chmod +x .claude/statusline-command.sh
  3. Add to .claude/settings.local.json: {"statusLine": {"command": ".claude/statusline-command.sh"}}
  ```

### Step 3: Check if Already Wired (Idempotency)

Use the Bash tool to check if the statusline is already configured:

```bash
test -f ".claude/statusline-command.sh" && cat ".claude/statusline-command.sh" || echo "NOT_PRESENT"
```

**Handle results**:
- If the output contains `NOT_PRESENT` or does not contain the `STATUSLINE_PATH` found in Step 2: proceed to Step 4.
- If the file exists and already contains the exact `STATUSLINE_PATH` from Step 2: show a confirmation message and skip to Step 5 (verify only):
  ```
  ✅ ACE statusline is already wired to: {STATUSLINE_PATH}
  No changes needed.
  ```
  Then jump to Step 5 to show the final status.

### Step 4: Create and Configure

**Step 4.1**: Ensure the `.claude` directory exists:
```bash
mkdir -p .claude
```

**Step 4.2**: Write `.claude/statusline-command.sh`. Replace `{STATUSLINE_PATH}` with the actual resolved path from Step 2:
```bash
cat > .claude/statusline-command.sh << 'SCRIPT_EOF'
#!/usr/bin/env bash
# ACE Statusline — wired by /ace-statusline-setup
exec "/path/to/ace-statusline.sh" "$@"
SCRIPT_EOF
```

**Important**: The `exec` line must use the literal resolved path, not a variable. Construct the file content with the actual path substituted.

**IMPORTANT: preserve the double quotes around the path — required for paths containing spaces (e.g. ~/Library/Application Support/...).**

**Step 4.3**: Make it executable:
```bash
chmod +x .claude/statusline-command.sh
```

**Step 4.4**: Update `.claude/settings.local.json` using `jq`.

First check if the file exists:
```bash
test -f .claude/settings.local.json && echo "EXISTS" || echo "NOT_PRESENT"
```

- If `NOT_PRESENT`: Create it with just the statusLine key:
  ```bash
  echo '{"statusLine":{"command":".claude/statusline-command.sh"}}' | jq '.' > .claude/settings.local.json
  ```

- If `EXISTS`: Merge non-destructively (preserves all existing settings and sub-keys under `statusLine`):
  ```bash
  jq -e --arg cmd ".claude/statusline-command.sh" '.statusLine.command = $cmd' .claude/settings.local.json > .claude/settings.local.json.tmp && mv .claude/settings.local.json.tmp .claude/settings.local.json
  ```

### Step 5: Verify and Confirm

Use the Bash tool to verify the wiring:

```bash
test -f .claude/statusline-command.sh && echo "WRAPPER_OK" || echo "WRAPPER_MISSING"
test -x .claude/statusline-command.sh && echo "EXECUTABLE_OK" || echo "NOT_EXECUTABLE"
jq -r '.statusLine.command // "NOT_SET"' .claude/settings.local.json 2>/dev/null || echo "SETTINGS_MISSING"
```

Show the user a summary:

```
✅ ACE statusline wired successfully!

  Script:   {STATUSLINE_PATH}
  Wrapper:  .claude/statusline-command.sh
  Setting:  .claude/settings.local.json → statusLine.command

Restart Claude Code for the statusline to appear in the status bar.
```

If any verification check failed, show what is missing and suggest running `/ace-statusline-setup` again.

---

## Notes

- This command is **idempotent** — safe to run multiple times.
- The wrapper script (`statusline-command.sh`) is a thin shell that delegates to the installed `ace-statusline.sh`.
- The statusline visualizes ACE session metrics (QPT score, focus, confidence, playbook health) in Claude Code's status bar.
- Requires `jq` at runtime (both for this setup command and for the statusline script itself).
