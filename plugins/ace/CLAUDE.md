<!-- ACE_SECTION_START v5.3.1 -->
# ACE Plugin

Automatic pattern learning - captures what works, retrieves it when needed.

## Installation

```bash
npm install -g @ce-dot-net/ce-ace-cli
/ace-configure
```

## How It Works

**Before tasks**: Hook searches playbook → Injects relevant patterns
**After main agent work**: PostToolUse detects task completion → Captures learning (NEW in v5.3.1!)
**After Task agents complete**: SubagentStop captures learning from substantial work (v5.3.0)
**At session end/compact**: Stop hook captures session-wide learning

Triggers on keywords: `implement`, `build`, `fix`, `debug`, `refactor`, etc.

## Playbook Sections

1. **strategies_and_hard_rules** - Architectural patterns, coding principles
2. **useful_code_snippets** - Reusable code patterns
3. **troubleshooting_and_pitfalls** - Known issues, solutions
4. **apis_to_use** - Recommended libraries, frameworks

## Commands

**Search & View**:
- `/ace-search <query>` - Find relevant patterns
- `/ace-patterns [section]` - View playbook
- `/ace-status` - Statistics

**Setup & Manage**:
- `/ace-configure` - Setup wizard
- `/ace-bootstrap` - Initialize from codebase
- `/ace-learn` - Manual learning capture
- `/ace-clear` - Reset playbook

## Quick Start

1. Install: `npm install -g @ce-dot-net/ce-ace-cli`
2. Configure: `/ace-configure`
3. Optional: `/ace-bootstrap` to seed from codebase
4. Start coding - hooks run automatically!

**Messages you'll see**:
- `🔍 [ACE] Found 3 relevant patterns` - Before tasks
- `✅ [ACE] Auto-approved: ce-ace search` - Permission auto-approval
- `📚 [ACE] Automatically capturing learning...` - At session end

## Debugging & Logging

**Hook Event Logs** (v5.2.0+):
- Location: `.claude/data/logs/ace-{event}.jsonl`
- Events: `ace-stop.jsonl`, `ace-precompact.jsonl`, `ace-userpromptsubmit.jsonl`, `ace-subagent-stop.jsonl`, `ace-posttooluse.jsonl`
- Errors: All errors also logged to `ace-errors.jsonl`

**View Logs**:
```bash
# Raw JSONL
cat .claude/data/logs/ace-stop.jsonl | jq

# With analyzer tool
uv run shared-hooks/utils/ace_log_analyzer.py --event-type Stop
uv run shared-hooks/utils/ace_log_analyzer.py --stats
uv run shared-hooks/utils/ace_log_analyzer.py --errors --hours 24
```

**Log Fields**:
- `timestamp` - ISO 8601 timestamp
- `event_type` - Hook name (Stop, PreCompact, UserPromptSubmit, SubagentStop, PostToolUse)
- `phase` - START or END
- `execution_time_ms` - Hook execution time (END phase only)
- `exit_code` - 0=success, non-zero=failure
- `error` - Error message (if failure)

### PostToolUse Task Detection (v5.3.1+)

**What**: Detects when main agent completes tasks and captures learning immediately
**Log**: `.claude/data/logs/ace-posttooluse.jsonl`
**State**: `.claude/data/logs/ace-task-state.json`

**Detection Heuristics** (OR logic - any one triggers):
- **Tool Sequence** (3+ tools) - Substantial work indicator
- **User Confirmation** ("thanks", "done", "perfect") - Explicit completion signal
- **Time-Based** (30s idle) - Natural pause after work
- **Todo Completion** (all todos done) - Clear task finish signal
- **Git Commit** (successful commit) - Work unit boundary

**View Logs**:
```bash
# View PostToolUse events
cat .claude/data/logs/ace-posttooluse.jsonl | jq

# View detection state
cat .claude/data/logs/ace-task-state.json | jq

# Analyze with tool
uv run shared-hooks/utils/ace_log_analyzer.py --event-type PostToolUse
```

**When It Fires**:
- ✅ Main agent uses 3+ tools (Edit, Write, Bash, etc.)
- ✅ User says confirmation keywords
- ✅ Natural pause after work (30s)
- ✅ All todos completed
- ✅ Git commit made

### SubagentStop Events (v5.3.0+)

**What**: Captures learning after each Task agent completes
**Log**: `.claude/data/logs/ace-subagent-stop.jsonl`
**Transcripts**: `.claude/data/logs/ace-subagent-{agent-type}-{timestamp}.json`

**View Logs**:
```bash
# View SubagentStop events
cat .claude/data/logs/ace-subagent-stop.jsonl | jq

# Analyze with tool
uv run shared-hooks/utils/ace_log_analyzer.py --event-type SubagentStop --stats

# Find slow subagents
cat .claude/data/logs/ace-subagent-stop.jsonl | jq 'select(.execution_time_ms > 5000)'
```

**When It Fires**:
- ✅ Task agent completes (implementation, debugging, refactoring)
- ✅ Subagent has substantial trajectory (tool uses, decisions)
- ❌ Not every tool use (only Task agents)

## New in v5.3.x

**Complete After-Task Learning System**:

**v5.3.1 - PostToolUse Hook**:
- ✅ **Main Agent Detection** - Intelligent heuristics detect task completion
- ✅ **5 Detection Methods** - Tool sequence, user confirmation, time-based, todos, commits
- ✅ **OR Logic** - Any one heuristic triggers (flexible detection)
- ✅ **Silent Operation** - No user-facing messages
- ✅ **Confidence Scoring** - Track which heuristics work best (0.60-0.95)

**v5.3.0 - SubagentStop Hook**:
- ✅ **Task Agent Detection** - Captures learning after each Task agent completes
- ✅ **Full Context** - Has complete subagent transcript
- ✅ **Agent Tracking** - Saves transcripts per agent type

**Three-Tier Architecture**:
- PostToolUse: Main agent tasks (immediate)
- SubagentStop: Task agent tasks (on completion)
- Stop: Session work (on close)

---

**Version**: v5.3.1
**Requires**: ce-ace CLI v1.0.13+

<!-- ACE_SECTION_END v5.3.1 -->
