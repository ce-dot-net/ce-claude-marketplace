---
description: Clear ACE playbook (reset all learned bullets)
argument-hint: [--confirm]
allowed-tools: mcp__ace-pattern-learning__ace_clear
---

# ACE Clear

Reset the ACE playbook by clearing all learned bullets.

⚠️ **WARNING**: This will delete ALL learned bullets across all 4 sections!

```
Use the mcp__ace-pattern-learning__ace_clear tool to reset the playbook.

IMPORTANT: You must pass { "confirm": true } to execute the clear operation.

Without confirmation, the tool will return an error.

Example:
{ "confirm": true }
```

## What Gets Deleted

**All playbook sections**:
- `strategies_and_hard_rules` - All strategies cleared
- `useful_code_snippets` - All code snippets cleared
- `troubleshooting_and_pitfalls` - All troubleshooting cleared
- `apis_to_use` - All API patterns cleared

**All metadata**:
- Helpful/harmful counters reset to 0
- Confidence scores lost
- Evidence trails removed
- Timestamps cleared

## Storage Impact

Clears from:
- **Remote server**: ACE Storage Server (ChromaDB)
- **Project-specific**: Only YOUR project's playbook
- **Multi-tenant safe**: Other projects/orgs unaffected

## When to Use

- **Fresh start**: Reset learning for new project phase
- **Bad patterns**: Clear after accumulating misleading bullets
- **Testing**: Clean state for testing ACE learning

## After Clearing

ACE will start learning from scratch:
- Execute tasks → ACE learns from outcomes
- Successful tasks → adds helpful bullets
- Failed tasks → adds troubleshooting bullets

## Backup First!

**Before clearing, export your playbook**:
```
/ace-export-patterns
```

This saves a JSON backup you can re-import later.

## See Also

- `/ace-export-patterns` - Backup before clearing
- `/ace-import-patterns` - Restore from backup
- `/ace-status` - Verify playbook is cleared
