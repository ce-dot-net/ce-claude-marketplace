<!-- ACE_SECTION_START v5.2.0 -->
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

## v5.2.0: Per-Task + Delta Learning Architecture

**Key Improvements**:
- **Per-Task Learning**: Captures learning per-task (not per-session)
- **Delta Tracking**: Stop hook captures NEW work since PreCompact
- **Client-Side Filtering**: Garbage trajectories filtered before server
- **User Feedback**: Skip reasons always shown (not silent)

**How Delta Works**:
1. PreCompact captures full task work → records position
2. Stop checks position → captures only NEW steps (delta)
3. Result: No duplicate learning, complete coverage

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

**Version**: v5.2.0 (Per-Task + Delta Learning)
**New in v5.2.0**: Complete architectural refactoring - per-task parsing from last user prompt, position-based delta tracking, client-side garbage filtering, user feedback on skip

<!-- ACE_SECTION_END v5.2.0 -->
