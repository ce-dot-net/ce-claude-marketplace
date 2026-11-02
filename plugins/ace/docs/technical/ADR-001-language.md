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
| TypeScript / Node | Only real structural win: in-process `@ace-sdk/core` import (in-process import 0.23-0.53 s CPU vs 1.97 s for the ace-cli spawn, see the v8.1 plan). Depends on a private `dist/cjs` path and an open server-team question. Deferred. |
| Go | Rejected: new toolchain and per-platform binaries for no measured gain over a single Python exec. |
| Rust | Rejected: same as Go, higher maintenance cost. |
| Claude Code mods (in-process JS hooks) | Follow-up: needs Claude Code >= 2.1.287 and has a Team/Enterprise guard caveat. Not in 8.0.0. |

## Decision
Keep Python; reduce process count (thin bash shims that `exec` Python) and I/O.

## Deferred follow-ups (not in 8.0.0; see the v8.1 plan below)
- Claude Code mods (in-process JS hooks).
- In-process `@ace-sdk/core` (TypeScript hooks); ace-cli/core stay off-limits and are consumed as a subprocess.

Round 2 of 8.0.0 already ships `prompt_id` as the task anchor (PreToolUse `Agent` prompt stash, PostToolBatch accumulator).

## v8.1 plan: mods + in-process (proven numbers)
Floor 2.1.287 (the v8 floor 2.1.311 already clears it). One hooks.json with `modules` + `hooks`, in this order:
1. `UserPromptSubmit` becomes `prompt.submit`: render the full server-curated set inline (41,579 chars proven; cap 100K vs 10K)
   on the same additional-context channel. Build behind a flag; the decision to inject over 10 K is the server team's.
2. `SubagentStart` becomes `agent.spawn` (94 ms settle): `e.prompt` is first-class, which deletes the PreToolUse `Agent` stash
   and the transcript scan.
3. Domain-shift becomes `tool.call` (tool=Read): one in-process hook replaces the PostToolUse shim.
4. Search in-process via a deep import of `@ace-sdk/core` (`dist/cjs/client/ace-client.js`): parity 100/100,
   0.23-0.53 s CPU and 81-96 MB RSS vs 1.97 s and 237 MB for the ace-cli spawn; sessions.db is never opened, which ends the
   lock storm structurally. Private path: version-gate it with an ace-cli fallback. Shipped via package.json + lockfile
   with `npm ci --ignore-scripts` (6.2 s cold, 123 MB; Claude Code runs it itself into `${CLAUDE_PLUGIN_ROOT}/node_modules`, not for `--plugin-dir` loads).
5. PermissionDenied, SessionStart(compact) and SessionEnd stay command hooks (the mod `classic.*` hooks are skipped where the
   Team/Enterprise guard is seated).

Expected gain: per-search CPU 1.5-2 s down to 0.3-0.5 s, RSS -60 %; wall time stays bounded by the server round trip. v8.1 work.

## Evaluated and rejected in 8.0.0 (research pass 2)
- `UserPromptExpansion` for slash-command names: evaluated, not useful (the expansion carries nothing the commands need; no hook added).
- `asyncRewake` on a hook: rejected, it wakes the model on a hook exit code; guarded by a test that hooks.json never uses it.
- ace-cli 4.1.2 is flag-complete for v8 (`--pin-session`, `--top-k`, `--no-stream`, `--retrieval-id`, `--applied-log-ids`); the plugin consumes it as is.
- CLI delivery is DESIGN section 23: `package.json` pins one exact `@ace-sdk/cli`, `package-lock.json` is committed, Claude Code installs it on plugin install/update; plugin and CLI are updated hand in hand (a CLI minor can add a flag or change a format, so no range is safe).

## What the server stores (checked against the CLI 4.2.2 payload)
- `render_variant` reaches the server: ace-cli forwards the trace verbatim, so the A/B attribution can use it.
- `parent_agent_id` is the server-declared name for the parent prompt id (the local state keeps `parent_task_id`).
- `effort_level` / `effort_weight` are dropped server-side (not stored or persisted); they stay in the local relevance log only.

## Note: ACE_CLIENT_ID (m3)
ace-cli hard-codes `X-ACE-Client: cli`, so the plugin's `ACE_CLIENT_ID` env var never reaches the server through the CLI. The env var is kept (harmless); only an in-process SDK engine could set the header.
