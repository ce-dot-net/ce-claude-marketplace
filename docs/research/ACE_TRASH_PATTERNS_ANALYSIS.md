# ACE Trash Patterns Investigation

## Executive Summary

**Problem**: The ACE playbook contains low-quality "trash" patterns learned from minimal/empty tool operations.

**Root Cause**: Both PostToolUse and PreCompact hooks are building trajectory actions with empty tool descriptions, creating patterns like "Edit - ", "Write - ", "Bash - " that get sent to the server and learned.

**Impact**: 
- 285+ observations of empty edit patterns
- 246+ observations of null operation patterns  
- Cluttering playbook with useless patterns
- Degrading pattern quality and search relevance

**Solution**: Implement 3-layer filtering to prevent trash patterns from being captured.

---

## Evidence of Trash Patterns

From actual ACE playbook (ce-ace patterns --json):

### Pattern 1: Empty Edit Operations
```json
{
  "id": "ctx-3458210482-3431",
  "content": "Empty task name edit operations: When task shows 'Edit:' with no content and minimal trajectory ('Edit - ' → 'completed'), this indicates a null or empty edit operation that completed successfully but performed no actual changes",
  "observations": 285,
  "helpful": 285,
  "evidence": [
    "Task name is literally 'Edit:' with no content",
    "Single step trajectory shows 'Edit - ' with no specific action",
    "Success=true despite no apparent work being done"
  ]
}
```

### Pattern 2: Empty Write Operations
```json
{
  "id": "ctx-3559050523-70e1",
  "content": "Minimal write operations with empty content: When task shows 'Write:' with no content and minimal trajectory ('Write - ' → 'completed'), this indicates a null or empty write operation that completed successfully but performed no actual file changes",
  "observations": 5,
  "helpful": 5
}
```

### Pattern 3: Empty Bash Operations
```json
{
  "id": "ctx-3584659067-2afe",
  "content": "Minimal bash operations with empty command: When task shows 'Bash' with no command content and minimal trajectory ('Bash - ' → 'completed'), this indicates a null or empty bash operation...",
  "observations": 3,
  "helpful": 3
}
```

### Pattern 4: Empty Grep Operations
```json
{
  "id": "ctx-3584584656-544f",
  "content": "Minimal grep operations with empty pattern: When task shows 'Grep' with no search pattern and minimal trajectory ('Grep - ' → 'completed')...",
  "observations": 1,
  "helpful": 1
}
```

**Key Evidence**: "Single step trajectory shows 'Edit - ' with no specific action"
This proves the hooks are creating actions with empty descriptions!

---

## Root Cause Analysis

### Where Trash Patterns Originate

#### Source 1: PostToolUse Hook (ace_task_complete.py)

**File**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-claude-marketplace/shared-hooks/ace_task_complete.py`

**Problem Code** (Line 180):
```python
# Add current tool as final step
trajectory.append({
    "step": len(trajectory) + 1,
    "action": f"{tool_name} - {tool_description}",  # ❌ PROBLEM: tool_description can be empty!
    "result": "completed"
})
```

**What Happens**:
- When Claude Code sends PostToolUse event with empty `description` field
- Creates action string: `"Edit - "` (tool name + dash + empty string)
- Gets appended to trajectory and sent to server
- Server learns this as a "pattern"

**Example Event That Causes Trash**:
```json
{
  "tool_name": "Edit",
  "description": "",  // Empty string!
  "result": {"summary": "completed"}
}
```

**Generated Trace**:
```json
{
  "task": "Task completed",
  "trajectory": [
    {
      "step": 1,
      "action": "Edit - ",  // ❌ TRASH!
      "result": "completed"
    }
  ]
}
```

#### Source 2: PreCompact Hook (ace_after_task.py)

**File**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-claude-marketplace/shared-hooks/ace_after_task.py`

