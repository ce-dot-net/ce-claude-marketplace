# ACE Trajectory Extraction Flow

## Overview

This document explains how trajectory extraction works in the wrapper architecture.

---

## Complete Flow Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│ CLAUDE CODE: Stop Event                                           │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Event fires when:                                                  │
│ 1. User stops conversation without tool use                       │
│ 2. Session ends naturally                                         │
│                                                                    │
│ Event data (via stdin):                                           │
│ {                                                                  │
│   "hook_event_name": "Stop",                                      │
│   "session_id": "32f80199-...",                                   │
│   "transcript_path": "~/.claude/projects/.../session.jsonl",     │
│   "permission_mode": "default"                                    │
│ }                                                                  │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ WRAPPER: ace_stop_wrapper.sh --log --chat                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Responsibilities:                                                  │
│ 1. Log event START (timestamp, input data)                        │
│ 2. Forward to ace_after_task.py (via stdin)                       │
│ 3. Wait for result                                                │
│ 4. Log event END (timestamp, output data, execution time)         │
│ 5. Optionally save chat transcript (--chat flag)                  │
│                                                                    │
│ Log entry (START):                                                │
│ {                                                                  │
│   "timestamp": "2025-11-21T18:00:00.000Z",                        │
│   "event_type": "Stop",                                           │
│   "phase": "start",                                               │
│   "session_id": "32f80199-...",                                   │
│   "input_data": { ... }                                           │
│ }                                                                  │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ PYTHON: ace_after_task.py                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                    │
│ STEP 1: Read transcript                                           │
│ ─────────────────────────────────────────────────────────────────│
│   transcript_path = event['transcript_path']                      │
│   messages = parse_transcript(transcript_path)                    │
│                                                                    │
│   Returns:                                                        │
│   [                                                               │
│     {"role": "user", "content": "Create debounce utility"},      │
│     {"role": "assistant", "tool_uses": [...]},                   │
│     {"role": "user", "tool_results": [...]}                      │
│   ]                                                               │
│                                                                    │
│ STEP 2: Extract trajectory                                        │
│ ─────────────────────────────────────────────────────────────────│
│   trajectory = extract_trajectory(messages)                       │
│                                                                    │
│   Returns:                                                        │
│   {                                                               │
│     "task": "Implement debounce utility function",               │
│     "steps": [                                                    │
│       "Created src/utils/debounce.ts",                           │
│       "Implemented debounce with closure pattern",               │
│       "Added cancel() and flush() methods",                      │
│       "Documented why debounce > throttle"                       │
│     ],                                                            │
│     "decisions": [                                               │
│       "Chose debounce over throttle for user input scenarios"    │
│     ],                                                            │
│     "gotchas": [                                                 │
│       "TypeScript generics preserve function signature"          │
│     ],                                                            │
│     "tool_use_count": 12,                                        │
│     "file_changes": ["src/utils/debounce.ts"]                   │
│   }                                                               │
│                                                                    │
│ STEP 3: Evaluate if substantial (3 OPTIONS)                       │
│ ─────────────────────────────────────────────────────────────────│
│                                                                    │
│   OPTION A: Simple Heuristic (Fast, Free, Deterministic)         │
│   ────────────────────────────────────────────────────────────   │
│   is_substantial = (                                              │
│     len(trajectory['steps']) >= 3 AND                            │
│     len(trajectory['tool_use_count']) >= 5 AND                   │
│     task_description not in TRIVIAL_TASKS                        │
│   )                                                               │
│                                                                    │
│   OPTION B: LLM Evaluation (Smart, $0.0001, Semantic)            │
│   ────────────────────────────────────────────────────────────   │
│   prompt = f"""                                                   │
│   Does this trajectory contain substantial technical learning?   │
│                                                                    │
│   Task: {trajectory['task']}                                     │
│   Steps: {trajectory['steps']}                                   │
│   Decisions: {trajectory['decisions']}                           │
│   Gotchas: {trajectory['gotchas']}                               │
│                                                                    │
│   Return JSON: {{"has_learning": bool, "reason": string}}        │
│   """                                                             │
│                                                                    │
│   response = haiku.generate(prompt)  # Via Anthropic SDK         │
│   is_substantial = response['has_learning']                      │
│                                                                    │
│   OPTION C: Always Capture (Let Server Filter)                   │
│   ────────────────────────────────────────────────────────────   │
│   is_substantial = True  # Capture everything, let Curator filter│
│                                                                    │
│ STEP 4: Capture learning (if substantial)                        │
│ ─────────────────────────────────────────────────────────────────│
│   if is_substantial:                                              │
│     result = subprocess.run([                                     │
│       "ce-ace", "learn",                                          │
│       "--task", trajectory['task'],                               │
│       "--trajectory", json.dumps(trajectory['steps']),            │
│       "--feedback", json.dumps({                                  │
│         "decisions": trajectory['decisions'],                     │
│         "gotchas": trajectory['gotchas']                          │
│       }),                                                          │
│       "--success", "true"                                         │
│     ])                                                             │
│                                                                    │
│     return {                                                      │
│       "learning_captured": True,                                 │
│       "pattern_count": 3,  # From ce-ace output                 │
│       "ce_ace_exit_code": result.returncode                      │
│     }                                                             │
│   else:                                                           │
│     return {                                                      │
│       "learning_captured": False,                                │
│       "reason": "Trajectory too simple (< 3 steps)"              │
│     }                                                             │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ WRAPPER: ace_stop_wrapper.sh (continued)                          │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                    │
│ Log entry (END):                                                  │
│ {                                                                  │
│   "timestamp": "2025-11-21T18:00:00.245Z",                        │
│   "event_type": "Stop",                                           │
│   "phase": "end",                                                 │
│   "session_id": "32f80199-...",                                   │
│   "execution_time_ms": 245,                                       │
│   "trajectory_summary": {                                         │
│     "task": "Implement debounce utility",                         │
│     "steps": 4,                                                   │
│     "tool_uses": 12,                                              │
│     "files_changed": 1                                            │
│   },                                                              │
│   "output_data": {                                                │
│     "learning_captured": true,                                    │
│     "pattern_count": 3,                                           │
│     "evaluation_method": "heuristic",                             │
│     "ce_ace_exit_code": 0                                         │
│   },                                                              │
│   "error": null                                                   │
│ }                                                                  │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ RESULT: .claude/data/logs/ace-stop.jsonl                          │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                    │
│ Complete log entry with both START and END data                   │
│ Can be analyzed with: jq, grep, awk, custom Python scripts       │
└────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Where Does Trajectory Extraction Happen?

