---
description: Export ACE playbook to JSON for backup or sharing
---

# ACE Export Playbook

Export your ACE playbook to JSON for backup or cross-project sharing.

## Instructions for Claude

When the user runs `/ace:export-patterns`, use ce-ace CLI to export the playbook:

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ce-dot-net/ce-ace-cli"
  exit 1
fi

# Read context
ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

# Try env wrapper format
if [ -z "$ORG_ID" ] || [ -z "$PROJECT_ID" ]; then
  ORG_ID=$(jq -r '.env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
fi

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Run /ace:configure first"
  exit 1
fi

# Export playbook
OUTPUT_FILE="${1:-ace-playbook-export.json}"

echo "📦 Exporting ACE playbook..."

if [ -n "$ORG_ID" ]; then
  ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" export > "$OUTPUT_FILE"
else
  ce-ace --json --project "$PROJECT_ID" export > "$OUTPUT_FILE"
fi

if [ $? -eq 0 ]; then
  PATTERN_COUNT=$(jq '.playbook | to_entries | map(.value | length) | add' "$OUTPUT_FILE" 2>/dev/null || echo "unknown")
  FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)

  echo "✅ Playbook exported successfully!"
  echo "   File: $OUTPUT_FILE"
  echo "   Size: $FILE_SIZE"
  echo "   Patterns: $PATTERN_COUNT"
else
  echo "❌ Export failed"
  exit 1
fi
```

## What Gets Exported

The exported JSON contains:

```json
{
  "playbook": {
    "strategies_and_hard_rules": [
      {
        "id": "ctx-xxx",
        "content": "Pattern content...",
        "helpful": 5,
        "harmful": 0,
        "confidence": 1.0,
        "evidence": [...],
        "observations": 10
      }
    ],
    "useful_code_snippets": [...],
    "troubleshooting_and_pitfalls": [...],
    "apis_to_use": [...]
  }
}
```

## Use Cases

**Backup**:
```
/ace:export-patterns ace-backup-2025-01-20.json
```

**Cross-project sharing**:
1. Export from project A: `/ace:export-patterns project-a-patterns.json`
2. Import to project B: `/ace:import-patterns project-a-patterns.json`

**Version control** (optional):
- Export periodically to track playbook evolution
- Commit to git for team sharing (careful with sensitive patterns!)

## See Also

- `/ace:import-patterns` - Import playbook from JSON
- `/ace:status` - View current playbook stats
- `/ace:clear` - Clear playbook before importing