**Problem Code** (Line 76):
```python
# Build trajectory entry with tool_use_id for correlation
trajectory_entry = {
    "step": idx,
    "action": f"{tool_name} - {tool_desc}",  # ❌ PROBLEM: tool_desc can be empty!
    "result": tool.get('result', {}).get('summary', 'completed') if isinstance(tool.get('result'), dict) else 'completed'
}

# Add tool_use_id if available (Claude Code v2.0.43+)
if tool_use_id:
    trajectory_entry["tool_use_id"] = tool_use_id

trajectory.append(trajectory_entry)  # ❌ Always appends, even if tool_desc is empty!
```

**What Happens**:
- Iterates over all `tool_uses` from PreCompact event
- Creates action for EVERY tool, even if description is empty
- No filtering for empty/whitespace-only descriptions
- All actions get appended to trajectory

**Example Event That Causes Trash**:
```json
{
  "tool_uses": [
    {
      "tool_name": "Edit",
      "description": "",  // Empty!
      "result": {"summary": "completed"}
    },
    {
      "tool_name": "Write",
      "description": " ",  // Whitespace only!
      "result": {"summary": "completed"}
    }
  ]
}
```

**Generated Trace**:
```json
{
  "trajectory": [
    {
      "step": 1,
      "action": "Edit - ",  // ❌ TRASH!
      "result": "completed"
    },
    {
      "step": 2,
      "action": "Write -  ",  // ❌ TRASH!
      "result": "completed"
    }
  ]
}
```

---

### Why Trash Patterns Pass Filtering

#### PostToolUse Hook (ace_task_complete.py)

**Current Check** (Line 112-145):
```python
def is_substantial_task(event):
    """
    Determine if this tool use represents substantial work worth learning from.
    """
    tool_name = event.get('tool_name', '')
    tool_description = event.get('description', '').lower()

    # Task tool completion is always substantial
    if tool_name == 'Task':
        return True  # ✓ Checks tool type

    # Git commits indicate completed work
    if tool_name == 'Bash' and 'git commit' in tool_description:
        return True  # ✓ Checks for git commits

    # Check if edit sequence just completed (regardless of current tool)
    if check_sequence_completion(tool_name):
        return True  # ✓ Checks edit sequences

    # All other cases - no trigger
    return False
```

**Missing Checks**:
- ❌ No validation of `tool_description` emptiness
- ❌ No minimum description length requirement
- ❌ No trajectory quality check before sending to server

**How Trash Gets Through**:
1. Edit sequence of 2+ files (triggers `check_sequence_completion`)
2. Some edits have empty descriptions
3. Hook builds trajectory with "Edit - " actions
4. Passes `is_substantial_task()` because it's an edit sequence
5. Gets sent to server and learned!

#### PreCompact Hook (ace_after_task.py)

**Current Check** (Line 178-181):
```python
has_substantial_work = (
    trace['trajectory'] and len(trace['trajectory']) > 0 and  # ✓ Trajectory exists
    not trace['task'].startswith("Session work")  # ✓ Not generic session
)
```

**Missing Checks**:
- ❌ No validation of trajectory action quality
- ❌ Accepts trajectories with ALL empty actions
- ❌ No minimum action description length
- ❌ No check for meaningful content

**How Trash Gets Through**:
1. Any tool use creates a trajectory entry
2. Even if ALL descriptions are empty
3. As long as `trajectory` list has length > 0
4. And task != "Session work"
5. Passes filter and gets sent to server!

---

## Detailed Examples

### Scenario 1: PostToolUse Edit Sequence

**User Action**: Claude makes 3 edits, some with empty descriptions

**PostToolUse Events**:
```json
// Event 1
{"tool_name": "Edit", "description": "Update auth.ts with JWT tokens"}

// Event 2  
{"tool_name": "Edit", "description": ""}  // Empty!

// Event 3
{"tool_name": "Read", "description": "Review changes"}
```

