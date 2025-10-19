---
description: Run multi-epoch offline training on your codebase to refine patterns
allowed-tools: mcp__ace-pattern-learning__ace_train_offline
---

# ACE Offline Training

Run ACE offline training to learn patterns from your codebase git history using the MCP server.

This implements the ACE research paper's multi-epoch training (Section 4.1, Table 3).

## How It Works

The MCP server will:
1. Analyze recent git commits (default: 50 commits)
2. Extract code from changed files
3. Invoke Claude (via MCP sampling) to discover patterns
4. Curate patterns using grow-and-refine algorithm (85% similarity)
5. Update pattern database with confidence scores

```
Use the mcp__ace-pattern-learning__ace_train_offline tool to run offline training.

Arguments:
- max_commits: Number of recent commits to analyze (default: 50)

Example:
{ "max_commits": 50 }
```

The tool returns:
- files_processed: Number of files analyzed
- insights_discovered: Total insights found
- patterns_before: Pattern count before training
- patterns_after: Pattern count after training
- avg_confidence_before: Average confidence before
- avg_confidence_after: Average confidence after

**Note**: This uses TRUE ACE agent-based pattern discovery. The MCP server invokes Claude
to analyze code and discover patterns, not keyword matching.
