"""The visible per-prompt notice is ONE line, identical in both chains (mod statusLine in mod/ui/status.ts)."""
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


def test_render_keeps_only_retrieval_id_and_count_at_top_level():
    """cli 4.3.0 passes every server field through; the injected JSON must not carry them (parity with the mod)."""
    from ace_pattern_render import render_patterns_dict
    resp = {"retrieval_id": "r1", "count": 1, "search_params": {"top_k": 100}, "tokens_in_response": 4000,
            "local_count": 1, "session_id": "s", "feedback_downvote": True, "render_full_pct": 50,
            "similar_patterns": [{"id": "11111111-2222-4333-8444-555555555555", "content": "x", "domain": "d"}]}
    out = render_patterns_dict(resp)
    d = out[0] if isinstance(out, tuple) else out
    d = d.get("dict", d) if isinstance(d, dict) else d
    assert set(d) == {"retrieval_id", "count", "similar_patterns"}, set(d)
