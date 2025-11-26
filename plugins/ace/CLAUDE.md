<!-- ACE_SECTION_START v5.1.22 -->
# ACE Plugin

Automatic pattern learning - captures what works, retrieves it when needed.

## Installation

```bash
npm install -g @ce-dot-net/ce-ace-cli
/ace-configure
```

## How It Works

**Before tasks**: Hook searches playbook → Injects relevant patterns
**After work**: Captures learning automatically (PostToolUse, SubagentStop, Stop hooks)

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

## Three-Tier Learning

- **PostToolUse**: Main agent tasks (heuristic-based detection)
- **SubagentStop**: Task agent tasks (on completion)
- **Stop**: Session work (on close)

---

**Version**: v5.1.22 (PostToolUse Hook Fix)
**New in v5.1.22**: Fixed jq syntax error when task detector returns comma-separated triggers

<!-- ACE_SECTION_END v5.1.22 -->