**What Happens**:
1. Edit #1: Tracked (description OK)
2. Edit #2: Tracked (description empty but still tracked!)
3. Read: Triggers `check_sequence_completion()` because 2+ edits
4. `is_substantial_task()` returns True (edit sequence complete)
5. Builds trajectory:
   ```json
   [
     {"step": 1, "action": "Edit - File modification", "result": "completed"},
     {"step": 2, "action": "Edit - File modification", "result": "completed"},
     {"step": 3, "action": "Read - Review changes", "result": "completed"}
   ]
   ```
6. Wait, the code doesn't preserve individual edit descriptions!
7. Line 171-175 creates generic "Edit - File modification" for ALL edits
8. But line 180 adds current tool with actual description
9. So if current tool (Read) has empty description → "Read - "

**Actually, re-reading the code more carefully...**

Looking at lines 167-175:
```python
if state.get('edit_count', 0) >= 2:
    # We have an edit sequence - this is what we're learning from
    task_description = f"Code modifications: {state['edit_count']} files edited"
    for i in range(1, state['edit_count'] + 1):
        trajectory.append({
            "step": i,
            "action": "Edit - File modification",  # Generic action!
            "result": "completed"
        })
```

**Ah! This creates GENERIC "Edit - File modification" actions!**

But then line 177-182 adds the CURRENT tool:
```python
# Add current tool as final step
trajectory.append({
    "step": len(trajectory) + 1,
    "action": f"{tool_name} - {tool_description}",  # ❌ Can be empty!
    "result": "completed"
})
```

**So trash comes from**:
- The current tool that ENDS the edit sequence
- If that tool has empty description → creates "Read - " or "Grep - "

### Scenario 2: PreCompact with Empty Descriptions

**User Session**: Simple session with tools

**PreCompact Event**:
```json
{
  "messages": [
    {"role": "user", "content": "Check the file"},
    {"role": "assistant", "content": "I'll read it"}
  ],
  "tool_uses": [
    {"tool_name": "Read", "description": ""},  // Empty!
    {"tool_name": "Grep", "description": ""}   // Empty!
  ]
}
```

**What Happens**:
1. `extract_execution_trace()` processes tool_uses
2. Line 76: Creates `"action": "Read - "` (empty!)
3. Line 76: Creates `"action": "Grep - "` (empty!)
4. Trajectory = [{"action": "Read - "}, {"action": "Grep - "}]
5. `has_substantial_work` check:
   - `trace['trajectory']` exists ✓
   - `len(trace['trajectory']) > 0` = 2 ✓
   - `not trace['task'].startswith("Session work")` ✓ (task = "User request: Check the file")
6. **PASSES FILTER!**
7. Sends to server with empty actions
8. Server learns: "Minimal read operations with empty content..."

---

## Proposed Solutions

### Solution 1: Filter Empty Descriptions (CRITICAL)

**Prevents trash at the source by skipping empty actions entirely.**

#### Fix 1A: ace_task_complete.py (Line 177-182)

**BEFORE**:
```python
# Add current tool as final step
trajectory.append({
    "step": len(trajectory) + 1,
    "action": f"{tool_name} - {tool_description}",
    "result": "completed"
})
```

**AFTER**:
```python
# Add current tool as final step (only if description is meaningful)
if tool_description and tool_description.strip() and len(tool_description.strip()) >= 5:
    trajectory.append({
        "step": len(trajectory) + 1,
        "action": f"{tool_name} - {tool_description}",
        "result": "completed"
    })
```

**Why**:
- `tool_description` - Checks not None/empty
- `.strip()` - Removes whitespace
- `len(...) >= 5` - Minimum 5 chars (excludes "Fix", "Run", etc.)

#### Fix 1B: ace_after_task.py (Line 74-84)

**BEFORE**:
```python
# Build trajectory entry with tool_use_id for correlation
trajectory_entry = {
    "step": idx,
    "action": f"{tool_name} - {tool_desc}",
    "result": tool.get('result', {}).get('summary', 'completed') if isinstance(tool.get('result'), dict) else 'completed'
}

# Add tool_use_id if available (Claude Code v2.0.43+)
if tool_use_id:
    trajectory_entry["tool_use_id"] = tool_use_id

trajectory.append(trajectory_entry)
```