**Answer**: In Python (`ace_after_task.py`), NOT in the wrapper.

**Why**:
- Transcript parsing requires reading .jsonl files
- Python has better JSON handling than bash
- Trajectory logic is complex (needs structured extraction)
- Wrapper stays simple (just log input/output)

### 2. Where Does LLM Evaluation Happen?

**Answer**: In Python (`ace_after_task.py`), NOT as a prompt hook.

**Why**:
- More control (can choose Haiku, Sonnet, or heuristic)
- Cheaper (no separate Hook API call overhead)
- Easier to debug (all logic in one place)
- Can log evaluation reasoning
- Can fallback to heuristic if LLM fails

### 3. What Gets Logged?

**Answer**: EVERYTHING - even if learning is NOT captured.

**Why**:
- See when hooks fire (even if they don't capture)
- Understand false negatives (should have captured, didn't)
- Debug trajectory extraction issues
- Calculate fire rate metrics (captured / total)

### 4. Prompt Hook vs Command Hook?

**Answer**: Use simple command hook, do evaluation in Python.

**Why Prompt Hook BAD**:
- ❌ Separate LLM call (adds latency)
- ❌ Less control (can't fallback to heuristic)
- ❌ Harder to debug (evaluation happens outside logs)
- ❌ Can't access trajectory (only raw transcript)

**Why Command Hook + Python Evaluation GOOD**:
- ✅ One execution path (wrapper → Python → ce-ace)
- ✅ Full control (choose evaluation method)
- ✅ Everything logged (input, trajectory, evaluation, output)
- ✅ Easy to test (just call Python script)

---

## Evaluation Methods Comparison

| Method | Speed | Cost | Accuracy | Debug | Recommendation |
|--------|-------|------|----------|-------|----------------|
| **Heuristic** | 1ms | Free | 80% | Easy | ✅ **Start with this** |
| **Haiku LLM** | 500ms | $0.0001 | 95% | Medium | Consider after testing |
| **Always Capture** | 1ms | Free | N/A | Easy | Good for bootstrapping |

### Recommended Strategy:

1. **Phase 1**: Use simple heuristic (fast, free, good enough)
   ```python
   is_substantial = (
       len(steps) >= 3 and
       tool_uses >= 5 and
       task not in ["greeting", "simple question"]
   )
   ```

2. **Phase 2**: Analyze logs, tune heuristic based on false positives/negatives

3. **Phase 3**: Add optional LLM evaluation if heuristic insufficient
   ```python
   if ENABLE_LLM_EVAL:
       is_substantial = haiku_evaluate(trajectory)
   else:
       is_substantial = heuristic_evaluate(trajectory)
   ```

---

## Trajectory Schema

```typescript
interface Trajectory {
  task: string;              // High-level description
  steps: string[];           // Sequential actions taken
  decisions: string[];       // "Why X over Y" explanations
  gotchas: string[];         // Edge cases, pitfalls discovered
  tool_use_count: number;    // Total tool invocations
  file_changes: string[];    // Files created/modified
  error_count: number;       // Errors encountered
  duration_seconds: number;  // Time from start to end
}
```

---

## Example Log Analysis

### Query: Find all Stop hooks that didn't capture learning
```bash
cat .claude/data/logs/ace-stop.jsonl | \
  jq 'select(.output_data.learning_captured == false)'
```

### Query: Calculate capture rate (last 100 hooks)
```bash
tail -100 .claude/data/logs/ace-stop.jsonl | \
  jq -r '.output_data.learning_captured' | \
  awk '{if($1=="true") yes++; total++} END {print yes/total*100 "%"}'
```

### Query: Show trajectory summaries for captured learning
```bash
cat .claude/data/logs/ace-stop.jsonl | \
  jq 'select(.output_data.learning_captured == true) | .trajectory_summary'
```

### Query: Find hooks that took > 1 second
```bash
cat .claude/data/logs/ace-stop.jsonl | \
  jq 'select(.execution_time_ms > 1000)'
```

---

## FAQ

**Q: Why not use the prompt hook with Haiku like in v5.1.13?**

A: Prompt hooks are opaque - you can't see why they made a decision. With Python evaluation + logging, you get full visibility. Plus it's cheaper and more flexible.

**Q: What if trajectory extraction fails?**

A: Wrapper logs the error, trajectory is empty, and learning is not captured. You can see the error in logs and fix the extraction logic.

**Q: Can I disable evaluation and capture everything?**

A: Yes! Set `ALWAYS_CAPTURE=true` in config. Useful for bootstrapping playbook with lots of data.

**Q: How do I know if the heuristic is working well?**

A: Analyze logs:
1. Calculate capture rate (should be 40-60%)
2. Sample 20 captured events → check if substantial
3. Sample 20 non-captured events → check for false negatives
4. Tune heuristic thresholds based on findings

---

**Next**: Implement `ace_stop_wrapper.sh` + update `ace_after_task.py` with logging
