---
description: Import ACE playbook from exported JSON
---

# ACE Import Playbook

Import a previously exported ACE playbook from JSON.

## Usage

```
Import a playbook by converting bullets back to execution traces:

1. Read the exported JSON file using Read tool
2. Parse the JSON to extract bullets from all 4 sections
3. For each bullet, create a synthetic execution trace
4. Call mcp__ace-pattern-learning__ace_learn to add each bullet

Example for a single bullet:
{
  "task": "Imported: Always check npm package names",
  "trajectory": [
    {
      "step": 1,
      "action": "imported_knowledge",
      "args": {"source": "exported-playbook.json"},
      "result": {"success": true}
    }
  ],
  "success": true,
  "output": "Always check npm package names before importing",
  "playbook_used": []
}
```

## How Import Works

1. **Read JSON**: Load exported playbook file
2. **Extract bullets**: Get all bullets from 4 sections
3. **Convert to traces**: Create execution traces for each bullet
4. **Call ace_learn**: Add each bullet via learning mechanism
5. **Merge automatically**: ACE curator deduplicates using 0.85 similarity threshold

## Merging Behavior

**ACE automatically handles deduplication:**
- Similar bullets (>85% similarity) are merged
- Helpful/harmful counts are combined
- Evidence lists are concatenated
- Confidence recalculated

**No duplicate bullets!** The grow-and-refine algorithm prevents redundancy.

## Use Cases

- **Team Onboarding**: Import team's learned patterns
- **Cross-Project**: Bring patterns from other projects
- **Restore Backup**: Recover after clearing playbook
- **Knowledge Base**: Import curated pattern libraries

## See Also

- `/ace-export-patterns` - Export playbook to JSON
- `/ace-status` - Check playbook after import
