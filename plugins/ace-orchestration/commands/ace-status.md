---
description: Show ACE playbook statistics and learning status
argument-hint:
---

# ACE Status

Display comprehensive statistics about your ACE playbook.

Call the MCP tool to get current statistics:

```
Use the mcp__ace-pattern-learning__ace_status tool to retrieve playbook statistics.
```

## What You'll See

**Playbook Summary**:
- Total bullets across all sections
- Bullets by section (strategies, snippets, troubleshooting, APIs)
- Average confidence score

**Top Helpful Bullets**:
- 5 most helpful bullets (highest ✅ counts)
- Shows which patterns are most valuable

**Top Harmful Bullets**:
- 5 most harmful bullets (highest ❌ counts)
- Shows which patterns are misleading

## Example Output

```json
{
  "total_bullets": 42,
  "by_section": {
    "strategies_and_hard_rules": 10,
    "useful_code_snippets": 15,
    "troubleshooting_and_pitfalls": 12,
    "apis_to_use": 5
  },
  "avg_confidence": 0.78,
  "top_helpful": [
    {
      "id": "ctx-1737387600-a1b2c",
      "section": "strategies_and_hard_rules",
      "content": "Always verify npm package names...",
      "helpful": 12,
      "harmful": 0,
      "confidence": 1.0
    },
    ...
  ],
  "top_harmful": [...]
}
```

## How to Interpret

**High helpful count** → Pattern proven useful across multiple tasks
**High harmful count** → Pattern caused errors, needs revision
**High confidence** → helpful/(helpful+harmful) ratio is strong
**Low confidence** → Pattern unreliable, may be pruned at 0.30 threshold

## Storage

ACE v3.0 stores playbooks in:
- **Remote**: ACE Storage Server (FastAPI + ChromaDB)
- **Project-specific**: Isolated by project ID
- **Multi-tenant**: Your org's patterns are private

## Next Steps

**After checking status:**

- **If playbook is empty (0 bullets):**
  - Run `/ace-orchestration:ace-bootstrap` to populate initial patterns from git/docs/code
  - Or start coding - ACE will learn automatically!

- **If not configured yet:**
  - Run `/ace-orchestration:ace-configure` to set up ACE server connection

- **If ACE not initialized in project:**
  - Run `/ace-orchestration:ace-claude-init` to add ACE instructions to CLAUDE.md

## See Also

- `/ace-orchestration:ace-configure` - Configure ACE server connection
- `/ace-orchestration:ace-claude-init` - Initialize ACE in project
- `/ace-orchestration:ace-bootstrap` - Bootstrap playbook from git/docs/code
- `/ace-orchestration:ace-patterns` - View learned patterns
- `/ace-orchestration:ace-clear` - Clear playbook and start fresh
