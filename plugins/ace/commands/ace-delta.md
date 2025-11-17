---
description: Manual pattern management - add, update, or remove patterns in the ACE playbook
---

# ACE Delta Operations

Manually manipulate patterns in the ACE playbook using delta operations. This is an **advanced feature** for manual curation, distinct from automatic learning via `ace_learn`.

## What This Does

Allows **direct manipulation** of patterns in the ACE playbook:
- **ADD**: Manually add new patterns without going through the learning pipeline
- **UPDATE**: Modify helpful/harmful scores or pattern content
- **REMOVE**: Delete patterns from the playbook

**Difference from `/ace-learn`**:
- `/ace-learn` → Automatic learning through Reflector/Curator pipeline (preferred)
- `/ace-delta` → Manual pattern manipulation (advanced/admin feature)

## Instructions for Claude

When the user runs `/ace-delta [operation]`, use ce-ace CLI with JSON input:

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ce-dot-net/ce-ace-cli"
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

# Operation: add | update | remove
OPERATION="$1"
shift

# Create JSON payload based on operation
# See examples below for JSON structure
```

### 1. Add New Pattern

```bash
# Example: Add new pattern
JSON_PAYLOAD=$(cat <<'EOF'
{
  "bullets": [
    {
      "id": "manual-001",
      "content": "Use HTTP-only cookies for JWT refresh tokens to prevent XSS attacks",
      "section": "strategies_and_hard_rules",
      "helpful": 0,
      "harmful": 0
    }
  ]
}
EOF
)

echo "$JSON_PAYLOAD" | if [ -n "$ORG_ID" ]; then
  ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" delta add --stdin
else
  ce-ace --json --project "$PROJECT_ID" delta add --stdin
fi
```

**Sections**:
- `strategies_and_hard_rules` - Architectural patterns, coding principles
- `useful_code_snippets` - Reusable code patterns
- `troubleshooting_and_pitfalls` - Known issues, gotchas, solutions
- `apis_to_use` - Recommended libraries, frameworks

### 2. Update Pattern Scores

```bash
# Example: Update pattern helpful score
JSON_PAYLOAD='{"bullets": [{"id": "ctx-1749038476-4cb2", "helpful": 5}]}'

echo "$JSON_PAYLOAD" | if [ -n "$ORG_ID" ]; then
  ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" delta update --stdin
else
  ce-ace --json --project "$PROJECT_ID" delta update --stdin
fi
```

**What can be updated**:
- `helpful`: Increment helpful score (pattern was useful)
- `harmful`: Increment harmful score (pattern was incorrect/outdated)
- `content`: Update pattern text (rare - usually just add new pattern)

### 3. Remove Pattern

```bash
# Example: Remove pattern
JSON_PAYLOAD='{"bullets": [{"id": "ctx-1749038476-4cb2"}]}'

echo "$JSON_PAYLOAD" | if [ -n "$ORG_ID" ]; then
  ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" delta remove --stdin
else
  ce-ace --json --project "$PROJECT_ID" delta remove --stdin
fi
```

**When to remove**:
- Pattern is outdated or incorrect
- Duplicate of another pattern
- No longer relevant to project

### 4. Batch Operations

```bash
# Example: Update multiple patterns
JSON_PAYLOAD=$(cat <<'EOF'
{
  "bullets": [
    {"id": "ctx-001", "helpful": 1},
    {"id": "ctx-002", "helpful": 1},
    {"id": "ctx-003", "helpful": 1}
  ]
}
EOF
)

echo "$JSON_PAYLOAD" | if [ -n "$ORG_ID" ]; then
  ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" delta update --stdin
else
  ce-ace --json --project "$PROJECT_ID" delta update --stdin
fi
```

## Use Cases

### 1. Quick Pattern Addition

**Scenario**: You discover a gotcha during debugging and want to immediately add it to the playbook without writing a full learning report.

```bash
/ace-delta add "PostgreSQL array_agg preserves nulls - use array_remove(array_agg(x), null) to filter" troubleshooting_and_pitfalls
```

### 2. Manual Curation

**Scenario**: You reviewed patterns and found some that need score adjustments or removal.

```bash
# Mark outdated pattern as harmful
/ace-delta update ctx-old-001 harmful=3

# Remove duplicate pattern
/ace-delta remove ctx-duplicate-002
```

### 3. Importing External Knowledge

**Scenario**: You have patterns from another project/team and want to import them.

```bash
/ace-delta add "React useEffect cleanup prevents memory leaks - always return cleanup function" useful_code_snippets
```

### 4. Correcting Incorrect Patterns

**Scenario**: Automatic learning captured a pattern incorrectly.

```bash
# Remove incorrect pattern
/ace-delta remove ctx-wrong-001

# Add corrected version
/ace-delta add "Correct pattern description..." strategies_and_hard_rules
```

## Delta vs Learn

| Feature | `/ace-delta` | `/ace-learn` (via skill) |
|---------|--------------|--------------------------|
| **Invocation** | Manual command | Automatic skill trigger |
| **Processing** | Direct to playbook | Reflector → Curator → Merge |
| **Use Case** | Quick fixes, curation | Post-task learning |
| **Quality Control** | User responsibility | Server-side analysis |
| **Trajectory** | Not captured | Full execution trace |
| **Preferred** | ❌ Rare/admin use | ✅ Primary method |

**Recommendation**: Use automatic learning (`ace_learn` via skill) for 99% of cases. Use delta operations only for manual curation or quick fixes.

## Safety Notes

⚠️ **Delta operations bypass automatic quality control**:
- No Reflector analysis
- No Curator validation
- No deduplication check
- Direct playbook manipulation

**Best Practices**:
1. **Prefer automatic learning** - Use `ace_learn` skill whenever possible
2. **Be specific** - Write clear, actionable pattern descriptions
3. **Use proper sections** - Place patterns in correct playbook section
4. **Verify after changes** - Run `/ace-patterns` to confirm updates
5. **Start with helpful=0** - Let usage naturally increase scores
6. **Don't duplicate** - Check `/ace-search` before adding manually

## Output Format

### Successful ADD:
```json
{
  "success": true,
  "operation": "add",
  "bullets_affected": 1,
  "message": "Successfully applied add operation to 1 bullet(s)"
}
```

### Successful UPDATE:
```json
{
  "success": true,
  "operation": "update",
  "bullets_affected": 2,
  "message": "Successfully applied update operation to 2 bullet(s)"
}
```

### Successful REMOVE:
```json
{
  "success": true,
  "operation": "remove",
  "bullets_affected": 1,
  "message": "Successfully applied remove operation to 1 bullet(s)"
}
```

## Error Handling

### Pattern ID Not Found:
```json
{
  "success": false,
  "error": "Pattern ctx-nonexistent-001 not found"
}
```

### Invalid Section:
```json
{
  "success": false,
  "error": "Invalid section: invalid_section"
}
```

## See Also

- **ACE Learning Skill** - Automatic pattern learning (preferred method)
- `/ace-patterns` - View playbook to find pattern IDs
- `/ace-search` - Search patterns before adding duplicates
- `/ace-status` - Check playbook statistics after changes
