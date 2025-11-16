<!-- ACE_SECTION_START v4.2.5 -->
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

## 🚨 ACE Workflow (Enforced by Hooks)

ACE uses **automated hooks** to ensure proper workflow compliance:

**Automatic Reminders**:
- **Before implementation work**: Hook detects keywords and reminds you to invoke ACE Retrieval
- **During substantial work**: Hook tracks file edits and reminds you to invoke ACE Learning
- **Before compaction**: Hook issues urgent reminder if Learning wasn't invoked

**Your Role**:
- **Respond to hook reminders** by invoking the requested subagent (Task tool)
- **Review retrieved patterns** from ACE Retrieval and apply relevant ones
- **Report pattern usage** to ACE Learning when capturing lessons

**Note**: Hooks guarantee you won't forget workflow steps. Just follow the reminders!

## 🔍 Visibility Instructions (v4.2.3+)

**IMPORTANT - Conversation Transparency**: Provide visibility into ACE workflow execution.

### When Hooks Inject Reminders
1. **Acknowledge** - Mention the hook: "🚨 Hook reminder - invoking ACE Retrieval before implementation"
2. **Announce intent** - Tell user what you're doing: "Searching for authentication patterns..."
3. **Then invoke** - Use Task tool to spawn subagent

### After Subagents Return
1. **Announce completion** - Tell user: "[ACE Retrieval] completed - found {count} patterns"
2. **Summarize results** - Key findings: "Top pattern: {content} (helpful: {score})"
3. **State next steps** - What you'll do: "Applying these patterns to implementation..."

**Note**: Subagents are configured to be verbose (report steps). You see their output and should summarize for the user.

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
[ACE Retrieval] Returns JSON with 3 patterns:
  {
    "patterns": [
      {"id": "ctx-xxx", "content": "Refresh token rotation prevents theft", "helpful": 8, "evidence": [...]},
      {"id": "ctx-yyy", "content": "HttpOnly cookies for refresh tokens", "helpful": 6, "evidence": [...]},
      {"id": "ctx-zzz", "content": "Rate limiting for auth endpoints", "helpful": 5, "evidence": [...]}
    ]
  }
    ↓
Claude reviews JSON patterns:
  - Prioritizes by helpful score (ctx-xxx: 8 > ctx-yyy: 6 > ctx-zzz: 5)
  - Checks evidence arrays for implementation details
  - Notes pattern IDs for later reporting
    ↓
Claude implements using patterns ctx-xxx, ctx-yyy, ctx-zzz
    ↓
[ACE Learning] Asks Claude which patterns were used
Claude responds: "Used ctx-xxx, ctx-yyy, ctx-zzz"
[ACE Learning] Captures new patterns + reports pattern usage
✅ Saved to playbook + pattern effectiveness tracked
    ↓
Next session: Enhanced playbook with usage data!
```

## Workflow Enforcement (v4.2.1+)

**Three-tier hook system ensures ACE workflow compliance:**

### 1. Pre-Implementation Check
- **Hook**: `enforce-ace-retrieval.py` (UserPromptSubmit)
- **Trigger**: Implementation keywords in user prompt
- **Action**: Reminds to invoke ACE Retrieval if not already done

### 2. During-Work Tracking
- **Hook**: `track-substantial-work.py` (PostToolUse)
- **Trigger**: 3+ file edits in recent 50 messages
- **Action**: Reminds to invoke ACE Learning after substantial work

### 3. Pre-Compaction Safety
- **Hook**: `pre-compact-ace-learning.py` (PreCompact)
- **Trigger**: Conversation compaction with uncaptured patterns
- **Action**: Urgent reminder to invoke Learning before trace is lost

### Benefits
- Deterministic workflow enforcement
- Prevents empty playbook
- Non-blocking reminders (never breaks workflow)
- **Research-optimized language** (v4.2.2): Scientifically-validated directive patterns improve compliance +5-10%

**Research**: Based on "Principled Instructions Are All You Need" (2023) and "Should We Respect LLMs?" (2024), hook reminders use explicit task framing ("Your task is"), strengthened imperatives ("You MUST"), affirmative language ("DO invoke"), and respectful tone for optimal LLM instruction-following.

**Opt-out**: Delete hook files from `hooks/` directory

## See Also

- **README.md** - Full documentation and architecture details
- **docs/** - Technical specifications and guides
- `/ace-orchestration:ace-doctor` - Health diagnostics and troubleshooting

---

**Version**: v4.2.5 (Console Output Freezing Fix)
**Fixed in v4.2.5**: Console output freezing resolved - removed transcript-reading PostToolUse hook for real-time output
**Opt-out**: Delete `agents/` or `hooks/` directories to disable ACE components

<!-- ACE_SECTION_END v4.2.5 -->
