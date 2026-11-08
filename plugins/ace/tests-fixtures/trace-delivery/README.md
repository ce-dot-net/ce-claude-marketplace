# trace-delivery: the `stored` field (8.1.4)

`stored_cases.json`: one POST /traces answer each (`status`, `body`), the engine/learn.js exit code it must produce
(0 = stored, 6 = answered but not proven stored) and the queue decision (`ace_trace_queue.classify`, first send).
`stored` present and `null` (the server fix: the first send is still running) or not a boolean = never stored, wait;
`stored` absent (an older server) = stored unless `duplicate` is true. Runners: tests/test_trace_queue.py (classify)
and tests/e2e/test_e2e_trace_delivery.py (the real engine against the fake server, both chains).
