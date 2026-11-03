export default [
 {
  "name": "true positive via tokens: the task ran the command the pattern names",
  "ids": [
   "ctx-1000000001-aaaa",
   "ctx-1000000002-bbbb"
  ],
  "contents": {
   "ctx-1000000001-aaaa": "Search with `ace-cli search --pin-session` and keep the pin in sessions/pins.json",
   "ctx-1000000002-bbbb": "Prefer small commits and clear messages always"
  },
  "message": "Done.",
  "tool_inputs": [
   {
    "command": "ace-cli search --pin-session abc --stdin"
   }
  ],
  "expected": [
   "ctx-1000000001-aaaa"
  ]
 },
 {
  "name": "true negative: generic words only",
  "ids": [
   "ctx-1000000001-aaaa"
  ],
  "contents": {
   "ctx-1000000001-aaaa": "Always run the tests before you commit and check the output carefully"
  },
  "message": "I ran the tests before the commit and checked the output carefully.",
  "tool_inputs": [
   {
    "command": "pytest -q"
   }
  ],
  "expected": []
 },
 {
  "name": "one distinctive token is not enough",
  "ids": [
   "ctx-1000000001-aaaa"
  ],
  "contents": {
   "ctx-1000000001-aaaa": "Use `jq -n --arg` for hook JSON output"
  },
  "message": "Used jq -n --arg for the hook JSON output.",
  "tool_inputs": [
   {
    "command": "jq --arg x 1 '.'"
   }
  ],
  "expected": []
 },
 {
  "name": "tokens shared by > 30% of the injected patterns are too generic",
  "ids": [
   "ctx-1000000001-aaaa",
   "ctx-1000000002-bbbb",
   "ctx-1000000003-cccc",
   "ctx-1000000004-dddd",
   "ctx-1000000005-eeee"
  ],
  "contents": {
   "ctx-1000000001-aaaa": "Edit plugins/ace/mod/core.ts carefully",
   "ctx-1000000002-bbbb": "Edit plugins/ace/mod/core.ts with care",
   "ctx-1000000003-cccc": "Read plugins/ace/mod/core.ts first",
   "ctx-1000000004-dddd": "Check plugins/ace/mod/core.ts again",
   "ctx-1000000005-eeee": "After plugins/ace/mod/core.ts run `claude plugin test` on it"
  },
  "message": "Done.",
  "tool_inputs": [
   {
    "file_path": "/repo/plugins/ace/mod/core.ts",
    "old_string": "a",
    "new_string": "b"
   },
   {
    "command": "claude plugin test plugins/ace"
   }
  ],
  "expected": [
   "ctx-1000000005-eeee"
  ]
 },
 {
  "name": "the id literal in the final message or report still counts",
  "ids": [
   "ctx-1000000001-aaaa",
   "ctx-1000000002-bbbb"
  ],
  "contents": {
   "ctx-1000000001-aaaa": "x",
   "ctx-1000000002-bbbb": "y"
  },
  "message": "Applied ctx-1000000002-bbbb here.",
  "tool_inputs": [],
  "expected": [
   "ctx-1000000002-bbbb"
  ]
 },
 {
  "name": "paths, identifiers and flags from tool inputs; edit bodies are not searched",
  "ids": [
   "ctx-1000000001-aaaa",
   "ctx-1000000002-bbbb"
  ],
  "contents": {
   "ctx-1000000001-aaaa": "Call render_patterns_dict() from shared-hooks/utils/ace_pattern_render.py",
   "ctx-1000000002-bbbb": "Keep sessionTitle and PRIVATE_WRITE_SH in sync"
  },
  "message": "Done.",
  "tool_inputs": [
   {
    "pattern": "render_patterns_dict",
    "path": "plugins/ace/shared-hooks/utils/ace_pattern_render.py"
   },
   {
    "file_path": "/x/y.ts",
    "new_string": "sessionTitle PRIVATE_WRITE_SH"
   }
  ],
  "expected": [
   "ctx-1000000001-aaaa"
  ]
 }
]
