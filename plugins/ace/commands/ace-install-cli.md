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

Use the Bash tool to check current installation status:

```bash
# Check if ce-ace is installed
if command -v ce-ace >/dev/null 2>&1; then
  VERSION=$(ce-ace --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  echo "INSTALLED:${VERSION:-unknown}"
else
  echo "NOT_INSTALLED"
fi
```

**Handle results**:

- **If output contains `INSTALLED:` and version >= 1.0.0**:
  - Show: `✅ ce-ace v{VERSION} installed and working`
  - EXIT immediately (silent success - no noise!)

- **If output contains `INSTALLED:` but version < 1.0.0**:
  - Show: `⚠️ ce-ace v{VERSION} installed (outdated, latest: check npm)`
  - Ask user: `Would you like to upgrade? (Y/n)`
  - If yes → proceed to Phase 2 (Installation)
  - If no → EXIT

- **If output contains `NOT_INSTALLED`**:
  - Show: `❌ ce-ace CLI not found`
  - Proceed to Phase 2 (Installation)

### Phase 2: Package Manager Detection

Use the Bash tool to detect available package managers:

```bash
# Detect available package managers
echo "=== Available Package Managers ==="
managers=""
counter=1

if command -v npm >/dev/null 2>&1; then
  npm_version=$(npm --version 2>/dev/null || echo "unknown")
  echo "${counter}. npm (v${npm_version})"
  managers="${managers}npm,"
  counter=$((counter + 1))
fi

if command -v pnpm >/dev/null 2>&1; then
  pnpm_version=$(pnpm --version 2>/dev/null || echo "unknown")
  echo "${counter}. pnpm (v${pnpm_version})"
  managers="${managers}pnpm,"
  counter=$((counter + 1))
fi

if command -v yarn >/dev/null 2>&1; then
  yarn_version=$(yarn --version 2>/dev/null || echo "unknown")
  echo "${counter}. yarn (v${yarn_version})"
  managers="${managers}yarn,"
  counter=$((counter + 1))
fi

# If no package managers found
if [ -z "$managers" ]; then
  echo "ERROR:NO_PACKAGE_MANAGERS"
else
  echo "MANAGERS:${managers%,}"
fi
```

**Handle results**:

- **If `ERROR:NO_PACKAGE_MANAGERS`**:
  - Show error message:
    ```
    ❌ No package managers found (npm, pnpm, or yarn required)

    Please install Node.js and npm first:
    - macOS: brew install node
    - Linux: https://nodejs.org/en/download/package-manager
    - Windows: https://nodejs.org/en/download
    ```
  - EXIT with error

- **If `MANAGERS:` found**:
  - Parse the list (e.g., `npm,pnpm`)
  - Proceed to Phase 3

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
npm install -g @ce-dot-net/ce-ace-cli
```

**pnpm**:
```bash
pnpm add -g @ce-dot-net/ce-ace-cli
```

**yarn**:
```bash
yarn global add @ce-dot-net/ce-ace-cli
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
       - Or use: npx @ce-dot-net/ce-ace-cli (run without install)

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

Use the Bash tool to verify the installation worked:

```bash
echo "=== Verification ==="

# Check 1: Command exists
if command -v ce-ace >/dev/null 2>&1; then
  echo "✅ ce-ace command found in PATH"
else
  echo "❌ ce-ace command not found in PATH"
  echo "   PATH issue - may need to restart terminal or update PATH"
  exit 1
fi

# Check 2: Get version
VERSION=$(ce-ace --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$VERSION" ]; then
  echo "✅ Version: ${VERSION}"
else
  echo "⚠️ Could not detect version"
fi

# Check 3: Basic OS check
OS=$(uname -s)
case "$OS" in
  Linux|Darwin)
    echo "✅ OS: ${OS} (supported)"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    echo "⚠️ OS: Windows detected - consider using WSL for better compatibility"
    ;;
  *)
    echo "⚠️ OS: ${OS} (untested, may have issues)"
    ;;
esac

echo "VERIFICATION_COMPLETE"
```

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

**If yes**, use the Bash tool:

```bash
# Test server connectivity
# Try to ping ACE server or use curl to test endpoint
echo "Testing server connectivity..."

# Check if config exists
if [ -f ~/.config/ace/config.json ]; then
  SERVER_URL=$(jq -r '.serverUrl // "https://ace.ce.dev"' ~/.config/ace/config.json 2>/dev/null)

  # Test connectivity with curl
  if curl -s --connect-timeout 5 "${SERVER_URL}/health" >/dev/null 2>&1; then
    echo "✅ Server connectivity: OK (${SERVER_URL})"
  else
    echo "⚠️ Server connectivity: Could not reach ${SERVER_URL}"
    echo "   This is normal if you haven't configured ACE yet"
    echo "   Run /ace:ace-configure to set up server connection"
  fi
else
  echo "ℹ️  No ACE configuration found"
  echo "   Run /ace:ace-configure to set up server connection"
fi
```

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
