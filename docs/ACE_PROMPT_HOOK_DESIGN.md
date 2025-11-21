# ACE Prompt Hook Design - Research-Aligned Trajectory Filtering

## Problem Statement

**Current Issue**: The Stop hook uses rigid regex-based filtering (line 376-389 of `ace_after_task.py`):

```python
has_substantial_work = (
    trace['trajectory'] and len(trace['trajectory']) > 0 and
    not trace['task'].startswith("Session work")  # ❌ TOO STRICT!
)
```

**Result**: The hook **never fires** because it's too conservative, missing valuable learning.

## Research Paper Guidance

### Core Philosophy (Page 2-3)

> "contexts should function not as concise summaries, but as **comprehensive, evolving playbooks**—detailed, inclusive, and rich with domain insights."

**Key Findings**:
1. **Brevity Bias**: Aggressive filtering drops domain insights (Page 3)
2. **Context Collapse**: Monolithic rewriting causes "sharp performance declines" (Figure 2, Page 3)
3. **Comprehensive > Concise**: LLMs benefit from long, detailed contexts (Page 2)

### ACE's Design Principles (Page 4-5)

✅ **Incremental Delta Updates** - Add insights without aggressive filtering
✅ **Grow-and-Refine** - Accumulate first, prune later via deduplication
✅ **Natural Signals** - Leverage execution feedback and trajectories

### What Should Be Captured (Page 6)

From Section 4.1:
- "execution traces, reasoning steps, or validation results"
- "successes and errors"
- "tool use, and environment interaction"
- "accumulated strategies can be reused across episodes"

## Solution: Prompt-Based Stop Hook

### Architecture

```
Stop Event Fires
    ↓
Haiku LLM Evaluation (intelligent decision)
    ↓
JSON Response: { "has_learning": true/false, "reason": "...", "learning_type": "..." }
    ↓
If has_learning === true → Run ace_after_task_wrapper.sh
If has_learning === false → Skip silently
```

### Benefits

| Approach | Regex (Current) | Prompt Hook (New) |
|----------|----------------|-------------------|
| **Intelligence** | ❌ Rigid keywords | ✅ Semantic understanding |
| **Flexibility** | ❌ Misses edge cases | ✅ Handles nuance |
| **Alignment** | ⚠️ Over-filters (brevity bias) | ✅ Comprehensive (paper-aligned) |
| **Cost** | Free | ~$0.0001 per eval (Haiku) |
| **Latency** | Instant | ~500ms (acceptable for Stop) |

### Prompt Design Principles

**1. Explicit ACE Philosophy**
```
"ACE Framework Philosophy:
- Prefer comprehensive, detailed contexts over concise summaries
- Capture execution feedback and natural signals from trajectories
- Avoid aggressive filtering that causes 'context collapse'"
```

**2. Inclusive Criteria** (7 types of learning):
1. Technical decisions or architectural choices
2. Code patterns, snippets, or implementation approaches
3. Debugging steps, gotchas, or error resolutions
4. API usage, library integration, or tool configuration
5. Strategic discussions about approaches or trade-offs
6. Lessons learned from failures or trial-and-error
7. Domain-specific knowledge or file organization insights

**3. Bias Toward Capture**
```
"Be INCLUSIVE - when in doubt, capture it! The server's Curator will handle
deduplication and quality filtering."
```

**4. Structured Output**
```json
{
  "has_learning": boolean,
  "confidence": number (0.0-1.0),
  "reason": string,
  "learning_type": "implementation|debugging|architecture|integration|strategy|trivial"
}
```

## Implementation (COMPLETED ✅)

**File**: `plugins/ace/hooks/hooks.json`

**What Changed**:
- ✅ **Stop hook** → Now uses prompt-based LLM evaluation (Haiku)
- ✅ **PreCompact hook** → Unchanged (still command-based, working fine)
- ✅ **UserPromptSubmit hook** → Unchanged (still command-based, working fine)

**The New Stop Hook**:
```json
{
  "type": "prompt",
  "model": "haiku",
  "prompt": "[Comprehensive evaluation prompt with ACE philosophy...]",
  "timeout": 15000,
  "action": {
    "if": "has_learning === true",
    "then": {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/scripts/ace_after_task_wrapper.sh",
      "timeout": 30000
    }
  }
}
```

**Flow**:
1. Stop event fires at end of session
2. Haiku evaluates transcript (15s timeout)
3. Returns JSON: `{"has_learning": true/false, "confidence": 0.85, ...}`
4. If `has_learning === true` → Run `ace_after_task_wrapper.sh`
5. Wrapper script calls `ce-ace learn` with execution trace
6. Server's Reflector + Curator process the learning

