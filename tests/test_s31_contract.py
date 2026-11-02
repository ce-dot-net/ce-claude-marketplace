#!/usr/bin/env python3
"""DESIGN §31 (FINAL client contract), Python chain.

- Assignment: default budget; full only via split, bucket = sha256('render:' + conversation_id) % 100 <
  ACE_RENDER_FULL_PCT (default 0); no conversation id -> budget. Python never renders full.
- Trace: render_variant 'budget'|'full' (strip + lowercase), OMITTED when unknown; conversation_id = CC session_id
  (<= 512), subagents inherit; session_id (pin) unchanged; playbook_used = all injected ids.
- applied_log_ids = only ACTUALLY USED ids for every variant: the id or a >= 40-char verbatim content fragment
  in the final message / handback report; else []. False positives are worse than misses.
"""
import json

import pytest

from test_stop_v8 import Box, ORG_ID, PROJECT_ID, WORK, box  # noqa: F401  (puts shared-hooks on sys.path)
from ace_pattern_render import normalize_render_variant, render_arm, render_cohort, trace_render_variant  # noqa: E402
from patterns_used_state import CONTENT_CAP, append_patterns_used, load_state, used_pattern_ids  # noqa: E402
from wpd_harness import flag_value

_ENV = ("ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT", "ACE_RENDER_FULL_PCT")


@pytest.fixture
def clean_env(monkeypatch):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ── assignment ──────────────────────────────────────────────────────────────────────────

def test_default_is_budget_full_share_0(clean_env):
    assert {render_arm("conv-%d" % i) for i in range(300)} == {"budget"}
    assert render_arm(None) == "budget" and render_arm("") == "budget"


@pytest.mark.parametrize("bad", ["x", "-5", ""])
def test_invalid_full_pct_means_0(clean_env, bad):
    clean_env.setenv("ACE_RENDER_FULL_PCT", bad)
    assert render_arm("any-session") == "budget"


def test_full_split_never_without_a_conversation_id(clean_env):
    clean_env.setenv("ACE_RENDER_FULL_PCT", "100")
    assert render_arm("conv-1") == "full" and render_cohort("conv-1") == "budget"
    assert render_arm(None) == "budget"


@pytest.mark.parametrize("raw,want", [("full", "full"), (" Budget\n", "budget"), ("FULL", "full"),
                                      ("control", None), ("compact", None), ("", None), (None, None), (7, None)])
def test_normalize_render_variant(raw, want):
    assert normalize_render_variant(raw) == want
    assert trace_render_variant(raw, "conv-1") == want, "unknown is omitted, never recomputed to budget"


# ── "actually used" ─────────────────────────────────────────────────────────────────────

A, B, C = "ctx-1111111111-aaaa", "ctx-2222222222-bbbb", "11c8834e-fcca-5c36-9897-915bb2d02dbe"
CONTENT_A = "When a hook writes JSON for Claude Code, always build it with jq -n --arg instead of sed escaping."
CONTENT_B = "Prefer the plugin-local pinned ace-cli over the global one; the global is marked untested."


def test_used_by_id():
    assert used_pattern_ids([A, B], {}, "I followed pattern %s here." % B) == [B]


def test_used_by_40_char_verbatim_fragment_whitespace_normalized():
    msg = "As the playbook says: always build it with jq -n --arg\n   instead of sed escaping. Done."
    assert used_pattern_ids([A, B], {A: CONTENT_A, B: CONTENT_B}, msg) == [A]


def test_39_chars_is_not_enough():
    frag = CONTENT_A[10:49]
    assert len(frag) == 39
    assert used_pattern_ids([A], {A: CONTENT_A}, "x " + frag + " y") == []


def test_nothing_recognizable_means_empty():
    assert used_pattern_ids([A, B, C], {A: CONTENT_A, B: CONTENT_B}, "Implemented the change and ran the tests.") == []
    assert used_pattern_ids([A], {A: CONTENT_A}, "") == [] and used_pattern_ids([A], {A: CONTENT_A}, None) == []


def test_order_follows_the_injected_ids():
    msg = CONTENT_B + " and also " + CONTENT_A
    assert used_pattern_ids([A, B], {A: CONTENT_A, B: CONTENT_B}, msg) == [A, B]


def test_state_keeps_capped_contents(tmp_path):
    append_patterns_used("s1", None, [A, B], state_dir=str(tmp_path), project_id="p",
                         pattern_contents={A: CONTENT_A, B: "y" * 5000, "not an id": "z"})
    st = load_state("s1", None, "Stop", str(tmp_path), "p")
    assert st["pattern_contents"] == {A: CONTENT_A, B: "y" * CONTENT_CAP}
    append_patterns_used("s1", None, [C], state_dir=str(tmp_path), project_id="p", pattern_contents={C: "c"})
    assert set(load_state("s1", None, "Stop", str(tmp_path), "p")["pattern_contents"]) == {A, B, C}


