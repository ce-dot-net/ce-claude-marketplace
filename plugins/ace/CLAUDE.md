<!-- ACE_SECTION_START v5.3.0 -->
# ACE Plugin

Automatic pattern learning - captures what works, retrieves it when needed.

## Installation

```bash
npm install -g @ce-dot-net/ce-ace-cli
/ace-configure
```

## How It Works

**Before tasks**: Hook searches playbook → Injects relevant patterns
**After Task agents complete**: SubagentStop captures learning from substantial work (NEW in v5.3.0!)
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
- Events: `ace-stop.jsonl`, `ace-precompact.jsonl`, `ace-userpromptsubmit.jsonl`, `ace-subagent-stop.jsonl`
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
- `event_type` - Hook name (Stop, PreCompact, UserPromptSubmit, SubagentStop)
- `phase` - START or END
- `execution_time_ms` - Hook execution time (END phase only)
- `exit_code` - 0=success, non-zero=failure
- `error` - Error message (if failure)

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

## New in v5.3.0

**SubagentStop Hook for After-Task Learning**:
- ✅ **Immediate Learning** - Capture patterns after each Task agent completes
- ✅ **Non-Intrusive** - Only fires for substantial subagent work
- ✅ **Full Context** - Has complete subagent transcript with all decisions
- ✅ **Agent Tracking** - Saves transcripts per agent type
- ✅ **Dual Hook Strategy** - SubagentStop (after tasks) + Stop (session end)

---

**Version**: v5.3.0
**Requires**: ce-ace CLI v1.0.13+

<!-- ACE_SECTION_END v5.3.0 -->
