# Release Gate (v8)

Run before every release. Automated part first, then one live session with `claude --debug-file <file>`.

## Automated
- [ ] `python3 -m pytest tests -q -p no:cacheprovider` is green
- [ ] `ACE_E2E=1 python3 -m pytest tests/e2e -q` is green
- [ ] `claude plugin validate plugins/ace --strict` reports 0 hook warnings
- [ ] All three manifests carry the same version; CHANGELOG has the entry

## Live session (from the --debug-file log)
- [ ] The UserPromptSubmit hook finishes in < 10 s at load < 60
- [ ] 0 `timed out after` lines for ACE hooks
- [ ] `patterns_injected` > 0 on the human prompt in `ace-relevance.jsonl`
- [ ] 0 `database is locked` rows for the session
- [ ] A `<task-notification>` prompt logs `search_skipped`
- [ ] The Stop learn row is present after the session exits (detached path)
- [ ] Async hooks produced 0 bytes of stdout
- [ ] `CLAUDE_ENV_FILE` exports (`ACE_CLIENT_ID`) reach later hooks
- [ ] SessionEnd completes in < 0.5 s
- [ ] The statusline renders with the new log fields
- [ ] Self-eval round-trip works (`ACE_REVIEW`)
- [ ] `disabled.flag` semantics: present = hooks silent, absent = hooks active
- [ ] Domain-shift matcher parity on the 20 recorded path/domain pairs
- [ ] No growth of files in `~/.claude/logs` and none written to the system temp dir
