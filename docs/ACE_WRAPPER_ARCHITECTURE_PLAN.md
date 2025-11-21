# ACE Plugin Wrapper Architecture - Implementation Plan

## 📋 Executive Summary

**Problem**: Current ACE hook implementation uses prompt-based evaluation but lacks visibility into when hooks fire, what data they receive, and why decisions are made.

**Solution**: Implement comprehensive wrapper architecture (inspired by cc-boilerplate-v2) that logs ALL hook events to local JSON files, enabling data-driven debugging and optimization.

**Impact**:
- ✅ Full visibility into hook execution (no more guessing)
- ✅ Data-driven hook optimization (analyze real patterns)
- ✅ Easy debugging (just read JSON logs)
- ✅ Optional observability integration (cc-observability compatible)

---

## 🎯 Goals

### Primary Goals
1. **Complete Event Logging** - Log every hook invocation with full context
2. **Diagnostic Transparency** - Make hook behavior observable and debuggable
3. **Data-Driven Optimization** - Capture metrics to improve hook logic
4. **Maintainability** - Clean separation of concerns (wrapper → logger → hook logic)

### Secondary Goals
5. **Observability Integration** - Optional integration with external monitoring
6. **Performance Monitoring** - Track hook execution times
7. **Error Tracking** - Capture and log hook failures

---

## 🏗️ Architecture Design

### Current Architecture (v5.1.13)
```
hooks.json
├── Stop: prompt hook (Haiku) → ace_after_task_wrapper.sh → ace_after_task.py
├── PreCompact: command → ace_after_task_wrapper.sh → ace_after_task.py
└── UserPromptSubmit: command → ace_before_task_wrapper.sh → (retrieval logic)

Problems:
❌ No visibility into when hooks fire
❌ No logging of hook input/output
❌ Prompt hook evaluation is opaque
❌ Can't debug why hooks don't fire
❌ No performance metrics
```

### Proposed Architecture
```
hooks.json
├── Stop:
│   ├── 1. ace_stop_wrapper.sh --log --chat
│   │   → Logs ALL events to .claude/data/logs/ace-stop.jsonl
│   │   → Forwards to ace_after_task.py
│   │   → ace_after_task.py: parse transcript → extract trajectory → decide → ce-ace learn
│   │   → Logs result (learning_captured, pattern_count, etc.)
│   │
│   └── 2. (Optional) send_event_wrapper.sh --event-type Stop
│       → Send to observability server
│
├── PreCompact:
│   ├── 1. ace_precompact_wrapper.sh --log --backup
│   │   → Logs to .claude/data/logs/ace-precompact.jsonl
│   │   → Forwards to ace_after_task.py
│   │
│   └── 2. (Optional) send_event_wrapper.sh --event-type PreCompact
│
├── UserPromptSubmit:
│   ├── 1. ace_prompt_submit_wrapper.sh --log
│   │   → Logs to .claude/data/logs/ace-prompt-submit.jsonl
│   │   → Forwards to ace_before_task.py
│   │
│   └── 2. (Optional) send_event_wrapper.sh --event-type UserPromptSubmit
│
└── SubagentStop: (NEW)
    └── ace_subagent_stop_wrapper.sh --log --notify

Benefits:
✅ Every hook invocation logged with timestamp (even if no learning captured)
✅ Full event data captured (session_id, transcript_path, trajectory, etc.)
✅ Easy to analyze: cat .claude/data/logs/ace-stop.jsonl | jq
✅ Performance metrics (execution time per hook)
✅ Error tracking (failures logged with stack traces)
✅ Observability integration (optional)
✅ LLM evaluation INSIDE Python (more control, cheaper, easier to debug)
✅ No prompt hooks needed (simpler architecture)
```

---

## 📁 File Structure

