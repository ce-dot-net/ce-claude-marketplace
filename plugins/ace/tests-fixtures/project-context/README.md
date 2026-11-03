cases.json and exit-codes.json are copied verbatim from ce-ace-clients branch feature/aop-1361-project-context, commit fbcbe1b (spec/fixtures/project-context/). Do not edit them; re-copy on a spec change.

extra-cases.json is ours (plugin probes beyond the spec), same format plus: `unreadable` (layout paths whose read raises), and `$ROOT` substituted in layout values as in env. A `message` in a result must be a non-empty string and is dropped before comparing.

Runners: tests/test_project_context_spec.py (Python) and plugins/ace/mod/tests/project_context.test.ts (TypeScript).

Mods load only .ts files, so the TS runner imports generated wrappers in plugins/ace/mod/tests/fixtures/project_context_{cases,extra}.ts (`export default <json>`); the Python suite fails if they drift. Regenerate after editing a JSON file:
`python3 -c "import json;[open(f'plugins/ace/mod/tests/fixtures/{d}.ts','w').write(f'// GENERATED from tests-fixtures/project-context/{s}.json (mods load only .ts); tests/test_project_context_spec.py guards the sync.\nexport default {json.dumps(json.load(open(f\"plugins/ace/tests-fixtures/project-context/{s}.json\")))}\n') for s,d in [('cases','project_context_cases'),('extra-cases','project_context_extra')]]"`
