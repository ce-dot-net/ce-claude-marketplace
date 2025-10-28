---
description: Orchestrate ACE playbook bootstrap with accurate pattern count reporting
---

# ACE Bootstrap Orchestrator

This skill handles the ACE bootstrap process and explains pattern compression to users.

## When to Invoke

Automatically invoke this skill when the user:
- Runs `/ace-bootstrap` command
- Says "bootstrap the playbook"
- Asks to "initialize ACE" or "extract patterns from codebase"

## Instructions for Claude

Follow these steps EXACTLY in order:

### Step 1: Acknowledge Start

Tell the user:

```
Starting ACE bootstrap analysis of your codebase...
```

### Step 2: Call the MCP Bootstrap Tool

**YOU MUST CALL THE MCP TOOL** - it handles communication with the ACE server.

Call: `mcp__plugin_ace-orchestration_ace-pattern-learning__ace_bootstrap`

Pass the user's parameters (mode, thoroughness, etc.) directly to the tool.

**What the MCP tool does**:
1. Extracts complete code blocks from the codebase (client-side)
2. Sends raw code to the ACE server via HTTP
3. Server's Reflector (Claude Sonnet 4) analyzes code and extracts patterns
4. Returns results to you

### Step 3: Show Progress Message

While the tool is running, display:

```
⏳ Analyzing codebase...

The MCP client is:
- Extracting complete code blocks (functions, methods, async patterns)
- Identifying error handling and API usage patterns
- Sending raw code to ACE server (NOT summaries!)

The server's Reflector (Claude Sonnet 4) will then:
- Analyze code blocks for reusable patterns
- Apply semantic deduplication (0.85 similarity threshold)
- Extract high-quality, actionable patterns

This typically takes 10-30 seconds.
```

### Step 4: Wait for Tool Completion

Do NOT poll or query status during execution. Simply wait for the MCP tool to return.

The MCP tool will block until the server finishes processing.

### Step 5: Query Final Status

After the tool completes, call:

`mcp__plugin_ace-orchestration_ace-pattern-learning__ace_status`

This returns the actual final pattern counts by section.

### Step 6: Generate Dynamic Report

Using the data from `ace_status`, generate a report following this EXACT structure:

**Template**:

```
✅ Bootstrap Complete!

Code Analysis:
- Files Scanned: {actual_file_count} files
- Code Blocks Extracted: {blocks_sent_to_server}
- Sent to Server: Complete functions with async/await, error handling, imports

Server Processing (Reflector AI):
- Analyzed: {blocks_sent_to_server} raw code blocks
- Extracted Patterns: {final_pattern_count} high-quality patterns
- Compression: {blocks_sent_to_server} → {final_pattern_count} ({compression_percentage}% reduction)
- Average Confidence: {average_confidence}

{IF compression_percentage > 80%}
Why such a large reduction?
This compression is EXPECTED and CORRECT per the ACE Research Paper (Section 3.2).
The Reflector intelligently merged similar patterns:
- Multiple similar database queries → Core query patterns
- Duplicate error handlers → Standard error handling pattern
- Similar API calls → Reusable API integration patterns

Result: A concise, high-quality playbook without redundancy.
{END IF}

Final Playbook Breakdown:
- Strategies & Hard Rules: {strategies_count} patterns
- Useful Code Snippets: {snippets_count} patterns
- Troubleshooting & Pitfalls: {troubleshooting_count} patterns
- APIs to Use: {apis_count} patterns

Next: Run /ace-patterns to view your complete playbook! 🎯
```

**Rules for dynamic generation:**

1. Calculate `compression_percentage`: `Math.round((1 - final_pattern_count / blocks_sent_to_server) * 100)`
2. ONLY show "Why such a large reduction?" section if `compression_percentage > 80%`
3. Use ACTUAL numbers from `ace_status`, NOT hardcoded examples
4. If you can identify specific pattern types from the playbook, mention them (e.g., "15 Prisma queries → 3 core database patterns")

### Step 7: Handle Errors

If the MCP tool fails:

```
❌ Bootstrap failed: {error_message}

Troubleshooting:
- Run /ace-configure to check your ACE server connection
- Verify the MCP server is running: claude --debug
- Check server logs for detailed error information
```

## Success Criteria

After this skill completes:

- ✅ User understands why pattern count changed (e.g., 112 → 12)
- ✅ User knows actual code was extracted, not summaries
- ✅ User sees patterns contain complete async/await examples
- ✅ User is satisfied with quality-over-quantity approach
