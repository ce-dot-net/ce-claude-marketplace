---
description: Clear ACE pattern database (reset learning)
argument-hint: [--confirm]
allowed-tools: mcp__ace-pattern-learning__ace_clear
---

# ACE Clear

Reset the ACE pattern learning database.

⚠️ **WARNING**: This will delete ALL learned patterns and insights!

```
Use the mcp__ace-pattern-learning__ace_clear tool to reset the pattern database.

IMPORTANT: You must pass { "confirm": true } to execute the clear operation.

Without confirmation, the tool will return an error.

Example:
{ "confirm": true }
```

This will:
- Delete all patterns from `.ace-memory/patterns.db`
- Clear all embeddings from the vector cache
- Reset all statistics to zero

After clearing, ACE will start learning patterns from scratch as you code.
