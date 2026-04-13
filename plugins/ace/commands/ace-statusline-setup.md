---
description: Install, update, or uninstall ACE statusline. Use '/ace-statusline-setup' to install, '/ace-statusline-setup update' to update, '/ace-statusline-setup uninstall' to remove.
argument-hint: "[update|uninstall]"
allowed-tools: Bash(ace-cli:*), Bash(jq:*), Bash(npm:*), Bash(cp:*), Bash(chmod:*), Bash(rm:*), Bash(mv:*), Read
---

# ACE Statusline Management

## Check the argument provided by the user:

- `/ace-statusline-setup uninstall` → run **Uninstall**
- `/ace-statusline-setup update` → run **Update**
- Otherwise → run **Install**

## Install (default)

1. Copy the statusline script from the plugin:
```bash
cp "$CLAUDE_PLUGIN_ROOT/scripts/ace_statusline.sh" ~/.claude/ace_statusline.sh
chmod +x ~/.claude/ace_statusline.sh
```

2. Configure statusLine in `~/.claude/settings.json`:
```bash
jq '.statusLine = {"type": "command", "command": "~/.claude/ace_statusline.sh", "refreshInterval": 5}' ~/.claude/settings.json > ~/.claude/settings.json.tmp \
  && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

3. Tell the user: "ACE statusline installed. Restart Claude Code to see it."

## Update

Re-copy the latest script from the plugin (preserves settings.json config):
```bash
cp "$CLAUDE_PLUGIN_ROOT/scripts/ace_statusline.sh" ~/.claude/ace_statusline.sh
chmod +x ~/.claude/ace_statusline.sh
```

Tell the user: "ACE statusline updated to latest version."

## Uninstall

1. Remove statusLine from `~/.claude/settings.json`:
```bash
jq 'del(.statusLine)' ~/.claude/settings.json > ~/.claude/settings.json.tmp \
  && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

2. Remove the script:
```bash
rm -f ~/.claude/ace_statusline.sh
```

3. Tell the user: "ACE statusline removed. Restart Claude Code to apply."
