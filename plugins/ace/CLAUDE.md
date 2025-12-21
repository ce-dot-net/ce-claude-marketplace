<!-- ACE_SECTION_START v5.3.3 -->
# ACE Plugin

Automatic pattern learning - hooks handle everything.

## How It Works (Automatic)

**Before tasks**: UserPromptSubmit hook searches playbook, injects relevant patterns
**During tasks**: PostToolUse hook accumulates tool calls for learning
**After tasks**: Stop hook captures learning, sends to server

All hooks run automatically. No manual invocation needed.

## v5.3.0: Continuous Search Architecture

**New Features**:
- **Domain-Aware Reminders**: PreToolUse hook detects domain shifts from file paths
  - Shows: "💡 [ACE] Domain shift: auth → cache. Consider: /ace-search cache patterns"
- **Pattern Preservation**: PreCompact hook recalls patterns before context compaction
- **Domain Filtering**: `/ace-search` now supports `--allowed-domains` and `--blocked-domains`

**Domain Filtering Examples**:
```bash
# When entering a new domain, get targeted patterns:
/ace-search caching strategies --allowed-domains cache,performance

# Exclude test patterns:
/ace-search patterns --blocked-domains test,debug
```

## Commands (Manual Override)

**Search & View**:
- `/ace-search <query>` - Semantic pattern search (supports domain filtering)
- `/ace-patterns [section]` - View full playbook
- `/ace-status` - Statistics

**Setup & Manage**:
- `/ace-configure` - Setup wizard
- `/ace-bootstrap` - Initialize from codebase
- `/ace-learn` - Manual learning capture
- `/ace-clear` - Reset playbook

## Playbook Sections

1. **strategies_and_hard_rules** - Architectural patterns, coding principles
2. **useful_code_snippets** - Reusable code patterns
3. **troubleshooting_and_pitfalls** - Known issues, solutions
4. **apis_to_use** - Recommended libraries, frameworks

## Hook Architecture (8 Hooks)

| Event | Hook | Purpose |
|-------|------|---------|
| SessionStart | ace_install_cli.sh | Check CLI installation |
| UserPromptSubmit | ace_before_task.py | Search + inject patterns |
| PreToolUse | ace_pretooluse_wrapper.sh | Domain shift reminders |
| PostToolUse | ace_posttooluse_wrapper.sh | Accumulate tool calls |
| PermissionRequest | ace_permission_request.sh | Auto-approve safe commands |
| PreCompact | ace_precompact_wrapper.sh | Pattern preservation |
| Stop | ace_stop_wrapper.sh | Capture learning |
| SubagentStop | ace_subagent_stop_wrapper.sh | Learn from subagents |

---

**Version**: v5.3.3 (Bug Fix: PreToolUse Domain Matching)
**Requires**: ce-ace CLI >= v3.3.0

<!-- ACE_SECTION_END v5.3.3 -->
