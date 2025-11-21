# ACE Wrapper Architecture - Testing Plan

## Overview

Comprehensive testing plan for v5.2.0 wrapper architecture implementation.

---

## Test Environment Setup

### Prerequisites
```bash
# Ensure ce-ace CLI is installed
which ce-ace

# Check Python version
python3 --version  # Should be 3.11+

# Verify uv is available
which uv
```

### Prepare Test Environment
```bash
# Clean any existing logs
rm -rf .claude/data/logs/

# Restart Claude Code to load new hooks
# (Close and reopen Claude Code)
```

---

## Phase 1: Basic Functionality Tests

### Test 1.1: Stop Hook Fires
**Goal**: Verify Stop hook executes when session ends

**Steps**:
1. Open Claude Code in this project
2. Send a simple message: "Hello, test message"
3. Wait for response (no tools used)
4. Check if Stop hook fired

**Expected Result**:
```bash
ls .claude/data/logs/
# Should show: ace-stop.jsonl

cat .claude/data/logs/ace-stop.jsonl | jq
# Should show 2 entries: START and END phase
```

**Success Criteria**:
- ✅ `.claude/data/logs/` directory created automatically
- ✅ `ace-stop.jsonl` file exists
- ✅ Both START and END events logged
- ✅ `execution_time_ms` is a positive number
- ✅ `exit_code` is 0 (success)

---

### Test 1.2: PreCompact Hook Fires
**Goal**: Verify PreCompact hook executes during context compaction

**Steps**:
1. Start a new session
2. Send 50+ tool uses to trigger compaction
3. Check if PreCompact hook fired

**Expected Result**:
```bash
cat .claude/data/logs/ace-precompact.jsonl | jq
# Should show START and END entries
```

**Success Criteria**:
- ✅ `ace-precompact.jsonl` exists
- ✅ Both START and END events logged
- ✅ Backup transcript created (if --backup flag used)
- ✅ `execution_time_ms` < 5000 (under 5 seconds)

---

### Test 1.3: Logs Created Automatically
**Goal**: Verify self-initializing behavior

**Steps**:
1. Delete `.claude/data/logs/` directory
2. Trigger Stop hook (simple message)
3. Check if directory and logs recreated

**Expected Result**:
```bash
# Directory recreated automatically
ls -la .claude/data/
# Should show: logs/

# Log file created automatically
ls .claude/data/logs/
# Should show: ace-stop.jsonl
```

**Success Criteria**:
- ✅ No manual directory creation needed
- ✅ Logs created on first hook execution
- ✅ No errors in stderr

---

## Phase 2: Log Format Tests

### Test 2.1: Log Format Validation
**Goal**: Verify log entries match expected schema

**Expected Schema**:
```json
{
  "timestamp": "2025-11-21T18:00:00.000Z",  // ISO 8601 format
  "event_type": "Stop",                     // Hook type
  "phase": "end",                           // start|end|complete|error
  "event_data": {...},                      // Hook input/output
  "metadata": {
    "plugin_version": "5.2.0",
    "claude_version": "...",
    "model": "..."
  },
  "execution_time_ms": 245,                 // Number
  "exit_code": 0,                           // 0 = success
  "error": null                             // null or string
}
```

**Steps**:
1. Trigger Stop hook
2. Parse log with jq:
```bash
cat .claude/data/logs/ace-stop.jsonl | jq '
  select(.phase == "end") |
  {
    has_timestamp: (.timestamp != null),
    has_execution_time: (.execution_time_ms != null),
    exit_code_valid: (.exit_code == 0 or .exit_code == 1),
    phase_valid: (.phase | IN("start", "end", "complete", "error"))
  }
'
```

**Success Criteria**:
- ✅ All required fields present
- ✅ Timestamp in ISO 8601 format
- ✅ execution_time_ms is a number
- ✅ exit_code is 0 or 1
- ✅ phase is valid enum value

---

### Test 2.2: Chat Transcript Saved
**Goal**: Verify --chat flag saves transcript copy

**Steps**:
1. Trigger Stop hook with --chat flag (already in hooks.json)
2. Check for saved transcript

**Expected Result**:
```bash
ls .claude/data/logs/ace-chat-*.json
# Should show timestamped transcript copy
```

**Success Criteria**:
- ✅ Chat transcript file created
- ✅ Filename includes timestamp (YYYYMMDD-HHMMSS)
- ✅ Content is valid JSON
- ✅ Contains conversation messages

