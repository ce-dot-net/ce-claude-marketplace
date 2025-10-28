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

### Step 5: Generate Dynamic Report

After the MCP tool completes, you'll have access to `BootstrapResponse` which includes all the compression metrics.

**IMPORTANT**: Use the ACTUAL values from the response, not hardcoded examples!

Generate this report using the response data:

```
✅ Bootstrap Complete!

Code Analysis:
- Files Scanned: {response.metadata.files_scanned} files
- Code Blocks Extracted: {response.blocks_received}
- Sent to Server: Complete functions with async/await, error handling, imports

Server Processing (Reflector AI):
- Analyzed: {response.blocks_received} raw code blocks
- Extracted Patterns: {response.patterns_extracted} high-quality patterns
- Compression: {response.blocks_received} → {response.patterns_extracted} ({response.compression_percentage}% reduction)
- Average Confidence: {response.average_confidence}
- Analysis Time: {response.analysis_time_seconds}s

{IF response.compression_percentage > 80%}

Why such a large reduction?

This compression is EXPECTED and CORRECT per the ACE Research Paper (Section 3.2).

The Reflector intelligently merged similar patterns using semantic deduplication (0.85 similarity threshold):

Example Compression:
- 15 similar Prisma queries → 1 core database query pattern
- 20 duplicate error handlers → 1 standard error handling pattern
- 12 similar API calls → 1 reusable API integration pattern

Result: A concise, high-quality playbook without redundancy.

{END IF}

Final Playbook Breakdown:
- Strategies & Hard Rules: {response.by_section.strategies_and_hard_rules} patterns
- Useful Code Snippets: {response.by_section.useful_code_snippets} patterns
- Troubleshooting & Pitfalls: {response.by_section.troubleshooting_and_pitfalls} patterns
- APIs to Use: {response.by_section.apis_to_use} patterns

Next Step: Run /ace-patterns to view your complete playbook! 🎯
```

**Rules for dynamic generation:**

1. Use `response.compression_percentage` directly (already calculated by server)
2. ONLY show "Why such a large reduction?" section if `response.compression_percentage > 80%`
3. Use ACTUAL values from `BootstrapResponse`, NOT hardcoded examples
4. Display `analysis_time_seconds` to show processing time
5. Use `response.by_section` for accurate breakdown by playbook section

### Step 6: Handle Errors

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
