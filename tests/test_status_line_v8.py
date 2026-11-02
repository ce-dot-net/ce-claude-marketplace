"""The visible per-prompt notice is ONE line, identical in both chains (mod statusLine in mod/core.ts)."""
import importlib.util, sys
from pathlib import Path

H = Path(__file__).resolve().parent.parent / "plugins/ace/shared-hooks"
sys.path.insert(0, str(H / "utils"))
spec = importlib.util.spec_from_file_location("abt_status", H / "ace_before_task.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def test_same_text_as_the_mod():
    pats = [{"domain": d} for d in ["a-b", "a-b", "c", "d", "e"]]
    assert m.status_line(11, 100, "budget", pats) == "ACE · 11 of 100 patterns · budget · a-b, c +2"
    assert m.status_line(1, 1, "full", [{"domain": "x"}]) == "ACE · 1 pattern · full · x"
    assert m.status_line(0, 0, "budget", []) == "ACE · no patterns for this prompt"
    assert "\n" not in m.status_line(3, 9, "budget", pats)
