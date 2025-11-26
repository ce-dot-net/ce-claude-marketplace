---
description: Install and verify ce-ace CLI tool (smart, non-noisy installation wizard)
argument-hint:
---

# ACE CLI Installation Wizard

This command provides a smart, interactive installation wizard for the `ce-ace` CLI tool.

## Behavior

- **Silent if already installed correctly** (no noise!)
- **Interactive wizard** only when action needed
- **Multi-package-manager support** (npm, pnpm, yarn)
- **Verification** of installation + server connectivity
- **Troubleshooting** guidance on failures

## Instructions for Execution

When the user invokes this command, follow these steps in order:

### Phase 1: Detection (Always Run, But Silent If OK)

Use the Bash tool to check current installation status. **IMPORTANT**: Break this into simple, single-purpose commands to avoid eval parse errors.

**Step 1.1**: Check if ce-ace command exists:
```bash
command -v ce-ace && echo "FOUND" || echo "NOT_INSTALLED"
```

**Step 1.2**: If FOUND, get version:
```bash
ce-ace --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
```

**Handle results**:

- **If Step 1.1 output contains `FOUND`** and Step 1.2 returns a version:
  - Check if version >= 1.0.0
  - If yes: Show `✅ ce-ace v{VERSION} installed and working` and EXIT (silent success!)
  - If no: Show `⚠️ ce-ace v{VERSION} installed (outdated)` and ask `Would you like to upgrade? (Y/n)`
    - If yes → proceed to Phase 2 (Installation)
    - If no → EXIT

- **If Step 1.1 output contains `NOT_INSTALLED`**:
  - Show: `❌ ce-ace CLI not found`
  - Proceed to Phase 2 (Installation)

### Phase 2: Package Manager Detection

Use the Bash tool to detect available package managers. **IMPORTANT**: Use simple, separate commands to avoid parse errors.

**Step 2.1**: Check for npm:
```bash
command -v npm >/dev/null 2>&1 && npm --version 2>/dev/null || echo "NOT_FOUND"
```

**Step 2.2**: Check for pnpm:
```bash
command -v pnpm >/dev/null 2>&1 && pnpm --version 2>/dev/null || echo "NOT_FOUND"
```

**Step 2.3**: Check for yarn:
```bash
command -v yarn >/dev/null 2>&1 && yarn --version 2>/dev/null || echo "NOT_FOUND"
```

**Build list of available managers** from the results above. For each manager that didn't return "NOT_FOUND", add it to a list with its version number.

**Handle results**:

- **If ALL managers returned `NOT_FOUND`**:
  - Show error message:
    ```
    ❌ No package managers found (npm, pnpm, or yarn required)

    Please install Node.js and npm first:
    - macOS: brew install node
    - Linux: https://nodejs.org/en/download/package-manager
    - Windows: https://nodejs.org/en/download
    ```
  - EXIT with error

- **If at least ONE manager was found**:
  - Display numbered list with versions (e.g., "1. npm (v11.1.0)")
  - Proceed to Phase 3 with the list of available managers

### Phase 3: User Selection

Present package manager options to the user and ask them to choose:

**If only one manager available** (e.g., just `npm`):
- Auto-select that manager
- Show: `📦 Using npm for installation`

**If multiple managers available**:
- Show the numbered list from Phase 2
- Ask: `Which package manager would you like to use? [1-{N}]:`
- Wait for user input (number selection)
- Validate input is a valid number

**Store selected manager** in a variable for Phase 4.

### Phase 4: Installation Command Construction

Based on the selected package manager, construct the installation command:

**npm**:
```bash
npm install -g @ace-sdk/cli
```

**pnpm**:
```bash
pnpm add -g @ace-sdk/cli
```

**yarn**:
```bash
yarn global add @ace-sdk/cli
```

**Show the command to the user**:
```
📥 Installation command:
{COMMAND}

Proceed with installation? (Y/n):
```

**Wait for user confirmation**:
- If `n` or `N` → EXIT (user cancelled)
- If `Y`, `y`, or Enter → proceed to Phase 5

