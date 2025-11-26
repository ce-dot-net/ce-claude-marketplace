---
description: Clear ACE playbook (reset all learned bullets)
argument-hint: [--confirm]
---

# ACE Clear

Reset the ACE playbook by clearing all learned bullets.

⚠️ **WARNING**: This will delete ALL learned bullets across all 4 sections!

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ace-sdk/cli"
  exit 1
fi

ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

if [ -z "$ORG_ID" ] || [ -z "$PROJECT_ID" ]; then
  echo "❌ Run /ace-configure first"
  exit 1
fi

echo "⚠️ WARNING: This will delete ALL learned patterns!"
read -p "Are you sure? Type 'yes' to confirm: " CONFIRMATION

if [ "$CONFIRMATION" != "yes" ]; then
  echo "❌ Aborted"
  exit 1
fi

ce-ace --org "$ORG_ID" --project "$PROJECT_ID" clear --confirm
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
/ace:ace-export-patterns
```

This saves a JSON backup you can re-import later.

## See Also

- `/ace:ace-export-patterns` - Backup before clearing
- `/ace:ace-import-patterns` - Restore from backup
- `/ace:ace-status` - Verify playbook is cleared