**Benefits**:
- ✅ Intelligent evaluation (semantic understanding vs regex)
- ✅ Research-aligned (avoids over-filtering per ACE paper)
- ✅ Still calls `ce-ace learn` (no workflow changes)
- ✅ Negligible cost (~$0.0001 per eval)

### Option 2: Two-Stage Hybrid

**Stage 1**: Prompt hook evaluates
**Stage 2**: If yes → Command hook calls ce-ace

```json
{
  "Stop": {
    "type": "prompt",
    "model": "haiku",
    "prompt": "[Evaluation prompt...]",
    "action": {
      "if": "$.has_learning === true && $.confidence > 0.6",
      "then": {
        "type": "command",
        "command": "{{marketplace_root}}/plugins/ace/scripts/ace_after_task_wrapper.sh"
      }
    }
  }
}
```

**Adds confidence threshold** for extra safety.

### Option 3: Remove Filtering Entirely (Paper-Pure)

**Modify ace_after_task.py** to remove lines 376-389:

```python
# REMOVED FILTERING - Let server's Curator handle quality control
# Per ACE research paper: "comprehensive, evolving playbooks" > aggressive filtering

# Always proceed to learning capture (server will handle deduplication)
trace = extract_execution_trace(event)
```

**Pros**:
- ✅ 100% aligned with paper (no brevity bias)
- ✅ Zero cost
- ✅ Simplest code

**Cons**:
- ⚠️ Sends more data to server (Curator handles filtering)
- ⚠️ May capture some truly trivial conversations

## Recommendation

**Use Option 1: Pure Prompt Hook**

**Rationale**:
1. **Research-aligned**: Avoids brevity bias while still being intelligent
2. **Cost-effective**: Haiku evaluations cost ~$0.0001 (negligible)
3. **Transparent**: Prompt documents evaluation criteria
4. **Flexible**: Easy to tune by adjusting prompt, no code changes

**Tuning Parameters**:
- Lower confidence threshold → More captures (research-aligned)
- Higher confidence threshold → Fewer captures (conservative)
- Default: `$.has_learning === true` (no confidence filter)

## Testing Strategy

### 1. Enable Debug Logging

```bash
export ACE_DEBUG_HOOKS=1
```

Check `/tmp/ace_hook_debug.log` for:
- Hook event data
- Haiku's evaluation JSON
- Decision reasoning

### 2. Test Cases

**Should Capture** (has_learning: true):
- ✅ Implementation discussions
- ✅ Debugging sessions
- ✅ Architecture planning
- ✅ API integration work
- ✅ Strategic discussions

**Should Skip** (has_learning: false):
- ❌ "How do I install X?" (basic Q&A)
- ❌ "Hello, how are you?" (greetings)
- ❌ "/clear" followed by nothing

### 3. Compare Before/After

**Metric**: Patterns captured per 100 sessions

**Before** (Regex):
- Estimated: 10-20 patterns (too strict)

**After** (Prompt Hook):
- Expected: 40-60 patterns (research-aligned)
- Quality: Maintained by server's Curator

## Migration Path

### Phase 1: Add Prompt Hook (Non-Breaking)

1. Create `hooks-prompt-based.json` (new file)
2. Test alongside existing hooks
3. Compare capture rates

### Phase 2: Gradual Rollout

1. Deploy to beta users
2. Monitor capture quality via `/ace-status`
3. Tune confidence threshold if needed

### Phase 3: Replace Regex (Breaking)

1. Rename `hooks.json` → `hooks-regex-legacy.json`
2. Rename `hooks-prompt-based.json` → `hooks.json`
3. Update plugin version to v5.2.0

## Cost Analysis

**Haiku Pricing** (Anthropic, as of 2025-01):
- Input: $0.25 / 1M tokens
- Output: $1.25 / 1M tokens

**Per Evaluation**:
- Transcript: ~2000 tokens (input)
- Response: ~50 tokens (output)
- **Cost**: ~$0.0001 per evaluation

**Monthly Cost** (100 sessions):
- 100 evaluations × $0.0001 = **$0.01/month**

**Negligible!** 🎉

## References

- **ACE Research Paper**: Published October 2025
- **Claude Code Hooks Docs**: [hooks documentation]
- **Prompt Hook Spec**: Supported events: Stop, SubagentStop, UserPromptSubmit, PreToolUse
