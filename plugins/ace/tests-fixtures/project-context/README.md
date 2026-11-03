cases.json and exit-codes.json are copied verbatim from ce-ace-clients branch feature/aop-1361-project-context, commit 9500190 (spec/fixtures/project-context/). Do not edit them; re-copy on a spec change.

init-target.json is copied verbatim from ce-ace-clients main, commit 8e9bf64 (cli 4.4.1; spec/project-context.md §9): where `ace-cli init` writes .ace/config.json (main checkout of a linked worktree, verified topology, shadowing file). Runners: tests/test_init_target.py (our fallback writer), tests/test_cli_contract.py (the real pinned CLI) and plugins/ace/mod/tests/init_target.test.ts (the mod's fallback target); wrapper plugins/ace/mod/tests/fixtures/init_target_cases.ts.

extra-cases.json is ours (plugin probes beyond the spec), same format plus: `unreadable` (layout paths whose read raises), and `$ROOT` substituted in layout values as in env. A `message` in a result must be a non-empty string and is dropped before comparing.

Runners: tests/test_project_context_spec.py (Python) and plugins/ace/mod/tests/project_context.test.ts (TypeScript).

Mods load only .ts files, so the TS runner imports generated wrappers in plugins/ace/mod/tests/fixtures/project_context_{cases,extra}.ts (`export default <json>`); the Python suite fails if they drift. Regenerate after editing a JSON file:
`python3 -c "import json;[open(f'plugins/ace/mod/tests/fixtures/{d}.ts','w').write(f'// GENERATED from tests-fixtures/project-context/{s}.json (mods load only .ts); tests/test_project_context_spec.py guards the sync.\nexport default {json.dumps(json.load(open(f\"plugins/ace/tests-fixtures/project-context/{s}.json\")))}\n') for s,d in [('cases','project_context_cases'),('extra-cases','project_context_extra')]]"`

verify-cases.json is ours: how `ace-cli status` (exit code + stderr, never stdout) maps to a context state, for the pinned 4.3.4 (exit 1 + stderr text) and the upcoming CLI (exit codes 3-9 + stderr `{"error":{code,status,message}}`). Both chains run it: tests/test_project_context_service.py and plugins/ace/mod/tests/context.test.ts.
