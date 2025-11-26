# Stop Hook Test Scenario

## Purpose
Test the new prompt-based Stop hook with Haiku evaluation in ACE v5.1.13.

## Test Task
Create a simple utility function with a clear learning pattern.

**Task**: Implement a `debounce` function in TypeScript

**Requirements**:
- Function should delay execution until after wait time has elapsed
- If called again before wait time, reset the timer
- Return a debounced version of the original function
- Include TypeScript types

**Expected Learning Capture**:
- **Pattern**: Debounce implementation using closure and setTimeout
- **Gotcha**: TypeScript typing for generic function parameters
- **Decision**: Why debounce over throttle for specific use cases

## Verification Steps

After implementing the debounce function:

1. **Check debug log**:
   ```bash
   cat /tmp/ace_hook_debug.log
   ```
   Should show:
   - `"hook_event_name": "Stop"`
   - Haiku evaluation response with `has_learning: true`
   - `learning_type: "implementation"`

2. **Check ACE status**:
   ```bash
   ce-ace status
   ```
   Pattern count should increment by 1

3. **Search for pattern**:
   ```bash
   ce-ace search "debounce"
   ```
   Should return the newly captured pattern

## Success Criteria
- ✅ Stop hook fires with prompt evaluation
- ✅ Haiku returns `has_learning: true`
- ✅ `ace_after_task_wrapper.sh` executes
- ✅ Pattern captured in playbook
- ✅ Pattern searchable via `ce-ace search`
