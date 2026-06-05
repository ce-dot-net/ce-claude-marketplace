---
model: claude-haiku-4-5
description: Get highest-rated ACE patterns by reward score
allowed-tools: Bash(ace-cli:*), Bash(jq:*), Bash(npm:*), Read
---

# ACE Top Patterns

Retrieve proven patterns with the highest reward scores - battle-tested patterns that have proven successful.

## What This Does

Returns patterns sorted by reward score (tier-weighted helpful-minus-harmful), giving you quality-first retrieval instead of quantity.

## Instructions for Claude

When the user runs `/ace-top [section] [limit] [min_reward]`, use ace-cli:

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v ace-cli >/dev/null 2>&1; then
  echo "❌ ace-cli not found - Install: npm install -g @ace-sdk/cli"
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
MIN_REWARD="${3:-0}"

# Build command
CMD_ARGS=""
if [ -n "$SECTION" ]; then
  CMD_ARGS="$CMD_ARGS --section $SECTION"
fi
CMD_ARGS="$CMD_ARGS --limit $LIMIT --min-reward $MIN_REWARD"

echo "🏆 Fetching top-rated patterns..."

# Execute command
if [ -n "$ORG_ID" ]; then
  ace-cli --org "$ORG_ID" --project "$PROJECT_ID" top $CMD_ARGS
else
  ace-cli --project "$PROJECT_ID" top $CMD_ARGS
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
- **min_reward** (optional): Minimum reward score (tier-weighted helpful-minus-harmful; default 0, only filters when >0)
  - Default: 0

### Example Usage

```bash
/ace-top
→ Returns top 10 patterns across all sections

/ace-top strategies_and_hard_rules
→ Returns top 10 architectural patterns/principles

/ace-top troubleshooting_and_pitfalls 5
→ Returns top 5 troubleshooting patterns

/ace-top apis_to_use 20 3
→ Returns top 20 API recommendations with reward >= 3
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
      "cumulative_v15_reward": 12.5,
      "n_hot_pos": 8,
      "n_hot_neg": 0,
      "isAtRisk": false,
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
  "min_reward": 5
}
```

Patterns are sorted by reward score (descending).

## Reward Score Interpretation

- **cumulative_v15_reward**: Tier-weighted sum of positive minus negative signals accumulated over all observations
- **n_hot_pos / n_hot_neg**: Count of recent positive and negative reinforcement events
- **isAtRisk**: `true` when recent negative signals outpace positives — use these patterns with extra caution
- **confidence**: Statistical confidence in the reward estimate (higher = more reliable signal)

Patterns with `isAtRisk: true` have recent negative feedback and should be used cautiously.

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
→ "What libraries have we had success with? (reward >= 5)"
```

## See Also

- `/ace-search` - Semantic search for specific queries
- `/ace-patterns` - View full playbook
- `/ace-status` - Check playbook statistics
