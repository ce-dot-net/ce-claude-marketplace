# ACE Plugin

**Agentic Context Engineering** - Self-improving Claude Code plugin using automatic pattern learning.

## 8.1.4: no silent trace loss

A learned trace that could not be sent is no longer lost without a trace of its own. When the server did not store
it (or, with the engine's stable `Idempotency-Key`, might not have), it is kept in a private, signed queue under the
plugin data dir and sent again at the next session start or after the next good learn, within 23 h. The decision reads
the server's `stored`/`duplicate` answer, never its message. A rejected trace (401/403/422/4xx) is never sent again. Every outcome is a row in
`ace-relevance.jsonl` (`learn_requeued`, `learn_replayed`, `learn_lost`, `learn_expired`), and `/ace:ace-doctor` shows
the queue. `ACE_TRACE_QUEUE=0` turns the queue off. Limits: a trace is still lost when the machine is off before the
learn finished, the plugin data dir is wiped, the queue is full (200 traces / 50 MB), the trace is older than 23 h, or
the ace-cli fallback (no engine) got a 5xx or a timeout. Details: docs/technical/ARCHITECTURE.md "Trace delivery
(8.1.4)".

## 8.1.3: task outcome

`result.success` in a learned trace is the task's END outcome: a grep without a match, a red test that later went
green or a retried call no longer fail the task, and stderr alone is no failure. `result.failed_steps` counts the
failed steps (informational). Bash trajectory actions start with the command family (`gh pr merge :: ...`) and
secrets are redacted (fail-closed after a keyword, a known flag or a known token prefix). Known limit: a secret
without a keyword or known prefix cannot be recognized, so do not write secrets into commands. The rule:
docs/technical/ARCHITECTURE.md "Task outcome (8.1.3)".

## What's new in 8.1.0

- **One binding core.** Every hook (both chains), every command and the statusline take org/project from one resolver
  (`mod/context/`, `shared-hooks/utils/ace_project_context.py`, contract: the SDK spec `project-context`). Precedence:
  `--org/--project` > tracked `.ace/config.json` (walk-up to the git root, then the main checkout of a worktree) >
  legacy `.claude/settings.json` env (same walk) > `ACE_ORG_ID`/`ACE_PROJECT_ID` > the per-machine remote map >
  unbound. There is never a default project. Every `ace-cli` call carries `--org/--project` explicitly.
- **Zero steps for repos that are already bound:** worktrees and subfolders resolve via the main checkout; a legacy
  binding is adopted into `.ace/config.json` at the main root automatically (never staged or committed; opt out
  `ACE_AUTO_ADOPT=0`), and a file-bound remote teaches the per-machine remote map, so a fresh clone binds by itself.
- **Status only on problems.** One background `ace-cli status` per session; nothing is shown when ok. On a problem:
  `ACE ▼ <state>` in the status area and one band above the prompt with exactly one action (Verbinden, Anmelden,
  Anderes wählen, Bereinigt neu schreiben, ace-cli installieren). A device login starts only on the button press.
  `Server nicht erreichbar` heals itself (8.2.4): it is checked again in the background (15 s, 30 s, 60 s, then every
  5 min, at most 30 times) and cleared by the first successful search; the other states stay until you act.
  The Python chain shows one line per session instead.
- **Model-free commands.** Where mods run, every `/ace:ace-*` command is answered by the mod without the model;
  writing commands show a preview and run only after the band's confirm button. The markdown commands are the
  fallback and call the one entrypoint `scripts/ace-context`.
- **Logs keyed to the repo root**, so subfolders and worktrees share one `.claude/data/logs/ace-relevance.jsonl`,
  which gets one `context` row (source, path, state) per session.

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
- **What each learn trace carries:** `render_variant` (`budget` or `full`, omitted when unknown; the Python chain
  always renders budget), `render_path` (`mod` or `python`, the chain that rendered; only next to `render_variant`),
  `conversation_id` (the Claude Code session id; subagents share it), the per-task pin as `session_id`; mod chain only,
  each omitted when unknown: `interactive` (session.start `isInteractive`), `prompt_origin` (the conversation's first
  prompt's origin kind, max 64 chars, `unclassified` without one) and `human_prompt_count` (composer + bridge prompts
  so far, a lower bound); both stored per Claude Code session id, so they survive a reload/resume and never cross a
  `/clear` (a conversation begun before 8.2.2 reports its first prompt after the update); and
  `applied_log_ids` only for patterns with evidence of use (at most 20): ids a Haiku review names (mod chain,
  interactive sessions), or patterns whose distinctive tokens or id appear in the task's tool inputs.
  `playbook_used` lists everything injected.
- **What each search carries (8.2.3, mod chain, engine path only):** `interactive` and `human_prompt_count` in the
  `POST /patterns/search` body, same source and rules as the trace fields above (each only when known, `false`/`0`
  kept); the main search counts the current prompt. The ace-cli fallback and the Python chain send neither.
- **CLI pin.** Claude Code installs the `@ace-sdk/cli` version pinned in `package.json` into the plugin directory. A
  global `ace-cli` at or above the pin is used only as a fallback and `/ace:ace-doctor` marks it untested. Requests
  through the in-process engine (`@ace-sdk/core`) and through the pinned `ace-cli` (4.4.2, via `ACE_CLIENT_ID`) both say
  `X-ACE-Client: claude-code-plugin/<version>`.

## 🚀 Quick Start

### 1. Install the plugin (the ACE CLI comes with it)

```
/plugin install ace --marketplace ce-dot-net/ce-claude-marketplace
```

Claude Code installs the exact `@ace-sdk/cli` version pinned in `package.json` (`package-lock.json`) into the plugin
directory when you install or update the plugin. Plugin and CLI go hand in hand: every plugin version runs the CLI it was
tested with, and a new CLI reaches you with the next plugin update. If Claude Code has not installed it (a fresh marketplace
install), the next session start installs it in the background (`npm ci --ignore-scripts` from the lockfile, then
`npm rebuild better-sqlite3`, in the plugin directory; no message, no restart; one retry per plugin version per hour after
a failure, with one band line and `[Erneut versuchen]`). `ACE_AUTO_INSTALL=0` turns that off: ACE then tells you and installs
only after `/ace:ace-install-cli` and its confirm button. Without npm/node, offline-managed or read-only: the same message.
If the CLI is there but better-sqlite3's native binding is missing or broken (8.1.2), the same background step runs only
`npm rebuild better-sqlite3`; if that fails ACE works RAM-only, with no band: `/ace:ace-doctor` shows `SQLite cache: active | off (reason)`.

**Requirements:** Claude Code >= 2.1.311, Node.js (for the CLI), macOS, Linux or WSL2. Windows is not supported (use WSL2).

**Statusline:** `~/.claude/ace_statusline.sh` is a user copy of the plugin script (install/refresh with `/ace:ace-statusline-setup update`). It reads the repo-root log through the plugin core, so subfolders and worktrees show the same task; a binding problem shows `ACE ▼ <state>` instead of the stats.

### 2. Enable Plugin

The plugin is part of the ce-dot-net marketplace and auto-loads when you enable the marketplace in Claude Code.

### 3. Bind the repo

```bash
# In Claude Code:
/ace:ace-login       # device login (once per machine)
/ace:ace-configure   # writes the tracked .ace/config.json {orgId, projectId} at the repo root
```

Commit `.ace/config.json`: every clone, worktree and subfolder is then bound. Details: `docs/guides/CONFIGURATION.md`.

### 4. Bootstrap (Optional)

```bash
/ace-bootstrap
```

Analyzes your codebase to create initial patterns. The legacy modes send raw function bodies (up to 50 source files), docs and
commit diffs unredacted; the preview says so. For a narrow, redacted path (8.2.0) use
`/ace:ace-bootstrap --backfill-only`: fix/revert commits and merged PRs become redacted learning traces (only titles, file
names and redacted texts leave the machine), sent when the server announces `bootstrap_backfill`. A job poll that loses
the network or gets 502/503/504 is retried (up to 5 times, 12.5 min in all) before the run stops (8.2.4). Details:
`commands/ace-bootstrap.md`.

### 5. Start Coding!

Every real prompt (not machine prompts, slash commands of ACE itself or very short prompts) is searched with a fresh
per-task pin, and the patterns are injected as hidden context. When the task ends, a detached learn sends the trace
(tools used, outcome, the patterns shown and the ones the answer used) to the ACE server.

## 🎯 Features

### Slash Commands

Where mods run these are answered by the mod without the model (output capped at about 60 KB); writes need the
confirm button. Elsewhere the markdown fallback runs.

| Command | What it does |
|---|---|
| `/ace` | Overview: the binding, its state, every command |
| `/ace:ace-search <query>` | Semantic search (query on stdin, never argv) |
| `/ace:ace-patterns [section] [min-reward]` | The playbook by section |
| `/ace:ace-top [limit] [section]` | Top-rated patterns |
| `/ace:ace-status` | Playbook statistics and where the binding came from |
| `/ace:ace-domains [min]` | Pattern domains |
| `/ace:ace-export-patterns [file]` | Export the playbook to a file inside the repo (preview + confirm) |
| `/ace:ace-import-patterns <file>` | Import a playbook JSON from inside the repo (preview + confirm) |
| `/ace:ace-insights [hours]` | Recap of the relevance log |
| `/ace:ace-graph [min-weight]` | Local knowledge graph of exactly this project |
| `/ace:ace-doctor` | Binding (source, path, tried, warnings), CLI, login, server |
| `/ace:ace-test` | Read-only round trip: version, status, one search |
| `/ace:ace-cleanup [days]` | Delete rotated logs (preview + confirm) |
| `/ace:ace-clear` | Clear the playbook (preview + confirm) |
| `/ace:ace-delta <op> <json>` | Add/update/remove patterns (preview + confirm) |
| `/ace:ace-learn <lesson>` | Send one lesson (preview + confirm) |
| `/ace:ace-bootstrap [mode] [level]` or `--mode X --thoroughness Y` or `--backfill-only [--sources session,git,merge] [--limit N] [--days-back N] [--target-project prj_x --target-org org_x] [--approved]` | Build the playbook from the codebase (legacy, sends raw code) or backfill redacted traces from session transcripts, fix/revert commits and merged PRs (default: all three, the limit shared round-robin so no source starves another; `--sources` narrows): preview + confirm (or `--approved`) |
| `/ace:ace-tune [show \| key=value ...]` | Show or change server settings (writes: preview + confirm) |
| `/ace:ace-configure [org_ prj_]` | Bind the repo: name-matched suggestion, `.gitignore` diff, confirm |
| `/ace:ace-login` | Login state; the device login starts on the button press |
| `/ace:ace-install-cli` | The pinned ace-cli; reinstall on the button press |

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
- `ACE_AUTO_INSTALL=0`: never install the pinned ace-cli in the background at SessionStart (default on).
- `ACE_TRACE_QUEUE=0`: never keep a failed trace for a later replay; the loss is still logged (`learn_lost`).

### Binding (project context)

The tracked `.ace/config.json` at the repo's main checkout root, nothing else in it:

```json
{"orgId": "org_xxxxx", "projectId": "prj_xxxxx"}
```

`.gitignore` must let it through: `.ace/*` plus `!.ace/config.json` (a bare `.ace/` rule blocks the negation;
`/ace:ace-configure` and the auto-adoption fix it). A file with `apiToken`/`serverUrl` is refused. Login lives in the
ace-cli global config (`~/.config/ace/config.json`, or `ACE_CONFIG_PATH`). Without a git repo (herdr, remote boxes)
bind via `ACE_ORG_ID`/`ACE_PROJECT_ID`. Check any directory with `scripts/ace-context --json`.

## 🛠️ Troubleshooting

### "ace-cli not found"

Run `/ace:ace-install-cli` (it reports which CLI is used and repairs a missing install).

### "ACE ▼ Repo nicht verbunden"

Run `/ace:ace-configure` (or press [Verbinden] in the band). `/ace:ace-doctor` lists every path that was tried.

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

**Version**: v8.2.3
**Maintainer**: CE.NET Team
**Requires**: Claude Code >= 2.1.311, ace-cli 4.4.2 pinned in package.json (@ace-sdk/core >= 3.8.2; installed with the plugin; a global ace-cli >= the pin is an untested fallback), Python >= 3.10 for the fallback hooks (Ubuntu 22.04+, Debian 12+, Homebrew/pyenv; the macOS system 3.9 is not enough, the mod chain is unaffected). Windows not supported (WSL2 works).
**Architecture**: mod + Python hooks + CLI/engine (no MCP)
