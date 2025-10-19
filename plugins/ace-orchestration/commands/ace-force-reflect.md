---
description: Manually trigger ACE reflection cycle on current file
argument-hint: [file-path]
allowed-tools: Read, mcp__ace-pattern-learning__ace_reflect
---

# ACE Force Reflect

Manually trigger the ACE reflection cycle on a specific file using the MCP server.

Normally, ACE runs automatically after code changes. Use this command to:
- Re-analyze a file with updated patterns
- Test the ACE system
- Get immediate feedback on patterns

## Usage:
- `/ace-force-reflect` - Analyze most recently edited file
- `/ace-force-reflect path/to/file.py` - Analyze specific file

```
1. Determine which file to analyze (use argument or get most recently edited file from git)
2. Read the file content using the Read tool
3. Detect the programming language from file extension
4. Call mcp__ace-pattern-learning__ace_reflect tool

Arguments:
{
  "code": "<file content>",
  "language": "<detected language>",
  "file_path": "<relative path>"
}

The MCP server will:
- Invoke Claude to discover patterns from the code
- Curate patterns using grow-and-refine (85% similarity)
- Store patterns in the database
- Return insights discovered and patterns merged
```

Example languages: typescript, javascript, python, go, java, rust
