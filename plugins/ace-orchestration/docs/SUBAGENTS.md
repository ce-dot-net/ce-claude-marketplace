# ACE Subagents Architecture

## Overview

ACE uses **two specialized subagents** to implement the complete learning cycle from the ACE research paper. These subagents run in separate context windows, ensuring transparent operation without blocking other plugins.

## The Two Subagents

### 1. ACE Retrieval Subagent

**Location**: `agents/ace-retrieval.md`
**Model**: Haiku (fast, cost-efficient)
**Role**: Pattern Retrieval Specialist

**When Invoked**: Before implementation, debugging, refactoring, or architectural tasks

**What It Does**:
- Receives task description from main Claude
- Searches ACE playbook using semantic search or full retrieval
- Returns 2-5 relevant patterns to inform the work
- Operates in separate context (transparent, non-blocking)

**Tools Available**:
- `ace_search` - Semantic search with natural language queries
- `ace_get_playbook` - Full playbook or section retrieval
- `ace_top_patterns` - Highest-rated patterns by helpful score
- `ace_batch_get` - Bulk pattern fetching by ID

**Example Invocation**:
```
Main Claude: "I need to implement JWT authentication"
    ↓
Main Claude invokes: ACE Retrieval subagent
    ↓
ACE Retrieval searches playbook for "JWT authentication"
    ↓
ACE Retrieval returns: "3 patterns found: token rotation, HttpOnly cookies, rate limiting"
    ↓
Main Claude proceeds with enhanced context
```

### 2. ACE Learning Subagent

**Location**: `agents/ace-learning.md`
**Model**: Haiku (fast, cost-efficient)
**Role**: Pattern Capture Specialist

**When Invoked**: After completing substantial work (implementations, bug fixes, refactoring)

**What It Does**:
- Receives completed work summary from main Claude
- Extracts lessons learned, gotchas, best practices
- Calls `ace_learn` tool to send patterns to ACE server
- Server processes via Reflector + Curator + Merge
- Operates in separate context (transparent, non-blocking)

**Tools Available**:
- `ace_learn` - Send execution trace to ACE server
- `ace_status` - Check playbook statistics (optional)

**Example Invocation**:
```
Main Claude: Completes JWT authentication implementation
    ↓
Main Claude invokes: ACE Learning subagent
    ↓
ACE Learning analyzes work, extracts lessons
    ↓
ACE Learning calls: ace_learn(task, trajectory, output)
    ↓
ACE Server processes and updates playbook
    ↓
Future retrievals will include these new patterns
```

## The Complete Workflow

### Sequential Pattern (NOT Parallel)

```
User Request: "Implement feature X"
    ↓
UserPromptSubmit Hook: Fires reminder to main Claude
    ↓
Main Claude: Manually invokes ACE Retrieval subagent
    ↓
ACE Retrieval: Searches playbook, returns patterns
    ↓
Main Claude: Executes work using retrieved patterns
    ↓
Main Claude: Manually invokes ACE Learning subagent
    ↓
ACE Learning: Captures patterns, calls ace_learn
    ↓
ACE Server: Updates playbook for future retrieval
    ↓
Main Claude: Responds to user
```

**Key Point**: Each step waits for the previous to complete. This is NOT parallel invocation.

## Why Subagents?

### v3.x Used Hooks + Skills (REMOVED)

