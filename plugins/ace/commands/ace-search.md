---
description: Semantic search for ACE patterns using natural language query
---

# ACE Semantic Search

Search for relevant patterns using natural language query instead of retrieving all patterns.

## What This Does

Uses semantic search to find only the most relevant patterns matching your query, reducing context usage by 50-80%.

## Instructions for Claude

When the user runs `/ace-search <query>`, use the Bash tool to call ce-ace CLI:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check ce-ace is available
if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace CLI not found in PATH"
  echo ""
  echo "Installation:"
  echo "  npm install -g @ce-dot-net/ce-ace-cli"
  echo ""
  exit 1
fi

# Get context from .claude/settings.json
ORG_ID=$(jq -r '.orgId // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // empty' .claude/settings.json 2>/dev/null || echo "")

if [ -z "$ORG_ID" ] || [ -z "$PROJECT_ID" ]; then
  echo "❌ No .claude/settings.json found or missing orgId/projectId"
  echo "Run /ace-configure to set up ACE"
  exit 1
fi

# Call ce-ace search (user query via args, not stdin)
ce-ace --org "$ORG_ID" --project "$PROJECT_ID" \
  search "$*" \
  --threshold 0.85
```

### Parameters

- **query** (required): Natural language description passed as command argument
  - Examples: "authentication patterns", "async debugging tips", "database connection pooling best practices"
- **--threshold**: Similarity threshold (default: 0.85)
  - Range: 0.0 - 1.0 (higher = stricter matching)
- **--limit**: Maximum patterns to return (default: 10)
- **--json**: Return JSON format for programmatic use

### Example Usage

```bash
/ace-search JWT authentication best practices
→ Calls: ce-ace search "JWT authentication best practices" --org ... --project ...

/ace-search async test failures debugging
→ Calls: ce-ace search "async test failures debugging" --org ... --project ...
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
