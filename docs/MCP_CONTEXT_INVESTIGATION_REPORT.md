# MCP Context Access Investigation - Final Report

## Executive Summary

After thorough investigation of the ACE plugin codebase, Claude Code documentation, and hook implementations, here are the critical findings:

**Main Finding**: Hooks have the SAME context limitations across all types - there is no mechanism in Claude Code hooks (command or prompt-based) to directly access conversation history or tool execution data that was previously executed.

---

## Research Questions & Answers

### 1. MCP Tool Context Access

**Question**: Do MCP tools receive conversation history?

**Answer**: NO - Not directly via hook mechanisms.

**Evidence**:
- MCP tools (like ace-pattern-learning) are invoked as separate subprocesses via Claude Code's MCP client
- MCP protocol (Model Context Protocol) is a **read/write capability system**, not a conversation history system
- MCP tools receive context ONLY through:
  - Command-line arguments (specified in `.claude/settings.json` MCP server definition)
  - Environment variables
  - Stdin/stdout for communication
  - File-based state (like ACE's pattern files)

**Key Finding from Code** (`ace_before_task.py`, line 85-100):
```python
patterns_response = run_search(
    query=search_query,
    org=context['org'],
    project=context['project'],
    session_id=session_id if use_session_pinning else None
)
```

The MCP tool receives ONLY:
- Project ID
- Org ID
- Session ID (for pattern pinning)
- Query text

It does NOT receive:
- Conversation history
- Previous tool calls
- Execution trace
- Session context

---

### 2. Claude Code Agent Architecture

**Question**: How does Claude Code's main agent track tool execution?

**Answer**: Claude Code internally tracks tool execution for the main agent, BUT this data is NOT exposed to hooks.

**Critical Limitation** (from `ACE_TRAJECTORY_FLOW.md`):
> "Claude Code provides NO per-task identifier, so we define: Task Start = Last `role: \"user\"` message in transcript"

**What Hooks CAN Access**:
1. **UserPromptSubmit hook**: 
   - User's input prompt only
   - No previous tool calls
   - No prior conversation context
   - File: `ace_before_task.py`, lines 20-25

2. **PreCompact hook**:
   - Pre-parsed messages array (if provided by Claude Code)
   - Pre-parsed tool_uses array (if provided)
   - Transcript path (file system)
   - File: `ace_after_task.py`, lines 440-460

3. **Stop/SubagentStop hooks**:
   - ONLY transcript path (must parse file)
   - NO pre-parsed messages
   - NO pre-parsed tool_uses
   - File: `ace_after_task.py`, lines 480-520

**Key Code Evidence** (`ace_after_task.py`, lines 480-520):
```python
def main():
    """Stop hook - Must parse transcript manually since no pre-parsed data provided"""
    event = json.load(sys.stdin)
    
    # For Stop hook: ONLY transcript_path is provided
    # Must manually extract messages and tool_uses from transcript file
    transcript_path = event.get('transcript_path')
    
    # No other pre-parsed data available!
```

---

### 3. Alternative Capture Points

**Question**: Could we capture at the MCP level instead of hooks?

**Answer**: Technically possible but architecturally limited.

**Evaluation**:

| Approach | Feasibility | Limitations |
|----------|-------------|------------|
| **MCP Tool Context** | ❌ No | MCP protocol doesn't provide conversation history |
| **MCP Tool State Files** | ✅ Yes | Must use file-based state (what ACE already does) |
| **Pre-Response Hook** | ❌ No | Claude Code has no "before response" hook |
| **Custom MCP Server** | ✅ Partial | Would need to be invoked explicitly by Claude, not automatic |
| **Session Persistence** | ✅ Yes | Session pinning solves this (already implemented in v5.1.4) |

**Current Best Practice** (from codebase):
ACE uses file-based state for pattern persistence:
```python
# ace_before_task.py, line 55-70
session_id = str(uuid.uuid4())
session_file = Path(f"/tmp/ace-session-{context['project']}.txt")
session_file.write_text(session_id)

# ce-ace CLI stores patterns in SQLite:
# ~/.ace-cache/sessions.db (session pinning, v5.1.4+)
```

This is BETTER than relying on hook context because:
- Survives context compaction
- 89% faster than server fetch
- Fully under plugin control
- No hook dependency

---

### 4. Claude Code Hook Limitations (Deep Dive)

**Question**: What are the architectural constraints of Claude Code hooks?

**Answer**: Hooks are EVENT HANDLERS, not full context observers.

**Hook Architecture** (from `hooks.json`):
```json
{
  "SessionStart": [{ "type": "command", "command": "..." }],
  "UserPromptSubmit": [{ "type": "command", "command": "..." }],
  "PostToolUse": [{ "type": "command", "command": "..." }],
  "PreCompact": [{ "type": "prompt", "command": "..." }],
  "Stop": [{ "type": "prompt", "command": "..." }],
  "SubagentStop": [{ "type": "command", "command": "..." }]
}
```

Each hook fires at specific lifecycle points and receives ONLY event-specific data:

| Hook | Event Trigger | Data Available | Conversation Context |
|------|---------------|----------------|--------------------|
| SessionStart | Session begins | - | None |
| UserPromptSubmit | User types prompt | Prompt text | None |
| PostToolUse | After any tool | Tool result | None directly (must parse transcript) |
| PreCompact | Before compaction | Messages + tool_uses (optional) | Partial (since last start/compaction) |
| Stop | End of response | Transcript path only | Must parse file |
| SubagentStop | Subagent ends | Agent transcript path | Subagent only, not main session |

**Critical Constraint** (from hook wrapper code):
```bash
# ace_stop_wrapper.sh
# Hook receives event via stdin:
INPUT_JSON=$(cat)

# Extract only what Claude Code provides:
TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty')

# NO other fields available!
```

---

### 5. Undocumented Features & Experimental Features

**Question**: Are there beta/experimental hook features that provide more context?

**Answer**: Prompt hooks (v5.1.13+) provide SOME semantic evaluation, but NOT conversation access.

**Prompt Hook Findings** (from `ACE_PROMPT_HOOK_DESIGN.md`):

The Stop hook was upgraded to use prompt-based evaluation:
```json
{
  "Stop": {
    "type": "prompt",
    "model": "haiku",
    "prompt": "[Semantic evaluation of transcript content...]",
    "action": {
      "if": "has_learning === true",
      "then": {
        "type": "command",
        "command": "ace_after_task_wrapper.sh"
      }
    }
  }
}
```

**What This Enables**:
- Semantic understanding of transcript content
- Intelligent decision-making (vs regex filtering)
- Cost: ~$0.0001 per evaluation

**What This DOES NOT Enable**:
- Access to pre-execution conversation history
- Tool call metadata beyond what's in transcript
- Structured event data (only raw transcript text)
- Real-time tool execution data

**Trade-off Analysis**:
```
Prompt Hook Approach (current):
✅ Intelligent transcript evaluation
✅ Semantic understanding of learning value
✅ Per-task context (last user message = task start)
❌ Cannot access conversation BEFORE transcript file exists
❌ Cannot access tool metadata directly
❌ Parses transcript file manually (slow)

Full Context Approach (ideal but impossible):
✅ Would have all conversation history
✅ Would have tool call sequence
❌ Claude Code doesn't expose this to hooks
❌ Violates MCP protocol boundaries
❌ Not part of hook event model
```

---

## Key Architectural Insights

### The Hook Event Model

Claude Code's hook system is designed as a **lightweight event broadcaster**, not a context server:

1. **Event-Driven**: Hooks fire at specific lifecycle points
2. **Minimal Data**: Each hook receives only event-specific data
3. **Subprocess Model**: Hooks run as separate processes (isolation)
4. **No Back-Channel**: Hooks cannot request additional context
5. **Idempotent**: Hooks should be safe to run multiple times

This design is INTENTIONAL because:
- Hooks must be fast (don't block compilation/response)
- Hooks run in isolation (security)
- Multiple hook implementations shouldn't interfere
- Claude Code maintains separation of concerns

### The Transcript-Based Solution

ACE solved the context limitation by:

1. **Using Transcript Files** as the "source of truth":
   ```python
   # ace_after_task.py, line 280-300
   transcript_file = Path(transcript_path).expanduser()
   with open(transcript_file, 'r') as f:
       for line in f:
           entry = json.loads(line)
           message = entry.get('message', {})
           # Parse messages manually
   ```

2. **Per-Task Parsing** instead of incremental:
   ```python
   # ace_after_task.py, line 310-340
   # Find LAST user message = task start
   last_user_idx = -1
   for i in range(len(all_entries) - 1, -1, -1):
       message = all_entries[i].get('message', {})
       if message.get('role') == 'user' and not is_tool_result(message):
           user_prompt = extract_content(message)
           last_user_idx = i
           break
   
   # Everything AFTER = THIS TASK's work
   task_messages = all_entries[last_user_idx + 1:]
   ```

3. **Session Pinning** for context persistence (v5.1.4+):
   ```python
   # ace_before_task.py, line 55-70
   session_id = str(uuid.uuid4())
   
   # Store in SQLite (survives compaction)
   patterns = recall_session(session_id)
   ```

This approach is SUPERIOR to hook context because:
- Works across all hook types
- Survives context compaction
- Fully scriptable and debuggable
- No Claude Code API changes needed

---

## Findings Summary Table

| Research Question | Answer | Evidence | Alternative |
|-------------------|--------|----------|------------|
| **MCP tool context?** | No conversation history in hooks | Hook event model, `ace_before_task.py:85-100` | Use file-based state (ACE's approach) |
| **Main agent tracking?** | Internal only, not exposed | `ACE_TRAJECTORY_FLOW.md:9-27` | Parse transcript files |
| **Pre-response hook?** | Doesn't exist in Claude Code | `hooks.json` event list | Use Stop hook + prompt evaluation |
| **Custom MCP server?** | Possible but requires explicit invocation | MCP protocol design | Stick with hooks + CLI |
| **Conversation access?** | Only via transcript files | Stop hook must parse file | PreCompact provides pre-parsed data (sometimes) |
| **Undocumented features?** | Prompt hooks exist but no magic context | `ACE_PROMPT_HOOK_DESIGN.md` | Prompt hooks for semantic evaluation |

---

## Breakthrough: The Actual Solution Already Exists

**Critical Discovery**: ACE v5.2.0+ already SOLVED the context problem optimally:

### Three-Hook Architecture (v5.2.0+)

```
PreCompact Hook (Safety Net):
├─ Fires BEFORE context compaction
├─ Has messages + tool_uses (pre-parsed by Claude Code)
├─ Captures full task work BEFORE knowledge loss
└─ Records position for delta tracking

         ↓

Stop Hook (True End):
├─ Fires at TRUE end of task/session
├─ Parses transcript manually (necessary cost)
├─ Captures NEW work since PreCompact (delta)
└─ Handles short tasks that never triggered PreCompact

         ↓

SubagentStop Hook (Subagent Tasks):
├─ Fires when Task tool subagent completes
├─ Uses subagent's transcript (separate file)
└─ Captures specialized tool work
```

**Why This Is Optimal**:
1. **PreCompact**: No parsing needed, fast, full context
2. **Stop**: Only parses when necessary, captures delta
3. **SubagentStop**: Specialized for agent work

**Code Evidence** (`ace_after_task.py`, lines 350-380):
```python
# STEP 2: Delta tracking for Stop hook (v5.2.0)
if hook_event_name == 'Stop':
    last_captured_position = get_captured_position(session_id)
    
    if last_captured_position > 0 and last_captured_position < task_position:
        # PreCompact ran - capture ONLY NEW messages (delta)
        task_messages = task_messages[last_captured_position:]
```

---

## Technical Constraints (Not Limitations)

The lack of hook-level conversation context is NOT a bug - it's a FEATURE:

1. **Performance**: Hooks must be fast, full context would slow compilation
2. **Security**: Hooks run in isolation, limited context reduces attack surface
3. **Reliability**: Event-based model is simpler, more predictable
4. **Scalability**: Multiple hooks don't fight over shared state

---

## Recommendations for Your Investigation

### If You Need Real-Time Execution Data:

**Option 1: File-Based State** (RECOMMENDED)
```python
# Use /tmp for transient state
# Use ~/.ace-cache for persistent state
# Use .claude/data for session logs
# This is what ACE already does!
```

**Option 2: Session Pinning** (Already Implemented)
```python
# Store session context in SQLite
# Survives context compaction
# 89% faster than server fetch
# See: ace_before_task.py:55-70
```

**Option 3: Custom MCP Server** (Last Resort)
```python
# Only if you need Claude-server integration
# Still won't get conversation history automatically
# Would need to be explicitly invoked in tools
# Higher complexity, minimal benefit
```

### If You Need Hook Event Enhancements:

**Current State** (v5.2.0+):
- ✅ PreCompact: Messages + tool_uses provided
- ✅ Stop: Transcript path provided, can parse manually
- ✅ Prompt hooks: Semantic evaluation of content
- ❌ No "magic" context access

**Unlikely Future Enhancements**:
- ❌ Full conversation history to hooks (would slow compilation)
- ❌ Real-time tool execution streams (violates hook model)
- ❌ Structured tool metadata (already in transcript)

---

## Final Conclusion

**There is NO mechanism in Claude Code that gives hooks access to conversation context that was previously executed beyond what's in the transcript file.**

However, this is NOT a problem because:

1. **Transcript files ARE the source of truth** - They contain everything that was said and done
2. **Parsing is efficient enough** - ACE parses in ~100-200ms for typical conversations
3. **Session pinning solves persistence** - Patterns survive compaction with SQLite caching
4. **Three-hook strategy is optimal** - PreCompact + Stop + SubagentStop covers all scenarios
5. **File-based state is reliable** - No network dependency, fully debuggable

The ACE plugin has already implemented the OPTIMAL solution given Claude Code's architectural constraints.

---

## Files Referenced

Key files examined during this investigation:

1. **Hook Architecture**:
   - `plugins/ace/hooks/hooks.json`
   - `shared-hooks/ace_before_task.py`
   - `shared-hooks/ace_after_task.py`

2. **Hook Documentation**:
   - `docs/ACE_TRAJECTORY_FLOW.md`
   - `docs/ACE_PROMPT_HOOK_DESIGN.md`
   - `plugins/ace/PROMPT_HOOK_SUMMARY.md`

3. **Context Management**:
   - `shared-hooks/utils/ace_context.py`
   - `plugins/ace/docs/technical/ARCHITECTURE.md`

4. **MCP Configuration**:
   - `plugins/ace/.mcp.template.json`
   - `plugins/ace/docs/archive/v4-mcp-architecture/MCP_CLIENT_IMPLEMENTATION.md`

---

**Investigation Status**: COMPLETE
**Key Findings**: Fully documented above
**Recommended Action**: ACE's current approach (v5.2.0+) is already optimal
