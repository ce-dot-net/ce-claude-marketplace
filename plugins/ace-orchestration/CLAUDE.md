<!-- ACE_SECTION_START v4.0.0 -->
# ACE Orchestration Plugin

This plugin provides automatic pattern learning using the ACE (Adaptive Context Evolution) framework.

## How It Works

**ACE helps Claude learn from your codebase over time:**

1. **Before complex tasks** - Retrieve relevant patterns from past work
2. **During execution** - Apply proven strategies and avoid known pitfalls
3. **After completion** - Capture new patterns for future use

Over time, the system builds organizational knowledge that compounds with each project session.

## Automatic Learning Cycle

ACE uses **two subagents** that run in separate contexts:

### ACE Retrieval Subagent (Before Work)

**When it runs**: Before implementation, debugging, refactoring, or architectural tasks

**What it does**:
- Searches the ACE playbook for relevant patterns
- Returns 2-5 key insights to inform your work
- Uses semantic search for 50-92% token efficiency

**You'll see**: `[ACE Retrieval] Searching playbook for patterns...`

**Triggers**: implement, build, create, fix, debug, refactor, optimize, integrate, architect, test, deploy, etc.

### ACE Learning Subagent (After Work)

**When it runs**: After substantial work completion (implementation, bug fixes, refactoring)

**What it does**:
- Captures lessons learned from the work
- Sends execution trace to ACE server
- Updates playbook for future retrieval

**You'll see**: `[ACE Learning] Captured 3 new patterns`

**Triggers**: Work completion with valuable lessons (successes AND failures)

## The Playbook

The ACE playbook has 4 sections:

1. **strategies_and_hard_rules** - Architectural patterns, coding principles
2. **useful_code_snippets** - Reusable code patterns with context
3. **troubleshooting_and_pitfalls** - Known issues, gotchas, solutions
4. **apis_to_use** - Recommended libraries, frameworks, integration patterns

Patterns accumulate helpful/harmful scores based on usage feedback.

## Setup

### First-Time Setup

1. **Configure connection**:
   ```
   /ace-orchestration:ace-configure
   ```
   Sets up server URL, API token, and project ID.

2. **Bootstrap initial patterns** (optional but recommended):
   ```
   /ace-orchestration:ace-bootstrap --mode hybrid --thoroughness deep
   ```
   Extracts patterns from docs, git history, and current code.

3. **Start coding**: Subagents auto-invoke when relevant.

### Manual Commands

View and manage patterns:
- `/ace-orchestration:ace-patterns` - View full playbook
- `/ace-orchestration:ace-search <query>` - Semantic search
- `/ace-orchestration:ace-top <section>` - Highest-rated patterns
- `/ace-orchestration:ace-status` - Statistics and health check

Configuration:
- `/ace-orchestration:ace-configure` - Setup wizard
- `/ace-orchestration:ace-tune` - Runtime configuration
- `/ace-orchestration:ace-doctor` - Diagnostic tool

## Disabling ACE

ACE subagents are **optional and controllable**. To disable:

**Temporary** (current session):
- Simply tell Claude: "Don't use ACE subagents for this task"

**Permanent** (remove from plugin):
1. Delete `agents/ace-retrieval.md` (disables retrieval)
2. Delete `agents/ace-learning.md` (disables learning)
3. Or disable entire plugin: `/plugin disable ace-orchestration`

**Re-enable**: Restore agent files or re-enable plugin.

## Architecture

**ACE Framework Components**:
- **Generator**: Main Claude instance (executing tasks)
- **Playbook**: Learned patterns (retrieved before work)
- **Reflector**: Server-side Sonnet 4 (analyzes execution traces)
- **Curator**: Server-side Haiku 4.5 (creates pattern updates)
- **Merge**: Non-LLM algorithm (applies incremental updates)

**Benefits**:
- ✅ Automatic learning from execution feedback
- ✅ Token-efficient retrieval (50-92% reduction vs full playbook)
- ✅ Transparent operation (see subagents running)
- ✅ Separate contexts (won't block other plugins)
- ✅ Self-improving over time

## Example Workflow

```
User: "Implement JWT authentication"
    ↓
[ACE Retrieval] Searching playbook...
[ACE Retrieval] Found 3 patterns:
  - Refresh token rotation prevents theft (helpful: 8)
  - HttpOnly cookies for refresh tokens (helpful: 6)
  - Rate limiting for auth endpoints (helpful: 5)
    ↓
Claude implements using retrieved patterns
    ↓
[ACE Learning] Captured 3 new patterns
✅ Saved to playbook for future retrieval
    ↓
Next session: Enhanced playbook with new insights!
```

## See Also

- **README.md** - Full documentation and architecture details
- **docs/** - Technical specifications and guides
- `/ace-orchestration:ace-doctor` - Health diagnostics and troubleshooting

---

**Version**: v4.0.0 (Subagent Architecture)
**Breaking Changes**: Removed hooks and skills (replaced with subagents)
**Migration**: Re-run `/ace-orchestration:ace-claude-init` after upgrade

<!-- ACE_SECTION_END v4.0.0 -->