### Phase 5: Execute Installation

Use the Bash tool to run the installation command:

```bash
# Run installation command (use the selected manager)
{INSTALL_COMMAND}
```

**Handle results**:

- **If exit code = 0** (success):
  - Show: `✅ Installation completed successfully!`
  - Proceed to Phase 6 (Verification)

- **If exit code != 0** (failure):
  - Show error message with common troubleshooting:
    ```
    ❌ Installation failed!

    Common issues:

    1. Permission errors:
       - Try: sudo {INSTALL_COMMAND}
       - Or use: npx @ace-sdk/cli (run without install)

    2. Network errors:
       - Check internet connection
       - Try: npm config set registry https://registry.npmjs.org/

    3. PATH issues:
       - After install, close and reopen terminal
       - Or add npm bin to PATH: export PATH="$(npm bin -g):$PATH"

    Full error output:
    {ERROR_OUTPUT}
    ```
  - EXIT with error

### Phase 6: Verify Installation

Use the Bash tool to verify the installation worked. **IMPORTANT**: Use simple, separate commands.

**Step 6.1**: Check if command exists:
```bash
command -v ce-ace
```

**Step 6.2**: Get version (if Step 6.1 succeeded):
```bash
ce-ace --version
```

**Step 6.3**: Get OS info:
```bash
uname -s
```

**Process results**:
- If Step 6.1 returns a path: ✅ ce-ace found
- If Step 6.1 fails: ❌ Not found (PATH issue, may need to restart terminal)
- Extract version number from Step 6.2 output
- Check OS from Step 6.3: Linux/Darwin = supported, Windows = suggest WSL

**Show verification results** to the user with a summary:
```
🔍 Installation Verification:
{OUTPUT_FROM_VERIFICATION}

🎉 All set! The ce-ace CLI tool is installed and ready to use.

Next steps:
1. Run /ace:ace-configure to set up your organization and project
2. Run /ace:ace-status to check your playbook
3. Start using ACE for automatic pattern learning!
```

### Phase 7: Optional Server Connectivity Test

**Ask user** if they want to test server connectivity:
```
Would you like to test connection to the ACE server? (Y/n):
```

**If yes**, use simple Bash commands:

**Step 7.1**: Check if global config exists:
```bash
test -f ~/.config/ace/config.json && echo "CONFIG_EXISTS" || echo "NO_CONFIG"
```

**Step 7.2**: If config exists, get server URL:
```bash
jq -r '.serverUrl // "https://ace-api.code-engine.app"' ~/.config/ace/config.json
```

**Step 7.3**: Test connectivity (using URL from Step 7.2):
```bash
curl -s --connect-timeout 5 {SERVER_URL}/health
```

**Process results**:
- If NO_CONFIG: Show "ℹ️  No ACE configuration found - Run /ace-configure"
- If Step 7.3 succeeds: ✅ Server connectivity OK
- If Step 7.3 fails: ⚠️ Could not reach server (normal if not configured)

**Show connectivity results** and exit with success.

---

## Error Handling Guidelines

**Always provide actionable guidance** when errors occur:

1. **Permission errors**: Suggest `sudo` or `npx` alternative
2. **Network errors**: Check internet, suggest registry config
3. **PATH errors**: Explain how to add npm bin to PATH
4. **Version conflicts**: Suggest uninstall old version first
5. **OS compatibility**: Warn about Windows, recommend WSL

**Use clear status indicators**:
- ✅ Success (green)
- ⚠️ Warning (yellow)
- ❌ Error (red)
- ℹ️ Info (blue)
- 🔍 Checking/verifying
- 📦 Package manager
- 📥 Installing
- 🎉 Complete

---

## Important Notes

1. **Be non-noisy**: If already installed correctly, just show "✅ installed" and exit
2. **Be interactive**: Ask for user confirmation before installing
3. **Be helpful**: Provide clear troubleshooting for common issues
4. **Be thorough**: Verify installation after completion
5. **Be informative**: Show next steps after successful install

Execute these phases in order, handling each result appropriately.
