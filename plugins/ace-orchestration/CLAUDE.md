# ACE Orchestration Plugin - Automatic Learning Cycle

This plugin provides fully automatic pattern learning using the ACE framework architecture.

## 📖 Setup Instructions

**First-Time Setup:** Run `/ace-claude-init` in your project to add this file to your project's CLAUDE.md. This provides always-on context about the ACE system and ensures optimal skill triggering.

## 🚨 AUTOMATIC: ACE Skill Enforcement

**Skill invocation is ENFORCED automatically via SessionStart hook.**

The plugin includes `hooks/ace-skill-enforcement.sh` which injects MANDATORY skill invocation instructions into your context at the start of every session. You don't need to remember to invoke skills - the system will remind you automatically.

### How Automatic Enforcement Works:

1. **Session starts** → SessionStart hook runs
2. **Hook output** → Added to Claude's context (system-level instruction)
3. **User task** → Claude sees MANDATORY protocol + user request
4. **Skills auto-invoke** → Triggered based on task keywords

### The Two Skills:

**Before tasks:** `ace-orchestration:ace-playbook-retrieval`
- Automatically invoked when you: implement, build, create, add, develop, debug, fix, troubleshoot, resolve, refactor, optimize, improve, restructure, integrate, connect, setup, configure, architect, design, plan
- Retrieves learned patterns from previous work
- Provides strategies, code snippets, troubleshooting tips, API recommendations

**After tasks:** `ace-orchestration:ace-learning`
- Automatically invoked after: implementing features, fixing bugs, solving problems, creating files, making architectural decisions, discovering gotchas
- Captures what you learned during execution
- Updates the playbook for future use

### Workflow Example:

```
User: "Implement JWT authentication"
    ↓
Automatic: ace-playbook-retrieval invokes (hook enforces)
    ↓
Retrieved: Previous auth patterns loaded
    ↓
Implementation: Using learned patterns
    ↓
Automatic: ace-learning invokes (hook enforces)
    ↓
Result: New patterns captured for next time
```

**Note:** The SessionStart hook provides system-level enforcement, making skill invocation truly automatic and non-optional.

## 🔄 Complete Automatic Learning Cycle (v3.2.24)

ACE uses **two Agent Skills** to create a self-improving learning cycle:

### 1. **ACE Playbook Retrieval** (Before Tasks)
**Model-Invoked**: Claude decides when to activate based on task context

**Triggers**: implement, build, create, fix, debug, refactor, integrate, optimize, architect

**What it does**:
- Calls: `mcp__ace-pattern-learning__ace_get_playbook`
- Retrieves: Learned patterns from previous sessions
- Returns: Strategies, code snippets, troubleshooting tips, API recommendations
- Cache: 3-tier (RAM → SQLite → Server) for fast access

**Result**: Claude has organizational knowledge BEFORE starting the task!

### 2. **ACE Learning from Execution** (After Tasks)
**Model-Invoked**: Claude decides when to capture learning

**Triggers**: Substantial work completion with valuable lessons

### When Agent Skill Triggers

The Agent Skill **automatically invokes** after completing:

1. **Problem-Solving & Debugging**
   - Fixed bugs or resolved errors
   - Debugged test failures or build issues
   - Troubleshot integration problems

2. **Code Implementation**
   - Implemented new features or functionality
   - Refactored existing code
   - Optimized performance

3. **API & Tool Integration**
   - Integrated external APIs or services
   - Used new libraries or frameworks
   - Configured build tools or CI/CD

4. **Learning from Failures**
   - Encountered and recovered from errors
   - Discovered edge cases or gotchas
   - Found better approaches after initial failures

5. **Substantial Subagent Tasks**
   - Completed complex multi-step tasks
   - Made significant technical decisions

### What the Agent Skill Does

When triggered, the Agent Skill:
1. **Extracts task information** - What was accomplished
2. **Captures trajectory** - Key steps and decisions made
3. **Gathers feedback** - Lessons learned, patterns discovered, gotchas
4. **Calls `mcp__ace-pattern-learning__ace_learn`** - Triggers automatic learning

**What it does**:
- Calls: `mcp__ace-pattern-learning__ace_learn`
- Captures: Task description, trajectory, feedback, lessons learned
- Sends: Execution trace to ACE Server
- Server: Reflector (Sonnet 4) → Curator (Haiku 4.5) → Merge

