# ADR-001: Implementation language of the ACE plugin hooks

Status: accepted for 8.0.0. Verdict: **Python stays.**

## Context
The measured hook cost is process topology (bash + 10-20 `jq` + a pyenv-shimmed `python3` + 2-3 `ace-cli`
spawns per event), per-search `--version`/`whoami` probes, global session-db writes and full-transcript
reads. It is not the interpreter.

## Options considered
| Option | Assessment |
|---|---|
| Python (stdlib only, 3.9 compatible) | Keeps 1300+ tests and all hook logic; v8 removes the real costs (shim + single spawn + cached interpreter and CLI version). **Chosen.** |
| TypeScript / Node | Only real structural win: in-process `@ace-sdk/core` import (0.23-0.53 s CPU vs 1.97 s for the ace-cli spawn). That win does not need rewriting the hooks: 8.0.0 takes it through a small Node engine the Python hooks spawn (see below). |
| Go | Rejected: new toolchain and per-platform binaries for no measured gain over a single Python exec. |
| Rust | Rejected: same as Go, higher maintenance cost. |
| Claude Code mods (in-process JS hooks) | Added in 8.0.0 alongside the Python hooks (see below): needs Claude Code >= 2.1.287. Where the Team/Enterprise or managed-settings guard is seated the mod still runs but its `classic.*` hooks are filtered; the Python chain then takes over those duties (per-duty markers, see below). |

## Decision
Keep Python; reduce process count (thin bash shims that `exec` Python) and I/O. Search and learn run through
the in-process engine below when its gate passes.

## In-process engine (in 8.0.0)
`plugins/ace/engine/` is plain Node with no build step, no `package.json` and no `node_modules`:
`engine/search.js`, `engine/learn.js`, `engine/resolve.js`. The ace-cli spawn loads the whole CLI (1.97 s CPU, 237 MB);
the engine loads only the client and context modules of the core the CLI already installed, and never opens `sessions.db`,
which removes the lock failures on that path.

**Gate.** `engine/resolve.js` first looks in the plugin's own install, `${CLAUDE_PLUGIN_ROOT}/node_modules/@ace-sdk/core` (nested
under the plugin-local CLI, then hoisted), and then needs no ace-cli at all. Otherwise it finds `realpath(ace-cli)`, its `@ace-sdk/cli`
package, then `@ace-sdk/core` (nested first, then hoisted). Either way it requires `dist/cjs/client/ace-client.js` and
`dist/cjs/config/context.js`, core >= 3.2.2 on major 3, and the `AceClient` + `createContext` exports. `dist/cjs` is a private path,
outside the core's `exports` map, so this gate is the only thing that makes it safe. Reasons: `ok`, `no_cli`, `core_missing`,
`file_missing`, `core_too_old`, `core_too_new`, `export_missing`.

**Layouts.** A plugin-local install makes PATH differences irrelevant. Without one, the engine needs `ace-cli` to resolve to a real
`@ace-sdk/cli` install: npm global, nvm, fnm and brew do. Volta, asdf and pnpm wrappers do not, so they report `core_missing` and stay
on the working ace-cli path. Windows is unsupported (WSL2 ok).

**Fallback.** `ACE_ENGINE=cli`, no node, or a failed gate uses the ace-cli path unchanged, including pin-drop and backoff.
A failed engine search (any non-zero exit, or output without a `similar_patterns` list) also falls back. Learn falls back only on exit 3 or a spawn error,
because any later failure may follow the POST and a re-send could duplicate the trace and double F-080 credit.
Every spawn writes an `event: "engine"` relevance row with `engine`, `reason`, `hook`. `/ace:ace-doctor` shows the active
engine through `ace_engine.py --status`.

**Interface** (shared by `shared-hooks/utils/ace_engine.py` and the mod, which runs the same files with
`$.process.run(node, [engine/search.js])`, so both chains use one implementation):
| Script | Input | Output |
|---|---|---|
| `resolve.js` | none | One JSON object `{ok, reason, cli_path, core_dir, core_version, min_core}`; exit 0, or exit 3 on gate failure |
| `search.js` | stdin JSON `{query, org, project, session_id?, top_k?}` | stdout: exactly the `ace-cli search --json` object; exit 3 on gate failure, exit 1 on runtime or server failure with the error on stderr |
| `learn.js` | `--transcript F --json [--retrieval-id R] [--applied-log-ids a,b] [--verbosity V] [--timeout MS] [--no-stream]`; org and project via `ACE_ORG_ID`/`ACE_PROJECT_ID` | Same requests as `ace-cli learn --no-stream` (always the sync POST), same `--json` object; exit 3 = nothing sent, exit 1 = the POST may have been sent |

