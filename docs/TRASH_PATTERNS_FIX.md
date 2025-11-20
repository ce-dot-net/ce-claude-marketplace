# ACE Trash Patterns Fix (v5.1.9)

## Problem Summary

**Issue**: Hooks created 700+ trash patterns by learning from tool operations instead of conversation outcomes.

**Impact**:
- Database polluted with patterns like "Edit - ", "Write - ", "Bash - " (empty/generic descriptions)
- Search returns garbage results instead of valuable knowledge
- Playbooks degraded to 3% trash patterns

**Root Cause**: Both `ace_task_complete.py` (PostToolUse) and `ace_after_task.py` (PreCompact) built trajectories from tool descriptions (operations) instead of conversation messages (patterns).

---

## What Was Wrong

### Learning OPERATIONS (what was done) ❌

```python
# OLD CODE (WRONG) - From tool descriptions:
trajectory = [
    {"action": "Write - Create auth.ts file"},
    {"action": "Edit - Update config.json"},
    {"action": "Bash - Run tests"},
    {"action": "Read - Check results"}
]

# Result in database:
"ACE minimal write operations: When task shows 'Write' with empty content..."
"ACE minimal edit operations: When task shows 'Edit' with empty content..."
```

**Problem**: These are OPERATIONS, not PATTERNS! No valuable knowledge captured.

### Should Learn PATTERNS (how to solve problems) ✅

```python
# NEW CODE (CORRECT) - From conversation messages:
trajectory = [
    {"action": "Made architectural decision",
     "result": "JWT tokens: 15min access, 7-day refresh (prevents token theft)"},
    {"action": "Discovered gotcha",
     "result": "Stripe webhooks require express.raw() middleware for signature verification"},
    {"action": "Solved CORS issue",
     "result": "Added credentials: 'include' to fetch calls for cookie-based auth"}
]

# Result in database:
"JWT refresh token rotation prevents token theft attacks"
"Stripe webhook signature verification requires express.raw() middleware"
```

**Benefit**: Real KNOWLEDGE captured, not just operations!

---

## The Fix

### Step 1: Disable PostToolUse Hook

**File**: `shared-hooks/ace_task_complete.py`

**Change**: Added `sys.exit(0)` at top to exit immediately

```python
#!/usr/bin/env -S uv run --script
# ... (script metadata)
"""
⚠️ DISABLED - This hook creates trash patterns by learning from tool operations.
"""

import json
import sys

# CRITICAL: Exit immediately - don't run the rest of this hook
sys.exit(0)
```

**Why**: PostToolUse fires after EVERY tool use (50+ times per session), creating 50+ trash patterns. Learning should happen ONCE per session from high-level outcomes.

---

### Step 2: Rewrite PreCompact Trajectory Extraction

**File**: `shared-hooks/ace_after_task.py`

**Change**: Replace tool_uses iteration with messages iteration

**OLD CODE (lines 58-84)**:
```python
for idx, tool in enumerate(tool_uses, 1):
    tool_name = tool.get('tool_name', 'unknown')
    tool_desc = tool.get('description', '')

    trajectory.append({
        "step": idx,
        "action": f"{tool_name} - {tool_desc}",  # ❌ Creates trash!
        "result": "completed"
    })
```

**NEW CODE**:
```python
# Extract high-level insights from conversation messages
decisions = []
gotchas = []
accomplishments = []

for msg in messages:
    role = msg.get('role')
    content = msg.get('content', '')

    # Only process assistant messages
    if role != 'assistant':
        continue

    content_lower = content.lower()

    # Extract decisions (architectural choices)
    if any(word in content_lower for word in ['decided', 'chose', 'using', 'approach']):
        for sentence in content.split('.'):
            if any(word in sentence.lower() for word in ['decided', 'chose']):
                clean = sentence.strip()
                if len(clean) > 20:
                    decisions.append(clean)

    # Extract gotchas (errors fixed, pitfalls discovered)
    if any(word in content_lower for word in ['error', 'fixed', 'solved', 'issue']):
        for sentence in content.split('.'):
            if any(word in sentence.lower() for word in ['error', 'fixed']):
                clean = sentence.strip()
                if len(clean) > 20:
                    gotchas.append(clean)

    # Extract accomplishments (successful completions)
    if any(word in content_lower for word in ['completed', 'working', 'successfully']):
        for sentence in content.split('.'):
            if any(word in sentence.lower() for word in ['completed', 'working']):
                clean = sentence.strip()
                if len(clean) > 20:
                    accomplishments.append(clean)

# Build meaningful trajectory
if decisions:
    trajectory.append({
        "step": 1,
        "action": "Made architectural decisions",
        "result": " | ".join(decisions[:3])  # Top 3
    })

if gotchas:
    trajectory.append({
        "step": len(trajectory) + 1,
        "action": "Encountered and resolved issues",
        "result": " | ".join(gotchas[:3])
    })

if accomplishments:
    trajectory.append({
        "step": len(trajectory) + 1,
        "action": "Completed work items",
        "result": " | ".join(accomplishments[:3])
    })
```

**Why**: Messages contain high-level decisions, gotchas, and accomplishments - REAL patterns worth learning!

---

## Key Principles

### Operations vs Patterns

| Type | Example | Value |
|------|---------|-------|
| **Operation** ❌ | "Write - Create file" | None - just describes what tool did |
| **Operation** ❌ | "Edit - Update config" | None - no knowledge captured |
| **Pattern** ✅ | "JWT 15min access tokens prevent theft" | High - reusable knowledge |
| **Pattern** ✅ | "Stripe needs express.raw() for webhooks" | High - saves future debugging |

