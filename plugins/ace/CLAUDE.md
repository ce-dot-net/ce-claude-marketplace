<!-- ACE_SECTION_START v5.4.13 -->
# ACE Plugin

Automatic pattern learning - hooks handle everything.

## How It Works (Automatic)

**Before tasks**: UserPromptSubmit hook searches playbook, injects relevant patterns
**During tasks**: PostToolUse hook accumulates tool calls for learning
**On domain shifts**: PreToolUse hook auto-searches and injects domain-specific patterns
**After tasks**: Stop hook captures learning, sends to server

All hooks run automatically. No manual invocation needed.

## v5.4.13: Device Code Login + Token Expiration Warnings

**New Authentication Flow:**
- `/ace-login`: Browser-based device code authentication (replaces API token entry)
- `/ace-configure`: Now requires login first, uses `ace-cli whoami/orgs/projects`

**Token Expiration Handling:**
- SessionStart hook: Checks auth on new sessions
- UserPromptSubmit hook: Catches 48h standby scenario (laptop sleep → resume)
- Shows clear "Run /ace-login" warnings when token expired

**Migration:** Users with old org tokens must run `/ace-login` then `/ace-configure`.

## v5.4.11: agent_type Capture (Claude Code 2.1.2+)

**Feature**: Captures `agent_type` from Claude Code 2.1.2+ SessionStart input.

**How it works**:
- SessionStart hook reads `agent_type` from input JSON (default: "main")
- Saves to `/tmp/ace-agent-type-{session_id}.txt` for other hooks
- UserPromptSubmit includes `agent-type` attribute in `<ace-patterns>` tag
- Stop hook includes `agent_type` in ExecutionTrace for learning

**Benefit**: Server can weight patterns differently based on agent type (main, refactorer, coder, etc.)

## v5.4.10: Claude Code 2.1.0+ Enhancements

**Added**: Wildcard permissions documentation for smoother workflow
**Added**: `context: fork` to ace-bootstrap for isolated execution

## v5.4.9: Fix GitHub Repository URLs

**Fixed**: GitHub repository URLs consolidated to ace-sdk monorepo:
- Old separate repos (ce-ace-server, ce-ace-cli, ce-ace-mcp) no longer exist
- All URLs now point to `github.com/ce-dot-net/ace-sdk`
- npm package reference `@ce-dot-net/ce-ace-cli` unchanged (for uninstall instructions)

## v5.4.7: CLI Migration & Blocking Detection

**Breaking Change** - Command renamed from `ce-ace` to `ace-cli`:

- Old `@ce-dot-net/ce-ace-cli` package causes 422 API errors (wrong format)
- SessionStart hook now detects and blocks old package installation
- Shows clear migration instructions when blocking

**Migration Required**:
```bash
# Remove old package
npm uninstall -g @ce-dot-net/ce-ace-cli

# Install new package
npm install -g @ace-sdk/cli
```

**New SessionStart Behavior**:
- ✅ `ace-cli` found → Normal operation
- ⚠️ `ace-cli` only found → Warning + continues (transition period)
- ⛔ Old `@ce-dot-net/ce-ace-cli` detected → ACE hooks DISABLED
- ⛔ Version < v3.4.1 → ACE hooks DISABLED

## v5.4.0: Continuous Auto-Search on Domain Shifts

**Feature** - PreToolUse hook **automatically searches** when Claude enters a new domain:

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
- Automatically calls `ace-cli search` with domain filtering
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
| SessionStart | ace_install_cli.sh | CLI detection + **agent_type capture** |
| UserPromptSubmit | ace_before_task.py | Search + inject patterns + agent_type |
| PreToolUse | ace_pretooluse_wrapper.sh | **Auto-search on domain shifts** |
| PostToolUse | ace_posttooluse_wrapper.sh | Accumulate tool calls |
| PermissionRequest | ace_permission_request.sh | Auto-approve safe commands |
| PreCompact | ace_precompact_wrapper.sh | Pattern preservation |
| Stop | ace_stop_wrapper.sh | Capture learning |
| SubagentStop | ace_subagent_stop_wrapper.sh | Learn from subagents |

---

**Version**: v5.4.13 (Device Code Login + Token Expiration Warnings)
**Requires**: Claude Code >= 2.1.2, ace-cli >= 3.5.0 (npm install -g @ace-sdk/cli)

<!-- ACE_SECTION_END v5.4.13 -->
