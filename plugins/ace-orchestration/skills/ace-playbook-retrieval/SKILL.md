---
name: ace-playbook-retrieval
description: MANDATORY FIRST STEP when user says: implement, build, create, add, develop, write, update, modify, change, edit, enhance, extend, revise, fix, debug, troubleshoot, resolve, diagnose, refactor, optimize, improve, restructure, integrate, connect, setup, configure, install, architect, design, plan, test, verify, validate, deploy, migrate, upgrade - OR when request clearly intends to write/modify code, solve technical problems, make architectural decisions, or perform substantial technical work. Retrieves learned patterns from ACE playbook BEFORE starting work. ALWAYS invoke - DO NOT skip.
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
- ONLY informational Q&A (user asks "what is X?", "explain Y", "how does Z work?")
- ONLY file reads explicitly for information gathering (user says "just read, don't change")

**NEVER SKIP** when user message contains trigger words:
- implement, build, create, add, develop, write
- update, modify, change, edit, enhance, extend, revise
- fix, debug, troubleshoot, resolve, diagnose
- refactor, optimize, improve, restructure
- integrate, connect, setup, configure, install
- architect, design, plan, test, verify, validate, deploy, migrate, upgrade

**Trigger words override all other considerations** - if present, invoke this skill FIRST.

## How This Skill Works

### Step 1: Choose Retrieval Strategy

**Decision Logic** - Choose based on task specificity:

**Use `ace_search`** (PREFERRED for specific queries):
```bash
mcp__ace-pattern-learning__ace_search(
  query="JWT authentication with refresh tokens",
  threshold=0.7
)
```
**When to use**:
- ✅ User request mentions specific technology/pattern (e.g., "JWT auth", "Stripe webhooks", "async debugging")
- ✅ Narrow domain focus (authentication, error handling, API integration)
- ✅ You can formulate the query as a natural language question
- ✅ Want 50-80% token reduction

**Use `ace_get_playbook`** (for comprehensive needs):
```bash
mcp__ace-pattern-learning__ace_get_playbook()
# or with section filter:
mcp__ace-pattern-learning__ace_get_playbook(section="strategies_and_hard_rules")
```
**When to use**:
- ✅ Complex multi-domain task (touches auth + database + API)
- ✅ Architectural decisions requiring broad context
- ✅ Refactoring affecting multiple areas
- ✅ No clear narrow query to formulate

**Use `ace_batch_get`** (for follow-up retrieval):
```bash
mcp__ace-pattern-learning__ace_batch_get(
  pattern_ids=["ctx-001", "ctx-002", "ctx-003"]
)
```
**When to use**:
- ✅ You have pattern IDs from previous search results
- ✅ Need to fetch full details of specific patterns
- ✅ Following up on references from other patterns

**Default Strategy**: **Try `ace_search` first** for specific requests, fall back to `ace_get_playbook` only if query is too broad.

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

### Example 1: Specific Implementation (Use ace_search)

```
User: "Implement JWT authentication with refresh tokens"
↓
Skill Auto-Invokes (matches "implement")
↓
Decision: Narrow domain (JWT auth) → Use ace_search
↓
Calls: mcp__ace_search(query="JWT authentication refresh tokens", threshold=0.7)
↓
Retrieves (Top 3 patterns):
  1. "Refresh token rotation prevents theft attacks - rotate on each use"
  2. "Short-lived access tokens (15min) balance security and UX"
  3. "HttpOnly cookies for refresh tokens prevent XSS attacks"
↓
Implements auth with learned patterns (80% token reduction vs full playbook!)
```

### Example 2: Specific Debugging (Use ace_search)

```
User: "Fix intermittent test failures in async operations"
↓
Skill Auto-Invokes (matches "fix")
↓
Decision: Specific issue (async test failures) → Use ace_search
↓
Calls: mcp__ace_search(query="async test failures intermittent", threshold=0.6)
↓
Retrieves: "Intermittent async failures often indicate missing await statements"
↓
First checks for missing await in cleanup code (root cause found!)
```

### Example 3: Specific API Integration (Use ace_search)

```
User: "Integrate Stripe payment webhooks"
↓
Skill Auto-Invokes (matches "integrate")
↓
Decision: Specific API (Stripe webhooks) → Use ace_search
↓
Calls: mcp__ace_search(query="Stripe webhook integration", threshold=0.7)
↓
Retrieves: "Stripe webhooks require express.raw() for signature verification"
↓
Implements webhook handler with correct body parser configuration
```

### Example 4: Complex Multi-Domain Task (Use ace_get_playbook)

```
User: "Refactor database queries to use connection pooling"
↓
Skill Auto-Invokes (matches "refactor")
↓
Decision: Broad refactoring touching multiple areas → Use ace_get_playbook
↓
Calls: mcp__ace_get_playbook()  # All sections - need comprehensive context
↓
Retrieves patterns from past database work:
  - strategies: "Connection pool size = 2-3x concurrent queries"
  - snippets: "Pool configuration with graceful shutdown"
  - troubleshooting: "Pool exhaustion causes intermittent timeouts"
↓
Refactors with proper pool sizing and error handling
```

### Example 5: Follow-Up Retrieval (Use ace_batch_get)

```
User: "Show me more details about those authentication patterns"
↓
Previous search returned IDs: ["ctx-001", "ctx-002", "ctx-003"]
↓
Decision: Have specific IDs from previous search → Use ace_batch_get
↓
Calls: mcp__ace_batch_get(pattern_ids=["ctx-001", "ctx-002", "ctx-003"])
↓
Retrieves: Full pattern details with evidence, observations, timestamps
↓
Displays comprehensive pattern information (10x faster than sequential fetches)
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

### Semantic Search with Thresholds

```bash
# Strict matching (fewer, more precise results)
mcp__ace_search(query="JWT authentication", threshold=0.85)

# Balanced (recommended default)
mcp__ace_search(query="JWT authentication", threshold=0.7)

# Broader matching (more results, less precision)
mcp__ace_search(query="JWT authentication", threshold=0.5)
```

### Search Within Specific Section

```bash
# Search only in troubleshooting patterns
mcp__ace_search(
  query="async test failures",
  section="troubleshooting_and_pitfalls",
  threshold=0.7
)

# Search only API-related patterns
mcp__ace_search(
  query="Stripe integration",
  section="apis_to_use",
  threshold=0.7
)
```

### Two-Stage Retrieval (Search → Batch Fetch)

```bash
# Stage 1: Find relevant pattern IDs
results = mcp__ace_search(query="authentication patterns", threshold=0.7)
pattern_ids = [p.id for p in results.patterns]  # Extract IDs

# Stage 2: Fetch full details in bulk
full_patterns = mcp__ace_batch_get(pattern_ids=pattern_ids)
# 10x-50x faster than fetching individually!
```

### Full Playbook with Filters

```bash
# Only highly-rated patterns (helpful >= 5)
mcp__ace_get_playbook(min_helpful=5)

# High-quality troubleshooting patterns
mcp__ace_get_playbook(section="troubleshooting_and_pitfalls", min_helpful=3)

# All architectural strategies
mcp__ace_get_playbook(section="strategies_and_hard_rules")
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
