# ACE Plugin

**Agentic Context Engineering** - Self-improving Claude Code plugin using automatic pattern learning.

## What's new in v8.0.0

- **Two chains, one state.** On Claude Code >= 2.1.287 an in-process mod (`mod/register.ts`) searches, injects and
  learns; the Python command hooks are the fallback and step aside per duty while the mod's markers are fresh. On
  Team/Enterprise or managed-settings seats Claude Code's built-in guard filters the mod's `classic.*` hooks: the mod
  still searches and injects, and the Python hooks take over tool accumulation, the Stop/SubagentStop learn and the
  session title.
- **Render: a 50/50 split of `budget` and `full`.** Both chains inject the server-ranked top patterns verbatim up to 9,500 chars
  (Claude Code caps hook context at 10,000). The mod can also render `full` (all server patterns, cut by whole
  patterns at 95,000 chars), but only for the share of conversations set by `ACE_RENDER_FULL_PCT` (default 50 =
  half of all conversations; 0 turns full off). `full` costs about 2.1-2.3x input tokens and 2.5x USD per task against budget; within one conversation the
  mod re-injects only patterns not yet injected since the last compaction. 8.0.0 ships the 50/50 split (the ACE server
  has AOP-1333 and AOP-1334 on prod); set `ACE_RENDER_FULL_PCT=0` to stay on budget only.
- **What each learn trace carries:** `render_variant` (`budget` or `full`, omitted when unknown),
  `conversation_id` (the Claude Code session id; subagents share it), the per-task pin as `session_id`, and
  `applied_log_ids` only for patterns with evidence of use (at most 20): ids a Haiku review names (mod chain,
  interactive sessions), or patterns whose distinctive tokens or id appear in the task's tool inputs.
  `playbook_used` lists everything injected.
- **CLI pin.** Claude Code installs the `@ace-sdk/cli` version pinned in `package.json` into the plugin directory. A
  global `ace-cli` at or above the pin is used only as a fallback and `/ace:ace-doctor` marks it untested. Requests
  through the in-process engine (`@ace-sdk/core`) and through the pinned `ace-cli` (4.3.4, via `ACE_CLIENT_ID`) both say
  `X-ACE-Client: claude-code-plugin/<version>`.

## 🚀 Quick Start

### 1. Install the plugin (the ACE CLI comes with it)

```
/plugin install ace --marketplace ce-dot-net/ce-claude-marketplace
```

Claude Code installs the exact `@ace-sdk/cli` version pinned in `package.json` (`package-lock.json`) into the plugin
directory when you install or update the plugin. Plugin and CLI go hand in hand: every plugin version runs the CLI it was
tested with, and a new CLI reaches you with the next plugin update. If the CLI is missing, run `/ace:ace-install-cli`.

**Requirements:** Claude Code >= 2.1.311, Node.js (for the CLI), macOS, Linux or WSL2. Windows is not supported (use WSL2).

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

Every real prompt (not machine prompts, slash commands of ACE itself or very short prompts) is searched with a fresh
per-task pin, and the patterns are injected as hidden context. When the task ends, a detached learn sends the trace
(tools used, outcome, the patterns shown and the ones the answer used) to the ACE server.

## 🎯 Features

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

```
prompt -> mod prompt.submit (or ace_before_task.py) -> engine / ace-cli search --pin-session <task pin>
       -> <ace-patterns> context (budget, or full in the split)
task end -> mod turn.complete (or ace_after_task.py) -> detached ace-cli/engine learn --no-stream
       (render_variant, conversation_id, applied_log_ids of the used patterns)
```

State lives under the plugin data dir (`~/.claude/plugins/data/ace-*`), project logs under `.claude/data/logs/`.
Details: `docs/technical/ARCHITECTURE.md`.

### Pattern Learning (Manual)

After completing work, run `/ace-learn`:
1. Opens interactive prompt
2. Asks for task description, success status, key steps, lessons
3. Calls `ace-cli learn --interactive`
4. Saves patterns to playbook
5. Available for next session!

## 🔧 Configuration

### Render knobs (environment)

- `ACE_RENDER_FULL_PCT` (default 50, 0 = off): share of conversations the mod renders `full`; see the cost note above.
  The ACE server can switch the share for everyone without a plugin release: a search response field `render_full_pct` (0-100, kept for 7 days in `render-full-pct.json`) applies when the env is unset.
- `ACE_ENGINE=cli`: never use the in-process engine.

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

Run `/ace:ace-install-cli` (it reports which CLI is used and repairs a missing install).

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

1. **ace-cli:** installed with the plugin; run `/ace:ace-install-cli` if it is missing.

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

Run `/ace:ace-doctor`. Hook rows go to `.claude/data/logs/ace-relevance.jsonl` in the project.

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

**Version**: v8.0.1
**Maintainer**: CE.NET Team
**Requires**: Claude Code >= 2.1.311, ace-cli pinned in package.json (installed with the plugin; a global ace-cli >= the pin is an untested fallback). Windows not supported (WSL2 works).
**Architecture**: mod + Python hooks + CLI/engine (no MCP)
