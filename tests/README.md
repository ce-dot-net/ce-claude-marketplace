# ACE plugin tests

```bash
python3 -m pytest tests -q -p no:cacheprovider            # main suite (~20 s)
python3 -m pytest plugins/ace/tests -q -p no:cacheprovider # plugin-local unit tests
ACE_E2E=1 python3 -m pytest tests/e2e -q                   # hook e2e, v8 target behavior
```

Stdlib + pytest only. Runs on Python 3.9 (stock macOS `/usr/bin/python3`) through current.
CI: `.github/workflows/tests.yml` (ubuntu + macos, Python 3.9 + 3.12).

## Hermetic environment (`tests/conftest.py`)

Applied before collection, for every test:

- `HOME`, `CLAUDE_PLUGIN_DATA`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME` point into one temp dir per run.
- All `ACE_*` variables (except `ACE_E2E`, `ACE_PLUGIN_ROOT_UNDER_TEST`) and `CLAUDE_CODE_SESSION_ID`,
  `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_ENV_FILE` are removed. Inside a Claude Code
  session these come from the real project's `.claude/settings.json`; set what a test needs with
  `monkeypatch.setenv` or an explicit subprocess `env`.
- Each test runs with `cwd` = its own temp dir, so hooks that resolve `.claude/...` relative to cwd
  never write into the checkout.
- A fake `ace-cli` (plus an `npm` stub) is first on `PATH`. It appends `{"argv": [...], "stdin": "..."}`
  per call to `$ACE_FAKE_CLI_LOG` (per test) and prints `{"count":0,"similar_patterns":[]}` for
  `search`, `{}` for `learn` and everything else, `4.2.2` for `--version`. The `fake_cli_calls`
  fixture returns the current test's calls. Tests that genuinely need the real CLI use
  `@pytest.mark.real_ace_cli`. Nothing in the suite may call the network.

## Hook e2e harness (`tests/e2e/`)

`ace_e2e_harness.py` runs one realistic stdin JSON per event (`tests/e2e/fixtures/*.json`, shapes
from the Claude Code hooks reference; the `<task-notification>` prompt is a real Monitor sample)
through exactly the commands `hooks/hooks.json` routes that event to — same matcher, `if`, exec/shell
form and placeholder rules as Claude Code. Each run gets its own `HOME`, plugin data dir, `TMPDIR`
and a project dir with `.claude/settings.json` `{projectId, orgId}`.

`test_e2e_hooks.py` asserts the v8 target (DESIGN §3): routing per event, exit 0, stdout empty or
one JSON object with only the fields the event accepts (additionalContext ≤ 10,000 chars), no
`/tmp/ace-*`, `~/.claude/logs/ace-*` or `mktemp` leftovers, no background process left behind,
< 1.5 s per hook with the fake CLI, and fake-CLI call counts (machine prompt → 0, human prompt →
exactly one `search`, SubagentStop with empty `agent_type` → 0, PostToolUse accumulator → 0,
SessionStart startup → no `whoami`). These tests are skipped unless `ACE_E2E=1`.

Validate a deployed copy instead of the repo: `ACE_PLUGIN_ROOT_UNDER_TEST=<plugin dir> ACE_E2E=1 python3 -m pytest tests/e2e -q`.
