---
description: Export ACE playbook to JSON for backup or sharing
---

# ACE Export Playbook

Export your ACE playbook to JSON for backup or cross-project sharing.

## Usage

```
Export the structured playbook using these steps:

1. Call mcp__ace-pattern-learning__ace_get_playbook() to get the full playbook
2. Access the nested playbook object: response.playbook (v3.8.0+)
3. Use Write tool to save as JSON (e.g., ./ace-playbook-export.json)

The exported file will contain the nested structure (v3.8.0+):
{
  "playbook": {
    "strategies_and_hard_rules": [
      {
        "id": "ctx-1737387600-a1b2c",
        "section": "strategies_and_hard_rules",
        "content": "Always check npm package names before importing",
        "helpful": 5,
        "harmful": 0,
        "confidence": 1.0,
        "evidence": ["ImportError in auth.ts:5"],
        "observations": 5,
        "created_at": "2025-01-20T17:00:00Z",
        "last_used": "2025-01-20T17:30:00Z"
      }
    ],
    "useful_code_snippets": [...],
    "troubleshooting_and_pitfalls": [...],
    "apis_to_use": [...]
  },
  "metadata": {
    "tokens_in_response": 30000
  }
}

**Note**: Access sections via response.playbook.* (v3.8.0+ structure change)
```

## What Gets Exported

**Complete playbook structure**:
- All 4 sections (strategies, snippets, troubleshooting, APIs)
- All bullets with metadata:
  - helpful/harmful counters
  - confidence scores
  - evidence (file paths, errors)
  - timestamps

## Use Cases

- **Backup**: Save playbook before clearing
- **Team Sharing**: Share learned patterns with colleagues
- **Cross-Project**: Transfer knowledge to new projects
- **Analysis**: Export for external analysis tools

## Next Steps

**After exporting:**

- **Backup complete!** Your playbook is saved to JSON
- **Share with team:** Send file to colleagues for import
- **Restore later:** Use `/ace-orchestration:ace-import-patterns` to restore from backup

## Import

To re-import exported playbooks:
```
/ace-orchestration:ace-import-patterns
```

See `/ace-orchestration:ace-import-patterns` command for full import instructions.

## See Also

- `/ace-orchestration:ace-import-patterns` - Import playbook from JSON
- `/ace-orchestration:ace-status` - Check current playbook statistics
- `/ace-orchestration:ace-patterns` - View current playbook