**Result**: Playbook updated with new patterns for future use!

### The Complete Automatic Cycle

```
┌─────────────────────────────────────────────────────────┐
│ 1. User Request: "Implement JWT authentication"        │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 2. ACE Playbook Retrieval Skill AUTO-INVOKES          │
│    - Claude matches: "implement" → triggers skill       │
│    - Calls: mcp__ace_get_playbook                      │
│    - MCP Client: RAM → SQLite → Server                 │
│    - Returns: "Refresh token rotation prevents theft"  │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Claude Executes Task with Learned Patterns         │
│    - Uses strategies from playbook                      │
│    - Applies proven code snippets                       │
│    - Avoids known pitfalls                             │
│    - Chooses recommended APIs                          │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 4. ACE Learning Skill AUTO-INVOKES                    │
│    - Claude recognizes substantial work completed      │
│    - Calls: mcp__ace_learn                             │
│    - Sends: task + trajectory + feedback → Server      │
│    - Server: Reflector → Curator → Delta Merge        │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Playbook Updated on Server                         │
│    - New patterns added to relevant sections           │
│    - Quality scores updated based on outcomes          │
│    - Ready for next retrieval!                         │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 6. Next Session → Enhanced Playbook Retrieved         │
│    - Knowledge compounds over time! 🎯                 │
└─────────────────────────────────────────────────────────┘
```

### Caching Architecture

ACE uses a 3-tier caching system for optimal performance:

1. **RAM Cache**: In-memory, session-scoped (fastest - instant access)
2. **SQLite Cache**: `~/.ace-cache/{org}_{project}.db`, 5-minute TTL (fast - milliseconds)
3. **Server Fetch**: Only when cache is stale or empty (slower - seconds)

**You don't manage caching** - the MCP client handles it automatically!

### Manual Override Commands

While skills auto-invoke, manual commands are available for explicit control:

- `/ace-patterns [section]` - View playbook manually
- `/ace-status` - Check playbook statistics
- `/ace-configure` - Configure ACE server connection
- `/ace-bootstrap` - Bootstrap playbook from docs, git history, and current code
  - **New in v3.2.17**: `bootstrap-orchestrator` skill provides dynamic pattern compression reporting
    - Automatically calculates compression percentage (e.g., 158 → 18 = 89% reduction)
    - Explains why compression > 80% is expected (semantic deduplication per ACE Research Paper)
    - Shows progress messages during 10-30 second analysis
    - Uses actual numbers from server, not hardcoded examples
  - **New in v3.2.15**: `hybrid` mode (default) - intelligently scans docs → git → local files
  - **New in v3.2.15**: `thoroughness` parameter - light/medium/deep (default: medium)
  - **New in v3.2.15**: 5x deeper defaults - 5000 files, 500 commits, 90 days
  - Use for initial setup or periodic refresh of playbook patterns
- `/ace-clear` - Clear playbook (requires confirmation)
- `/ace-export-patterns` - Export playbook to JSON
- `/ace-import-patterns` - Import playbook from JSON

## 🤖 How Agent Skills Work (Model-Invoked)

### Example Complete Cycles

**Cycle 1: Implementation with Prior Knowledge**
```
User: "Add JWT authentication with refresh tokens"
↓
Playbook Retrieval: Fetches previous auth patterns
Retrieved: "Refresh token rotation prevents theft attacks"
↓
Implementation: Uses learned pattern (short-lived access + rotating refresh)
↓
Learning: Captures successful implementation
Result: Pattern reinforced with +1 helpful score
```

**Cycle 2: Debugging with Learned Patterns**
```
User: "Fix intermittent test failures"
↓
Playbook Retrieval: Fetches troubleshooting patterns
Retrieved: "Intermittent async failures often mean missing await"
↓
Debugging: Checks for missing await first (found it!)
↓
Learning: Captures successful debugging approach
Result: Pattern reinforced, new context added
```

**Cycle 3: API Integration with Gotcha Prevention**
```
User: "Integrate Stripe webhook handling"
↓
Playbook Retrieval: Fetches API integration patterns
Retrieved: "Stripe webhooks need express.raw() for signature verification"
↓
Implementation: Uses correct body parser from the start (no trial-and-error!)
↓
Learning: Captures successful integration
Result: Pattern confirmed, additional webhook patterns captured
```

