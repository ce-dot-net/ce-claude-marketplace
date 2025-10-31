---
description: Semantic search for ACE patterns using natural language query
---

# ACE Semantic Search

Search for relevant patterns using natural language query instead of retrieving all patterns.

## What This Does

Uses semantic search to find only the most relevant patterns matching your query, reducing context usage by 50-80%.

## Instructions for Claude

When the user runs `/ace-search <query>`, call the MCP tool:

```bash
mcp__plugin_ace-orchestration_ace-pattern-learning__ace_search(
  query="<user's query>",
  top_k=10
)
```

### Parameters

- **query** (required): Natural language description of what patterns to find
  - Examples: "authentication patterns", "async debugging tips", "database connection pooling best practices"
- **section** (optional): Filter to specific playbook section
  - Values: `strategies_and_hard_rules`, `useful_code_snippets`, `troubleshooting_and_pitfalls`, `apis_to_use`
- **top_k** (optional): Maximum patterns to return (default: 10)
- **threshold** (optional): Similarity threshold for matching (default: 0.7)
  - Range: 0.0 - 1.0 (higher = stricter matching)
  - Use 0.3-0.5 for broader matches, 0.8+ for very precise matches

### Example Usage

```bash
/ace-search "JWT authentication best practices"
→ Returns top 10 patterns related to JWT authentication

/ace-search "async test failures debugging"
→ Returns debugging patterns for async test issues

/ace-search "database connection pooling" troubleshooting_and_pitfalls
→ Returns top 10 troubleshooting patterns about connection pools
```

### When to Use This

✅ **Use `/ace-search` when**:
- You have a specific implementation question
- You're debugging a specific type of problem
- You know what domain/topic you need help with
- You want to minimize context usage

❌ **Don't use when**:
- You need comprehensive architectural overview
- You're working on multi-domain tasks
- You want to see all patterns in a section

For those cases, use `/ace-patterns` instead.

## Output Format

The tool returns JSON with matching patterns:

```json
{
  "patterns": [
    {
      "content": "Pattern description with context",
      "helpful": 8,
      "harmful": 0,
      "confidence": 0.92,
      "section": "strategies_and_hard_rules",
      "similarity": 0.87
    }
  ],
  "query": "your search query",
  "count": 10
}
```

Patterns are sorted by semantic similarity to your query.

## Performance Impact

**Before** (full playbook):
- Retrieves: ALL patterns in section
- Token usage: ~10,000-15,000 tokens
- Time: 100-300ms

**After** (semantic search):
- Retrieves: Top 10 relevant patterns only
- Token usage: ~2,000-3,000 tokens
- Time: 150-400ms
- **80% token reduction!**

## See Also

- `/ace-top` - Get highest-rated patterns by helpful score
- `/ace-patterns` - View full playbook (comprehensive)
- `/ace-status` - Check playbook statistics
