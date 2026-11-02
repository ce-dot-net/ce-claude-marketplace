# ACE Plugin

**Agentic Context Engineering** - Self-improving Claude Code plugin using automatic pattern learning.

## 🎯 What's New in v5.1.17

**Critical Bug Fixes - User-Reported Issues**

- ✅ **ace-configure** - Added global config verification (7 bugs fixed: env pollution, directory creation, validation errors, project count check, jq dependency)
- ✅ **ace-status** - Fixed "empty 0 playbooks" bug, now works with global config, better error messages
- ✅ **SessionStart Hook** - Fixed bash eval parse errors, removed interactive prompts blocking sessions
- ✅ **Stop Hook** - Fixed organization configuration errors, added pre-checks for CLI and config
- ✅ **ace-install-cli** - Fixed complex bash eval errors, simplified all multi-line commands

## 🚀 Quick Start

### 1. Install ACE CLI

```bash
npm install -g @ace-sdk/cli
```

**Requirements:** Claude Code >= 2.1.300, ace-cli >= 4.1.2

**Statusline:** `~/.claude/ace_statusline.sh` is a user copy of the plugin script; refresh it after a plugin update with `/ace:ace-statusline-setup update`.

### 2. Enable Plugin

The plugin is part of the ce-dot-net marketplace and auto-loads when you enable the marketplace in Claude Code.

### 3. Configure

```bash
# In Claude Code:
/ace-configure
```

Follow the interactive wizard to set up your ACE server connection.

### 4. Bootstrap (Optional)

```bash
/ace-bootstrap
```

Analyzes your codebase to create initial patterns.

### 5. Start Coding!

Hooks automatically:
- **Search** patterns when you start tasks (`implement`, `build`, `fix`, etc.)
- **Remind** you to capture learning after work completion

## 🎯 Features

### Automatic Workflow

**Before Implementation:**
- Hook detects keywords: `implement`, `build`, `create`, `fix`, `debug`, `refactor`, etc.
- Calls `ace-cli search --stdin --pin-session` with your prompt
- Pins patterns to session (24-hour TTL, survives context compaction)
- Injects relevant patterns as hidden context
- Shows summary: `🔍 [ACE] Found 3 relevant patterns`

**During Work:**
- Patterns persist in session storage (`~/.ace-cache/sessions.db`)
- Fast recall (~10ms) when context compacts

**After Completion:**
- Hook auto-captures learning with rich context (task description, files modified, outcomes)
- Shows: `✅ [ACE] Learned from: [task description]...`
- Patterns saved with specific, valuable context (no generic messages)

### Slash Commands

**View Patterns:**
- `/ace-search <query>` - Semantic search for patterns
- `/ace-patterns [section]` - View full playbook
- `/ace-status` - Show statistics

**Manage Patterns:**
- `/ace-learn` - Capture learning interactively
- `/ace-bootstrap` - Initialize from codebase
- `/ace-clear` - Reset playbook

**Configuration:**
- `/ace-configure` - Setup wizard

### The Playbook

**4 Sections:**
1. **strategies_and_hard_rules** - Architectural patterns, coding principles
2. **useful_code_snippets** - Reusable code patterns
3. **troubleshooting_and_pitfalls** - Known issues, gotchas, solutions
4. **apis_to_use** - Recommended libraries, frameworks

Patterns accumulate **helpful/harmful scores** based on usage feedback.

## 🏗️ Architecture

### Simple & Direct

```
User types: "implement JWT auth"
    ↓
Hook (UserPromptSubmit) detects "implement"
    ↓
Bash Wrapper (ace_before_task_wrapper.sh)
    ↓
Python Shared Hook (ace_before_task.py)
    ↓
Subprocess: ace-cli search --stdin
    ↓
ACE Server
    ↓
Returns: 3 relevant patterns
    ↓
Claude sees hidden context + visible summary
    ↓
Implements using learned patterns!
```

### File Structure

```
plugins/ace/
├── scripts/
│   └── ace_*_wrapper.sh               # thin shims -> shared-hooks/*.py
├── hooks/
│   └── hooks.json                     # hook topology (see ARCHITECTURE.md)
├── commands/
│   ├── ace-search.md                  # CLI wrappers
│   ├── ace-patterns.md
│   ├── ace-status.md
│   ├── ace-learn.md
│   ├── ace-bootstrap.md
│   ├── ace-configure.md
│   └── ace-clear.md
└── CLAUDE.md                          # Plugin documentation

shared-hooks/ (marketplace root)
├── ace_before_task.py                 # Search hook
├── ace_after_task.py                  # Learn reminder hook
└── utils/
    ├── ace_cli.py                     # CLI subprocess wrapper
    └── ace_context.py                 # Context resolution
```

## 📖 How It Works

### Pattern Retrieval (Automatic)

When you start a task with implementation keywords, the hook:
1. Reads your prompt from stdin
2. Calls `ace-cli search --stdin` with full prompt text
3. Receives JSON with relevant patterns
4. Injects patterns as `<ace-patterns>` block for Claude
5. Shows you a summary of what was found

**Example:**
```
You: "implement JWT authentication"
    ↓
🔍 [ACE] Found 3 relevant patterns:
• Refresh token rotation prevents theft (+8 helpful)
• HttpOnly cookies for refresh tokens (+6 helpful)
• Rate limiting for auth endpoints (+5 helpful)
    ↓
Claude uses these patterns to implement!
```