**Progressive Intelligence**: Each cycle makes future tasks faster and more accurate!

### Key Principles

**Skills are Model-Invoked**:
- Claude decides when to activate based on description matching
- No manual invocation needed (skills just exist and auto-trigger)
- Triggered by specific words: implement, build, fix, debug, refactor, integrate

**Automatic Invocation**:
- **Retrieval**: Before complex tasks (implementation, debugging, architecture)
- **Learning**: After substantial work (problem-solving, discoveries, lessons)
- **Skips**: Trivial Q&A, simple file reads, basic informational responses

**Progressive Disclosure**:
- Skills metadata: ~100 tokens (always loaded)
- Skills instructions: ~5k tokens (loaded when triggered)
- Playbook content: Variable (only when retrieved)

**Context-Aware**:
- Skills only trigger when relevant to task
- Playbook only fetched for complex work
- Cache prevents redundant server calls

### MCP Tools (For Manual Testing)

While skills handle automation, you can manually call MCP tools:

**Retrieve Playbook**:
```bash
mcp__ace-pattern-learning__ace_get_playbook
mcp__ace-pattern-learning__ace_get_playbook(section="strategies_and_hard_rules")
mcp__ace-pattern-learning__ace_get_playbook(min_helpful=5)
```

**Capture Learning**:
```bash
mcp__ace-pattern-learning__ace_learn(
  task="Brief description",
  success=true,
  trajectory="Key steps taken",
  output="Lessons learned"
)
```

**Check Status**:
```bash
mcp__ace-pattern-learning__ace_status
```

## 🎯 ACE Architecture (v3.2.24)

The ACE framework implements fully automatic learning with complete retrieval → learning cycle:

### ACE Architecture Components
- **Generator**: Main Claude instance (you!) executing tasks
- **Playbook**: Evolving context with learned patterns (4 sections)
- **Reflector**: Server-side pattern analysis using Sonnet 4
- **Curator**: Server-side delta updates using Haiku 4.5 (60% cost savings)
- **Merge**: Non-LLM algorithm applying incremental updates

### Implementation
- **Generator**: Claude Code with Agent Skills (model-invoked)
- **Playbook Retrieval**: `ace-playbook-retrieval` skill (before tasks)
- **Playbook Learning**: `ace-learning` skill (after tasks)
- **MCP Client**: 3-tier cache + HTTP interface to ACE Server
- **ACE Server**: Autonomous analysis engine (separate repo)

### Playbook Sections
1. **strategies_and_hard_rules**: Architectural patterns, coding principles
2. **useful_code_snippets**: Reusable code patterns with context
3. **troubleshooting_and_pitfalls**: Known issues, gotchas, solutions
4. **apis_to_use**: Recommended libraries, frameworks, integration patterns

### Benefits
- ✅ **Automatic**: Skills auto-invoke based on task context (no manual intervention)
- ✅ **Universal**: Works with ALL MCP clients (Claude Code, Cursor, Cline, etc.)
- ✅ **Fast**: 3-tier caching (RAM → SQLite → Server)
- ✅ **Cost-Optimized**: Sonnet 4 for intelligence, Haiku 4.5 for efficiency
- ✅ **Token-Efficient**: Progressive disclosure, only loads when needed
- ✅ **Self-Improving**: Each task makes the system smarter
- ✅ **Transparent**: Server-side logging for debugging

**Result**: Provides significant performance improvement on agentic tasks through fully automatic pattern learning AND retrieval!

## 📁 File Structure

```
plugins/ace-orchestration/
├── skills/
│   ├── ace-playbook-retrieval/    # NEW: Retrieval skill
│   │   └── SKILL.md               # Before-task pattern fetching
│   └── ace-learning/              # Learning skill
│       └── SKILL.md               # After-task pattern capture
├── commands/
│   ├── ace-patterns.md            # Manual playbook view
│   ├── ace-status.md              # Playbook statistics
│   ├── ace-configure.md           # Server setup
│   ├── ace-init.md                # Bootstrap from git
│   └── ace-clear.md               # Clear playbook
├── hooks/
│   └── hooks.json                 # SessionStart + PostToolUse
├── .mcp.json                      # MCP client config
└── CLAUDE.md                      # This file!
```
