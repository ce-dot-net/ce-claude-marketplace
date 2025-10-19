---
description: Export learned patterns to share across projects
allowed-tools: mcp__ace-pattern-learning__ace_get_patterns, Write
---

# ACE Export Patterns

Export your learned patterns to a JSON file for backup or cross-project sharing.

## Usage

```
Use mcp__ace-pattern-learning__ace_get_patterns to retrieve all patterns, then write them to a JSON file.

Steps:
1. Call ace_get_patterns() to get all patterns as JSON
2. Use Write tool to save the patterns to a file (e.g., my-patterns.json)

Example:
- Get patterns: mcp__ace-pattern-learning__ace_get_patterns
- Save to file: Write to ./exported-patterns.json
```

Exported patterns include:
- Pattern ID, name, domain
- Content and rationale
- Confidence scores
- Observation counts
- Creation/update timestamps
