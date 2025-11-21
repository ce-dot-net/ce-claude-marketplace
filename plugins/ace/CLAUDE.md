<!-- ACE_SECTION_START v5.1.12 -->
# ACE Plugin

Automatic pattern learning - captures what works, retrieves it when needed.

## Installation

```bash
npm install -g @ce-dot-net/ce-ace-cli
/ace-configure
```

## How It Works

**Before tasks**: Hook searches playbook → Injects relevant patterns
**At session end/compact**: Hook captures learning from conversation → Playbook updates automatically

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

## New in v5.1.12

**Dual-Hook Learning Strategy**:
- ✅ **Transcript Parsing** - Stop hook now reads .jsonl transcript for complete learning capture
- ✅ **PreCompact + Stop** - Safety net before compaction + true end-of-task learning
- ✅ **Debug Logging** - ACE_DEBUG_HOOKS=1 flag for hook event diagnostics

---

**Version**: v5.1.12
**Requires**: ce-ace CLI v1.0.13+

<!-- ACE_SECTION_END v5.1.12 -->
