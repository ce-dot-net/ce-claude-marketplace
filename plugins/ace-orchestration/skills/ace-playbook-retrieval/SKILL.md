---
name: ace-playbook-retrieval
description: Retrieve learned strategies, code patterns, and troubleshooting solutions before implementation tasks. Use when starting: feature implementation, bug fixes, API integration, code refactoring, architecture decisions, debugging issues, performance optimization. Provides project-specific strategies, tested code snippets, known pitfalls, and recommended libraries from past work.
---

# ACE Playbook Retrieval

Retrieve organizational knowledge from the ACE playbook to inform current work.

## When to Use This Skill

Use **BEFORE** starting:

- **Implementation**: Building features, adding functionality, creating new modules
- **Refactoring**: Restructuring code, optimizing performance, improving architecture
- **Debugging**: Troubleshooting errors, fixing test failures, resolving build issues
- **Architecture**: Making design decisions, choosing patterns, planning structure
- **Integration**: Working with APIs, libraries, external services, third-party tools
- **Problem-Solving**: Complex technical challenges requiring domain expertise

**SKIP FOR**:
- Simple Q&A or informational queries
- Basic file reads without problem-solving
- Trivial edits without technical complexity
- Documentation updates without code changes

## ⚠️ CRITICAL CHECKPOINT

**Before starting ANY substantial task, ask yourself:**
1. Is the user asking me to implement, build, create, debug, fix, refactor, or configure something?
2. Am I about to write code, solve a technical problem, or make architectural decisions?
3. Could learned patterns from previous work help me here?

**If YES to any:** STOP - Invoke this skill NOW before starting work.

**Timing Rule:** This skill should be invoked **IMMEDIATELY after understanding the task** and **BEFORE writing any code or solutions**.

## How This Skill Works

### Step 1: Call MCP Tool

```bash
mcp__ace-pattern-learning__ace_get_playbook
```

**Parameters** (all optional):
- `section`: Filter by specific playbook section
  - `strategies_and_hard_rules`: Architectural patterns and coding principles
  - `useful_code_snippets`: Reusable code patterns with tested implementations
  - `troubleshooting_and_pitfalls`: Known issues, gotchas, and solutions
  - `apis_to_use`: Recommended libraries, frameworks, and integration patterns
- `min_helpful`: Minimum helpful count (filter by quality score)

**No section parameter** = Returns all sections (recommended for complex tasks)

### Step 2: MCP Client Handles Caching Automatically

The MCP client uses 3-tier caching for optimal performance:

1. **RAM Cache**: Instant access during current session (fastest)
2. **SQLite Cache**: `~/.ace-cache/{org}_{project}.db` with 5-minute TTL
3. **Server Fetch**: Only when cache is stale or empty

**You don't manage caching** - the MCP client does it transparently! Just call the tool.

### Step 3: Review Retrieved Patterns

The playbook returns JSON with four sections:

```json
{
  "strategies_and_hard_rules": [
    {
      "bullet": "Pattern or principle learned from past work",
      "helpful": 5,
      "harmful": 0
    }
  ],
  "useful_code_snippets": [
    {
      "bullet": "Reusable code pattern with context",
      "helpful": 8,
      "harmful": 0
    }
  ],
  "troubleshooting_and_pitfalls": [
    {
      "bullet": "Known issue and solution",
      "helpful": 6,
      "harmful": 0
    }
  ],
  "apis_to_use": [
    {
      "bullet": "Recommended library or API with rationale",
      "helpful": 7,
      "harmful": 0
    }
  ]
}
```

### Step 4: Apply Patterns to Current Task

- **Reference strategies** when making architectural decisions
- **Reuse code snippets** where applicable (adapt to current context)
- **Avoid known pitfalls** documented in troubleshooting section
- **Use recommended APIs** and integration patterns
- **Learn from past failures** to prevent repeated mistakes

### Step 5: Proceed with Task

Execute the user's request informed by organizational knowledge!

## Examples

### Example 1: Implementation Task

```
User: "Implement JWT authentication with refresh tokens"
↓
Skill Auto-Invokes (matches "implement")
↓
Calls: mcp__ace_get_playbook(section="strategies_and_hard_rules")
↓
Retrieves: "Refresh token rotation prevents theft attacks - rotate on each use"
↓
Implements auth with learned pattern: short-lived access tokens + rotating refresh tokens
```

### Example 2: Debugging Task

