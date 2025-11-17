<!-- ACE_SECTION_START v5.1.0 -->
# ACE Plugin

This plugin provides automatic pattern learning using the ACE (Adaptive Context Evolution) framework.

## Installation

**Prerequisites:**
```bash
npm install -g @ce-dot-net/ce-ace-cli
```

Then configure:
```
/ace-configure
```

## How It Works

**Before tasks** - Hook searches playbook → Injects relevant patterns as context
**After tasks** - Hook automatically captures learning → Playbook updates incrementally
**Manual access** - Use slash commands like `/ace-search <query>`

**No subagents, no MCP server** - Just direct CLI calls via hooks!

## Automatic Workflow

### Before Implementation

When you start a task with keywords like `implement`, `build`, `fix`, `debug`, etc., a hook automatically:
- Calls `ce-ace search --stdin` with your prompt
- Retrieves relevant patterns from the playbook
- Injects them as hidden context for Claude
- Shows you a summary: `🔍 [ACE] Found 3 relevant patterns`

### After Completion

**Automatic learning per task** (ACE Research Paper alignment):
- After substantial work completes (Task tool, multiple edits, implementations)
- Hook automatically calls `ce-ace learn --stdin` with execution trace
- Learning captured and sent to server for analysis
- Playbook updates incrementally without manual intervention
- Shows confirmation: `✅ [ACE] Learned from: Implementation task...`

**Backup learning at session end**:
- PreCompact hook captures any missed learning when conversation compacts
- Stop hook ensures learning is saved at session end

**Manual override**: Run `/ace-learn` anytime to capture learning interactively.

## The Playbook

The ACE playbook has 4 sections:

1. **strategies_and_hard_rules** - Architectural patterns, coding principles
2. **useful_code_snippets** - Reusable code patterns with context
3. **troubleshooting_and_pitfalls** - Known issues, gotchas, solutions
4. **apis_to_use** - Recommended libraries, frameworks, integration patterns

Patterns accumulate helpful/harmful scores based on usage feedback.

## Setup

### First-Time Setup

1. **Install CLI**:
   ```bash
   npm install -g @ce-dot-net/ce-ace-cli
   ```

2. **Configure connection**:
   ```
   /ace-configure
   ```

3. **Bootstrap** (optional):
   ```
   /ace-bootstrap
   ```

4. **Start coding**: Hooks auto-run when you implement tasks.

### Manual Commands

**View patterns**:
- `/ace-search <query>` - Semantic search
- `/ace-patterns [section]` - View playbook
- `/ace-status` - Statistics

**Manage patterns**:
- `/ace-learn` - Capture learning
- `/ace-bootstrap` - Initialize from codebase
- `/ace-clear` - Reset playbook

**Configuration**:
- `/ace-configure` - Setup wizard

## Disabling ACE

To disable:
1. Delete hook wrappers from `scripts/`
2. Or disable plugin: `/plugin disable ace`

## Architecture

**Simple & Direct**:
```
Claude Code
    ↓
Hooks (UserPromptSubmit, PreCompact)
    ↓
Bash Wrappers
    ↓
Python Shared Hooks
    ↓
ce-ace CLI (subprocess)
    ↓
ACE Server
```

**Benefits**:
- ✅ No MCP server required
- ✅ No subagent overhead
- ✅ Direct subprocess calls
- ✅ Easy debugging
- ✅ Faster execution
- ✅ Self-improving playbook

## Example Workflow

```
User: "Implement JWT authentication"
    ↓
Hook detects "implement" keyword
    ↓
Calls: ce-ace search --stdin (with user's prompt)
    ↓
Returns: 3 patterns
  • Refresh token rotation prevents theft (+8 helpful)
  • HttpOnly cookies for refresh tokens (+6 helpful)
  • Rate limiting for auth endpoints (+5 helpful)
    ↓
Claude implements using these patterns
    ↓
Task completes → PostToolUse hook automatically:
    ↓
Calls: ce-ace learn --stdin (with execution trace)
    ↓
Server: Reflector → Curator → Playbook merge
    ↓
Shows: "✅ [ACE] Learned from: Implement JWT authentication..."
    ↓
✅ Playbook updated automatically!
    ↓
Next task: Enhanced playbook with new patterns!
```

## Hooks

**Three automatic hooks**:

1. **ace_before_task_wrapper.sh** (UserPromptSubmit)
   - Triggers on: `implement`, `build`, `fix`, `debug`, etc.
   - Calls: `ce-ace search --stdin`
   - Shows: Pattern summaries

2. **ace_task_complete_wrapper.sh** (PostToolUse) **NEW in v5.1.0**
   - Triggers on: Task completion, multiple edits, implementations
   - Calls: `ce-ace learn --stdin` automatically
   - Shows: Learning confirmation
   - Skips: Trivial operations (single reads, basic Q&A)

3. **ace_after_task_wrapper.sh** (PreCompact, Stop)
   - Triggers on: Conversation compaction, session end
   - Captures any missed learning as backup

**Non-blocking** - Never interrupts your workflow!
**Per-task learning** - Aligns with ACE Research Paper (2510.04618v1)

## See Also

- **README.md** - Full documentation
- **docs/** - Technical specifications
- `/ace-status` - Health check

---

**Version**: v5.1.0
**New in v5.1.0**: Automatic per-task learning via PostToolUse hook - aligns with ACE Research Paper
**Install**: `npm install -g @ce-dot-net/ce-ace-cli@1.0.4`

<!-- ACE_SECTION_END v5.1.0 -->
