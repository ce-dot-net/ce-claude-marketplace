---
name: ace-statusline
description: Install ACE statusline integration for Claude Code
---

# ACE Statusline Setup

This command installs the ACE statusline script (`ace_statusline.sh`) into your Claude Code environment.

## What it does

1. Copies `ace_statusline.sh` to `~/.claude/` for portability
2. Configures `statusLine` in `~/.claude/settings.json` to use the ACE statusline script

## Installation Steps

```bash
# Copy the statusline script
cp "$CLAUDE_PLUGIN_ROOT/scripts/ace_statusline.sh" ~/.claude/ace_statusline.sh
chmod +x ~/.claude/ace_statusline.sh

# Add statusLine to settings.json
jq '.statusLine = "~/.claude/ace_statusline.sh"' ~/.claude/settings.json > ~/.claude/settings.json.tmp \
  && mv ~/.claude/settings.json.tmp ~/.claude/settings.json
```

After install, the statusline will show ACE pattern count, learning results, and context usage.
