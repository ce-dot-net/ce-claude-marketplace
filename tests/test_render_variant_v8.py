#!/usr/bin/env python3
"""DESIGN §28/§29, as amended by §31 (final contract: default budget, unknown label omitted), Python chain.

- render_arm(): arms in bucket order control, compact, full, rest budget; ACE_RENDER_FULL_PCT default 100;
  bucket = sha256("render:" + CC session_id)[:8] % 100. render_cohort() is what the PYTHON chain renders:
  it has no full renderer, so the full arm renders (and is labelled) budget.
- The bucket input is the stable CC session_id (subagents of that conversation share it), never the
  per-task pin; the pin / trace session_id semantics stay per task (§12).
- The rendered variant is stored in task state at render time and read back at learn; every trace carries it
  (subagents, PermissionDenied, traces without a pin). Under `full`: applied_log_ids = [] and no
  --applied-log-ids flag; retrieval_id + playbook_used unchanged.
"""
import hashlib
import json
import uuid

import pytest

from test_stop_v8 import Box, ORG_ID, PROJECT_ID, WORK, box  # noqa: F401  (also puts shared-hooks on sys.path)
from ace_pattern_render import render_arm, render_cohort  # noqa: E402
from wpd_harness import HookEnv, flag_value
from test_permission_denied_v8 import _mod as _pd_mod

_ENV = ("ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT", "ACE_RENDER_FULL_PCT")


def _bucket(sid):
    return int(hashlib.sha256(("render:" + sid).encode()).hexdigest()[:8], 16) % 100


def _sid_with(pred):
    for i in range(10000):
        sid = "cc-%d" % i
        if pred(_bucket(sid)):
            return sid
    raise AssertionError("no sid")


@pytest.fixture
def clean_env(monkeypatch):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ── arms ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ctrl,comp,full", [(10, 10, 30), (0, 0, 50), (25, 0, 100), (5, 20, 0)])
def test_arm_order_control_compact_full_budget(clean_env, ctrl, comp, full):
    clean_env.setenv("ACE_AB_CONTROL_PCT", str(ctrl))
    clean_env.setenv("ACE_AB_COMPACT_PCT", str(comp))
    clean_env.setenv("ACE_RENDER_FULL_PCT", str(full))
    eff_full = min(full, 100 - ctrl - comp)
    for i in range(500):
        sid = "s-%d" % i
        b = _bucket(sid)
        want = ("control" if b < ctrl else "compact" if b < ctrl + comp
                else "full" if b < ctrl + comp + eff_full else "budget")
        assert render_arm(sid) == want, (sid, b)
        assert render_cohort(sid) == ("budget" if want == "full" else want)


# ── bucket input = CC session_id; state carries the rendered variant ────────────────────

RESPONSE = {"count": 1, "retrieval_id": "ret-rv", "similar_patterns": [{
    "id": "ctx-1234567890-abcd", "content": "a pattern", "section": "strategies", "confidence": 0.9,
    "helpful": 2, "harmful": 0, "cumulative_v15_reward": 1.0, "isAtRisk": False,
    "match_factors": {"bandit_rank": 1, "retrieval_log_id": 11}}]}


@pytest.fixture
def henv(tmp_path):
    e = HookEnv(tmp_path, project_id="prj_rv_%s" % uuid.uuid4().hex[:6])
    e.set_search_response(RESPONSE)
    return e


def _ups(env, sid, prompt_id, **extra_env):
    ev = {"session_id": sid, "cwd": str(env.proj), "hook_event_name": "UserPromptSubmit", "prompt_id": prompt_id,
          "transcript_path": str(env.tmp / "t.jsonl"),
          "prompt": "refactor the authentication middleware to use JSON web tokens"}
    p = env.run("ace_before_task_wrapper.sh", ev, extra_env=extra_env)
    assert p.returncode == 0, p.stderr
    return p