---

## Phase 3: Log Analyzer Tests

### Test 3.1: View Last N Entries
**Goal**: Verify log analyzer can display recent entries

**Command**:
```bash
uv run shared-hooks/utils/ace_log_analyzer.py --event-type Stop --last 10
```

**Expected Output**:
```
📊 Stop Hook Analysis
Total entries: 10

timestamp                | phase | execution_time_ms | exit_code
-------------------------|-------|-------------------|----------
2025-11-21T18:00:00.000Z | end   | 245              | 0
...
```

**Success Criteria**:
- ✅ Table displays correctly
- ✅ Shows last N entries (not all)
- ✅ Columns aligned properly
- ✅ Timestamps sorted chronologically

---

### Test 3.2: Statistics Calculation
**Goal**: Verify stats are calculated correctly

**Command**:
```bash
uv run shared-hooks/utils/ace_log_analyzer.py --event-type Stop --stats
```

**Expected Output**:
```
📊 Stop Hook Analysis
Total entries: 100

Statistics:
  Total Events: 100
  Avg Execution Time: 245.5ms
  Max Execution Time: 1203.0ms
  Success Rate: 98.0%
  Error Rate: 2.0%
```

**Success Criteria**:
- ✅ All statistics calculated
- ✅ Percentages sum to 100%
- ✅ Average is reasonable (100-1000ms)
- ✅ No division by zero errors

---

### Test 3.3: Error Filtering
**Goal**: Verify error-only filter works

**Command**:
```bash
uv run shared-hooks/utils/ace_log_analyzer.py --errors --hours 24
```

**Expected Output**:
```
🔴 Found 3 errors

timestamp                | event_type | error
-------------------------|------------|------
2025-11-21T18:00:00.000Z | Stop       | ce-ace command not found
...
```

**Success Criteria**:
- ✅ Only shows entries with errors
- ✅ Includes all error fields
- ✅ Time filtering works (last N hours)

---

### Test 3.4: CSV Export
**Goal**: Verify CSV export functionality

**Command**:
```bash
uv run shared-hooks/utils/ace_log_analyzer.py \
  --event-type Stop \
  --export test_export.csv
```

**Expected Result**:
```bash
cat test_export.csv | head -2
# Should show: CSV header + first data row
```

**Success Criteria**:
- ✅ CSV file created
- ✅ Header row with all field names
- ✅ Data rows with proper escaping
- ✅ Valid CSV format (parseable by Excel/Numbers)

---

## Phase 4: Integration Tests

### Test 4.1: Existing Logic Preserved
**Goal**: Verify ace_after_task.py still works correctly

**Steps**:
1. Trigger Stop hook with substantial work
2. Check if ce-ace learn was called
3. Verify playbook was updated

**Verification**:
```bash
# Check ce-ace status
ce-ace status
# Pattern count should increase

# Search for new patterns
ce-ace search "your test keyword"
```

**Success Criteria**:
- ✅ ce-ace learn executes
- ✅ Playbook updated with new patterns
- ✅ Pattern count increased
- ✅ Patterns searchable

---

### Test 4.2: Error Handling
**Goal**: Verify errors are logged properly

**Steps**:
1. Temporarily break ce-ace (rename binary)
2. Trigger Stop hook
3. Check error logging

**Expected Result**:
```bash
cat .claude/data/logs/ace-errors.jsonl | jq
# Should show error entry with:
# - error: "ce-ace command not found"
# - context: {...}
```

**Success Criteria**:
- ✅ Error logged to ace-errors.jsonl
- ✅ Error logged to event-specific log
- ✅ Hook doesn't crash Claude Code
- ✅ Error message is descriptive

---

### Test 4.3: Performance Impact
**Goal**: Verify logging doesn't significantly slow down hooks

**Steps**:
1. Trigger 10 Stop hooks
2. Calculate average execution time
3. Compare with baseline (no logging)

**Baseline**: ~200ms (ace_after_task.py execution)
**With Logging**: ~250ms (logging overhead should be < 50ms)

**Success Criteria**:
- ✅ Logging overhead < 50ms
- ✅ No noticeable slowdown
- ✅ Hooks still complete within timeout (30s)

---

## Phase 5: Real-World Scenarios

### Test 5.1: Implement Debounce Utility
**Goal**: Test with substantial implementation task

**Steps**:
1. Implement debounce utility (src/utils/debounce.ts)
2. Complete implementation
3. End session (trigger Stop hook)
4. Verify learning captured