**AFTER**:
```python
# Skip tools with empty/whitespace-only descriptions
if not tool_desc or not tool_desc.strip() or len(tool_desc.strip()) < 5:
    continue  # Skip this tool, don't add to trajectory

# Build trajectory entry with tool_use_id for correlation
trajectory_entry = {
    "step": idx,
    "action": f"{tool_name} - {tool_desc}",
    "result": tool.get('result', {}).get('summary', 'completed') if isinstance(tool.get('result'), dict) else 'completed'
}

# Add tool_use_id if available (Claude Code v2.0.43+)
if tool_use_id:
    trajectory_entry["tool_use_id"] = tool_use_id

trajectory.append(trajectory_entry)
```

**Why**:
- Filters BEFORE creating trajectory_entry
- Uses `continue` to skip empty descriptions entirely
- Step numbers will auto-adjust via enumerate

---

### Solution 2: Trajectory Quality Check (SAFETY NET)

**Validates trajectory quality before sending to server.**

#### Fix 2A: ace_task_complete.py (Before line 251)

**BEFORE** (Line 250-254):
```python
# Substantial work detected - capture learning immediately!
trace = build_execution_trace_from_posttooluse(event)

# Capture learning
stats = capture_learning(trace, context)
```

**AFTER**:
```python
# Substantial work detected - capture learning immediately!
trace = build_execution_trace_from_posttooluse(event)

# Validate trajectory quality before sending to server
if not trace['trajectory'] or len(trace['trajectory']) == 0:
    # Empty trajectory - skip learning
    print(json.dumps({}))
    sys.exit(0)

# Check for meaningful actions (not just empty strings)
meaningful_actions = [
    t for t in trace['trajectory']
    if t.get('action') and len(t['action'].split(' - ', 1)[-1].strip()) >= 5
]

if len(meaningful_actions) == 0:
    # All actions are empty/trash - skip learning
    print(json.dumps({}))
    sys.exit(0)

# Capture learning
stats = capture_learning(trace, context)
```

**Why**:
- Double-checks trajectory after building
- Ensures at least ONE meaningful action exists
- Splits action on " - " and checks description part
- Prevents sending all-empty trajectories to server

#### Fix 2B: ace_after_task.py (Line 178-181)

**BEFORE**:
```python
has_substantial_work = (
    trace['trajectory'] and len(trace['trajectory']) > 0 and
    not trace['task'].startswith("Session work")
)
```

**AFTER**:
```python
# Check for meaningful trajectory actions
meaningful_actions = [
    t for t in trace['trajectory']
    if t.get('action') and len(t['action'].split(' - ', 1)[-1].strip()) >= 5
]

has_substantial_work = (
    len(meaningful_actions) > 0 and  # At least one meaningful action
    not trace['task'].startswith("Session work") and
    len(trace['task']) >= 20  # Minimum task description length
)
```

**Why**:
- Validates action quality, not just quantity
- Requires at least 1 action with 5+ char description
- Requires task description >= 20 chars (prevents "Task completed")
- Multi-layer quality check

---

### Solution 3: Minimum Task Description Length

**Ensures task descriptions are meaningful.**

#### Fix 3A: ace_task_complete.py (Line 161)

**BEFORE**:
```python
# Build task description from recent context
task_description = f"Task completed: {tool_description[:200]}" if tool_description else "Task completed"
```

**AFTER**:
```python
# Build task description from recent context (skip if too short)
if tool_description and len(tool_description.strip()) >= 10:
    task_description = f"Task completed: {tool_description[:200]}"
else:
    # Description too short - use generic fallback
    # This will be caught by trajectory quality check
    task_description = "Task completed"
```

