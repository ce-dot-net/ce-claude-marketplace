#!/usr/bin/env python3
"""WP-G RED — DESIGN §9 G2: prompt_id is the task anchor.

p3 PROVEN: the identical `prompt_id` (cc_hooks_reference.md:733) arrives on UPS ->
PreToolUse -> SubagentStart -> every subagent hook -> SubagentStop -> Stop -> SessionEnd;
background subagents keep the spawning prompt_id. So:
- UPS: task_session_id = prompt_id (else uuid4); `--pin-session <prompt_id>`; state tsid = prompt_id.
- SubagentStart: pin + state tsid = prompt_id (the task that spawned it).
- domain-shift: pin keyed by prompt_id — no uuid minting when prompt_id is present, and a
  stale tsid left in the state by an earlier prompt does not win over the current prompt_id.
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


def test_subagent_start_pins_spawning_prompt_id(env):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "SubagentStart",
          "transcript_path": str(_transcript(env)), "prompt_id": PROMPT_ID,
          "agent_id": "agent-a1", "agent_type": "Explore"}
    proc = env.run("ace_subagent_start_wrapper.sh", ev)
    assert proc.returncode == 0, proc.stderr
    assert _pins(env) == [PROMPT_ID], "SubagentStart must pin the spawning prompt_id (G2)"
    assert env.read_state(SID, "agent-a1")["task_session_id"] == PROMPT_ID


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


def test_domain_shift_pins_prompt_id_without_state(env):
    """G2: no uuid minting — with no state yet, the pin is the event prompt_id."""
    _read(env)
    assert _pins(env) == [PROMPT_ID]
    assert env.read_state(SID)["task_session_id"] == PROMPT_ID


def test_domain_shift_prompt_id_beats_stale_state_tsid(env):
    """G2 'state keyed by prompt_id': a tsid left by an EARLIER prompt (e.g. a skipped
    machine prompt did not reset it) must not be reused for the current prompt."""
    env.write_state(SID, None, task_session_id="tsid-from-previous-prompt")
    _read(env)
    assert _pins(env) == [PROMPT_ID]


def test_domain_shift_in_subagent_pins_prompt_id(env):
    """G2: subagent hooks carry the spawning prompt_id -> same anchor as its SubagentStart."""
    env.write_state(SID, "agent-ds", task_session_id=PROMPT_ID)
    _read(env, agent_id="agent-ds")
    assert _pins(env) == [PROMPT_ID]


def test_domain_shift_without_prompt_id_reuses_state_tsid(env):
    """Back-compat (no prompt_id): reuse the state tsid. Regression guard."""
    env.write_state(SID, None, task_session_id="tsid-main-from-ups")
    _read(env, prompt_id=None)
    assert _pins(env) == ["tsid-main-from-ups"]
