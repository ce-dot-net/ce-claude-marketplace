---
description: Get highest-rated ACE patterns by helpful score
---

# ACE Top Patterns

Retrieve proven patterns with the highest helpful scores - battle-tested patterns that have proven successful.

## What This Does

Returns patterns sorted by helpful score (upvotes from successful usage), giving you quality-first retrieval instead of quantity.

## Instructions for Claude

When the user runs `/ace-top [section] [limit]`, use ce-ace CLI:

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ace-sdk/cli"
  exit 1
fi

# Read context
ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

# Try env wrapper format
if [ -z "$ORG_ID" ] || [ -z "$PROJECT_ID" ]; then
  ORG_ID=$(jq -r '.env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
fi

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Run /ace:configure first"
  exit 1
fi

# Parse arguments
SECTION="${1:-}"
LIMIT="${2:-10}"
MIN_HELPFUL="${3:-0}"

# Build command
CMD_ARGS=""
if [ -n "$SECTION" ]; then
  CMD_ARGS="$CMD_ARGS --section $SECTION"
fi
CMD_ARGS="$CMD_ARGS --limit $LIMIT --min-helpful $MIN_HELPFUL"

echo "🏆 Fetching top-rated patterns..."

# Execute command
if [ -n "$ORG_ID" ]; then
  ce-ace --org "$ORG_ID" --project "$PROJECT_ID" top $CMD_ARGS
else
  ce-ace --project "$PROJECT_ID" top $CMD_ARGS
fi

if [ $? -eq 0 ]; then
  echo "✅ Retrieved top patterns"
else
  echo "❌ Failed to retrieve patterns"
  exit 1
fi
```

### Parameters

- **section** (optional): Filter to specific playbook section
  - Values: `strategies_and_hard_rules`, `useful_code_snippets`, `troubleshooting_and_pitfalls`, `apis_to_use`
  - Default: All sections
- **limit** (optional): Maximum patterns to return
  - Default: 10
- **min_helpful** (optional): Minimum helpful score threshold
  - Default: 0
  - Use `5` for only highly-rated patterns

### Example Usage

```bash
/ace-top
→ Returns top 10 patterns across all sections

/ace-top strategies_and_hard_rules
→ Returns top 10 architectural patterns/principles

/ace-top troubleshooting_and_pitfalls 5
→ Returns top 5 troubleshooting patterns

/ace-top apis_to_use 20 3
→ Returns top 20 API recommendations with helpful >= 3
```

### When to Use This

✅ **Use `/ace-top` when**:
- You want proven, high-quality patterns
- You're asking for "best practices"
- You need patterns that have been validated through use
- You want quick access to most valuable knowledge

❌ **Don't use when**:
- You have a specific query (use `/ace-search` instead)
- You need comprehensive coverage (use `/ace-patterns` instead)
- You're looking for something specific (semantic search is better)

## Output Format

The tool returns JSON with top-rated patterns:

```json
{
  "patterns": [
    {
      "content": "Always use refresh token rotation to prevent theft attacks",
      "helpful": 12,
      "harmful": 0,
      "confidence": 0.95,
      "section": "strategies_and_hard_rules",
      "observations": 15,
      "evidence": [
        "Prevented auth bypass in 3 projects",
        "Industry standard per OWASP recommendations"
      ]
    }
  ],
  "section": "strategies_and_hard_rules",
  "count": 10,
  "min_helpful": 5
}
```

Patterns are sorted by helpful score (descending).

## Helpful Score Interpretation

- **0-2**: New pattern, not yet validated
- **3-5**: Moderately proven, used successfully a few times
- **6-10**: Well-proven, reliable pattern
- **11+**: Highly validated, cornerstone pattern

Patterns with `harmful > 0` indicate they've had negative feedback and should be used cautiously.

## Performance Impact

Similar to semantic search - retrieves only top patterns instead of full playbook:

- Token usage: ~2,000-4,000 tokens (vs ~15,000 for full)
- **60-75% token reduction**
- Fast retrieval with quality guarantee

## Use Cases

**Architecture questions**:
```
/ace-top strategies_and_hard_rules 10
→ "What are the best architectural patterns we've learned?"
```

**Debugging help**:
```
/ace-top troubleshooting_and_pitfalls 5
→ "What are the most common issues we've encountered?"
```

**Library selection**:
```
/ace-top apis_to_use 10 5
→ "What libraries have we had success with?"
```

## See Also

- `/ace-search` - Semantic search for specific queries
- `/ace-patterns` - View full playbook
- `/ace-status` - Check playbook statistics