**Expected**:
```bash
# Check logs
cat .claude/data/logs/ace-stop.jsonl | jq '.event_data'

# Should show:
# - task: "Implement debounce utility"
# - trajectory: [...steps...]
# - learning_captured: true
```

**Success Criteria**:
- ✅ Stop hook fired
- ✅ Trajectory extracted
- ✅ Learning captured
- ✅ Pattern added to playbook

---

### Test 5.2: Short Session (No Learning)
**Goal**: Test with trivial session

**Steps**:
1. Send simple greeting: "Hello"
2. End session
3. Verify logged but no learning

**Expected**:
```bash
cat .claude/data/logs/ace-stop.jsonl | jq 'select(.phase == "end") | .event_data'

# Should show:
# - learning_captured: false
# - reason: "Trivial conversation"
```

**Success Criteria**:
- ✅ Hook fired and logged
- ✅ No learning captured (as expected)
- ✅ Reason logged
- ✅ No error

---

### Test 5.3: Long Session with PreCompact
**Goal**: Test both PreCompact and Stop hooks

**Steps**:
1. Start long session (100+ tool uses)
2. Trigger PreCompact (context compaction)
3. Continue working
4. End session (trigger Stop)
5. Verify both hooks logged

**Expected**:
```bash
# Check PreCompact log
cat .claude/data/logs/ace-precompact.jsonl | jq

# Check Stop log
cat .claude/data/logs/ace-stop.jsonl | jq

# Should show:
# - PreCompact fired first (@ ~50-70 tool uses)
# - Stop fired at end
# - Both captured learning
```

**Success Criteria**:
- ✅ PreCompact fired during session
- ✅ Stop fired at end
- ✅ Both logged separately
- ✅ No duplicate learning capture

---

## Test Results Template

### Test Summary

| Test ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| 1.1 | Stop Hook Fires | ⏸️ Pending | |
| 1.2 | PreCompact Hook Fires | ⏸️ Pending | |
| 1.3 | Logs Auto-Created | ⏸️ Pending | |
| 2.1 | Log Format Valid | ⏸️ Pending | |
| 2.2 | Chat Saved | ⏸️ Pending | |
| 3.1 | View Last N | ⏸️ Pending | |
| 3.2 | Statistics | ⏸️ Pending | |
| 3.3 | Error Filter | ⏸️ Pending | |
| 3.4 | CSV Export | ⏸️ Pending | |
| 4.1 | Existing Logic | ⏸️ Pending | |
| 4.2 | Error Handling | ⏸️ Pending | |
| 4.3 | Performance | ⏸️ Pending | |
| 5.1 | Real Implementation | ⏸️ Pending | |
| 5.2 | Trivial Session | ⏸️ Pending | |
| 5.3 | Long Session | ⏸️ Pending | |

**Legend**:
- ⏸️ Pending
- ✅ Pass
- ❌ Fail
- ⚠️ Partial

---

## Quick Test Commands

```bash
# Clean slate
rm -rf .claude/data/logs/ && echo "✅ Logs cleared"

# Trigger test (simple message)
# (Send "test" in Claude Code, wait for response)

# Verify logs created
ls -lah .claude/data/logs/

# View Stop hooks
cat .claude/data/logs/ace-stop.jsonl | jq

# Analyze with tool
uv run shared-hooks/utils/ace_log_analyzer.py --event-type Stop --stats

# Check errors
uv run shared-hooks/utils/ace_log_analyzer.py --errors

# Export to CSV
uv run shared-hooks/utils/ace_log_analyzer.py --event-type Stop --export stop_test.csv
```

---

## Success Criteria Summary

**Critical (Must Pass)**:
- ✅ Logs created automatically (no manual setup)
- ✅ Stop hook fires and logs correctly
- ✅ Log format matches schema
- ✅ Existing ace_after_task.py logic preserved
- ✅ Errors logged without crashing

**Important (Should Pass)**:
- ✅ PreCompact hook fires and logs
- ✅ Log analyzer displays data correctly
- ✅ Statistics calculated accurately
- ✅ CSV export works
- ✅ Performance impact < 50ms

**Nice to Have (Can Fix Later)**:
- Chat transcript saving
- Advanced filtering
- Pretty-printed tables
- Multi-format export

---

**Ready to Execute**: Start with Phase 1 (Basic Functionality Tests)

**Estimated Time**: 30-45 minutes for all phases
