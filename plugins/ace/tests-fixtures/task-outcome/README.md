Task outcome (8.1.3). `result.success` = the end outcome of the task, `result.failed_steps` = how many steps failed
(informational), `result.aborted` = true only when the run's last step was interrupted. docs/technical/ARCHITECTURE.md "Task outcome (8.1.3)" states the contract and the rule.

cases.json: step sequences and the expected `{success, failed_steps}` plus `aborted: true` when the run was aborted
(the trace key exists only when true). A step is neutral: `tool`, and optionally
`command` (Bash), `file_path`, `exit` (known exit code), `stdout`, `stderr`, `is_error`, `denied`, `interrupted`.
Each runner turns a step into its chain's native shape and runs the real code: tests/test_task_outcome.py (the
accumulator / transcript response dict -> ace_after_task.task_outcome) and plugins/ace/mod/tests/outcome.test.ts
(tool.call result -> lib/trace.ts toolRec -> taskOutcome).

tables.json: the benign-exit, read-only and decisive tables plus `[command, family]` pairs. Both chains keep their own
copy; tests/test_task_outcome.py asserts the Python and the mod tables equal this file.

Mods load only .ts files: plugins/ace/mod/tests/fixtures/outcome_cases.ts wraps both files (`export default`) and
tests/test_task_outcome.py fails if it drifts. Regenerate after editing a JSON file:
`python3 tests/test_task_outcome.py --regen`