```
User: "Fix intermittent test failures in async operations"
↓
Skill Auto-Invokes (matches "fix")
↓
Calls: mcp__ace_get_playbook(section="troubleshooting_and_pitfalls")
↓
Retrieves: "Intermittent async failures often indicate missing await statements"
↓
First checks for missing await in cleanup code (root cause found!)
```

### Example 3: API Integration Task

```
User: "Integrate Stripe payment webhooks"
↓
Skill Auto-Invokes (matches "integrate")
↓
Calls: mcp__ace_get_playbook(section="apis_to_use")
↓
Retrieves: "Stripe webhooks require express.raw() for signature verification"
↓
Implements webhook handler with correct body parser configuration
```

### Example 4: Refactoring Task

```
User: "Refactor database queries to use connection pooling"
↓
Skill Auto-Invokes (matches "refactor")
↓
Calls: mcp__ace_get_playbook()  # All sections
↓
Retrieves patterns from past database work:
  - strategies: "Connection pool size = 2-3x concurrent queries"
  - snippets: "Pool configuration with graceful shutdown"
  - troubleshooting: "Pool exhaustion causes intermittent timeouts"
↓
Refactors with proper pool sizing and error handling
```

## Integration with ACE Learning

This skill completes the ACE automatic learning cycle:

1. **Retrieve** (this skill) → Fetch learned patterns before task
2. **Apply** → Execute task using organizational knowledge
3. **Learn** (ACE Learning skill) → Capture new insights after completion
4. **Update** → Server processes feedback and updates playbook
5. **Next Task** → Retrieval gets enhanced playbook with new patterns

**Result**: Knowledge compounds over time! Each task makes the system smarter.

## Key Principles

### Progressive Learning
- Early playbooks may be sparse → fall back on general knowledge
- As tasks complete, playbook grows richer with domain-specific insights
- Patterns with high `helpful` scores are proven through repeated success

### Context-Aware Usage
- Don't force patterns that don't fit current context
- Adapt snippets to current codebase conventions
- Use playbook as guidance, not rigid rules

### Feedback Loop
- If a retrieved pattern proves helpful → contributes to its `helpful` score
- If a pattern is outdated or incorrect → report via ACE Learning skill
- Server-side Curator refines patterns based on usage feedback

## Troubleshooting

### Playbook Returns Empty
- **Cause**: New project without learned patterns yet
- **Solution**: Complete tasks and use ACE Learning skill to build playbook
- **Workaround**: Use `/ace-init` to bootstrap from git history

### Patterns Seem Outdated
- **Cause**: Technology stack changed, old patterns no longer applicable
- **Solution**: Continue using ACE Learning to capture new patterns
- **Note**: Harmful feedback automatically demotes outdated patterns

### Skill Doesn't Auto-Invoke
- **Cause**: Task description doesn't match trigger words
- **Solution**: Manually call `/ace-patterns` or invoke skill explicitly
- **Check**: Ensure task is substantial (not simple Q&A)

## Advanced Usage

### Filter by Section for Focused Retrieval

```bash
# For architectural decisions
mcp__ace_get_playbook(section="strategies_and_hard_rules")

# For code implementation
mcp__ace_get_playbook(section="useful_code_snippets")

# For debugging
mcp__ace_get_playbook(section="troubleshooting_and_pitfalls")

# For choosing libraries
mcp__ace_get_playbook(section="apis_to_use")
```

### Filter by Quality

```bash
# Only highly-rated patterns (helpful >= 5)
mcp__ace_get_playbook(min_helpful=5)
```

### Combine Filters

```bash
# High-quality troubleshooting patterns
mcp__ace_get_playbook(section="troubleshooting_and_pitfalls", min_helpful=3)
```

## ACE Framework Architecture

This skill implements the ACE framework's automatic context retrieval:

```
User Request
    ↓
ACE Playbook Retrieval Skill (model-invoked)
    ↓
mcp__ace_get_playbook → MCP Client
    ↓
RAM Cache (hit?) → Return instantly
    ↓ (miss)
SQLite Cache (hit?) → Return quickly
    ↓ (miss/stale)
ACE Server → Fetch latest playbook
    ↓
Update Caches → Return to Claude
    ↓
Claude Uses Patterns in Context
```

**Benefits**:
- ✅ Token-efficient: Only ~100 tokens for skill metadata until triggered
- ✅ Fast: 3-tier caching ensures minimal latency
- ✅ Automatic: Model-invoked based on task context
- ✅ Progressive: Playbook grows richer over time
- ✅ Universal: Works with any MCP-compatible client

**Result**: Comprehensive, evolving contexts enable scalable, efficient, and self-improving LLM systems.
