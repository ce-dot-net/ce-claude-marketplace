<!-- ACE_SECTION_START v5.2.4 -->
# ACE Plugin

Automatic pattern learning - captures what works, retrieves it when needed.

## Installation

```bash
npm install -g @ace-sdk/cli
/ace-configure
```

## How It Works

**Before tasks**: Hook searches playbook → Injects relevant patterns
**After work**: Captures learning automatically (PostToolUse + Stop hooks)

Triggers on keywords: `implement`, `build`, `fix`, `debug`, `refactor`, etc.

## v5.2.4: Learning Stats Display Fix

**Updates**:
- Fix: Only show "📚 ACE Learning:" header when stats are available
- Prevents empty header when no patterns created/updated/pruned

**Architecture**: PostToolUse → SQLite → Stop hook queries accumulated tools.

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

1. Install: `npm install -g @ace-sdk/cli`
2. Configure: `/ace-configure`
3. Optional: `/ace-bootstrap` to seed from codebase
4. Start coding - hooks run automatically!

## Two-Hook Architecture

- **PostToolUse**: Accumulates every tool call to SQLite (ground truth)
- **Stop**: Queries accumulated tools → builds trajectory → sends to server

---

**Version**: v5.2.4 (Stats Display Fix)
**New in v5.2.4**: Only show stats header when patterns are created/updated

<!-- ACE_SECTION_END v5.2.4 -->