```
plugins/ace/
├── hooks/
│   └── hooks.json                          # Updated with wrapper calls
│
├── scripts/
│   ├── ace_stop_wrapper.sh                 # NEW: Stop event wrapper
│   ├── ace_precompact_wrapper.sh           # NEW: PreCompact wrapper
│   ├── ace_prompt_submit_wrapper.sh        # NEW: UserPromptSubmit wrapper
│   ├── ace_subagent_stop_wrapper.sh        # NEW: SubagentStop wrapper
│   │
│   ├── ace_after_task_wrapper.sh           # EXISTS: Keep as-is
│   ├── ace_before_task_wrapper.sh          # EXISTS: Keep as-is
│   └── ace_permission_request_wrapper.sh   # EXISTS: Keep as-is
│
├── docs/
│   ├── ACE_WRAPPER_ARCHITECTURE_PLAN.md    # THIS FILE
│   ├── ACE_LOG_FORMAT_SPEC.md              # NEW: Log format documentation
│   └── ACE_DEBUGGING_GUIDE.md              # NEW: How to debug with logs
│
└── .claude/data/logs/                      # NEW: Log directory (gitignored)
    ├── ace-stop.jsonl                      # Stop hook events
    ├── ace-precompact.jsonl                # PreCompact hook events
    ├── ace-prompt-submit.jsonl             # UserPromptSubmit events
    ├── ace-subagent-stop.jsonl             # SubagentStop events
    └── ace-errors.jsonl                    # All hook errors

shared-hooks/
├── ace_event_logger.py                     # NEW: Core logging utility
├── ace_after_task.py                       # EXISTS: Keep logic, add logging
└── utils/
    ├── log_analyzer.py                     # NEW: Analyze logs, generate reports
    └── performance_tracker.py              # NEW: Hook performance metrics
```

---

## 🔧 Implementation Details

### Phase 1: Logging Infrastructure (Priority: HIGH)

#### 1.1 Create ace_event_logger.py
```python
# shared-hooks/ace_event_logger.py
"""
Core logging utility for ACE hooks.
Logs all hook events to .claude/data/logs/ in JSONL format.
"""

Features:
- Log hook events with full context (timestamp, session_id, event type)
- Performance tracking (execution time)
- Error tracking (exceptions, stack traces)
- Rotating logs (max 100MB per file, keep last 10 files)
- JSON schema validation
- Thread-safe writes

API:
  log_event(event_type, event_data, metadata={})
  log_error(event_type, error, context={})
  get_log_path(event_type) -> Path
```

#### 1.2 Create Log Directory Structure
```bash
mkdir -p .claude/data/logs
echo "*.jsonl" >> .claude/data/.gitignore
echo "*.json" >> .claude/data/.gitignore
```

#### 1.3 Define Log Format Specification
```json
{
  "timestamp": "2025-11-21T17:30:00.123Z",
  "event_type": "Stop",
  "session_id": "32f80199-6ad2-4315-b5c0-3baab9922d25",
  "hook_name": "ace_stop_wrapper.sh",
  "execution_time_ms": 245,
  "input_data": {
    "session_id": "...",
    "transcript_path": "~/.claude/projects/.../session.jsonl",
    "permission_mode": "default"
  },
  "output_data": {
    "learning_captured": true,
    "pattern_count": 3,
    "ce_ace_exit_code": 0
  },
  "metadata": {
    "claude_version": "2.0.49",
    "plugin_version": "5.1.13",
    "model": "claude-sonnet-4-5-20250929"
  },
  "error": null
}
```

---

### Phase 2: Wrapper Scripts (Priority: HIGH)

#### 2.1 ace_stop_wrapper.sh
```bash
#!/usr/bin/env bash
# ace_stop_wrapper.sh - Stop hook with comprehensive logging
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LOGGER="${MARKETPLACE_ROOT}/shared-hooks/ace_event_logger.py"

# Parse arguments
ENABLE_LOG=false
ENABLE_CHAT=false
ENABLE_NOTIFY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --log) ENABLE_LOG=true; shift ;;
    --chat) ENABLE_CHAT=true; shift ;;
    --notify) ENABLE_NOTIFY=true; shift ;;
    *) shift ;;
  esac
done

# Read stdin and log
INPUT_JSON=$(cat)

# Log event start
if [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$INPUT_JSON" | uv run "$LOGGER" --event-type Stop --phase start
fi

# Forward to ace_after_task.py
RESULT=$(echo "$INPUT_JSON" | uv run "${MARKETPLACE_ROOT}/shared-hooks/ace_after_task.py")
EXIT_CODE=$?

# Log event end with result
if [[ "$ENABLE_LOG" == "true" ]]; then
  echo "$RESULT" | uv run "$LOGGER" --event-type Stop --phase end --exit-code $EXIT_CODE
fi

# Optional: Save chat transcript
if [[ "$ENABLE_CHAT" == "true" ]]; then
  # Copy transcript to .claude/data/logs/chat.json
  TRANSCRIPT_PATH=$(echo "$INPUT_JSON" | jq -r '.transcript_path // empty')
  if [[ -n "$TRANSCRIPT_PATH" ]]; then
    cp "$TRANSCRIPT_PATH" ".claude/data/logs/ace-chat-$(date +%Y%m%d-%H%M%S).json"
  fi
fi

echo "$RESULT"
exit $EXIT_CODE
```

