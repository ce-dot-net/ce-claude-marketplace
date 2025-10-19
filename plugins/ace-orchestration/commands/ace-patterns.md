---
description: List learned patterns with filtering options
argument-hint: [domain] [min-confidence]
allowed-tools: mcp__ace-pattern-learning__ace_get_patterns
---

# ACE Patterns

Display learned patterns with optional filtering using the MCP server.

## Usage:
- `/ace-patterns` - Show all patterns
- `/ace-patterns error-handling` - Show only error-handling domain patterns
- `/ace-patterns api-usage 0.7` - Show api-usage patterns with ≥70% confidence

```
Use the mcp__ace-pattern-learning__ace_get_patterns tool to retrieve patterns.

Arguments:
- domain: Optional domain filter (e.g., "error-handling", "api-usage", "code-snippets")
- min_confidence: Optional minimum confidence threshold (0.0-1.0)

Examples:
- All patterns: Call with no arguments
- Domain filter: { "domain": "error-handling" }
- Confidence filter: { "min_confidence": 0.7 }
- Both: { "domain": "api-usage", "min_confidence": 0.5 }
```

The MCP server will return patterns as JSON with:
- id: Pattern identifier (e.g., "err-00001")
- name: Pattern name
- domain: Category
- content: Pattern description
- confidence: Confidence score (0-1)
- observations: Number of helpful observations
- harmful: Number of harmful observations
