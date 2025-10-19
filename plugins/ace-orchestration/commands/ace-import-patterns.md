---
description: Import patterns from another project or backup
allowed-tools: Read, mcp__ace-pattern-learning__ace_reflect
---

# ACE Import Patterns

Import patterns from a previously exported JSON file.

## Usage

```
Import patterns by converting them back to insights and using ace_reflect:

Steps:
1. Read the exported patterns JSON file
2. For each pattern, create an insight with the pattern's content
3. Call mcp__ace-pattern-learning__ace_reflect to re-curate

Note: Imported patterns will be merged with existing ones using ACE's
deterministic curation algorithm (85% similarity threshold).

The ACE curator automatically handles deduplication and merging.
```
