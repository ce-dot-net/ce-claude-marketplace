---
description: List available pattern domains for filtering
argument-hint:
---

# List Available Domains

Shows all pattern domains with counts. Use these domain names with `/ace-search --allowed-domains`.

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check ce-ace CLI is installed
if ! command -v ce-ace >/dev/null 2>&1; then
  echo "ce-ace not found - Install: npm install -g @ace-sdk/cli"
  exit 1
fi

# Check for jq (required for JSON formatting)
if ! command -v jq >/dev/null 2>&1; then
  echo "jq not found - Install: brew install jq (macOS) or apt-get install jq (Linux)"
  exit 1
fi

# Optional: Export environment variables if available from .claude/settings.json
export ACE_ORG_ID="${ACE_ORG_ID:-}"
export ACE_PROJECT_ID="${ACE_PROJECT_ID:-}"

# Run ce-ace domains and capture output
# Filter out CLI update notifications (💡 lines) that break JSON parsing
RAW_OUTPUT=$(ce-ace domains --json 2>&1)
EXIT_CODE=$?
DOMAINS_OUTPUT=$(echo "$RAW_OUTPUT" | grep -v '^💡' | grep -v '^$')

# Check if command succeeded
if [ $EXIT_CODE -ne 0 ]; then
  echo "Failed to get domains"
  echo ""
  echo "Error details:"
  echo "$DOMAINS_OUTPUT"
  echo ""
  echo "Common fixes:"
  echo "  1. Run: /ace-configure to setup configuration"
  echo "  2. Verify global config exists: cat ~/.config/ace/config.json"
  echo "  3. Check API token is valid at: https://ace.code-engine.app/settings"
  exit 1
fi

# Verify we got valid JSON
if ! echo "$DOMAINS_OUTPUT" | jq empty 2>/dev/null; then
  echo "Invalid response from ce-ace (not valid JSON)"
  echo ""
  echo "Response:"
  echo "$DOMAINS_OUTPUT"
  exit 1
fi

# Format output as table
echo "Available Pattern Domains"
echo ""

TOTAL_DOMAINS=$(echo "$DOMAINS_OUTPUT" | jq -r '.total_domains // (.domains | length)')
TOTAL_PATTERNS=$(echo "$DOMAINS_OUTPUT" | jq -r '.total_patterns // 0')

echo "Total: $TOTAL_DOMAINS domains, $TOTAL_PATTERNS patterns"
echo ""

# Output domains sorted by count (descending)
echo "$DOMAINS_OUTPUT" | jq -r '
  .domains | sort_by(-.count) | .[] |
  "  \(.name): \(.count) patterns"
'

echo ""
echo "Use with /ace-search:"
echo "  /ace-search \"query\" --allowed-domains <domain-name>"
```

## What You'll See

A list of all available pattern domains with their pattern counts:

```
Available Pattern Domains

Total: 21 domains, 558 patterns

  troubleshooting-and-pitfalls: 120 patterns
  useful-code-snippets: 101 patterns
  strategies-and-hard-rules: 70 patterns
  ace-platform-task-detection-and-hooks: 48 patterns
  ...

Use with /ace-search:
  /ace-search "query" --allowed-domains <domain-name>
```

## Use With Filtering

After discovering domains, use them with `/ace-search`:

```bash
# Search only in specific domain
/ace-search "authentication" --allowed-domains strategies-and-hard-rules

# Search excluding certain domains
/ace-search "patterns" --blocked-domains troubleshooting-and-pitfalls
```

## Why This Matters

Without knowing domain names, `--allowed-domains` is unusable:

```
# Before: guessing domain names
ce-ace search "auth" --allowed-domains "typescript"
Result: 0 patterns (wrong domain name!)

# After: using discovered domain names
/ace-domains
→ "typescript-development-practices"

ce-ace search "auth" --allowed-domains "typescript-development-practices"
Result: Filtered patterns! ✓
```

## See Also

- `/ace-search` - Search patterns with optional domain filtering
- `/ace-status` - Playbook statistics
- `/ace-patterns` - View full playbook by section
