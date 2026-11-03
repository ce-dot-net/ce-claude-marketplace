---
model: claude-haiku-4-5
description: Show ACE playbook statistics and learning status
argument-hint:
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(jq:*), Bash(npm:*), Read
---

# ACE Status

Display comprehensive statistics about your ACE playbook.

## Instructions for Claude

When the user runs `/ace-status`:

### Step 1: Pre-flight Auth Check (v5.4.21)

First, run this bash script to check authentication:

```bash
#!/usr/bin/env bash
# ACE Pre-flight Auth Check (v5.4.21)

# Check ace-cli is available
if ! ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version >/dev/null 2>&1; then
  echo "ACE_STATUS=cli_not_found"
  exit 0
fi

# Check authentication status
AUTH_JSON=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli whoami --json 2>/dev/null || echo '{"authenticated":false}')
IS_AUTH=$(echo "$AUTH_JSON" | jq -r '.authenticated // false')

if [ "$IS_AUTH" != "true" ]; then
  echo "ACE_STATUS=not_authenticated"
else
  echo "ACE_STATUS=ok"
fi
```

### Step 2: Handle Auth Status

Based on the output:

- **If `ACE_STATUS=cli_not_found`**: Tell the user to install ace-cli:
  ```
  ❌ ace-cli not found. Install: /ace:ace-install-cli
  ```

- **If `ACE_STATUS=not_authenticated`**: Use the **AskUserQuestion** tool to ask the user:
  - **Question**: "ACE is not authenticated. Would you like to login now?"
  - **Options**:
    1. **"Login now"** - Run `/ace-login` command for them
    2. **"Continue without ACE"** - Show message: "⚠️ ACE pattern learning is disabled for this session. Run /ace-login anytime to enable."
    3. **"Skip"** - Just exit without action

- **If `ACE_STATUS=ok`**: Proceed to Step 3

### Step 3: Get Status (only if authenticated)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check for jq (required for JSON formatting)
if ! command -v jq >/dev/null 2>&1; then
  echo "❌ jq not found - Install: brew install jq (macOS) or apt-get install jq (Linux)"
  exit 1
fi

# The ACE CLI version is pinned by this plugin version (package.json); updates arrive with the plugin.

# Optional: Export environment variables if available from .claude/settings.json
# ace-cli will use these if provided, otherwise fallback to global config
export ACE_ORG_ID="${ACE_ORG_ID:-}"
export ACE_PROJECT_ID="${ACE_PROJECT_ID:-}"

# Run ace-cli status and capture output
# Filter out CLI update notifications (💡 lines) that break JSON parsing
RAW_OUTPUT=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli status --json 2>&1)
EXIT_CODE=$?
STATUS_OUTPUT=$(echo "$RAW_OUTPUT" | grep -v '^💡' | grep -v '^$')

# Check if command succeeded
if [ $EXIT_CODE -ne 0 ]; then
  echo "❌ Failed to get ACE status"
  echo ""
  echo "Error details:"
  echo "$STATUS_OUTPUT"
  echo ""
  echo "Common fixes:"
  echo "  1. Run: /ace-login to authenticate"
  echo "  2. Run: /ace-configure to setup configuration"
  echo "  3. Verify global config exists: cat ~/.config/ace/config.json"
  exit 1
fi

# Verify we got valid JSON
if ! echo "$STATUS_OUTPUT" | jq empty 2>/dev/null; then
  echo "❌ Invalid response from ACE CLI (not valid JSON)"
  echo ""
  echo "Response:"
  echo "$STATUS_OUTPUT"
  exit 1
fi

# Format output for readability
echo "$STATUS_OUTPUT" | jq -r '
  "📊 ACE Playbook Status",
  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
  "",
  "📚 Total Patterns: \(.playbook.total_patterns // 0)",
  "",
  "By Section:",
  "  • Strategies & Rules: \(.playbook.by_section.strategies_and_hard_rules // 0)",
  "  • Code Snippets: \(.playbook.by_section.useful_code_snippets // 0)",
  "  • Troubleshooting: \(.playbook.by_section.troubleshooting_and_pitfalls // 0)",
  "  • APIs to Use: \(.playbook.by_section.apis_to_use // 0)",
  "",
  "📈 Helpful: \(.playbook.helpful_total // 0) | Harmful: \(.playbook.harmful_total // 0)",
  "📈 Confidence: \((if (.playbook.helpful_total // 0) + (.playbook.harmful_total // 0) > 0 then ((.playbook.helpful_total // 0) * 100 / ((.playbook.helpful_total // 0) + (.playbook.harmful_total // 0))) else ((.avg_confidence // 0) * 100) end) | floor)%",
  "⚠️  At Risk: \(.at_risk_count // 0) | V15 Rewarded: \(.patterns_with_v15_reward // 0)",
  "",
  "💼 Plan: \(.subscription.plan // "unknown")",
  "📊 Patterns Used: \(.subscription.usage.patterns.used // 0)/\(.subscription.usage.patterns.limit // 0)"
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

## See Also

- `/ace:configure` - Configure ACE server connection
- `/ace:bootstrap` - Bootstrap playbook from git/docs/code
- `/ace:patterns` - View learned patterns
- `/ace:clear` - Clear playbook and start fresh