#### 2.2 ace_precompact_wrapper.sh
```bash
#!/usr/bin/env bash
# ace_precompact_wrapper.sh - PreCompact hook with logging
# (Similar structure to ace_stop_wrapper.sh)
```

#### 2.3 ace_prompt_submit_wrapper.sh
```bash
#!/usr/bin/env bash
# ace_prompt_submit_wrapper.sh - UserPromptSubmit with logging
# (Similar structure)
```

---

### Phase 3: Diagnostic Tools (Priority: MEDIUM)

#### 3.1 log_analyzer.py
```python
# shared-hooks/utils/log_analyzer.py
"""
Analyze ACE hook logs and generate reports.

Usage:
  uv run log_analyzer.py --event-type Stop --last 24h
  uv run log_analyzer.py --session-id abc123 --format table
  uv run log_analyzer.py --errors-only
"""

Features:
- Filter logs by event type, session, time range
- Calculate hook frequency and timing statistics
- Identify patterns (when hooks fire, when they don't)
- Generate reports (markdown, JSON, table)
- Export to CSV for analysis
```

#### 3.2 Quick Diagnostic Commands
```bash
# View last 10 Stop hook events
tail -10 .claude/data/logs/ace-stop.jsonl | jq

# Count hooks by type today
find .claude/data/logs -name "*.jsonl" -mtime -1 | \
  xargs grep -h "event_type" | jq -r .event_type | sort | uniq -c

# Average execution time for Stop hooks
jq -r '.execution_time_ms' .claude/data/logs/ace-stop.jsonl | \
  awk '{sum+=$1; count++} END {print sum/count " ms"}'

# Find all errors in last hour
find .claude/data/logs -name "*.jsonl" -mmin -60 | \
  xargs grep -h '"error"' | jq 'select(.error != null)'

# Show Stop hook fire rate (last 100 events)
tail -100 .claude/data/logs/ace-stop.jsonl | \
  jq -r '.output_data.learning_captured' | \
  awk '{if($1=="true") yes++; total++} END {print yes/total*100 "%"}'
```

---

### Phase 4: Observability Integration (Priority: LOW)

#### 4.1 send_event_wrapper.sh (Optional)
```bash
# plugins/ace/scripts/send_event_wrapper.sh
# Send ACE hook events to external observability server
# Compatible with cc-observability architecture

exec uv run "${MARKETPLACE_ROOT}/shared-hooks/send_event.py" \
  --source-app "ace-plugin" \
  --server-url "${OBSERVABILITY_URL:-http://localhost:4000/events}" \
  "$@"
```

#### 4.2 Update hooks.json
```json
{
  "Stop": [
    {
      "matcher": "",
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/scripts/ace_stop_wrapper.sh --log --chat"
        },
        {
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/scripts/send_event_wrapper.sh --event-type Stop",
          "optional": true
        }
      ]
    }
  ]
}
```

---

## 📊 Success Metrics

### Technical Metrics
1. **Hook Fire Rate**: % of sessions where Stop hook fires (target: 40-60%)
2. **Hook Latency**: Average execution time per hook (target: <500ms for Stop)
3. **Error Rate**: % of hook executions that fail (target: <1%)
4. **Log Coverage**: % of hook events captured in logs (target: 100%)

