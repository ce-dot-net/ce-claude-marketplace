#!/usr/bin/env python3
"""WP-G RED — DESIGN §10 P-26: every hook early-exits on <session>/disabled.flag AND
<project>/disabled.flag (plugin_data_dir.is_disabled).

Scope here = the WP-G hooks (UPS, SubagentStart, domain-shift, PreToolUse Agent stash).
Early exit = no ace-cli spawn, no stdout, and no new state written.
The Stop/SubagentStop/accumulator/PermissionDenied/SessionStart side is WP-H.
"""
import json
import uuid

import pytest

from wpd_harness import HookEnv

SID = "cc-disabled-1"
PID = "f486434d-0000-4000-8000-00000000d15a"
RESPONSE = {"count": 1, "retrieval_id": "r", "similar_patterns": [{
    "id": "ctx-1234567890-abcd", "content": "p", "section": "s", "confidence": 0.9,
    "cumulative_v15_reward": 1.0, "isAtRisk": False, "match_factors": {"bandit_rank": 1}}]}


@pytest.fixture
def env(tmp_path):
    e = HookEnv(tmp_path, project_id="prj_dis_%s" % uuid.uuid4().hex[:6])
    e.set_search_response(RESPONSE)
    e.write_domains({"auth:local": {"count": 2}})
    return e


def _disable(env, scope):
    if scope == "session":
        env.disable(SID)
    else:
        p = env.pd / "projects" / env.project_id / "disabled.flag"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("disabled for the whole project")


def _transcript(env):
    t = env.tmp / "parent.jsonl"
    t.write_text(json.dumps({"message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Agent",
         "input": {"subagent_type": "Explore", "prompt": "map the auth module endpoints"}}]}}) + "\n")
    return str(t)


def _events(env):
    base = {"session_id": SID, "cwd": str(env.proj), "prompt_id": PID,
            "transcript_path": str(env.tmp / "t.jsonl")}
    return {
        "ace_before_task_wrapper.sh": dict(base, hook_event_name="UserPromptSubmit",
                                           prompt="refactor the authentication middleware to use JWT"),
        "ace_subagent_start_wrapper.sh": dict(base, hook_event_name="SubagentStart",
                                              transcript_path=_transcript(env),
                                              agent_id="agent-d1", agent_type="Explore"),
        "ace_posttooluse_domain_inject.sh": dict(base, hook_event_name="PostToolUse", tool_name="Read",
                                                 tool_input={"file_path": str(env.proj / "src/auth/x.py")},
                                                 tool_response={"type": "text"}, tool_use_id="t1"),
        "ace_pretooluse_agent_stash.sh": dict(base, hook_event_name="PreToolUse", tool_name="Agent",
                                              tool_use_id="t2",
                                              tool_input={"prompt": "map the auth module",
                                                          "subagent_type": "Explore"}),
    }


HOOKS = ["ace_before_task_wrapper.sh", "ace_subagent_start_wrapper.sh",
         "ace_posttooluse_domain_inject.sh", "ace_pretooluse_agent_stash.sh"]


def _state_files(env):
    d = env.session_dir(SID)
    if not d.exists():
        return []
    return sorted(str(p.relative_to(d)) for p in d.rglob("*")
                  if p.is_file() and p.name != "disabled.flag")


def test_enabled_baseline_spawns(env):
    """Sanity: without a flag the UPS hook does search (so the cases below are meaningful)."""
    ev = _events(env)["ace_before_task_wrapper.sh"]
    env.run("ace_before_task_wrapper.sh", ev)
    assert [c for c in env.cli_calls() if c["argv"][:1] == ["search"]]


@pytest.mark.parametrize("scope", ["session", "project"])
@pytest.mark.parametrize("hook", HOOKS)
def test_hook_early_exits_when_disabled(env, hook, scope):
    _disable(env, scope)
    proc = env.run(hook, _events(env)[hook])
    assert proc.returncode == 0, proc.stderr
    assert env.cli_calls() == [], "%s spawned ace-cli while %s-disabled" % (hook, scope)
    assert proc.stdout.strip() == "", "%s printed output while disabled" % hook
    assert _state_files(env) == [], "%s wrote state while disabled: %s" % (hook, _state_files(env))


# ── WP-H side (round 2 final fix): Stop/SubagentStop/accumulator/PermissionDenied/compact ──

def _wph_events(env):
    base = {"session_id": SID, "cwd": str(env.proj), "prompt_id": PID,
            "transcript_path": str(env.tmp / "t.jsonl")}
    tr = env.tmp / "agent.jsonl"
    tr.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "refactor the parser"}}) + "\n")
    return {
        "ace_stop_wrapper.sh": (dict(base, hook_event_name="Stop", last_assistant_message="done"), ()),
        "ace_subagent_stop_wrapper.sh": (dict(base, hook_event_name="SubagentStop", agent_id="agent-w1",
                                              agent_type="Explore", agent_transcript_path=str(tr),
                                              last_assistant_message="done"), ()),
        "ace_posttooluse_wrapper.sh": (dict(base, hook_event_name="PostToolBatch", tool_calls=[
            {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}, "tool_response": "ok",
             "tool_use_id": "tb1"}]), ("--batch",)),
        "ace_posttoolusefailure_wrapper.sh": (dict(base, hook_event_name="PostToolUseFailure",
                                                   tool_name="Bash", tool_input={"command": "x"},
                                                   tool_use_id="tf1", error="Exit code 1\nboom",
                                                   is_interrupt=False), ()),
        "ace_permission_denied_wrapper.sh": (dict(base, hook_event_name="PermissionDenied",
                                                  tool_name="Bash", tool_input={"command": "rm -rf /"}), ()),
        "ace_sessionstart_compact.sh": (dict(base, hook_event_name="SessionStart", source="compact"),
                                        ("--compact",)),
    }


WPH_HOOKS = ["ace_stop_wrapper.sh", "ace_subagent_stop_wrapper.sh", "ace_posttooluse_wrapper.sh",
             "ace_posttoolusefailure_wrapper.sh", "ace_permission_denied_wrapper.sh",
             "ace_sessionstart_compact.sh"]


def test_compact_reinjects_when_enabled(env):
    env.write_state(SID, None, rendered_context="RENDERED-CTX")
    ev, args = _wph_events(env)["ace_sessionstart_compact.sh"]
    proc = env.run("ace_sessionstart_compact.sh", ev, args=args)
    assert "RENDERED-CTX" in proc.stdout


@pytest.mark.parametrize("scope", ["session", "project"])
@pytest.mark.parametrize("hook", WPH_HOOKS)
def test_wph_hook_early_exits_when_disabled(env, hook, scope):
    env.write_state(SID, None, rendered_context="RENDERED-CTX", user_prompt="refactor the parser module")
    env.write_state(SID, "agent-w1", user_prompt="refactor the parser module")
    _disable(env, scope)
    before = _state_files(env)
    ev, args = _wph_events(env)[hook]
    proc = env.run(hook, ev, args=args, extra_env={"ACE_LEARN_INLINE": "1"})
    assert proc.returncode == 0, proc.stderr
    assert env.cli_calls() == [], "%s spawned ace-cli while %s-disabled" % (hook, scope)
    assert proc.stdout.strip() == "", "%s printed output while disabled" % hook
    assert _state_files(env) == before, "%s touched state while disabled" % hook
    assert not (env.session_dir(SID) / "tools.db").exists()