**Problems**:
- Hook Storm Bug (Issue #3523) - Progressive hook duplication causing crashes
- Skill Blocking - ACE skills prevented other plugins from executing
- Hidden Operation - Users couldn't see what was happening
- Cascading Triggers - Hooks triggered other hooks exponentially

### v4.0+ Uses Subagents (CURRENT)

**Benefits**:
- ✅ No Hook Storms - No cascading hooks that multiply
- ✅ No Blocking - Separate contexts don't interfere with other plugins
- ✅ Transparent - Users see `[ACE Retrieval]` and `[ACE Learning]` running
- ✅ User Controllable - Easy to disable (delete agent files or tell Claude)
- ✅ Separate Context - Clean slate for each invocation

## Invocation Methods

### Automatic Invocation (UNRELIABLE)

Claude Code theoretically supports auto-invocation based on description field matching, but **community consensus is that this is unreliable**:

> "Not even if you put 'USE THIS AGENT EXTENSIVELY' in the description with emojis. The realistic approach is to invoke them explicitly."

**Why It Fails**:
- Auto-delegation logic is inconsistent
- Duplicate registration can confuse selection
- Description matching is not deterministic

### Manual Invocation (RELIABLE - CURRENT APPROACH)

**Hook-Assisted Manual Invocation**:
1. User request contains trigger word (implement, fix, debug, etc.)
2. UserPromptSubmit hook fires, showing reminder to main Claude
3. Main Claude manually invokes subagent via Task tool
4. Subagent executes and returns results
5. Main Claude proceeds with work

**Benefits**:
- ✅ Reliable - Always works when explicitly called
- ✅ Visible - Users see the invocation happening
- ✅ Controllable - Main Claude decides when to invoke
- ✅ Debuggable - Clear execution flow in transcript

## Subagent Configuration

### Frontmatter Fields

```yaml
---
name: ace-retrieval
description: MUST BE USED PROACTIVELY before starting any implementation...
tools: mcp__plugin_ace-orchestration_ace-pattern-learning__ace_get_playbook, ...
model: haiku
---
```

**Required Fields**:
- `name` - Unique identifier (lowercase, hyphens)
- `description` - For main Claude to know when to invoke (not for auto-invoke!)

**Optional Fields**:
- `tools` - Comma-separated list of allowed tools
- `model` - `sonnet`, `opus`, `haiku`, or `inherit`

### Tool Naming Convention

**CRITICAL**: Tool names must use full plugin namespace:

✅ **Correct**: `mcp__plugin_ace-orchestration_ace-pattern-learning__ace_search`
❌ **Wrong**: `mcp__ace-pattern-learning__ace_search` (missing prefix)

The tool name format is:
```
mcp__plugin_{plugin-name}_{mcp-server-name}__{tool-name}
```

For ACE:
- Plugin name: `ace-orchestration`
- MCP server name: `ace-pattern-learning`
- Tool names: `ace_search`, `ace_get_playbook`, `ace_learn`, etc.

## Plugin Registration

### Auto-Discovery

Claude Code automatically discovers agents from the `agents/` directory in plugin root. **No plugin.json configuration needed**.

**Per official docs**: "If `agents/` exists, it's loaded in addition to custom agent paths."

### Common Mistake: Duplicate Registration

❌ **Don't do this**:
```json
{
  "agents": [
    "./agents/ace-retrieval.md",
    "./agents/ace-learning.md"
  ]
}
```

**Problem**:
- `agents/` directory is auto-discovered (loads: ace-retrieval.md, ace-learning.md)
- Explicit `agents` field supplements (loads: ace-retrieval.md, ace-learning.md AGAIN)
- Result: Each agent registered twice, hooks fire twice

✅ **Correct approach**: Omit `agents` field, rely on auto-discovery

```json
{
  "name": "ace-orchestration",
  "version": "4.1.11",
  "hooks": "./hooks/hooks.json"
}
```

## Testing Subagents

### Manual Test

```bash
# In Claude Code:
User: "Use ACE Retrieval to search for JWT patterns"

# Expected:
# 1. Subagent starts with: 🔍 [ACE Retrieval] Searching playbook...
# 2. MCP request hits server (check logs)
# 3. Subagent returns patterns or "no patterns found"
# 4. Main Claude proceeds with work
```

### Check Registration

```bash
/agents
```

**Expected output**: Each agent appears once:
```
Plugin agents
ace-orchestration:ace-retrieval · haiku
ace-orchestration:ace-learning · haiku
```

**If duplicates appear**: Remove `agents` field from plugin.json

### Verify MCP Tools

When subagent is invoked, check server logs for:
```
GET /playbook?include_metadata=true HTTP/1.1
POST /learn HTTP/1.1
```

If no requests appear, the tool names may be incorrect.

## Troubleshooting

### Subagents Not Auto-Invoking

**Expected**: Auto-invoke is unreliable per community feedback
**Solution**: Use manual invocation via hook reminders (current approach)

### Agents Appear Twice in /agents

**Cause**: Both auto-discovery and explicit `agents` field in plugin.json
**Solution**: Remove `agents` field, rely on auto-discovery only

### Hook Fires Twice

**Cause**: Same as above - duplicate agent registration
**Solution**: Remove `agents` field from plugin.json

### Subagent Can't Call MCP Tools

**Cause**: Tool names in agent instructions don't match actual tool names
**Solution**: Use full namespace: `mcp__plugin_ace-orchestration_ace-pattern-learning__*`

### No Server Requests When Subagent Runs

**Cause**: Subagent may not be actually calling tools
**Debug**: Check subagent instructions have correct tool names
**Verify**: Test tool directly: `/tool mcp__plugin_ace-orchestration_ace-pattern-learning__ace_status`

## Best Practices

### Writing Subagent Instructions

**For the subagent (separate Claude instance)**:
- ✅ Focus on: role, input, procedure, output
- ✅ Clear examples with correct tool names
- ✅ Specify what it receives when invoked
- ❌ Don't include: trigger words (irrelevant to invoked subagent)
- ❌ Don't explain: hook workflow (subagent doesn't need context)

