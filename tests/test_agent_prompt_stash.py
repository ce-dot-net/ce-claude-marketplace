#!/usr/bin/env python3
"""WP-G RED — DESIGN §9 G1: SubagentStart query via a PreToolUse `Agent` stash.

p3 REFUTED "prompt in SubagentStart input": SubagentStart gets only {session_id,
transcript_path, cwd, prompt_id, agent_id, agent_type} (cc_hooks_reference.md:2553-2566).
The Agent tool input carries prompt / description / subagent_type (doc :1905-1912).
- PreToolUse matcher `Agent` (sync, timeout 5; NOT `Task`, a live alias that would
  double-fire) -> scripts/ace_pretooluse_agent_stash.sh -> shared-hooks/ace_agent_prompt_stash.py
  writes <session>/agent-prompts/<prompt_id>-<subagent_type>.json (<= 8 KB), no ace-cli,
  no stdout (a PreToolUse stdout could be read as a decision).
- SubagentStart consumes the stash for its prompt_id + agent_type (deletes it) and falls
  back to the 2 MB transcript scan only when absent.
"""
import json
import os
import time
import uuid

import pytest

from wpd_harness import PLUGIN_ROOT, SCRIPTS, HookEnv, shim_violations

SHIM = "ace_pretooluse_agent_stash.sh"
ENTRY = "ace_agent_prompt_stash.py"
SID = "cc-stash-1"
PID = "f486434d-aaaa-4bbb-8ccc-dddddddddddd"
STASH_PROMPT = "audit the payment webhook retry logic for idempotency bugs"
TRANSCRIPT_PROMPT = "an older, unrelated agent prompt about css colours"


@pytest.fixture
def env(tmp_path):
    return HookEnv(tmp_path, project_id="prj_stash_%s" % uuid.uuid4().hex[:6])


def _pre(env, prompt=STASH_PROMPT, subagent_type="Explore", prompt_id=PID, tool="Agent", **extra):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "PreToolUse",
          "transcript_path": str(env.tmp / "t.jsonl"), "permission_mode": "default",
          "tool_name": tool, "tool_use_id": "toolu_agent_1",
          "tool_input": {"prompt": prompt, "description": "audit webhook retries",
                         "subagent_type": subagent_type}}
    if prompt_id:
        ev["prompt_id"] = prompt_id
    ev.update(extra)
    return env.run(SHIM, ev)


def _stash(env, prompt_id=PID, subagent_type="Explore"):
    return env.session_dir(SID) / "agent-prompts" / ("%s-%s.json" % (prompt_id, subagent_type))


# ── hooks.json + shim ───────────────────────────────────────────────────────

def test_hooks_json_pretooluse_agent_only():
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    groups = hooks.get("PreToolUse") or []
    assert [g.get("matcher") for g in groups] == ["Agent"], "exactly one PreToolUse group, matcher 'Agent'"
    (h,) = groups[0]["hooks"]
    assert h["command"] == "${CLAUDE_PLUGIN_ROOT}/scripts/" + SHIM and h.get("args") == []
    assert h.get("timeout") == 5 and not h.get("async")


def test_shim_is_thin_and_executable():
    p = SCRIPTS / SHIM
    assert p.is_file() and os.access(p, os.X_OK)
    assert shim_violations(p, ENTRY) == []


# ── the stash writer ────────────────────────────────────────────────────────

