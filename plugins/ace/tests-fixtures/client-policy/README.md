# client_policy cases (8.1.4)

Shared by both chains: `tests/test_client_policy.py` (Python, `plugin_data_dir`) and `mod/tests/policy.test.ts`
(via the generated `mod/tests/fixtures/client_policy_cases.ts`; the Python test guards the sync).

Each case: `policy` (absent = the search response has no `client_policy`), the running plugin `version`, how many days
ago it was stored (`age_days`), `expect_valid` (null = nothing to validate), `expect_state` (null | recommended | min).