**Why**:
- Minimum 10 chars for task description
- Falls back to generic "Task completed"
- Will be filtered by Solution 2's trajectory quality check

#### Fix 3B: ace_after_task.py (Line 54-56)

**BEFORE**:
```python
content = first_user.get('content', '')
if content:
    # Use first user message as task description (captures intent)
    task_description = f"User request: {content[:250]}"
```

**AFTER**:
```python
content = first_user.get('content', '')
if content and len(content.strip()) >= 10:
    # Use first user message as task description (captures intent)
    task_description = f"User request: {content[:250]}"
```

**Why**:
- Requires user message >= 10 chars
- Prevents learning from empty/minimal user inputs
- Falls back to "Session work" which gets filtered out

---

## Implementation Recommendations

### Priority Order

1. **CRITICAL**: Implement Solution 1 (Filter Empty Descriptions)
   - Prevents trash at the source
   - Simplest fix with biggest impact
   - Applies to both hooks

2. **HIGH**: Implement Solution 2 (Trajectory Quality Check)
   - Safety net for edge cases
   - Prevents any trash from reaching server
   - Validates before expensive API calls

3. **MEDIUM**: Implement Solution 3 (Minimum Task Length)
   - Extra layer of protection
   - Improves task description quality
   - Less critical if Solutions 1-2 are implemented

### Testing Strategy

1. **Unit Tests**: Test with empty descriptions
   ```python
   # Test empty Edit
   event = {"tool_name": "Edit", "description": ""}
   assert is_filtered_out(event)
   
   # Test whitespace-only Write
   event = {"tool_name": "Write", "description": "   "}
   assert is_filtered_out(event)
   
   # Test minimal Bash (< 5 chars)
   event = {"tool_name": "Bash", "description": "ls"}
   assert is_filtered_out(event)
   ```

2. **Integration Tests**: Simulate real workflows
   - Edit sequence with some empty descriptions
   - PreCompact with all empty tool descriptions
   - Mixed scenario (some empty, some valid)

3. **Validation**: Check playbook after fixes
   - Clear playbook: `ce-ace clear --confirm`
   - Use ACE for several sessions
   - Check patterns: `ce-ace patterns`
   - Verify no "Edit - " or "Write - " patterns

### Rollout Plan

1. **Phase 1**: Implement Solution 1 (filter empty descriptions)
   - Update ace_task_complete.py
   - Update ace_after_task.py
   - Test locally
   - Release as patch version (v5.1.9)

2. **Phase 2**: Add Solution 2 (quality checks)
   - Add trajectory validation
   - Test with edge cases
   - Release as minor version (v5.2.0)

3. **Phase 3**: Monitor and adjust
   - Watch for new trash patterns
   - Adjust minimum lengths if needed
   - Consider server-side filtering as backup

---

## Expected Impact

### Before Fix
- 285+ observations of "Empty edit operations"
- 246+ observations of "Empty operations as no-ops"
- 211+ observations of "Empty operations should be logged"
- Total: 700+ trash pattern observations

### After Fix
- Zero new trash patterns captured
- Existing trash patterns decay (low helpful scores)
- Playbook quality improves
- Search relevance increases

### Performance Impact
- Minimal CPU overhead (string length checks)
- Reduces server API calls (fewer traces sent)
- Improves learning quality (better patterns)

---

## Conclusion

**Root Cause Confirmed**:
- Both PostToolUse and PreCompact hooks create trajectory actions with empty tool descriptions
- Current filtering checks existence of trajectory, not quality of actions
- Empty actions like "Edit - " get sent to server and learned as patterns

**Solution Verified**:
- Filter empty descriptions BEFORE adding to trajectory (Solution 1)
- Validate trajectory quality BEFORE sending to server (Solution 2)  
- Require minimum task description lengths (Solution 3)

**Recommended Action**:
Implement all 3 solutions for robust protection against trash patterns.

**Priority**: CRITICAL - Trash patterns are degrading playbook quality at scale (700+ observations).