### Pattern Learning (Manual)

After completing work, run `/ace-learn`:
1. Opens interactive prompt
2. Asks for task description, success status, key steps, lessons
3. Calls `ace-cli learn --interactive`
4. Saves patterns to playbook
5. Available for next session!

## 🔧 Configuration

### Recommended Settings (Claude Code 2.1.0+)

Add to your `~/.claude/settings.json` to auto-approve ACE CLI operations:

```json
{
  "permissions": {
    "allow": [
      "Bash(ace-cli *)",
      "Bash(uv run *)"
    ]
  }
}
```

This eliminates permission prompts for ACE operations, providing a smoother workflow.

### Server Connection

The `/ace-configure` wizard sets up:
- **Server URL** - ACE server endpoint
- **API Token** - Your authentication token
- **Organization ID** - Auto-fetched from server
- **Project ID** - Selected from available projects

Config stored in: `~/.config/ace/config.json`

### Project Context

Each project needs `.claude/settings.json`:
```json
{
  "orgId": "org_xxxxx",
  "projectId": "prj_xxxxx"
}
```

Created automatically by `/ace-configure`.

## 🛠️ Troubleshooting

### "ace-cli not found"

Install the CLI:
```bash
npm install -g @ace-sdk/cli
```

### "No .claude/settings.json"

Run `/ace-configure` to create project config.

### "ACE authentication failed"

Your token expired. Run `/ace-configure` to update.

### Hook not firing

Check hooks.json exists and wrappers are executable:
```bash
ls -la plugins/ace/scripts/*.sh
chmod +x plugins/ace/scripts/*.sh
```

## 🔄 Migration from v4.x

### Breaking Changes

- ❌ MCP server no longer used
- ❌ Subagents removed (no more `Task` tool invocations)
- ❌ `mcp__ace-pattern-learning__*` tools gone

### Migration Steps

1. **Install ace-cli:**
   ```bash
   npm install -g @ace-sdk/cli
   ```

2. **Update plugin:**
   ```bash
   /plugin update ace
   ```

3. **Reconfigure:**
   ```bash
   /ace-configure
   ```

4. **Verify:**
   ```bash
   /ace-status
   ```

5. **Optional - Remove old MCP config:**
   ```bash
   # Edit ~/.claude/mcp/config.json
   # Remove "ace-pattern-learning" entry
   ```

### What Changed

**Before (v4.2.6):**
```
Claude → Task Tool → ACE Retrieval Subagent → MCP Tools → ACE Server
Claude → Task Tool → ACE Learning Subagent → MCP Tools → ACE Server
```

**After (v5.0.0+):**
```
Claude → Hooks → ace-cli → ACE Server
Claude → Commands → ace-cli → ACE Server
```

## 🧪 Development

### Testing Hooks

```bash
# Test before-task hook
echo '{"prompt":"implement auth"}' | \
  ./scripts/ace_before_task_wrapper.sh

# Test after-task hook
echo '{"hook_event_name":"Stop"}' | \
  ./scripts/ace_stop_wrapper.sh
```

### Debugging

Set debug mode:
```bash
export DEBUG=ace:*
/ace-search test query
```

Check logs:
```bash
tail -f ~/.ace-logs/hooks.log
```

## 📚 Examples

### Example 1: Authentication Implementation

```
You: "Implement JWT authentication with refresh tokens"

Hook fires:
🔍 [ACE] Found 3 relevant patterns:
• Refresh token rotation prevents theft (+8)
• HttpOnly cookies for refresh tokens (+6)
• Rate limiting for auth endpoints (+5)

Claude implements using these patterns...

After completion:
📚 [ACE] Run /ace-learn to capture patterns

You: /ace-learn
Task: Implemented JWT auth with refresh rotation
Success: yes
Key steps: Added HttpOnly cookies, rate limiting, token expiry
Lessons: Rotation prevents token theft, always use HttpOnly
✅ Patterns saved!
```

### Example 2: Debugging

```
You: "Debug async test failures"

Hook fires:
🔍 [ACE] Found 2 relevant patterns:
• Intermittent async failures mean missing await (+7)
• Check cleanup functions for async operations (+5)

Claude checks for missing await...
Found it! Fixed the bug.

You: /ace-learn
Task: Fixed intermittent async test failures
Success: yes
Key steps: Found missing await in cleanup function
Lessons: Always check async cleanup, use await on all promises
✅ Patterns saved!
```

## 🤝 Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) in the marketplace root.

## 📄 License

MIT License - See [LICENSE](../../LICENSE)

## 🔗 Links

- **ACE SDK**: https://github.com/ce-dot-net/ace-sdk
- **ACE SDK (CLI)**: https://github.com/ce-dot-net/ace-sdk
- **Marketplace**: https://github.com/ce-dot-net/ce-claude-marketplace
- **Documentation**: See `docs/` directory

---

**Version**: v5.4.7 (CLI Migration + Blocking Detection)
**Status**: Active Development
**Maintainer**: CE.NET Team
**Requires**: Claude Code >= 2.1.300, ace-cli >= 4.1.2 (npm install -g @ace-sdk/cli)
**Architecture**: Hooks + CLI (no MCP)
