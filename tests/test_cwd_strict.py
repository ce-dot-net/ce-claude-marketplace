#!/usr/bin/env python3
"""
CWD strict mode: ace_posttooluse_wrapper.sh must NOT substitute $(pwd)
for a missing event .cwd — it should omit --working-dir entirely and
emit a stderr warning instead.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "plugins" / "ace" / "scripts" / "ace_posttooluse_wrapper.sh"


def test_no_pwd_fallback_in_working_dir_arg():
    text = WRAPPER.read_text()
    # The --working-dir default substitution must be gone
    assert "WORKING_DIR:-$(pwd)" not in text, \
        "Must not fall back to $(pwd) for --working-dir"
    # --working-dir must not be passed as a literal flag with $(pwd)
    assert '--working-dir "$(pwd)' not in text
    assert "--working-dir '$(pwd)" not in text


def test_conditional_working_dir_flag():
    text = WRAPPER.read_text()
    # Must build conditional flag
    assert "WORKING_DIR_ARG" in text, "Must build conditional --working-dir arg"
    # Must emit stderr warning when empty
    assert re.search(r"\[ACE WARN\].*WORKING_DIR", text), \
        "Must emit [ACE WARN] when WORKING_DIR is empty"
    # The accumulator call should use $WORKING_DIR_ARG (not --working-dir inline)
    assert "$WORKING_DIR_ARG" in text, "Accumulator call must use $WORKING_DIR_ARG"
