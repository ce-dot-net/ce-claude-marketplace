---
description: Show ACE playbook statistics and learning status
argument-hint:
---

# ACE Status

Display comprehensive statistics about your ACE playbook.

Call ce-ace CLI to get current statistics:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check ce-ace CLI is installed
if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ace-sdk/cli"
  exit 1
fi

# Check for jq (required for JSON formatting)
if ! command -v jq >/dev/null 2>&1; then
  echo "❌ jq not found - Install: brew install jq (macOS) or apt-get install jq (Linux)"
  exit 1
fi

# Optional: Export environment variables if available from .claude/settings.json
# ce-ace will use these if provided, otherwise fallback to global config
export ACE_ORG_ID="${ACE_ORG_ID:-}"
export ACE_PROJECT_ID="${ACE_PROJECT_ID:-}"

# Run ce-ace status and capture output
STATUS_OUTPUT=$(ce-ace status --json 2>&1)
EXIT_CODE=$?

# Check if command succeeded
if [ $EXIT_CODE -ne 0 ]; then
  echo "❌ Failed to get ACE status"
  echo ""
  echo "Error details:"
  echo "$STATUS_OUTPUT"
  echo ""
  echo "Common fixes:"
  echo "  1. Run: /ace-configure to setup configuration"
  echo "  2. Verify global config exists: cat ~/.config/ace/config.json"
  echo "  3. Check API token is valid at: https://ace.code-engine.app/settings"
  exit 1
fi

# Verify we got valid JSON
if ! echo "$STATUS_OUTPUT" | jq empty 2>/dev/null; then
  echo "❌ Invalid response from ce-ace (not valid JSON)"
  echo ""
  echo "Response:"
  echo "$STATUS_OUTPUT"
  exit 1
fi

# Format output for readability
echo "$STATUS_OUTPUT" | jq -r '
  "📊 ACE Playbook Status",
  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
  "Organization: \(.org_id // "Not configured")",
  "Project: \(.project_id // "Not configured")",
  "",
  "📚 Total Patterns: \(.total_bullets // 0)",
  "",
  "By Section:",
  "  • Strategies & Rules: \(.by_section.strategies_and_hard_rules // 0)",
  "  • Code Snippets: \(.by_section.useful_code_snippets // 0)",
  "  • Troubleshooting: \(.by_section.troubleshooting_and_pitfalls // 0)",
  "  • APIs to Use: \(.by_section.apis_to_use // 0)",
  "",
  "📈 Average Confidence: \((.avg_confidence // 0) * 100 | floor)%"
'
```

## What You'll See

**Playbook Summary**:
- Total bullets across all sections
- Bullets by section (strategies, snippets, troubleshooting, APIs)
- Average confidence score

**Top Helpful Bullets**:
- 5 most helpful bullets (highest ✅ counts)
- Shows which patterns are most valuable

**Top Harmful Bullets**:
- 5 most harmful bullets (highest ❌ counts)
- Shows which patterns are misleading

## Example Output

```json
{
  "total_bullets": 42,
  "by_section": {
    "strategies_and_hard_rules": 10,
    "useful_code_snippets": 15,
    "troubleshooting_and_pitfalls": 12,
    "apis_to_use": 5
  },
  "avg_confidence": 0.78,
  "top_helpful": [
    {
      "id": "ctx-1737387600-a1b2c",
      "section": "strategies_and_hard_rules",
      "content": "Always verify npm package names...",
      "helpful": 12,
      "harmful": 0,
      "confidence": 1.0
    },
    ...
  ],
  "top_harmful": [...]
}
```

## How to Interpret

**High helpful count** → Pattern proven useful across multiple tasks
**High harmful count** → Pattern caused errors, needs revision
**High confidence** → helpful/(helpful+harmful) ratio is strong
**Low confidence** → Pattern unreliable, may be pruned at 0.30 threshold

## Storage

ACE v3.0 stores playbooks in:
- **Remote**: ACE Storage Server (FastAPI + ChromaDB)
- **Project-specific**: Isolated by project ID
- **Multi-tenant**: Your org's patterns are private

## Next Steps

**After checking status:**

- **If playbook is empty (0 bullets):**
  - Run `/ace:bootstrap` to populate initial patterns from git/docs/code
  - Or start coding - ACE will learn automatically!

- **If not configured yet:**
  - Run `/ace:configure` to set up ACE server connection

- **If ACE not initialized in project:**
  - Run `/ace:claude-init` to add ACE instructions to CLAUDE.md

## See Also

- `/ace:configure` - Configure ACE server connection
- `/ace:claude-init` - Initialize ACE in project
- `/ace:bootstrap` - Bootstrap playbook from git/docs/code
- `/ace:patterns` - View learned patterns
- `/ace:clear` - Clear playbook and start fresh
