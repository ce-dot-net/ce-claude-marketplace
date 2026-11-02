#!/usr/bin/env python3
"""WP-G RED — DESIGN §9 G2: prompt_id is the task anchor.

p3 PROVEN: the identical `prompt_id` (cc_hooks_reference.md:733) arrives on UPS ->
PreToolUse -> SubagentStart -> every subagent hook -> SubagentStop -> Stop -> SessionEnd;
background subagents keep the spawning prompt_id. So:
- UPS: task_session_id = prompt_id (else uuid4); `--pin-session <prompt_id>`; state tsid = prompt_id.
- SubagentStart (DESIGN §12, overrides G2): fresh uuid4 per agent, parent prompt_id only as parent_task_id.
- domain-shift (§16 P8): NO --pin-session (the server never credits those rows; sqlite pin is the lock
  source). The state tsid stays: main agent = prompt_id; inside a subagent = that subagent's own id — no uuid
  minting when prompt_id is present, and a stale tsid left by an earlier prompt does not win over prompt_id.
Hooks run through their shims (HookEnv: fake ace-cli on PATH, tmp CLAUDE_PLUGIN_DATA).
"""
import json
import uuid

import pytest

from wpd_harness import HookEnv, flag_value

PROMPT_ID = "f486434d-1111-4222-8333-944455556666"
SID = "cc-anchor-1"
RESPONSE = {"count": 1, "retrieval_id": "ret-anchor", "similar_patterns": [{
    "id": "ctx-1234567890-abcd", "content": "anchor pattern", "section": "strategies",
    "confidence": 0.9, "helpful": 2, "harmful": 0, "cumulative_v15_reward": 1.0,
    "isAtRisk": False, "match_factors": {"bandit_rank": 1, "retrieval_log_id": 11}}]}


@pytest.fixture
def env(tmp_path):
    e = HookEnv(tmp_path, project_id="prj_anchor_%s" % uuid.uuid4().hex[:6])
    e.set_search_response(RESPONSE)
    return e


def _pins(env):
    return [flag_value(c["argv"], "--pin-session") for c in env.cli_calls() if c["argv"][:1] == ["search"]]


def _ups(env, prompt_id=PROMPT_ID):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "UserPromptSubmit",
          "transcript_path": str(env.tmp / "t.jsonl"),
          "prompt": "refactor the authentication middleware to use JSON web tokens"}
    if prompt_id:
        ev["prompt_id"] = prompt_id
    return env.run("ace_before_task_wrapper.sh", ev)


def test_ups_pins_prompt_id(env):
    proc = _ups(env)
    assert proc.returncode == 0, proc.stderr
    assert _pins(env) == [PROMPT_ID], "UPS must pin the hook input prompt_id (G2)"
    assert env.read_state(SID)["task_session_id"] == PROMPT_ID


def test_ups_without_prompt_id_pins_uuid4(env):
    """G2 fallback (headless / old CC): uuid4. Regression guard."""
    _ups(env, prompt_id=None)
    pins = _pins(env)
    assert len(pins) == 1 and uuid.UUID(pins[0]).version == 4
    assert env.read_state(SID)["task_session_id"] == pins[0]


def _transcript(env, subagent_type="Explore", prompt="find every API endpoint in the auth module"):
    t = env.tmp / "parent.jsonl"
    t.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Agent",
         "input": {"subagent_type": subagent_type, "description": "find endpoints", "prompt": prompt}}]}}) + "\n")
    return t


def _sstart(env, agent_id, prompt_id=PROMPT_ID):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "SubagentStart",
          "transcript_path": str(_transcript(env)), "agent_id": agent_id, "agent_type": "Explore"}
    if prompt_id:
        ev["prompt_id"] = prompt_id
    return env.run("ace_subagent_start_wrapper.sh", ev, extra_env={"ACE_LOCAL_REUSE": ""})  # per-agent pins, not §32 reuse


