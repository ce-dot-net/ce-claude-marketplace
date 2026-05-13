#!/usr/bin/env python3
"""Smoke marker that an ACE hook test module loads successfully.

History: this file originally called `exit(0)` at module load, which crashed
pytest collection. It has been converted to a proper (trivial) pytest test
so the suite can collect cleanly. Real hook verification lives in
`test_hooks_json_matcher.py`, `test_precompact_handoff.py`, and the custom
validators under `/tmp/ace-prerelease-v650/`.
"""


def test_module_loads() -> None:
    """Module must import without side effects (no exit, no print)."""
    assert True