@pytest.mark.parametrize("want", ["control", "budget"])
def test_ups_cohort_buckets_on_cc_session_id_not_the_prompt_id(henv, want):
    sid = _sid_with(lambda b: b < 50) if want == "control" else _sid_with(lambda b: b >= 50)
    for pid in ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222",
                "33333333-3333-4333-8333-333333333333"):
        _ups(henv, sid, pid, ACE_AB_CONTROL_PCT="50")
        st = henv.read_state(sid)
        assert st["render_variant"] == want, (pid, st)
        assert st["task_session_id"] == pid, "the pin stays per task (§12)"


def test_subagent_inherits_the_conversation_arm(henv):
    sid = _sid_with(lambda b: b < 50)
    ev = {"session_id": sid, "cwd": str(henv.proj), "hook_event_name": "SubagentStart",
          "agent_id": "agent-rv-1", "agent_type": "workflow-subagent",
          "prompt_id": "44444444-4444-4444-8444-444444444444", "transcript_path": str(henv.tmp / "t.jsonl"),
          "prompt": "audit the session-end reaper for races between the learn lock and the GC"}
    henv.write_state(sid, None, task_session_id="44444444-4444-4444-8444-444444444444",
                     user_prompt="audit the session-end reaper for races between the learn lock and the GC")
    p = henv.run("ace_subagent_start_wrapper.sh", ev, extra_env={"ACE_AB_CONTROL_PCT": "50"})
    assert p.returncode == 0, p.stderr
    st = henv.read_state(sid, "agent-rv-1")
    assert st["render_variant"] == "control"
    assert st["task_session_id"] not in (None, "44444444-4444-4444-8444-444444444444"), "own pin (§12)"


# ── learn: §29 + render_variant on every trace ──────────────────────────────────────────

def _main_learn(box, sid="s-rv", **state):
    box.write_state(sid, "main", user_prompt="refactor the parser module", **state)
    box.seed_tools(sid, WORK)
    p = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    return learn


IDS = ["ctx-1111111111-aaaa", "ctx-2222222222-bbbb"]


def test_full_sends_no_applied_log_ids(box):
    learn = _main_learn(box, pattern_ids=IDS, retrieval_id="ret-full",
                        retrieval_log_ids={IDS[0]: 7, IDS[1]: 8}, render_variant="full")
    t = learn["trace"]
    assert "--applied-log-ids" not in learn["argv"]
    assert not t.get("applied_log_ids")
    assert flag_value(learn["argv"], "--retrieval-id") == "ret-full" and t["retrieval_id"] == "ret-full"
    assert t["playbook_used"] == IDS
    assert t["render_variant"] == "full"


def test_control_variant_is_no_server_label(box):
    learn = _main_learn(box, retrieval_id="ret-c", render_variant="control")
    assert "render_variant" not in learn["trace"], "§31: only budget|full are sent"


def test_trace_without_pin_or_label_omits_both(box):
    learn = _main_learn(box, task_session_id=None)
    t = learn["trace"]
    assert "session_id" not in t
    assert "render_variant" not in t, "§31: unknown is omitted, never defaulted to budget"
    assert t["conversation_id"] == "s-rv"


def test_subagent_trace_carries_stored_variant(box):
    sid = "s-rv-sub"
    box.write_state(sid, "a-rv", task_session_id="own", user_prompt="refactor the parser module",
                    pattern_ids=IDS, retrieval_log_ids={IDS[0]: 7}, render_variant="full")
    box.seed_tools(sid, WORK, agent_id="a-rv")
    p = box.run_after_task(box.subagent_event(sid, "a-rv"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    assert learn["trace"]["render_variant"] == "full"
    assert "--applied-log-ids" not in learn["argv"]


def test_permission_denied_trace_carries_render_variant(clean_env, tmp_path):
    from test_permission_denied_v8 import _stored
    m = _stored(tmp_path, clean_env, "full")
    t = m._build_trace({"session_id": "pd-rv", "tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert t["render_variant"] == "full"
