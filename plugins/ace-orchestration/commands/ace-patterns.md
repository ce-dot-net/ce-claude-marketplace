---
description: View ACE playbook organized by section (strategies, snippets, troubleshooting, APIs)
argument-hint: [section] [min-helpful]
allowed-tools: mcp__ace-pattern-learning__ace_get_playbook
---

# ACE Playbook

Display the ACE playbook (4 sections per ACE research paper Figure 3).

## Usage:
- `/ace-patterns` - Show entire playbook
- `/ace-patterns strategies` - Show strategies_and_hard_rules section only
- `/ace-patterns troubleshooting 5` - Show troubleshooting bullets with ≥5 helpful count

## Playbook Sections

The ACE paper defines 4 sections:
- `strategies_and_hard_rules` - Core strategies and rules
- `useful_code_snippets` - Reusable code patterns
- `troubleshooting_and_pitfalls` - Common issues and solutions
- `apis_to_use` - API usage patterns

```
Use the mcp__ace-pattern-learning__ace_get_playbook tool.

Arguments:
- section: Optional section filter (strategies_and_hard_rules, useful_code_snippets, troubleshooting_and_pitfalls, apis_to_use)
- min_helpful: Optional minimum helpful count (bullets with fewer helpful marks filtered out)

Examples:
- All sections: Call with no arguments {}
- Single section: { "section": "strategies_and_hard_rules" }
- High-value bullets: { "min_helpful": 5 }
- Both filters: { "section": "troubleshooting_and_pitfalls", "min_helpful": 3 }
```

The tool returns markdown with bullets sorted by helpful count.

Each bullet shows:
- **ID**: ctx-{timestamp}-{random}
- **Helpful/Harmful**: ✅ 5 | ❌ 0
- **Confidence**: 100%
- **Content**: The learned insight
- **Evidence**: File paths, errors, line numbers

## How Bullets Are Created

ACE learns from **execution feedback**:

**Successful task** → adds to `strategies_and_hard_rules` or `useful_code_snippets`
**Failed task** → adds to `troubleshooting_and_pitfalls`
**API usage** → adds to `apis_to_use`

Bullets accumulate helpful/harmful counts over time as they prove useful or misleading.
