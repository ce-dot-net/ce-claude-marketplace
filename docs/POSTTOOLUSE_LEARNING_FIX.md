# PostToolUse Learning Capture Fix

## Problem

The ACE plugin had a critical gap in its learning capture architecture:

### Before (BROKEN)

1. **PostToolUse** (`ace_task_complete.py`):
   - ✅ **Detected** when substantial work was complete (edit sequences, Task tool, git commits)
   - ❌ **Did NOTHING** - just silent exit
   - Comment said: "Actual learning happens via PreCompact/Stop"

2. **PreCompact** (`ace_after_task.py`):
   - ❌ Might **never fire** if no compaction happens
   - Unreliable timing

3. **Stop** (`ace_after_task.py`):
   - ❌ Only fires when **session ends** (too late!)
   - Loses context by the time it runs

**Result**: Learning was often **never captured** because:
- PreCompact doesn't fire if task completes before compaction
- Stop only fires when user quits (loses context)
- PostToolUse detected work but didn't capture it

## Solution

Make **PostToolUse hook actually capture learning** when it detects substantial work!

### After (FIXED)

**PostToolUse** (`ace_task_complete.py`):
- ✅ **Detects** substantial work completion
- ✅ **Captures learning immediately** via `ce-ace learn --stdin`
- ✅ **Shows user feedback** with learning statistics (v1.0.13+)
- ✅ **No waiting** for PreCompact (which might never come!)

## Changes Made

### File: `shared-hooks/ace_task_complete.py`

**Added**:

1. **`build_execution_trace_from_posttooluse(event)`** (lines 148-193)
   - Builds ExecutionTrace from PostToolUse event
   - Uses accumulated edit sequence state
   - Creates trajectory from edit count

2. **`capture_learning(trace, context)`** (lines 196-229)
   - Calls `ce-ace learn --stdin --json`
   - Returns learning statistics if available
   - Handles errors gracefully

3. **Updated `main()`** (lines 232-286)
   - Builds ExecutionTrace when substantial work detected
   - Captures learning immediately
   - Shows user feedback with statistics:
     ```
     ✅ [ACE] Task complete - Learning captured!

     📚 ACE Learning:
        • 1 new pattern
        • Quality: 90%
     ```

**Removed**:
- Silent exit (lines 170-171)
- "Tracking for future learning" comment (misleading - we now capture immediately!)

## Test Results

```bash
$ python3 /tmp/test_posttooluse_learning.py

Test Scenario:
  - 3 files edited (Edit sequence)
  - Now using Read tool (sequence ends)
  - Should trigger: Learning capture!

✅ SUCCESS: PostToolUse hook captured learning!
   - Edit sequence detected (3 files)
   - Learning submitted to server
   - User sees feedback immediately

Output:
✅ [ACE] Task complete - Learning captured!

📚 ACE Learning:
   • 1 new pattern
   • Quality: 90%
```

## Trigger Conditions

PostToolUse now captures learning when:

1. **Edit sequence completes** (2+ edits, then different tool)
   - Example: Edit #1, Edit #2, Edit #3, Read → TRIGGER!

2. **Task tool finishes**
   - Example: Task (subagent) completes → TRIGGER!

3. **Git commit happens**
   - Example: `git commit -m "..."` → TRIGGER!

## User Experience

### Before
```
[User edits 3 files]
[User continues working...]
[Maybe learning captured at session end... maybe not!]
```

### After
```
[User edits 3 files]
[User switches to Read tool]

✅ [ACE] Task complete - Learning captured!

📚 ACE Learning:
   • 1 new pattern
   • Quality: 90%
```

**Immediate feedback** - no waiting, no uncertainty!

## Benefits

1. ✅ **Reliable learning capture** - No dependency on PreCompact timing
2. ✅ **Immediate feedback** - User sees what was learned right away
3. ✅ **Better timing** - Captures learning when work is done, not later
4. ✅ **Context preservation** - Captures while context is fresh
5. ✅ **v1.0.13 integration** - Shows enhanced learning statistics

## Architecture

### Hook Flow (After Fix)

```
Task Completion Detected:
  ↓
PostToolUse (ace_task_complete.py):
  1. Check is_substantial_task() ✅
  2. Build ExecutionTrace from event ✅
  3. Call ce-ace learn --stdin ✅
  4. Show user feedback ✅

PreCompact/Stop (ace_after_task.py):
  - Still exist as backup
  - Capture full conversation context
  - Complement PostToolUse learning
```

### Substantial Work Detection

```python
# Triggers on:
- Task tool completion ✅
- Git commits ✅
- Edit sequence completion (2+ edits, then different tool) ✅

# Skips:
- Single isolated edits ❌
- Trivial operations (Read, Grep without prior work) ❌
- Mid-sequence edits (during Edit → Edit → Edit) ❌
```

## Backward Compatibility

- ✅ Works with old servers (v3.9.x) - graceful fallback
- ✅ Works with new servers (v3.10.0+) - enhanced statistics
- ✅ No breaking changes
- ✅ PreCompact/Stop still exist as backup

## Related Issues

- Fixes: Learning not captured when task completes before compaction
- Fixes: No user feedback about learning capture
- Enables: Immediate learning visibility (v1.0.13+)

## Testing

**Test Script**: `/tmp/test_posttooluse_learning.py`

**Manual Test**:
1. Edit 2-3 files
2. Use a different tool (Read, Bash, etc.)
3. Should see: "✅ [ACE] Task complete - Learning captured!"

## Version

- **Implemented**: 2025-11-20
- **Plugin Version**: v5.1.8 (targeting)
- **Requires**: ce-ace CLI v1.0.11+ (v1.0.13+ for learning statistics)

## Summary

**Before**: PostToolUse detected work but didn't capture learning (relied on unreliable PreCompact)
**After**: PostToolUse detects AND captures learning immediately (reliable, fast, user-friendly)

**Impact**: Users get immediate feedback on learning, no more missed learning events! 🎯