def test_stash_written_silently_without_cli(env):
    proc = _pre(env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "", "PreToolUse stash must print nothing"
    assert env.cli_calls() == [], "stash hook must not spawn ace-cli"
    data = json.loads(_stash(env).read_text())
    assert data["prompt"] == STASH_PROMPT
    assert data["subagent_type"] == "Explore"
    assert data["description"] == "audit webhook retries"


def test_stash_bounded_to_8kb(env):
    _pre(env, prompt="x" * 200000)
    f = _stash(env)
    assert f.is_file() and f.stat().st_size <= 8192
    assert json.loads(f.read_text())["prompt"].startswith("xxxx")


def test_stash_fast(env):
    t0 = time.monotonic()
    _pre(env)
    assert time.monotonic() - t0 < 2.0, "sync PreToolUse with a 5 s budget"


@pytest.mark.parametrize("tool", ["Read", "Bash"])
def test_non_agent_tool_writes_nothing(env, tool):
    proc = _pre(env, tool=tool)
    assert proc.returncode == 0 and proc.stdout == ""
    assert not (env.session_dir(SID) / "agent-prompts").exists() or \
        not any((env.session_dir(SID) / "agent-prompts").iterdir())


def test_missing_prompt_id_writes_nothing(env):
    """No prompt_id (headless/old CC) -> SubagentStart cannot key the stash; fall back to scan."""
    proc = _pre(env, prompt_id=None)
    assert proc.returncode == 0 and proc.stdout == ""
    d = env.session_dir(SID) / "agent-prompts"
    assert not d.exists() or not any(d.iterdir())


@pytest.mark.parametrize("raw", ["", "not json", "[]"])
def test_garbage_stdin_exit_0_silent(env, raw):
    proc = env.run(SHIM, None, raw_stdin=raw)
    assert proc.returncode == 0 and proc.stdout == ""


# ── SubagentStart consumes the stash ────────────────────────────────────────

def _transcript(env, subagent_type="Explore"):
    t = env.tmp / "parent.jsonl"
    t.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_old", "name": "Agent",
         "input": {"subagent_type": subagent_type, "prompt": TRANSCRIPT_PROMPT}}]}}) + "\n")
    return t


def _start(env, agent_type="Explore", agent_id="agent-s1", prompt_id=PID):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "SubagentStart",
          "transcript_path": str(_transcript(env, agent_type)), "agent_id": agent_id,
          "agent_type": agent_type}
    if prompt_id:
        ev["prompt_id"] = prompt_id
    return env.run("ace_subagent_start_wrapper.sh", ev)


def _queries(env):
    return [c["stdin"] for c in env.cli_calls() if c["argv"][:1] == ["search"]]


def test_subagent_start_uses_stash_over_transcript(env):
    _pre(env)
    proc = _start(env)
    assert proc.returncode == 0, proc.stderr
    assert _queries(env) == [STASH_PROMPT], "stash (G1) must be the primary query source"


def test_subagent_start_consumes_stash(env):
    _pre(env)
    assert _stash(env).exists(), "precondition: PreToolUse wrote the stash"
    _start(env)
    assert not _stash(env).exists(), "the stash is consumed (deleted) by SubagentStart"


def test_subagent_start_ignores_stash_of_other_agent_type(env):
    _pre(env, subagent_type="Plan", prompt="plan something else entirely different")
    _start(env, agent_type="Explore")
    assert _queries(env) == [TRANSCRIPT_PROMPT]
    assert _stash(env, subagent_type="Plan").exists(), "another type's stash stays for its own agent"


def test_subagent_start_ignores_stash_of_other_prompt(env):
    _pre(env, prompt_id="00000000-0000-4000-8000-000000000000")
    _start(env)
    assert _queries(env) == [TRANSCRIPT_PROMPT]


def test_subagent_start_plugin_scoped_agent_type(env):
    """Plugin agents: agent_type 'my-plugin:reviewer' on both sides (doc :2551)."""
    _pre(env, subagent_type="my-plugin:reviewer")
    _start(env, agent_type="my-plugin:reviewer")
    assert _queries(env) == [STASH_PROMPT]


def test_subagent_start_falls_back_to_transcript_without_stash(env):
    """Regression guard: no stash -> bounded 2 MB transcript scan, as before."""
    _start(env)
    assert _queries(env) == [TRANSCRIPT_PROMPT]


def test_two_same_type_siblings_fall_back_to_transcript(env):
    """Parallel agents of one type in one prompt share a key: never answer with the
    wrong sibling's prompt -> mark ambiguous, reader falls back to the transcript scan."""
    _pre(env, prompt="first sibling prompt")
    _pre(env, prompt="second sibling prompt")
    _start(env)
    assert _queries(env) == [TRANSCRIPT_PROMPT]
