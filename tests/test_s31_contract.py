#!/usr/bin/env python3
"""DESIGN §31 (FINAL client contract), Python chain.

- Assignment: default budget; full only via split, bucket = sha256('render:' + conversation_id) % 100 <
  ACE_RENDER_FULL_PCT (default 50, 8.0.0 user ruling); no conversation id -> budget. Python never renders full.
- Trace: render_variant 'budget'|'full' (strip + lowercase), OMITTED when unknown; conversation_id = CC session_id
  (<= 512), subagents inherit; session_id (pin) unchanged; playbook_used = all injected ids.
- applied_log_ids = only ACTUALLY USED ids for every variant (item H2): the id in the answer/report, or >= 2
  distinctive content tokens in the task's tool-call inputs (the 40-char answer-fragment rule is gone)
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

def test_default_is_a_50_50_split(clean_env):
    arms = [render_arm("conv-%d" % i) for i in range(300)]
    assert set(arms) == {"budget", "full"} and 120 <= arms.count("full") <= 180
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
    assert trace_render_variant(raw, None) == want, "no stored label and no conversation: omitted"


def test_trace_without_a_search_carries_its_conversations_arm(clean_env):
    """Server request (2026-11-02): traces with conversation_id but no search before must still carry the arm."""
    clean_env.setenv("ACE_RENDER_FULL_PCT", "100")
    assert trace_render_variant(None, "conv-1", mod=True) == "full"      # the mod renders the full arm as full
    assert trace_render_variant(None, "conv-1") == "budget"              # the Python chain renders it as budget
    assert trace_render_variant("budget", "conv-1", mod=True) == "budget"  # a stored label always wins
    clean_env.setenv("ACE_AB_CONTROL_PCT", "100"); clean_env.setenv("ACE_RENDER_FULL_PCT", "0")
    assert trace_render_variant(None, "conv-1", mod=True) is None        # control/compact are no server labels


# ── "actually used" ─────────────────────────────────────────────────────────────────────

A, B, C = "ctx-1111111111-aaaa", "ctx-2222222222-bbbb", "11c8834e-fcca-5c36-9897-915bb2d02dbe"
CONTENT_A = "When a hook writes JSON for Claude Code, always build it with jq -n --arg instead of sed escaping."
CONTENT_B = "Prefer the plugin-local pinned ace-cli over the global one; the global is marked untested."


def test_used_by_id():
    assert used_pattern_ids([A, B], {}, "I followed pattern %s here." % B) == [B]


def test_the_answer_text_alone_is_no_evidence():
    """Item H2: a verbatim fragment in the answer no longer counts (the 40-char rule is gone)."""
    msg = "As the playbook says: always build it with jq -n --arg\n   instead of sed escaping. Done."
    assert used_pattern_ids([A, B], {A: CONTENT_A, B: CONTENT_B}, msg) == []


def test_two_tokens_in_the_tool_inputs_are_evidence():
    from patterns_used_state import tool_haystack
    hay = tool_haystack([{"command": "${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version"}, {"file_path": "/p/plugin-local/x.json"}])
    assert used_pattern_ids([A, B], {A: CONTENT_A, B: "Prefer `scripts/ace-cli --version` over a plugin-local/x.json check"}, "", hay) == [B]


def test_nothing_recognizable_means_empty():
    assert used_pattern_ids([A, B, C], {A: CONTENT_A, B: CONTENT_B}, "Implemented the change and ran the tests.") == []
    assert used_pattern_ids([A], {A: CONTENT_A}, "") == [] and used_pattern_ids([A], {A: CONTENT_A}, None) == []


def test_order_follows_the_injected_ids():
    msg = B + " and also " + A
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


CONTENT_JQ = "Build hook output with `jq -n --arg` and check it with `python3 -m json.tool` afterwards."


@pytest.mark.parametrize("variant", ["budget", "full"])
def test_applied_log_ids_only_the_used_ones_for_every_variant(box, variant):
    """Item H2: evidence = tokens in the task's tool inputs (or the id); the answer text alone does not count."""
    sid = "s31-a-" + variant
    box.write_state(sid, user_prompt="refactor the parser module", pattern_ids=[A, B], retrieval_id="ret-31",
                    retrieval_log_ids={A: 7, B: 8}, pattern_contents={A: CONTENT_JQ, B: CONTENT_B}, render_variant=variant)
    box.seed_tools(sid, WORK + [("Bash", {"command": "jq -n --arg x 1 '{a:$x}' | python3 -m json.tool"}, {"stdout": "{}"})])
    p = box.run_after_task(box.stop_event(sid, last_assistant_message=CONTENT_B), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    t = learn["trace"]
    assert flag_value(learn["argv"], "--applied-log-ids") == "7" and t["applied_log_ids"] == [7]
    assert t["playbook_used"] == [A, B] and t["render_variant"] == variant
    assert (t["used_ids_model"], t["used_ids_tokens"]) == (0, 1), "per-source counters in the trace itself"
    assert flag_value(learn["argv"], "--retrieval-id") == "ret-31"
    (row,) = box.relevance_rows("execution")
    assert row["used_ids_count"] == 1 and row["used_source"] == "tokens"
    assert row["used_ids_tokens"] == 1 and row["used_ids_model"] == 0  # item 2: per-source counts, parity with the mod


def test_nothing_used_sends_empty_applied_ids_in_the_trace(box):
    learn = _learn(box, box.stop_event("s31-b"), pattern_ids=[A, B], retrieval_id="ret-31",
                   retrieval_log_ids={A: 7, B: 8}, pattern_contents={A: CONTENT_A, B: CONTENT_B}, render_variant="budget")
    assert "--applied-log-ids" not in learn["argv"] and learn["trace"]["applied_log_ids"] == []
    assert (learn["trace"]["used_ids_model"], learn["trace"]["used_ids_tokens"]) == (0, 0)


def test_conversation_id_and_pin_on_the_main_trace(box):
    learn = _learn(box, box.stop_event("conv-main-1"), task_session_id="pin-1", render_variant="budget")
    t = learn["trace"]
    assert t["conversation_id"] == "conv-main-1" and t["session_id"] == "pin-1"


def test_conversation_id_truncated_to_512(clean_env):
    from test_permission_denied_v8 import _mod as _pd_mod
    t = _pd_mod()._build_trace({"session_id": "c" * 600, "tool_name": "Bash", "tool_input": {}})
    assert t["conversation_id"] == "c" * 512


def test_unknown_variant_falls_back_to_the_conversation_arm(box):
    for i, stored in enumerate((None, "control", "compact")):
        b = Box(box.root / ("v%d" % i))
        st = {} if stored is None else {"render_variant": stored}
        learn = _learn(b, b.stop_event("s31-u"), **st)
        assert learn["trace"]["render_variant"] == "budget", stored  # Python chain: the conversation arm as budget


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
    assert t["render_variant"] == "budget"  # no stored variant -> the conversation arm (Python chain)
    assert "applied_log_ids" not in t


# ── used check reads the FULL handback report (mod parity, USED_MESSAGE_CAP) ────────────

def test_pattern_named_after_char_4000_of_a_long_handback_is_credited(box):
    from test_r3d_hook_behavior import _handback_transcript
    report = "filler. " * 700 + "applied " + A  # the id starts well past char 4000
    assert report.index(A) > 4000
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


def test_more_than_20_used_ids_are_capped_at_20(box):
    """Server 5.15.8: > 20 applied_log_ids in one trace counts as 'all shown' (the trace falls to COLD)."""
    ids = ["11c8834e-fcca-5c36-9897-%012d" % i for i in range(25)]
    sid = "s31-cap"
    box.write_state(sid, user_prompt="refactor the parser module", pattern_ids=ids, retrieval_id="ret-31",
                    retrieval_log_ids={p: i + 1 for i, p in enumerate(ids)}, render_variant="budget")
    box.seed_tools(sid, WORK)
    p = box.run_after_task(box.stop_event(sid, last_assistant_message="used " + " ".join(ids)),
                           ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    assert learn["trace"]["applied_log_ids"] == list(range(1, 21))
    assert flag_value(learn["argv"], "--applied-log-ids") == ",".join(str(i) for i in range(1, 21))
    (row,) = box.relevance_rows("execution")
    assert row["used_ids_capped"] is True and row["used_ids_count"] == 25


def test_20_used_ids_are_not_marked_capped(box):
    ids = ["11c8834e-fcca-5c36-9897-%012d" % i for i in range(20)]
    box.write_state("s31-cap20", user_prompt="refactor the parser module", pattern_ids=ids, retrieval_id="ret-31",
                    retrieval_log_ids={p: i + 1 for i, p in enumerate(ids)}, render_variant="budget")
    box.seed_tools("s31-cap20", WORK)
    p = box.run_after_task(box.stop_event("s31-cap20", last_assistant_message=" ".join(ids)),
                           ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    assert box.cli_calls("learn")[0]["trace"]["applied_log_ids"] == list(range(1, 21))
    assert "used_ids_capped" not in box.relevance_rows("execution")[0]
