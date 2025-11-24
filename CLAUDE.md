# ACE Marketplace Project

## ACE Plugin Instructions

<!-- ACE_SECTION_START v5.1.19 -->
# ACE Plugin Instructions

Automatic pattern learning plugin. Hooks inject learned patterns before tasks, capture new patterns after completion.

## Commands Available

**Pattern Access:**

- `/ace:ace-search <query>` - Search for relevant patterns
- `/ace:ace-patterns [section]` - View all patterns
- `/ace:ace-top [section] [limit]` - Get highest-rated patterns
- `/ace:ace-status` - Show statistics

**Pattern Capture:**

- `/ace:ace-learn` - Capture learning from recent work (uses AskUserQuestion prompts)

**Setup:**

- `/ace:ace-configure` - Interactive setup wizard
- `/ace:ace-bootstrap` - Initialize playbook from codebase
- `/ace:ace-install-cli` - Install ce-ace CLI tool interactively

**Management:**

- `/ace:ace-export-patterns [file]` - Export to JSON
- `/ace:ace-import-patterns <file>` - Import from JSON
- `/ace:ace-clear` - Clear playbook
- `/ace:ace-doctor` - Run diagnostics

## Guidelines

**When hooks inject patterns:**

- Use them to inform your work
- Don't quote them verbatim unless asked

**When user asks "how do we handle X?":**

- Suggest `/ace:ace-search <X>`

**After substantial work:**

- Remind user they can capture learning with `/ace:ace-learn`

**For /ace:ace-learn command:**

- Use AskUserQuestion tool for interactive prompts
- Collect: task description, success/failure, lessons learned

## Playbook Sections

Patterns are organized into:

- `strategies_and_hard_rules` - Architectural patterns, principles
- `useful_code_snippets` - Reusable code patterns
- `troubleshooting_and_pitfalls` - Known issues, solutions
- `apis_to_use` - Recommended libraries, frameworks

## Technical Notes

- **Architecture**: Hooks + ce-ace CLI (no MCP server)
- All commands use `ce-ace` CLI subprocess calls
- Hooks run automatically on trigger keywords: `implement`, `build`, `fix`, `debug`, `refactor`, etc.
- Settings in `.claude/settings.json` - supports both `{orgId, projectId}` and `{env: {ACE_ORG_ID, ACE_PROJECT_ID}}` formats
- **SessionStart hook**: Auto-checks ce-ace CLI installation (silent when installed)

---

**Version**: v5.1.19
**Requires**: ce-ace CLI >= v1.0.14
**Architecture**: Hooks + CLI (no MCP)

<!-- ACE_SECTION_END v5.1.19 -->