# ── traces ──────────────────────────────────────────────────────────────────────────────

def _learn(box, event, agent="main", **state):
    box.write_state(event["session_id"], agent, user_prompt="refactor the parser module", **state)
    box.seed_tools(event["session_id"], WORK, agent_id=None if agent == "main" else agent)
    p = box.run_after_task(event, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    return learn


@pytest.mark.parametrize("variant", ["budget", "full"])
def test_applied_log_ids_only_the_used_ones_for_every_variant(box, variant):
    msg = "Built the hook output with jq: always build it with jq -n --arg instead of sed escaping."
    learn = _learn(box, box.stop_event("s31-a", last_assistant_message=msg), pattern_ids=[A, B], retrieval_id="ret-31",
                   retrieval_log_ids={A: 7, B: 8}, pattern_contents={A: CONTENT_A, B: CONTENT_B}, render_variant=variant)
    t = learn["trace"]
    assert flag_value(learn["argv"], "--applied-log-ids") == "7" and t["applied_log_ids"] == [7]
    assert t["playbook_used"] == [A, B] and t["render_variant"] == variant
    assert flag_value(learn["argv"], "--retrieval-id") == "ret-31"


def test_nothing_used_sends_no_applied_ids(box):
    learn = _learn(box, box.stop_event("s31-b"), pattern_ids=[A, B], retrieval_id="ret-31",
                   retrieval_log_ids={A: 7, B: 8}, pattern_contents={A: CONTENT_A, B: CONTENT_B}, render_variant="budget")
    assert "--applied-log-ids" not in learn["argv"] and not learn["trace"].get("applied_log_ids")


def test_conversation_id_and_pin_on_the_main_trace(box):
    learn = _learn(box, box.stop_event("conv-main-1"), task_session_id="pin-1", render_variant="budget")
    t = learn["trace"]
    assert t["conversation_id"] == "conv-main-1" and t["session_id"] == "pin-1"


def test_conversation_id_truncated_to_512(clean_env):
    from test_permission_denied_v8 import _mod as _pd_mod
    t = _pd_mod()._build_trace({"session_id": "c" * 600, "tool_name": "Bash", "tool_input": {}})
    assert t["conversation_id"] == "c" * 512


def test_unknown_variant_is_omitted(box):
    for i, stored in enumerate((None, "control", "compact")):
        b = Box(box.root / ("v%d" % i))
        st = {} if stored is None else {"render_variant": stored}
        learn = _learn(b, b.stop_event("s31-u"), **st)
        assert "render_variant" not in learn["trace"], stored


def test_subagent_inherits_the_conversation_id_and_uses_its_report(box):
    sid = "conv-sub-1"
    ev = box.subagent_event(sid, "a-31", last_assistant_message="Used " + B)
    learn = _learn(box, ev, agent="a-31", task_session_id="own-pin", pattern_ids=[A, B], retrieval_log_ids={A: 7, B: 8},
                   render_variant="full")
    t = learn["trace"]
    assert t["conversation_id"] == sid and t["session_id"] == "own-pin"
    assert t["applied_log_ids"] == [8]


def test_permission_denied_trace_carries_conversation_id_and_a_normalized_variant(clean_env):
    from test_permission_denied_v8 import _mod as _pd_mod
    t = _pd_mod()._build_trace({"session_id": "pd-31", "tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert t["conversation_id"] == "pd-31"
    assert "render_variant" not in t  # no stored variant -> omitted
    assert "applied_log_ids" not in t


# ── used check reads the FULL handback report (mod parity, USED_MESSAGE_CAP) ────────────

def test_pattern_quoted_after_char_4000_of_a_long_handback_is_credited(box):
    from test_r3d_hook_behavior import _handback_transcript
    report = "filler. " * 700 + CONTENT_A  # quote starts well past char 4000
    assert report.index(CONTENT_A) > 4000
    sid, agent = "s31-hb", "a31"
    box.write_state(sid, agent, user_prompt="refactor the parser module", pattern_ids=[A, B], retrieval_id="ret-31",
                    retrieval_log_ids={A: 7, B: 8}, pattern_contents={A: CONTENT_A, B: CONTENT_B})
    box.seed_tools(sid, WORK, agent_id=agent)
    ev = box.subagent_event(sid, agent, agent_type="Explore", last_assistant_message="done")
    ev["agent_transcript_path"] = _handback_transcript(box, agent, report)()
    p = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    assert learn["trace"]["applied_log_ids"] == [7]
    assert len(learn["trace"]["result"]["summary"]) == 4000
