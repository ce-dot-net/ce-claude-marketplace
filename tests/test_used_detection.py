"""Item H2: a pattern counts as used when >= 2 of its distinctive tokens appear in the TOOL CALL inputs of the
task (Bash commands, file paths, Grep patterns, Edit targets), or its id appears in the final message / report.
The same fixture drives the mod (plugins/ace/mod/tests/ace_mod.test.ts): parity."""
import json
from pathlib import Path

import pytest

from test_stop_v8 import box  # noqa: F401  (puts shared-hooks on sys.path)
from patterns_used_state import tool_haystack, used_pattern_ids, distinctive_tokens  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "mod" / "tests" / "fixtures" / "used_cases.ts"
CASES = json.loads(FIX.read_text()[len("export default "):])


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_used_cases(case):
    hay = tool_haystack(case["tool_inputs"])
    assert used_pattern_ids(case["ids"], case["contents"], case["message"], hay) == case["expected"]


def test_distinctive_tokens():
    toks = distinctive_tokens("Search with `ace-cli search --pin-session` and keep sessions/pins.json; call fooBar and a_b_c, e.g. done")
    assert {"ace-cli search --pin-session", "ace-cli search", "--pin-session", "sessions/pins.json", "foobar", "a_b_c"} <= toks
    assert "search" not in toks and "e.g" not in toks and "e.g." not in toks
