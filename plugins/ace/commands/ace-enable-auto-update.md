---
description: Enable or disable automatic ACE CLAUDE.md updates on session start
---

# ACE Enable Auto-Update

Control automatic updates of ACE plugin instructions in your project's CLAUDE.md.

## What This Does

Toggles automatic updating of ACE instructions when the plugin version changes. When enabled, ACE will silently update your project's CLAUDE.md on session start if a new plugin version is detected.

## Instructions for Claude

When the user runs `/ace-enable-auto-update`, follow these steps:

### Check Current Status

1. Check if auto-update is currently enabled:
   ```bash
   if [ -f ~/.ace/auto-update-enabled ]; then
       echo "Status: ENABLED"
   else
       echo "Status: DISABLED"
   fi
   ```

2. Show current status to user with explanation

### Ask User for Action

Present options:
```
Auto-Update Status: [ENABLED/DISABLED]

What would you like to do?
1. Enable auto-update  - ACE instructions update automatically on session start
2. Disable auto-update - Manual updates only (run /ace:ace-claude-init)
3. Show more info     - Learn about auto-update feature
4. Cancel            - No changes
```

### Perform Action

**If user chooses "Enable":**
```bash
mkdir -p ~/.ace
touch ~/.ace/auto-update-enabled
echo "✅ Auto-update ENABLED"
echo ""
echo "ACE will now automatically update your project's CLAUDE.md when:"
echo "- A new ACE plugin version is installed"
echo "- You start a Claude Code session"
echo "- Your project's ACE instructions are outdated"
echo ""
echo "Updates are:"
echo "- ✅ Silent (no interruption)"
echo "- ✅ Safe (backups created)"
echo "- ✅ Smart (only when needed)"
echo ""
echo "To disable: Run /ace:ace-enable-auto-update again"
```

**If user chooses "Disable":**
```bash
rm -f ~/.ace/auto-update-enabled
echo "✅ Auto-update DISABLED"
echo ""
echo "ACE will now require manual updates:"
echo "- Run /ace:ace-claude-init to update"
echo "- You'll be notified when updates are available"
echo ""
echo "To re-enable: Run /ace:ace-enable-auto-update"
```

**If user chooses "Show more info":**
```
## Auto-Update Feature Details

**How It Works:**
1. SessionStart hook checks for ACE version mismatch
2. If update available AND auto-update enabled:
   - Script runs in background (< 1 second)
   - Updates only ACE section (preserves your content)
   - Creates backup before update
   - Logs update to ~/.ace/update-history.log

**What Gets Updated:**
- ACE plugin instructions (between HTML markers)
- Version markers
- New features and improvements

**What's Preserved:**
- All your custom CLAUDE.md content (before and after ACE section)
- File structure and formatting
- Git history (you can revert if needed)

**Safety Features:**
- Automatic backups: ~/.claude-md-backup/
- Only updates marked sections (HTML markers required)
- Falls back to manual if complex merge needed
- Never overwrites without validation

**Token Savings:**
- Script-based updates: 0 tokens
- LLM-based updates: ~17,000 tokens (fallback)
- Manual checks eliminated: ~1,000 tokens per session

**When Updates Happen:**
- Only on plugin version changes (not every session)
- Only when your project's ACE version is outdated
- Requires markers in CLAUDE.md (v3.2.36+)

**Control:**
- Enable/disable anytime
- Per-user setting (not per-project)
- Applies to all projects with auto-update enabled

**Recommendation:**
- Enable if: You trust automatic updates and want seamless experience
- Disable if: You prefer manual control over documentation changes
```

**If user chooses "Cancel":**
```
No changes made. Auto-update status unchanged.
```

## Usage Examples

### Enable Auto-Update

```
User: /ace-enable-auto-update

Claude: Auto-Update Status: DISABLED

What would you like to do?
1. Enable auto-update
2. Disable auto-update
3. Show more info
4. Cancel

User: 1

Claude: ✅ Auto-update ENABLED
...
```

### Check Status

```
User: /ace-enable-auto-update

Claude: Auto-Update Status: ENABLED

What would you like to do?
[options...]

User: 4

Claude: No changes made.
```

## How Auto-Update Works

**SessionStart Flow:**
```
Session Start
    ↓
check-ace-version.sh runs
    ↓
Detects version mismatch?
    ↓
Check ~/.ace/auto-update-enabled exists?
    ↓
YES → Run ace-claude-init.sh --auto-update
NO  → Create notification only
    ↓
Update completed silently
(or notification shown)
```

**Update Process:**
1. Backup created: `CLAUDE.md.backup-YYYYMMDD-HHMMSS`
2. ACE section extracted using HTML markers
3. New template content inserted
4. File validated (must have ACE content)
5. Original file replaced
6. Log entry created

## Configuration Files

**Auto-update flag:**
- Location: `~/.ace/auto-update-enabled`
- Type: Empty file (presence = enabled)
- Scope: User-wide (applies to all projects)

**Update history:**
- Location: `~/.ace/update-history.log`
- Format: JSON lines (one per update)
- Example:
  ```json
  {"timestamp":"2025-10-30T12:00:00Z","project":"/path/to/project","from":"3.2.28","to":"3.2.36","status":"success"}
  ```

## Troubleshooting

### Auto-update not working

1. Check if enabled:
   ```bash
   ls -la ~/.ace/auto-update-enabled
   ```

2. Check for update notifications:
   ```bash
   cat ~/.ace/update-notification.txt
   ```

3. Check update history:
   ```bash
   tail ~/.ace/update-history.log
   ```

### Manual update after auto-update failure

If auto-update fails (complex file structure), you'll see a notification. Run:
```
/ace:ace-claude-init
```

This will use LLM-based update (more robust, handles complex cases).

### Restore from backup

If an update went wrong:
```bash
# List backups
ls -lt CLAUDE.md.backup-*

# Restore specific backup
cp CLAUDE.md.backup-20251030-120000 CLAUDE.md
```

## See Also

- `/ace:ace-claude-init` - Manual update command
- `/ace:ace-status` - Check ACE connection and status
- `/ace:ace-configure` - Configure ACE server

## Security Note

Auto-update modifies your project's CLAUDE.md file automatically. While safe (backups are created), you should:
- ✅ Review changes periodically
- ✅ Commit backups to git (optional)
- ✅ Disable if working on critical documentation
- ✅ Trust the ACE plugin source (official marketplace)
