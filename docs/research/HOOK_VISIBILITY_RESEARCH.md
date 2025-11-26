# Hook Visibility Research: cc-boilerplate-v2 vs ACE Implementation

## Executive Summary

This research compares how cc-boilerplate-v2 and ACE marketplace handle hook output visibility in Claude Code conversations. The key finding: **cc-boilerplate uses `hookSpecificOutput` JSON structure for framework-level visibility, while ACE uses direct stdout with emoji prefixes for user-visible output**.

---

## 1. How Hook Output Appears in Claude Code

### cc-boilerplate-v2 Approach: `hookSpecificOutput` JSON

**Mechanism**: Return structured JSON from hooks that Claude Code's framework recognizes and injects into conversation context.

**Location**: `/shared-hooks/session_start.py` (lines 168-176)

```python
# When --load-context flag is used:
output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context  # User-visible context
    }
}
print(json.dumps(output))
```

**How it works**:
- Hook prints JSON with `hookSpecificOutput` key
- Claude Code framework recognizes this structure
- Content injected directly into conversation as context
- User sees: "Session started at: 2024-11-17 10:30:45"

**Advantages**:
- Framework-integrated: Claude Code natively handles this format
- Clean separation between machine/user content
- Context is injected, not printed as visible output
- No visual clutter in conversation

---

### ACE Approach: Direct stdout with Emoji Markers

**Mechanism**: Print text directly to stdout with emoji prefixes; hooks write to log files for persistence.

**Locations**: 
- `/shared-hooks/ace_before_task.py` (lines 41-80)
- `/shared-hooks/ace_after_task.py` (lines 98-154)

```python
# In ace_before_task.py - Before Task Hook
print("🔍 [ACE] Searching playbook...")  # Visible to user
print(f"✅ [ACE] Found {pattern_count} relevant patterns:")
for pattern in pattern_list[:5]:
    print(f"   • {content} (+{helpful} helpful)")

# In ace_after_task.py - After Task Hook
print("📚 [ACE] Automatically capturing learning from this session...")
print(f"   Task: {trace['task'][:80]}...")
print(f"   Steps: {len(trace['trajectory'])} actions")
print(f"   Status: {'✅ Success' if trace['result']['success'] else '❌ Failed'}")
```

**How it works**:
- Hooks print directly to stdout/stderr
- All output visible in Claude Code conversation
- Emoji prefixes make output scannable
- Structured logging to `.claude/data/logs/` for persistence

**Advantages**:
- Transparent: Users see exactly what hooks are doing
- Immediate feedback: No hidden processing
- Works without framework support
- Self-explanatory output with visual hierarchy

---

## 2. Wrapper Scripts and Output Routing

### cc-boilerplate-v2 Wrapper Pattern

**File**: `/plugins/core/scripts/session_start_wrapper.sh`

```bash
#!/usr/bin/env bash
# Forward to session_start.py in marketplace
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/session_start.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] session_start.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

exec uv run "${HOOK_SCRIPT}" "$@"
```

**Key Features**:
- Simple pass-through to Python script
- Error checking for missing scripts
- Uses `exec` to replace shell process
- All output flows through naturally

### ACE Wrapper Pattern

**Files**: 
- `/plugins/ace/scripts/ace_before_task_wrapper.sh`
- `/plugins/ace/scripts/ace_after_task_wrapper.sh`

```bash
#!/usr/bin/env bash
# ACE Before Task Wrapper - Forwards to shared-hooks/ace_before_task.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/ace_before_task.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_before_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

exec uv run "${HOOK_SCRIPT}" "$@"
```

**Key Features**:
- Identical to cc-boilerplate pattern
- Simple forwarding architecture
- No special output routing
- Direct stdout pass-through to Claude Code

---

## 3. Hook Lifecycle and Visibility

### cc-boilerplate-v2: Event-Based with Structured Output

| Hook | Trigger | Output Type | Visibility |
|------|---------|------------|-----------|
| SessionStart | App startup | Optional `hookSpecificOutput` JSON | Framework-injected context |
| PreToolUse | Before tool call | JSON logging only | Hidden (logging only) |
| PostToolUse | After tool call | JSON logging + token metrics | Hidden (logging only) |
| UserPromptSubmit | User sends prompt | Validation logging | Hidden (logging only) |
| PreCompact | Before compaction | Backup events | Hidden (logging only) |
| Notification | Event notification | TTS audio + JSON | Out-of-band (audio) |

**Visibility Pattern**:
- Most hooks are "silent" (hidden logging)
- SessionStart can inject context via `hookSpecificOutput`
- Notification uses out-of-band audio channel

### ACE: Visible Hook Output with Reminders

| Hook | Trigger | Output Type | Visibility |
|------|---------|------------|-----------|
| SessionStart | App startup | CLI installation check | Visible in conversation |
| UserPromptSubmit | User sends prompt | Emoji-prefixed search results | Visible in conversation |
| PreCompact | Before compaction | Learning capture with status | Visible in conversation |
| Stop | Stop event | Learning capture with status | Visible in conversation |

