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
    # the 300 s limit tore down a green-but-slow suite on a host at load 100+ (the suite takes ~1 min idle): it is no assertion about
    # speed, only a hang guard, so it is generous
    return subprocess.run([CLAUDE, "plugin", *args], capture_output=True, text=True, timeout=1800, cwd=str(R.REPO))


def _failures(out):
    """NAME and message of every failed mod test, complete (the tail of ~1300 test lines cut them off: a red run was unreadable)."""
    keep, on = [], False
    for l in out.splitlines():
        if l.startswith("(fail)"):
            keep.append(l)
            on = True
        elif l.startswith("(pass)") or (l and not l[0].isspace() and not l.startswith("(")):
            on = False
        elif on and l.strip():
            keep.append(l)
    return "\n".join(keep)


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
    assert p.returncode == 0, "failed mod tests:\n%s\n--- tail ---\n%s" % (_failures(out) or "(none parsed)", out[-1500:])
    assert " 0 fail" in out and "Ran " in out, "failed mod tests:\n%s\n--- tail ---\n%s" % (_failures(out) or "(none parsed)", out[-1500:])
