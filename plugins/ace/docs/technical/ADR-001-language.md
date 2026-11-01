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
| TypeScript / Node | Only real structural win: in-process `@ace-sdk/core` import (deep import ~0.03 s). Depends on a private `dist/cjs` path and an open server-team question. Deferred. |
| Go | Rejected: new toolchain and per-platform binaries for no measured gain over a single Python exec. |
| Rust | Rejected: same as Go, higher maintenance cost. |
| Claude Code mods (in-process JS hooks) | Follow-up: needs Claude Code >= 2.1.287 and has a Team/Enterprise guard caveat. Not in 8.0.0. |

## Decision
Keep Python; reduce process count (thin bash shims that `exec` Python) and I/O.

## Deferred follow-ups (not in 8.0.0)
- `prompt_id` as the `--pin-session` value instead of the home-grown `task_session_id` (needs a live check that it reaches SubagentStart/SubagentStop input).
- `PostToolBatch` instead of per-tool PostToolUse for the accumulator (one spawn per parallel batch; different `tool_response` shape).
- `UserPromptExpansion` for matching slash-command names.
- Claude Code mods (in-process JS hooks).
- In-process `@ace-sdk/core` (TypeScript hooks); ace-cli/core stay off-limits and are consumed as a subprocess.