**Visibility Pattern**:
- All hooks produce visible, emoji-marked output
- Immediate user feedback on what's happening
- Persistent logging to `.claude/data/logs/`
- Reminders to run manual commands (`/ace-learn`)

---

## 4. Data Flow Comparison

### cc-boilerplate-v2 Data Flow

```
Hook Event (JSON from Claude Code)
    ↓
Bash Wrapper (session_start_wrapper.sh)
    ↓
Python Script (session_start.py)
    ↓
Three Paths:
    1. LOGGING: Write to .claude/data/logs/session_start.json
    2. CONTEXT_INJECTION: Return hookSpecificOutput JSON → Framework injects
    3. TTS: Execute TTS script (async, out-of-band)
    ↓
Exit(0) - Non-blocking
```

### ACE Data Flow

```
Hook Event (JSON from Claude Code)
    ↓
Bash Wrapper (ace_before_task_wrapper.sh)
    ↓
Python Script (ace_before_task.py)
    ↓
Three Paths:
    1. STDOUT_VISIBLE: Print emoji-marked status messages
    2. SUBPROCESS: Call ce-ace CLI for search/learn
    3. LOGGING: Write to .claude/data/logs/ (optional)
    ↓
Exit(0) - Non-blocking
```

---

## 5. Key Differences

### Visibility Philosophy

| Aspect | cc-boilerplate-v2 | ACE |
|--------|------------------|-----|
| Default visibility | Hidden (logging) | Visible (stdout) |
| User awareness | Framework handles context injection | User sees all output |
| Output format | Structured JSON or audio | Emoji-marked text |
| Framework integration | Uses `hookSpecificOutput` | Direct stdout printing |
| Logging | Primary method | Secondary (detailed logs) |

### Output Patterns

**cc-boilerplate-v2 - Silent Processing**:
```
# What user sees:
(Nothing - context injected silently)

# What happens in background:
Pre/PostToolUse hooks → Log to JSON → Process metrics
SessionStart hook → Load context → Inject via hookSpecificOutput
Notification hook → TTS audio announcement
```

**ACE - Transparent Processing**:
```
# What user sees:
🔍 [ACE] Searching playbook...
✅ [ACE] Found 3 relevant patterns:
   • Refresh token rotation prevents theft (+8 helpful)
   • HttpOnly cookies for refresh tokens (+6 helpful)
   ...
📚 [ACE] Automatically capturing learning from this session...
   Task: Implement JWT auth...
   Steps: 5 actions
   Status: ✅ Success
```

---

## 6. Making Output Visible: Available Mechanisms

### Mechanism 1: `hookSpecificOutput` (Framework-Integrated)

**When to use**: Need framework-level visibility that integrates with conversation context

**How**:
```python
output = {
    "hookSpecificOutput": {
        "hookEventName": "YourEventName",
        "additionalContext": "User-visible context",
        "otherField": "Additional data"
    }
}
print(json.dumps(output))
```

**Limitations**:
- Only works in certain hooks (SessionStart, UserPromptSubmit)
- Requires Claude Code framework support
- Content injected as context, not visible message

### Mechanism 2: Direct stdout (Transparent)

**When to use**: Want visible, user-facing output with emoji markers

**How**:
```python
print("🔍 [PREFIX] User-visible message")
print(f"✅ [PREFIX] Success status: {detail}")
print(f"   • Bullet point detail")
```

**Advantages**:
- Works in all hooks
- User sees exact output
- No framework dependencies
- Emoji makes it scannable

### Mechanism 3: Structured Logging (Hidden)

**When to use**: Need to track hook activity without cluttering conversation

**How**:
```python
log_dir = Path.cwd() / '.claude' / 'data' / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
with open(log_dir / 'hook_name.json', 'a') as f:
    json.dump(event_data, f)
```

**Advantages**:
- Silent processing
- Detailed audit trail
- Searchable for analytics

---

## 7. Recommendations for ACE Hook Visibility

### Current Situation
ACE already uses **Mechanism 2** effectively:
- UserPromptSubmit hook shows search results with emoji markers
- PreCompact hook shows learning capture status
- All output visible and transparent

### What's Working Well
✅ Direct stdout with emoji prefixes  
✅ Clear visual hierarchy (`🔍` search, `✅` success, `📚` learning)  
✅ Immediate user feedback  
✅ Works without framework modifications  
✅ Transparent about what's happening  

### Potential Enhancements

1. **Add hook timing information**:
```python
import time
start = time.time()
# ... do work ...
elapsed = time.time() - start
print(f"⏱️  [ACE] Search completed in {elapsed:.2f}s")
```

2. **Show pattern impact**:
```python
print(f"🎯 [ACE] Patterns retrieved from {len(patterns)} sessions")
print(f"📊 [ACE] Cumulative helpful score: {total_helpful}")
```

