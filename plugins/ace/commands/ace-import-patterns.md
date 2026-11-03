---
disable-model-invocation: true
description: Import ACE playbook from JSON file
argument-hint: <file>
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(npm:*), Read
---

# ACE Import Playbook

Import an ACE playbook from a JSON file to restore backup or share patterns across projects.

## Instructions for Claude

When the user runs `/ace:import-patterns <file>`, use ace-cli to import the playbook:

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version >/dev/null 2>&1; then
  echo "❌ ACE CLI not found - Install: /ace:ace-install-cli"
  exit 1
fi

# 8.1.0: the one binding lookup (scripts/ace-context, the plugin core); never read binding files here
CTX="$("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --shell)" || exit 1
eval "$CTX"; ORG_ID="$ACE_ORG_ID"; PROJECT_ID="$ACE_PROJECT_ID"

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
if ! "${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --get . < "$IMPORT_FILE" >/dev/null 2>&1; then
  echo "❌ Invalid JSON in $IMPORT_FILE"
  exit 1
fi

echo "📥 Importing ACE playbook from $IMPORT_FILE..."

# Import playbook
if [ -n "$ORG_ID" ]; then
  ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --json --org "$ORG_ID" --project "$PROJECT_ID" import --file "$IMPORT_FILE"
else
  ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --json --project "$PROJECT_ID" import --file "$IMPORT_FILE"
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
