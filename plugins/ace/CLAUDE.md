<!-- ACE_SECTION_START v5.4.5 -->
# ACE Plugin

Automatic pattern learning - hooks handle everything.

## How It Works (Automatic)

**Before tasks**: UserPromptSubmit hook searches playbook, injects relevant patterns
**During tasks**: PostToolUse hook accumulates tool calls for learning
**On domain shifts**: PreToolUse hook auto-searches and injects domain-specific patterns
**After tasks**: Stop hook captures learning, sends to server

All hooks run automatically. No manual invocation needed.

## v5.4.0: Continuous Auto-Search on Domain Shifts

**New Feature** - PreToolUse hook now **automatically searches** when Claude enters a new domain:

```
User: "Fix the authentication bug"
    ↓
UserPromptSubmit: Auto-search "auth" → injects auth patterns ✅
    ↓
Claude reads /cache/redis.ts
    ↓
PreToolUse detects: auth → cache domain shift
    ↓
PreToolUse: Auto-search "cache" → injects cache patterns ✅
    ↓
Claude now has BOTH auth AND cache patterns in context!
```

**How it works**:
- Detects domain shift from file paths (e.g., reading a `cache/` file after working on `auth/`)
- Automatically calls `ce-ace search` with domain filtering
- Injects patterns via `hookSpecificOutput.additionalContext`
- Shows: "🔄 [ACE] Domain shift: auth → cache. Auto-loaded 5 patterns."

**Fallback**: If search fails or no patterns found, shows reminder instead.

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
| PreToolUse | ace_pretooluse_wrapper.sh | **Auto-search on domain shifts** |
| PostToolUse | ace_posttooluse_wrapper.sh | Accumulate tool calls |
| PermissionRequest | ace_permission_request.sh | Auto-approve safe commands |
| PreCompact | ace_precompact_wrapper.sh | Pattern preservation |
| Stop | ace_stop_wrapper.sh | Capture learning |
| SubagentStop | ace_subagent_stop_wrapper.sh | Learn from subagents |

---

**Version**: v5.4.5 (Event Logging OFF by Default)
**Requires**: ce-ace CLI >= v3.4.1

<!-- ACE_SECTION_END v5.4.5 -->