### Invoking from Main Claude

**Before technical work**:
```javascript
Task({
  subagent_type: "ace-orchestration:ace-retrieval",
  prompt: "Search for patterns about [technology/domain]",
  model: "haiku"
})
```

**After completing work**:
```javascript
Task({
  subagent_type: "ace-orchestration:ace-learning",
  prompt: "Capture lessons from: [summary of work done]",
  model: "haiku"
})
```

### Token Efficiency

- Use Haiku for subagents (fast, cheap, sufficient for pattern operations)
- ACE Retrieval uses semantic search (50-92% token reduction vs full playbook)
- Subagents return concise summaries (2-5 bullets), not full playbook

### Monitoring

- Watch for `[ACE Retrieval]` and `[ACE Learning]` headers in output
- Check server logs for MCP requests
- Verify patterns being captured with `/ace-status`
- Monitor playbook growth over time

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│ User Request                                │
│ "Implement JWT authentication"              │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ UserPromptSubmit Hook                       │
│ - Detects trigger word: "implement"         │
│ - Shows reminder to main Claude             │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Main Claude (Sonnet)                        │
│ - Sees hook reminder                        │
│ - Manually invokes ACE Retrieval subagent   │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ ACE Retrieval Subagent (Haiku)             │
│ - Separate context window                   │
│ - Calls: ace_search("JWT auth")            │
│ - MCP request → ACE Server                  │
│ - Returns: 3 patterns                       │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Main Claude                                 │
│ - Receives patterns from subagent           │
│ - Implements JWT auth with patterns         │
│ - Completes work                            │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Main Claude                                 │
│ - Manually invokes ACE Learning subagent    │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ ACE Learning Subagent (Haiku)              │
│ - Separate context window                   │
│ - Analyzes completed work                   │
│ - Calls: ace_learn(task, trajectory, output)│
│ - MCP request → ACE Server                  │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ ACE Server                                  │
│ - Reflector (Sonnet 4) analyzes trace      │
│ - Curator (Haiku 4.5) creates delta        │
│ - Merge algorithm updates playbook          │
│ - Patterns ready for next retrieval         │
└─────────────────────────────────────────────┘
```

## Summary

- **Two subagents**: Retrieval (before work) + Learning (after work)
- **Separate contexts**: Transparent, non-blocking operation
- **Manual invocation**: Reliable approach via hook reminders
- **Auto-discovery**: No plugin.json config needed
- **Tool naming**: Use full `mcp__plugin_ace-orchestration_ace-pattern-learning__*` format
- **Model**: Haiku for cost-efficiency and speed
- **Result**: Self-improving system that builds organizational knowledge over time
