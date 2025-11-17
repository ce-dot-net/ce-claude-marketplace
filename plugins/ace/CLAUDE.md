<!-- ACE_SECTION_START v5.0.3 -->
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
**After tasks** - Hook reminds to capture learning → Run `/ace-learn`
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

When conversation compacts, a hook reminds:
```
📚 [ACE] Reminder: Capture learning from this session
   /ace-learn
```

Run `/ace-learn` to capture patterns interactively.

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
Work complete → PreCompact hook reminds:
"📚 [ACE] Run /ace-learn to capture patterns"
    ↓
User runs: /ace-learn
    ↓
Calls: ce-ace learn --interactive
    ↓
✅ Patterns saved to playbook
    ↓
Next session: Enhanced playbook!
```

## Hooks

**Two simple hooks**:

1. **ace_before_task_wrapper.sh** (UserPromptSubmit)
   - Triggers on: `implement`, `build`, `fix`, `debug`, etc.
   - Calls: `ce-ace search --stdin`
   - Shows: Pattern summaries

2. **ace_after_task_wrapper.sh** (PreCompact)
   - Triggers on: Conversation compaction
   - Shows: Reminder to run `/ace-learn`

**Non-blocking** - Never interrupts your workflow!

## See Also

- **README.md** - Full documentation
- **docs/** - Technical specifications
- `/ace-status` - Health check

---

**Version**: v5.0.3
**New in v5.0.3**: Hook visibility improvements + server-side threshold control
**Install**: `npm install -g @ce-dot-net/ce-ace-cli`

<!-- ACE_SECTION_END v5.0.3 -->
