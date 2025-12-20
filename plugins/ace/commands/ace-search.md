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
  echo "  npm install -g @ace-sdk/cli"
  echo ""
  exit 1
fi

# Get context from .claude/settings.json and export as env vars
export ACE_ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
export ACE_PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

if [ -z "$ACE_ORG_ID" ] || [ -z "$ACE_PROJECT_ID" ]; then
  echo "❌ No .claude/settings.json found or missing orgId/projectId"
  echo "Run /ace-configure to set up ACE"
  exit 1
fi

# Call ce-ace search - CLI reads org/project from env vars automatically
# Threshold comes from server config (ce-ace tune show) - don't override!
ce-ace search "$*"
```

### Parameters

- **query** (required): Natural language description passed as command argument
  - Examples: "authentication patterns", "async debugging tips", "database connection pooling best practices"
- **--threshold**: Similarity threshold (optional, overrides server config)
  - Default: Uses server config from `ce-ace tune show`
  - Range: 0.0 - 1.0 (higher = stricter matching)
  - Only specify if you want to override project's default
- **--allowed-domains**: Whitelist domains (comma-separated, v5.3.0+)
  - Example: `--allowed-domains auth,security` returns only patterns from those domains
  - Use when entering a new domain to get targeted patterns
- **--blocked-domains**: Blacklist domains (comma-separated, v5.3.0+)
  - Example: `--blocked-domains test,debug` excludes patterns from those domains
  - Cannot use with `--allowed-domains` (mutually exclusive)
- **--json**: Return JSON format for programmatic use

**Note**: To limit number of results, use `jq` for filtering:
```bash
ce-ace search "query" --json | jq '.patterns[:5]'  # First 5 results
```
The `--limit` flag is not supported by ce-ace CLI. Use `--top-k` via server config (`/ace-tune`) instead.

### Example Usage

```bash
/ace-search JWT authentication best practices
→ Calls: ce-ace search "JWT authentication best practices"
→ Uses: Server config threshold (e.g., 0.45)

/ace-search async test failures debugging
→ Calls: ce-ace search "async test failures debugging"

# Override threshold if needed:
/ace-search "JWT auth" --threshold 0.7
→ Calls: ce-ace search "JWT auth" --threshold 0.7

# Domain filtering (v5.3.0+):
/ace-search caching patterns --allowed-domains cache,performance
→ Returns ONLY patterns from cache or performance domains

/ace-search patterns --blocked-domains test,debug
→ Excludes test and debug patterns
```

### When to Use This

✅ **Use `/ace-search` when**:
- You have a specific implementation question
- You're debugging a specific type of problem
- You know what domain/topic you need help with
- You want to minimize context usage
- **After domain shift reminder**: When you see "💡 [ACE] Domain shift: X → Y", use `--allowed-domains Y` to get targeted patterns

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