### Why PostToolUse Was Wrong

- **Frequency**: Fires 50+ times per session (once per tool use)
- **Granularity**: Too fine-grained (individual tool operations)
- **Context**: Limited context (just recent tool, not full conversation)
- **Result**: 50+ trash patterns per session

### Why PreCompact Is Right

- **Frequency**: Fires once per session (at compaction or session end)
- **Granularity**: High-level (full conversation arc)
- **Context**: Full context (all messages, decisions, outcomes)
- **Result**: 1-3 meaningful patterns per session

---

## Testing the Fix

### Test 1: Verify PostToolUse Disabled

```bash
# Run a simple task
echo "Create a new file called test.txt" | claude-code

# Check for trash patterns
ce-ace patterns | grep -E "Write -|Edit -|Bash -|Read -"

# Expected: NO MATCHES ✅
# If you see matches: PostToolUse still running ❌
```

### Test 2: Verify PreCompact Captures High-Level

```bash
# Run a complex task
claude-code "Build a JWT authentication system with refresh tokens"

# After completion, check what was learned
ce-ace patterns --section strategies_and_hard_rules | tail -5

# Expected:
# ✅ "JWT tokens: 15min access, rotating refresh"
# ✅ "HttpOnly cookies prevent XSS token theft"
# ❌ NOT "Write - Create auth.ts"
# ❌ NOT "Edit - Update config.json"
```

### Test 3: Monitor Database Quality

```bash
# Check trash pattern count (should decrease over time)
ce-ace patterns | grep -E "Write -|Edit -|Bash -" | wc -l

# Day 0: 700+ trash patterns
# Day 1: 700 (no new trash added)
# Day 7: 600 (old trash pruned by quality scoring)
# Day 30: <100 (trash patterns faded out)
```

---

## Validation Checklist

Before considering this fixed:

- [x] `ace_task_complete.py` exits immediately at line 34 (`sys.exit(0)`)
- [x] `ace_after_task.py` does NOT iterate over `tool_uses` for trajectory
- [x] `ace_after_task.py` DOES iterate over `messages` for insights
- [x] Trajectory built from decisions/gotchas/accomplishments (not tool descriptions)
- [ ] Test task creates NO patterns matching `(Write|Edit|Bash|Read) -`
- [ ] Test task DOES create patterns with meaningful content
- [ ] Database shows no new trash patterns after 24 hours of use

---

## Impact Metrics

### Before Fix (v5.1.8)

- **PostToolUse**: 50+ learning captures per session
- **Patterns per session**: 50+ trash patterns
- **Database quality**: 3% trash (700/23,000 patterns)
- **Search quality**: Poor (trash patterns pollute results)

### After Fix (v5.1.9)

- **PostToolUse**: Disabled (0 captures)
- **PreCompact**: 1 learning capture per session
- **Patterns per session**: 1-3 meaningful patterns
- **Database quality**: Improving (no new trash added)
- **Search quality**: Improving (high-quality patterns prioritized)

**Expected Timeline**:
- Day 0: Immediate stop of new trash creation
- Week 1: Noticeable improvement in search quality
- Month 1: Trash patterns pruned to <5% via quality scoring
- Month 3: Trash patterns completely faded out

---

## Server Team Feedback

From ACE Server Team:

> "Tool descriptions should NEVER become patterns in the first place! These are OPERATIONS (what was done), not PATTERNS (how to solve problems)."

> "The ACTUAL Fix: Don't filter descriptions - DON'T CREATE PATTERNS FROM TOOLS AT ALL!"

> "PreCompact should extract: Decisions made (NOT 'Write file', but 'Chose JWT with refresh rotation'), Gotchas found (NOT 'Edit code', but 'Stripe needs express.raw()'), Accomplishments (NOT 'Run tests', but 'Working auth system')"

---

## Migration Guide

### For Users

**No action required!** Update to v5.1.9 and the fix is automatic.

**What you'll notice**:
- No more trash patterns being created
- Search results improve over time
- Playbook contains actual valuable knowledge

### For Developers

**If you modified hooks**:
1. Pull latest changes
2. Review `ace_task_complete.py` - should exit immediately
3. Review `ace_after_task.py` - should extract from messages, not tools
4. Test with sample task to verify no trash patterns created

**If you have custom learning logic**:
- Ensure you extract from conversation messages, not tool descriptions
- Focus on decisions, gotchas, accomplishments (high-level)
- Avoid learning from individual tool operations (low-level)

---

## References

- **Server Team Analysis**: Provided in user message (2024-11-20)
- **ACE Research Paper**: arXiv:2510.04618v1
- **Related Issues**: #3523 (Hook Storm Bug)
- **Related Docs**:
  - `QUERY_ENHANCEMENT_DECISION.md` (semantic search vs keyword stuffing)
  - `ACE_V1_0_13_INTEGRATION.md` (learning statistics)
  - `POSTTOOLUSE_LEARNING_FIX.md` (v5.1.8 - now superseded)

---

## Version History

- **v5.1.8** (2024-11-19): Added PostToolUse learning capture (MISTAKE - created trash)
- **v5.1.9** (2024-11-20): Fixed trash patterns by disabling PostToolUse and rewriting PreCompact
- **Future**: Consider removing PostToolUse hook code entirely (kept for reference now)
