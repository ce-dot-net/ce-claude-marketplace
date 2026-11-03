---
disable-model-invocation: true
model: claude-haiku-4-5
description: Export ACE playbook to JSON for backup or sharing
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(jq:*), Bash(npm:*), Read
---

# ACE Export Playbook

Export your ACE playbook to JSON for backup or cross-project sharing.

## Instructions for Claude

When the user runs `/ace:export-patterns`, use ace-cli to export the playbook:

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

# Export playbook: written ONLY inside the repo root, never through a symlink, never over an existing file
# unless the user confirmed the overwrite (then add --force). 8.1.0 security review.
OUTPUT_FILE="${1:-ace-playbook-export.json}"

echo "📦 Exporting ACE playbook..."

if ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli export --json --org "$ORG_ID" --project "$PROJECT_ID" \
  | "${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --write-export "$OUTPUT_FILE"; then
  echo "✅ Playbook exported (the line above names the file)"
else
  echo "❌ Export failed or refused (see the line above)"
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
