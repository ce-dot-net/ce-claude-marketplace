# FROZEN: redaction rules of commit 36159e0. Do not change.

`redact.ts`, `redact_rules.ts` and `redact.py` are byte copies of `git show 36159e0:<path>`:

- `plugins/ace/mod/lib/redact.ts`
- `plugins/ace/mod/lib/redact_rules.ts`
- `plugins/ace/shared-hooks/utils/redact.py`

They are the reference for `tests/test_redact_differential.py`. That test fails when the current rules leave text visible that this base
redacted, unless the case matches one of the listed exceptions. The copies run standalone: `redact.ts` imports `./redact_rules`, and
`redact.py` uses only the standard library. Never edit these files. A new release criterion means a new frozen directory.
