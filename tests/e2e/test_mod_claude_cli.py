"""Release gates for the mod (DESIGN §13.1): `claude plugin validate plugins/ace --strict` is clean and
names the mod's hooks, and `claude plugin test plugins/ace` (plugins/ace/mod/tests) is green.
Skips when the `claude` binary is missing (CI without Claude Code)."""
import shutil
import subprocess

import pytest

import mod_reference as R

CLAUDE = shutil.which("claude")
pytestmark = pytest.mark.skipif(not CLAUDE, reason="claude binary not installed")
MOD_HOOKS = ["session.start", "prompt.submit", "agent.spawn", "tool.call", "turn.start", "turn.complete",
             "session.end", "classic.UserPromptSubmit", "classic.Stop", "classic.SubagentStop"]


def _run(*args):
    return subprocess.run([CLAUDE, "plugin", *args], capture_output=True, text=True, timeout=300, cwd=str(R.REPO))


def test_validate_strict_is_clean_and_lists_the_mod_hooks():
    p = _run("validate", str(R.PLUGIN), "--strict")
    out = p.stdout + p.stderr
    assert p.returncode == 0, out[-3000:]
    assert "mod/hooks.json" in out, out[-3000:]
    line = next((l for l in out.splitlines() if "./register.ts hooks:" in l), "")
    for hook in MOD_HOOKS:
        assert hook in line, "validate does not see %s: %s" % (hook, line)
    assert "env reads:" in out and "CLAUDE_PLUGIN_DATA" not in next(
        (l for l in out.splitlines() if "env reads:" in l), ""), "F1: never read CLAUDE_PLUGIN_DATA"


def test_claude_plugin_test_suite_is_green():
    p = _run("test", str(R.PLUGIN))
    out = p.stdout + p.stderr
    assert p.returncode == 0, out[-4000:]
    assert " 0 fail" in out and "Ran " in out, out[-4000:]
