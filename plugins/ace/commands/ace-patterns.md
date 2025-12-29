---
description: View ACE playbook organized by section (strategies, snippets, troubleshooting, APIs)
argument-hint: [section] [min-helpful]
---

# ACE Playbook

Display the ACE playbook (4 structured sections).

## Usage:
- `/ace:ace-patterns` - Show entire playbook
- `/ace:ace-patterns strategies` - Show strategies_and_hard_rules section only
- `/ace:ace-patterns troubleshooting 5` - Show troubleshooting bullets with ≥5 helpful count

## Playbook Sections

The ACE framework defines 4 sections:
- `strategies_and_hard_rules` - Core strategies and rules
- `useful_code_snippets` - Reusable code patterns
- `troubleshooting_and_pitfalls` - Common issues and solutions
- `apis_to_use` - API usage patterns

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check ace-cli available
if ! command -v ace-cli >/dev/null 2>&1; then
  echo "❌ ace-cli not found - Install: npm install -g @ace-sdk/cli"
  exit 1
fi

# Get context and export as env vars (support both formats)
export ACE_ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
export ACE_PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

if [ -z "$ACE_ORG_ID" ] || [ -z "$ACE_PROJECT_ID" ]; then
  echo "❌ Run /ace-configure first"
  exit 1
fi

# Parse arguments
SECTION="${1:-}"  # Optional section filter
MIN_HELPFUL="${2:-0}"  # Optional min helpful score

# Call ace-cli patterns - CLI reads org/project from env vars automatically
ace-cli patterns \
  ${SECTION:+--section "$SECTION"} \
  --min-helpful "$MIN_HELPFUL"
```

Arguments:
- section: Optional section filter (strategies, snippets, troubleshooting, apis)
- min_helpful: Optional minimum helpful count (default: 0)

Examples:
- All sections: /ace-patterns
- Single section: /ace-patterns strategies
- High-value patterns: /ace-patterns troubleshooting 5
```

The tool returns a nested JSON structure (v3.8.0+):

```json
{
  "playbook": {
    "strategies_and_hard_rules": [...],
    "useful_code_snippets": [...],
    "troubleshooting_and_pitfalls": [...],
    "apis_to_use": [...]
  },
  "metadata": {
    "tokens_in_response": 30000
  }
}
```

**Access sections via**: `response.playbook.strategies_and_hard_rules`, `response.playbook.useful_code_snippets`, etc.

Each bullet shows:
- **ID**: ctx-{timestamp}-{random}
- **Helpful/Harmful**: ✅ 5 | ❌ 0
- **Confidence**: 100%
- **Content**: The learned insight
- **Evidence**: File paths, errors, line numbers
- **Metadata** (v3.8.0+): Token count when include_metadata=true

## How Bullets Are Created

ACE learns from **execution feedback**:

**Successful task** → adds to `strategies_and_hard_rules` or `useful_code_snippets`
**Failed task** → adds to `troubleshooting_and_pitfalls`
**API usage** → adds to `apis_to_use`

Bullets accumulate helpful/harmful counts over time as they prove useful or misleading.

## Next Steps

**After viewing patterns:**

- **See full statistics:** Run `/ace:ace-status` for counts and top helpful/harmful
- **Filter patterns:** Use section parameter (e.g., `/ace:ace-patterns strategies`)
- **Filter by quality:** Use min-helpful parameter (e.g., `/ace:ace-patterns troubleshooting 5`)
- **Export patterns:** Run `/ace:ace-export-patterns` for backup or sharing
- **Bootstrap more patterns:** Run `/ace:ace-bootstrap` to analyze git/docs/code
- **Clear bad patterns:** Run `/ace:ace-clear --confirm` to reset playbook

## See Also

- `/ace:ace-status` - View playbook statistics
- `/ace:ace-bootstrap` - Add patterns from git/docs/code
- `/ace:ace-export-patterns` - Backup playbook to JSON
- `/ace:ace-clear` - Clear playbook (reset)
