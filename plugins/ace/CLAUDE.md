<!-- ACE_SECTION_START v5.2.1 -->
# ACE Plugin

Automatic pattern learning - captures what works, retrieves it when needed.

## Installation

```bash
npm install -g @ce-dot-net/ce-ace-cli
/ace-configure
```

## How It Works

**Before tasks**: Hook searches playbook → Injects relevant patterns
**After work**: Captures learning automatically (PreCompact, SubagentStop, Stop hooks)

Triggers on keywords: `implement`, `build`, `fix`, `debug`, `refactor`, etc.

## v5.2.1: Tool-Based Substantial Work Detection

**Critical Fix**: Learning was being skipped even for substantial work (Edit, Write, Bash).
Root cause: Semantic trajectory extraction missed actual tool information.

**Fix**: Now checks `tool_uses` directly as ground truth for substantial work detection.
If any state-changing tool (Edit, Write, Bash, mcp__, NotebookEdit) was used → learning triggers.

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

## Three-Tier Learning

- **PreCompact**: Safety net before context compaction (records position)
- **SubagentStop**: Task agent tasks (on completion)
- **Stop**: End-of-task (captures delta since PreCompact)

---

**Version**: v5.2.1 (Tool-Based Work Detection)
**New in v5.2.1**: Ground truth tool_uses detection fixes learning skip bug

<!-- ACE_SECTION_END v5.2.1 -->
