---
name: ace-statusline
description: Install, update, or uninstall ACE statusline integration for Claude Code. Use '/ace-statusline' to install, '/ace-statusline update' to update, '/ace-statusline uninstall' to remove.
---

# ACE Statusline Management

Manage the ACE statusline in Claude Code. Supports: **install** (default), **update**, and **uninstall**.

## Check the argument provided by the user:

- If the user typed `/ace-statusline uninstall` → run the **Uninstall** steps
- If the user typed `/ace-statusline update` → run the **Update** steps
- Otherwise → run the **Install** steps

## Install (default)

1. Copy the statusline script from the plugin to `~/.claude/`:
```bash
cp "$CLAUDE_PLUGIN_ROOT/scripts/ace_statusline.sh" ~/.claude/ace_statusline.sh
chmod +x ~/.claude/ace_statusline.sh
```

2. Add `statusLine` to `~/.claude/settings.json`:
```bash
jq '.statusLine = {"type": "command", "command": "~/.claude/ace_statusline.sh"}' ~/.claude/settings.json > ~/.claude/settings.json.tmp \
  && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

3. Tell the user: "ACE statusline installed. Restart Claude Code to see it."

## Update

Re-copy the latest script from the plugin (preserves settings.json config):
```bash
cp "$CLAUDE_PLUGIN_ROOT/scripts/ace_statusline.sh" ~/.claude/ace_statusline.sh
chmod +x ~/.claude/ace_statusline.sh
```

Tell the user: "ACE statusline updated to latest version. Changes take effect on next refresh."

## Uninstall

1. Remove `statusLine` from `~/.claude/settings.json`:
```bash
jq 'del(.statusLine)' ~/.claude/settings.json > ~/.claude/settings.json.tmp \
  && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

2. Remove the script:
```bash
rm -f ~/.claude/ace_statusline.sh
```

3. Tell the user: "ACE statusline removed. Restart Claude Code to apply."
