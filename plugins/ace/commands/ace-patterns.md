---
model: claude-haiku-4-5
description: View ACE playbook organized by section (strategies, snippets, troubleshooting, APIs)
argument-hint: "[section] [min-reward]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(npm:*), Read
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
if ! ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version >/dev/null 2>&1; then
  echo "❌ ACE CLI not found - Install: /ace:ace-install-cli"
  exit 1
fi

# 8.1.0: the one binding lookup (scripts/ace-context, the plugin core); never read binding files here
CTX="$("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --shell)" || exit 1
eval "$CTX"; ORG_ID="$ACE_ORG_ID"; PROJECT_ID="$ACE_PROJECT_ID"

if [ -z "$ACE_ORG_ID" ] || [ -z "$ACE_PROJECT_ID" ]; then
  echo "❌ Run /ace-configure first"
  exit 1
fi

# Parse arguments
SECTION="${1:-}"  # Optional section filter
MIN_REWARD="${2:-0}"  # Optional min reward score

# Call ace-cli patterns - CLI reads org/project from env vars automatically
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli patterns --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" \
  ${SECTION:+--section "$SECTION"} \
  --min-reward "$MIN_REWARD"
```

Arguments:
- section: Optional section filter (strategies, snippets, troubleshooting, apis)
- min_reward: tier-weighted helpful-minus-harmful; default 0, only filters when >0

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
- **Filter by quality:** Use min-reward parameter (e.g., `/ace:ace-patterns troubleshooting 5`)
- **Export patterns:** Run `/ace:ace-export-patterns` for backup or sharing
- **Bootstrap more patterns:** Run `/ace:ace-bootstrap` to analyze git/docs/code
- **Clear bad patterns:** Run `/ace:ace-clear --confirm` to reset playbook

## See Also

- `/ace:ace-status` - View playbook statistics
- `/ace:ace-bootstrap` - Add patterns from git/docs/code
- `/ace:ace-export-patterns` - Backup playbook to JSON
- `/ace:ace-clear` - Clear playbook (reset)
