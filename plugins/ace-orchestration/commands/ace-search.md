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
mcp__ace-pattern-learning__ace_search(
  query="<user's query>",
  top_k=10,
  threshold=0.85,
  include_metadata=true  # Default: true (v3.8.0+)
)
```

### Parameters

- **query** (required): Natural language description of what patterns to find
  - Examples: "authentication patterns", "async debugging tips", "database connection pooling best practices"
- **section** (optional): Filter to specific playbook section
  - Values: `strategies_and_hard_rules`, `useful_code_snippets`, `troubleshooting_and_pitfalls`, `apis_to_use`
- **top_k** (optional): Maximum patterns to return (default: 10)
- **threshold** (optional): Similarity threshold for matching (default: 0.85, production-validated by Server Team)
  - Range: 0.0 - 1.0 (higher = stricter matching)
  - Use 0.85 for production quality, 0.7 for broader searches, 0.5 for exploratory
- **include_metadata** (optional): Include token efficiency metrics (default: true, v3.8.0+)
  - Returns: tokens_in_response, tokens_saved_vs_full_playbook, efficiency_gain, full_playbook_size
  - Set to false to exclude metadata (~5-10ms faster)

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

The tool returns JSON with matching patterns and metadata (v3.8.0+):

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
  "count": 10,
  "metadata": {
    "tokens_in_response": 2400,
    "tokens_saved_vs_full_playbook": 27600,
    "efficiency_gain": "92%",
    "full_playbook_size": 30000
  }
}
```

Patterns are sorted by semantic similarity to your query.

**Metadata field** (v3.8.0+): Provides token efficiency metrics. Omitted if `include_metadata=false`.

## Performance Impact

**Before** (full playbook):
- Retrieves: ALL patterns in section
- Token usage: ~10,000-15,000 tokens (measured via metadata)
- Time: 100-300ms

**After** (semantic search with metadata):
- Retrieves: Top 10 relevant patterns only
- Token usage: ~2,400 tokens (confirmed via metadata)
- Time: 150-400ms
- **50-92% token reduction** (exact savings shown in metadata.efficiency_gain)

**After** (semantic search without metadata):
- Token usage: ~2,000-2,200 tokens
- Time: 140-390ms (~10ms faster)
- **85-92% token reduction**

**Metadata overhead**: Adds ~5-10ms response time + ~200-400 tokens for efficiency metrics

## See Also

- `/ace-top` - Get highest-rated patterns by helpful score
- `/ace-patterns` - View full playbook (comprehensive)
- `/ace-status` - Check playbook statistics