### Operational Metrics
5. **Debug Time**: Time to diagnose hook issues (target: <5 min with logs)
6. **Log Size**: Disk space used by logs (target: <100MB/month with rotation)
7. **False Positives**: % of learning captures that are noise (target: <10%)

---

## 🚀 Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Create `ace_event_logger.py` with core logging
- [ ] Define log format specification
- [ ] Create `.claude/data/logs/` directory structure
- [ ] Implement basic log rotation

### Phase 2: Wrappers (Week 1-2)
- [ ] Implement `ace_stop_wrapper.sh`
- [ ] Implement `ace_precompact_wrapper.sh`
- [ ] Implement `ace_prompt_submit_wrapper.sh`
- [ ] Update `hooks.json` to use wrappers
- [ ] Test all wrappers with real scenarios

### Phase 3: Diagnostics (Week 2)
- [ ] Create `log_analyzer.py` with basic reports
- [ ] Add performance tracking
- [ ] Create debugging guide documentation
- [ ] Test with 10+ real sessions

### Phase 4: Optimization (Week 3)
- [ ] Analyze collected data
- [ ] Optimize hook logic based on patterns
- [ ] Add observability integration (optional)
- [ ] Performance tuning

---

## 🧪 Testing Strategy

### Unit Tests
- Test log writing (valid JSON, proper format)
- Test log rotation (max size, file count)
- Test error handling (malformed input, missing files)

### Integration Tests
- Test wrapper → logger → hook chain
- Test with real Claude Code sessions
- Test with various event types (Stop, PreCompact, etc.)

### Scenarios to Test
1. **Short session** (12 tool uses) - PreCompact doesn't fire, Stop does
2. **Long session** (100+ tool uses) - Both PreCompact and Stop fire
3. **Error scenario** - Hook fails, error logged correctly
4. **High frequency** - Multiple hooks in quick succession
5. **Prompt hook evaluation** - Haiku returns false, wrapper still logs

---

## 📝 Documentation Deliverables

1. **ACE_LOG_FORMAT_SPEC.md** - JSON schema, field definitions, examples
2. **ACE_DEBUGGING_GUIDE.md** - How to use logs to debug issues
3. **ACE_WRAPPER_ARCHITECTURE.md** - Architecture overview, design decisions
4. **CHANGELOG.md** - Update with v5.2.0 wrapper architecture changes

---

## 🔄 Migration Plan

### v5.1.13 → v5.2.0 (Wrapper Architecture)

**Breaking Changes**: None (additive changes only)

**Steps**:
1. Add new wrapper scripts (doesn't affect existing hooks)
2. Update `hooks.json` to call wrappers first, then existing logic
3. Test in development environment
4. Deploy to production with feature flag (optional)
5. Monitor logs for 1 week
6. Analyze data and optimize

**Rollback**: Remove wrapper calls from `hooks.json`, revert to v5.1.13

---

## 💡 Future Enhancements

### v5.3.0+
- **Real-time dashboard** - Web UI showing hook activity
- **Anomaly detection** - ML-based detection of unusual patterns
- **Smart sampling** - Log only interesting events (configurable)
- **Compression** - Compress old logs (gzip)
- **Cloud sync** - Optional sync to S3/GCS for team-wide analysis

---

## ❓ Open Questions

1. **Log retention**: How long to keep logs? (Proposal: 30 days)
2. **Observability default**: Enable by default or opt-in? (Proposal: opt-in)
3. **Performance impact**: Acceptable latency for logging? (Proposal: <50ms)
4. **Privacy**: What data is sensitive and should be redacted? (Proposal: API keys, secrets)

---

## 📚 References

- **Boilerplate**: `/Users/ptsafaridis/Downloads/cc-boilerplate-v2-main`
- **Current ACE**: `plugins/ace/hooks/hooks.json`
- **Research Paper**: ACE: Agentic Context Engineering (arXiv:2510.04618v1)
- **Claude Code Hooks**: https://docs.claude.com/hooks

---

**Next Steps**: Review plan → Approve → Start Phase 1 implementation

**Estimated Timeline**: 3 weeks (Part-time) | 1 week (Full-time)

**Risk Level**: Low (additive changes, easy rollback)
