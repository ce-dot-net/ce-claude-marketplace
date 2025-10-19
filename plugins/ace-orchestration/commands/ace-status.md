---
description: Show ACE pattern learning statistics and status
argument-hint:
allowed-tools: mcp__ace-pattern-learning__ace_status
---

# ACE Status

Display comprehensive statistics about the ACE pattern learning system using the MCP server.

Call the MCP tool to get current statistics:

```
Use the mcp__ace-pattern-learning__ace_status tool to retrieve ACE pattern database statistics.
```

This will show:
- Total patterns in database
- High confidence patterns (≥70%)
- Medium confidence patterns (30-70%)
- Low confidence patterns (<30%)
- Active domains

The MCP server reads from `.ace-memory/patterns.db` (SQLite database).