`session_id` goes to the server for its retrieval-log stamp; the engine writes no local pin. The default `cacheDir` stays on, so
the graph sqlite keeps feeding `result.expanded` (CLI parity) and `/ace:ace-graph`.

**Attribution.** The engine sets `X-ACE-Client: claude-code-plugin/<version>` itself; ace-cli >= 4.3.0 sends `ACE_CLIENT_ID`
(else `cli`), and the plugin exports `ACE_CLIENT_ID=claude-code-plugin/<version>` to every spawn, so both paths read as the plugin
(ace-cli < 4.3.0 hard-coded `cli`).

**Numbers.** Search via the deep import: parity 100/100, 0.23-0.53 s CPU and 81-96 MB RSS vs 1.97 s and 237 MB for the ace-cli spawn.
Wall time stays bounded by the server round trip. A plugin-local dependency installed with `npm ci --ignore-scripts` costs 6.2 s cold and 123 MB;
the engine adds nothing to it, because it reads the core the CLI installed.

## Mods (in 8.0.0)
Floor 2.1.287 (the v8 floor 2.1.311 already clears it). Mod hooks replace the matching command hooks while the mod is active:
- `prompt.submit` replaces `UserPromptSubmit` and can render the server-curated set inline: 41,579 chars measured in one context entry. The docs give no limit for mod `context`; the client keeps its own 95,000-char guard (not a documented Claude Code limit). The default render stays budget (§31); full is reached only through `ACE_RENDER_FULL_PCT`.
- `agent.spawn` replaces `SubagentStart` (94 ms settle): `e.prompt` is first-class.
- `tool.call` (tool=Read) replaces domain-shift.
- PermissionDenied, SessionStart(compact) and SessionEnd stay command hooks.
- Per-duty coexistence: `mod-active` (prompt/tool/agent events) silences the Python search/inject hooks; `mod-classic` (written by the mod's `classic.*` hooks) silences the Python accumulator and Stop/SubagentStop. The built-in `sec-default@builtin` guard filters a user mod's `classic.*` hooks (it does not skip the mod), so on those seats only `mod-active` is fresh and the Python chain learns, defers and sets the title.

Round 2 of 8.0.0 already ships `prompt_id` as the task anchor (PreToolUse `Agent` prompt stash, PostToolBatch accumulator).

## Evaluated and rejected in 8.0.0 (research pass 2)
- `UserPromptExpansion` for slash-command names: evaluated, not useful (the expansion carries nothing the commands need; no hook added).
- `asyncRewake` on a hook: rejected, it wakes the model on a hook exit code; guarded by a test that hooks.json never uses it.
- ace-cli 4.1.2 is flag-complete for v8 (`--pin-session`, `--top-k`, `--no-stream`, `--retrieval-id`, `--applied-log-ids`); the plugin consumes it as is.
- CLI delivery is DESIGN section 23: `package.json` pins one exact `@ace-sdk/cli`, `package-lock.json` is committed, Claude Code installs it on plugin install/update; plugin and CLI are updated hand in hand (a CLI minor can add a flag or change a format, so no range is safe).

## What the server stores (checked against the CLI 4.2.2 payload)
- `render_variant` reaches the server: ace-cli forwards the trace verbatim, so the A/B attribution can use it. Since 8.2.1
  `render_path` (`mod` | `python`, the chain that rendered) travels next to it, under the same condition.
- Since 8.2.2 (mod chain only; the Python chain never sets them; each omitted when unknown): `interactive` (session.start
  `isInteractive`, never defaulted), `prompt_origin` (origin.kind of the conversation's first prompt.submit, any kind,
  max 64 chars, `unclassified` without one) and `human_prompt_count` (prompts with origin `composer` or `bridge` so far).
  Both live in `sessions/<cc-session-id>/prompt-origin.json` (the conversation, never the task pin): they survive a
  reload/resume, never cross a `/clear`, and go with the session dir. Limit: a conversation begun before 8.2.2 reports
  the first prompt after the update; the count is a lower bound. Subagent traces carry the same values.
- `parent_agent_id` is the server-declared name for the parent prompt id (the local state keeps `parent_task_id`).
- `effort_level` / `effort_weight` are dropped server-side (not stored or persisted); they stay in the local relevance log only.
