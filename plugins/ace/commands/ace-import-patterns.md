---
description: Import ACE playbook from JSON file
argument-hint: <file>
---

# ACE Import Playbook

Import an ACE playbook from a JSON file to restore backup or share patterns across projects.

## Instructions for Claude

When the user runs `/ace:import-patterns <file>`, use ce-ace CLI to import the playbook:

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ce-dot-net/ce-ace-cli"
  exit 1
fi

# Read context
ORG_ID=$(jq -r '.orgId // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // empty' .claude/settings.json 2>/dev/null || echo "")

# Try env wrapper format
if [ -z "$ORG_ID" ] || [ -z "$PROJECT_ID" ]; then
  ORG_ID=$(jq -r '.env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
fi

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Run /ace:configure first"
  exit 1
fi

# Get filename from argument
IMPORT_FILE="${1:-ace-playbook-export.json}"

if [ ! -f "$IMPORT_FILE" ]; then
  echo "❌ File not found: $IMPORT_FILE"
  exit 1
fi

# Validate JSON
if ! jq empty "$IMPORT_FILE" 2>/dev/null; then
  echo "❌ Invalid JSON in $IMPORT_FILE"
  exit 1
fi

echo "📥 Importing ACE playbook from $IMPORT_FILE..."

# Import playbook
if [ -n "$ORG_ID" ]; then
  ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" import --file "$IMPORT_FILE"
else
  ce-ace --json --project "$PROJECT_ID" import --file "$IMPORT_FILE"
fi

if [ $? -eq 0 ]; then
  echo "✅ Playbook imported successfully!"
  echo "   Run /ace:status to verify"
else
  echo "❌ Import failed"
  exit 1
fi
```

## See Also

- `/ace:export-patterns` - Export current playbook
- `/ace:clear` - Clear playbook before importing
- `/ace:status` - Verify import results
