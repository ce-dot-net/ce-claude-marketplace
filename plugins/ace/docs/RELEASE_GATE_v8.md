# Release Gate (v8)

Run before every release. Automated part first, then one live session with `claude --debug-file <file>`.

## Rollout blocker (server)
- [ ] The server team confirms AOP-1333 (trace_render_log, `conversation_id`) AND AOP-1334 (full -> WARM only for judged patterns) live on prod, with date and version. 8.0.0 is not rolled out before both.
- [ ] 8.0.0 ships with the budget default: `ACE_RENDER_FULL_PCT` default 0 in both chains (`render_arm` / `renderCohort`).
- [ ] `applied_log_ids` = only the used ids, verified with a fake-CLI trace: under `full` and `budget`, an answer that names no pattern sends no `--applied-log-ids` (tests/test_s31_contract.py, test_render_variant_v8.py::test_full_sends_no_applied_log_ids).

## Automated
- [ ] `python3 -m pytest tests -q -p no:cacheprovider` is green
- [ ] `ACE_E2E=1 python3 -m pytest tests/e2e -q` is green
- [ ] `claude plugin validate plugins/ace --strict` reports 0 hook warnings
- [ ] `claude plugin test plugins/ace` (the mod suite) is green
- [ ] `/usr/bin/python3 -m py_compile` on every changed .py, and the suite collects under Python 3.9
- [ ] Docker `node:22-bookworm` from `git archive HEAD` (npm ci --ignore-scripts): unit + e2e green
- [ ] Opt-in engine tests, run separately: `-m real_engine` (10x) and, with a real login, `-m live_server`
- [ ] All three manifests carry the same version; CHANGELOG has the entry

## Live session, mod chain (default on Claude Code >= 2.1.287)
- [ ] `ace-relevance.jsonl` rows carry `source: "mod"`; the Python UPS hook logs nothing while `mod-active` is fresh
- [ ] Learn trace: `render_variant` = budget (default), `conversation_id` = the CC session id, `applied_log_ids` only for patterns named in the answer
- [ ] With `ACE_RENDER_FULL_PCT=100`: `render_variant: "full"`, `truncated_for_cap` when cut, the second prompt injects only new ids; report the `playbook_used` trace size
- [ ] Multi-turn cost run (5+ prompts, one conversation): cumulative input tokens and compaction count for full vs budget
- [ ] `~/.ace-cache/sessions.db` growth over the session (§25; doctor threshold 100 MB)

## Live session, Python chain (from the --debug-file log)
- [ ] The UserPromptSubmit hook finishes in < 10 s at load < 60
- [ ] 0 `timed out after` lines for ACE hooks
- [ ] `patterns_injected` > 0 on the human prompt in `ace-relevance.jsonl`
- [ ] 0 `database is locked` rows for the session
- [ ] Locked-retry / pin-drop path exercised (a `pin_failed` row is logged, patterns still injected)
- [ ] A `<task-notification>` prompt logs `search_skipped`
- [ ] The Stop learn row is present after the session exits (detached path)
- [ ] Async accumulator durability (accumulator rows are present after Stop)
- [ ] Async hooks produced 0 bytes of stdout
- [ ] `CLAUDE_ENV_FILE` exports (`ACE_CLIENT_ID`) reach later hooks
- [ ] SessionEnd completes in < 0.5 s
- [ ] The statusline renders with the new log fields
- [ ] Self-eval round-trip works (`ACE_REVIEW`)
- [ ] `disabled.flag` semantics: present = hooks silent, absent = hooks active
- [ ] Domain-shift matcher parity on the 20 recorded path/domain pairs
- [ ] No growth of files in `~/.claude/logs` and none written to the system temp dir