3. **Use structured output for both visibility AND logging**:
```python
# Show to user
print("✅ [ACE] Learning captured successfully")

# Also log detailed data
log_data = {
    "timestamp": datetime.now().isoformat(),
    "task": task_description,
    "patterns": len(patterns),
    "success": True
}
with open(log_file, 'w') as f:
    json.dump(log_data, f)
```

4. **Add hook execution summary at session end**:
```
ACE Hook Summary:
  UserPromptSubmit: 5 searches (avg 0.3s)
  PreCompact: 1 learning capture
  Total patterns used: 8
```

### Why ACE's Approach is Better for Observability

Unlike cc-boilerplate which hides most activity:

1. **Transparency**: User sees exactly what hook is doing
2. **Trust**: No "magic" happening behind the scenes
3. **Debugging**: Easy to spot hook issues
4. **User Control**: User can see patterns being used
5. **Feedback Loop**: User gets immediate confirmation

---

## 8. Code Snippets Comparison

### Session Start Context Injection (cc-boilerplate)

```python
# /shared-hooks/session_start.py (lines 168-176)
if args.load_context:
    context = load_development_context(source)
    if context:
        # Using JSON output to add context
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context
            }
        }
        print(json.dumps(output))
        sys.exit(0)
```

**Result**: Context silently injected into conversation

### Pre-Task Pattern Retrieval (ACE)

```python
# /shared-hooks/ace_before_task.py (lines 41-80)
print("🔍 [ACE] Searching playbook...")

patterns = run_search(
    query=user_prompt,
    org=context['org'],
    project=context['project'],
    threshold=0.85
)

if patterns:
    pattern_list = patterns.get('similar_patterns', [])
    pattern_count = len(pattern_list)
    print(f"✅ [ACE] Found {pattern_count} relevant patterns:")
    for pattern in pattern_list[:5]:
        content = pattern.get('content', '')
        if len(content) > 80:
            content = content[:77] + '...'
        helpful = pattern.get('helpful', 0)
        print(f"   • {content} (+{helpful} helpful)")
else:
    print("❌ [ACE] Search failed or returned no results")
```

**Result**: Clear, visible feedback to user with pattern details

---

## 9. Architecture Comparison

### cc-boilerplate-v2: Silent Observability

```
User Interaction
    ↓
Hook Triggered (SessionStart, PreToolUse, PostToolUse)
    ↓
Bash Wrapper
    ↓
Python Hook
    ↓
├─ Optional: Inject context via hookSpecificOutput
├─ Always: Log to .claude/data/logs/*.json
└─ Optional: Run async operation (TTS, notify)
    ↓
Return exit(0)
    ↓
User Continues (Most output invisible)
```

**Philosophy**: Hooks work silently in background; only inject context when needed

### ACE: Transparent Active Feedback

```
User Interaction
    ↓
Hook Triggered (UserPromptSubmit, PreCompact)
    ↓
Bash Wrapper
    ↓
Python Hook
    ↓
├─ Print status: "🔍 [ACE] Searching..."
├─ Call subprocess: ce-ace search/learn --stdin
├─ Print results: "✅ [ACE] Found 3 patterns:"
├─ Log details: .claude/data/logs/*.json
└─ Print completion: "📚 [ACE] Learning captured!"
    ↓
Return exit(0)
    ↓
User Sees Feedback (All output visible)
```

**Philosophy**: Transparency and immediate feedback on hook activity

---

## 10. Summary: Which Approach for What?

### Use `hookSpecificOutput` (cc-boilerplate style) When:
- Context should be injected silently
- Don't want to clutter conversation output
- Need framework integration for special handling
- SessionStart or similar framework hooks

### Use Direct stdout (ACE style) When:
- Want transparent, visible feedback
- Hook performs user-facing operations (search, learn)
- Need immediate confirmation of action
- Want to show results/patterns to user
- Debugging or observability is important

### Use Structured Logging When:
- Recording audit trail
- Collecting metrics (token usage, timing)
- Analyzing hook performance
- Not meant for user visibility

---

## Conclusion

**cc-boilerplate-v2** achieves hook visibility through:
1. **`hookSpecificOutput` JSON** for framework-level context injection
2. **Structured logging** to `.claude/data/logs/` for audit trail
3. **Out-of-band TTS** for notifications

**ACE Marketplace** achieves hook visibility through:
1. **Direct stdout** with emoji-marked output for immediate feedback
2. **Structured logging** to `.claude/data/logs/` for audit trail
3. **CLI integration** for subprocess operations (search, learn)

**ACE's approach is superior for observability** because:
- Users see what's happening in real-time
- No hidden processing or "magic"
- Transparent operation builds trust
- Easy to debug issues
- Immediate feedback loop

**Recommendation**: ACE should continue its current approach of direct stdout with emoji markers. It's more transparent, user-friendly, and requires no framework modifications.