def test_subagent_start_pin_is_fresh_uuid4_not_prompt_id(env):
    """§12: a subagent is its own ACE session; the parent prompt_id is only parent_task_id."""
    proc = _sstart(env, "agent-a1")
    assert proc.returncode == 0, proc.stderr
    pins = _pins(env)
    assert len(pins) == 1 and pins[0] != PROMPT_ID and uuid.UUID(pins[0]).version == 4
    st = env.read_state(SID, "agent-a1")
    assert st["task_session_id"] == pins[0]
    assert st["parent_task_id"] == PROMPT_ID
    rows = [r for r in env.relevance_rows() if r.get("hook") == "SubagentStart"]
    assert rows and rows[-1].get("parent_task_id") == PROMPT_ID


def test_two_concurrent_agents_get_different_ids(env):
    _sstart(env, "agent-c1")
    _sstart(env, "agent-c2")
    pins = _pins(env)
    assert len(pins) == 2 and pins[0] != pins[1] and PROMPT_ID not in pins
    assert env.read_state(SID, "agent-c1")["task_session_id"] != env.read_state(SID, "agent-c2")["task_session_id"]


def test_subagent_start_without_prompt_id_pins_uuid4(env):
    """Regression guard for the no-prompt_id fallback."""
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "SubagentStart",
          "transcript_path": str(_transcript(env)), "agent_id": "agent-a2", "agent_type": "Explore"}
    env.run("ace_subagent_start_wrapper.sh", ev)
    pins = _pins(env)
    assert len(pins) == 1 and uuid.UUID(pins[0]).version == 4


# ── domain shift ────────────────────────────────────────────────────────────

def _read(env, prompt_id=PROMPT_ID, agent_id=None):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "PostToolUse",
          "transcript_path": str(env.tmp / "t.jsonl"), "tool_name": "Read",
          "tool_input": {"file_path": str(env.proj / "src/auth/login_handler.py")},
          "tool_response": {"type": "text"}, "tool_use_id": "toolu_ds"}
    if prompt_id:
        ev["prompt_id"] = prompt_id
    if agent_id:
        ev.update(agent_id=agent_id, agent_type="Explore")
    env.write_domains({"auth:local": {"count": 3}})
    return env.run("ace_posttooluse_domain_inject.sh", ev)


def test_domain_shift_state_tsid_is_prompt_id_without_state(env):
    """G2: no uuid minting — with no state yet, the state tsid is the event prompt_id."""
    _read(env)
    assert _pins(env) == [None], "P8: domain-shift passes no --pin-session"
    assert env.read_state(SID)["task_session_id"] == PROMPT_ID


def test_domain_shift_keeps_the_stored_anchor_over_the_event_prompt_id(env):
    """§16 P2 (reverses G2 here): UPS writes the anchor on every human prompt, so the stored tsid is the task's.
    After a deferred Stop the <task-notification> turn has a NEW prompt_id that must not replace it."""
    env.write_state(SID, None, task_session_id="tsid-of-the-human-prompt")
    _read(env)
    assert _pins(env) == [None]
    assert env.read_state(SID)["task_session_id"] == "tsid-of-the-human-prompt"


def test_domain_shift_without_stored_anchor_falls_back_to_prompt_id(env):
    _read(env)
    assert env.read_state(SID)["task_session_id"] == PROMPT_ID


def test_domain_shift_in_subagent_uses_subagent_id_not_prompt_id(env):
    """§12: inside a subagent the state tsid is the subagent's own id from SubagentStart."""
    env.write_state(SID, "agent-ds", task_session_id="sub-own-id")
    _read(env, agent_id="agent-ds")
    assert _pins(env) == [None]
    assert env.read_state(SID, "agent-ds")["task_session_id"] == "sub-own-id"


def test_domain_shift_in_subagent_without_state_mints_uuid4(env):
    _read(env, agent_id="agent-ds2")
    assert _pins(env) == [None]
    tsid = env.read_state(SID, "agent-ds2")["task_session_id"]
    assert tsid != PROMPT_ID and uuid.UUID(tsid).version == 4


def test_domain_shift_without_prompt_id_reuses_state_tsid(env):
    """Back-compat (no prompt_id): reuse the state tsid. Regression guard."""
    env.write_state(SID, None, task_session_id="tsid-main-from-ups")
    _read(env, prompt_id=None)
    assert _pins(env) == [None]
    assert env.read_state(SID)["task_session_id"] == "tsid-main-from-ups"
