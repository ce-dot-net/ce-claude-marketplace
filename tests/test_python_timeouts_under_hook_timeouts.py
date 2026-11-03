#!/usr/bin/env python3
"""WP-G RED — DESIGN §11 A2: Python-level subprocess timeouts sit under the hook timeouts.

hooks.json (seconds, cc_hooks_reference.md:414): UPS 30, domain-shift 20, SubagentStart 30,
SessionStart 30, PreToolUse(Agent) 5; SessionEnd has no timeout (hard 1.5 s plugin budget,
doc :3578-3586). Python: run_search default 25, domain-shift 17, SubagentStart 25.
Guard: every ace-cli spawn timeout < its hook timeout - 2 s (p7: a 15 s Python cap killed
healthy searches under load; a Python cap >= the hook cap means CC kills the hook first
and the relevance row / state are lost). SessionEnd Python < 0.5 s cold.

The ace-cli spawn is captured in-process (subprocess.run patched); nothing hits the network.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from wpd_harness import PLUGIN_ROOT, SHARED, HookEnv

HOOKS = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
RESPONSE = {"count": 1, "retrieval_id": "r", "similar_patterns": [{
    "id": "ctx-1234567890-abcd", "content": "p", "section": "s", "confidence": 0.9,
    "cumulative_v15_reward": 1.0, "isAtRisk": False, "match_factors": {"bandit_rank": 1}}]}


def _hook_timeout(event, script):
    for g in HOOKS.get(event, []):
        for h in g["hooks"]:
            if h["command"].endswith("/" + script):
                return h.get("timeout")
    return None


@pytest.mark.parametrize("event,script,expected", [
    ("UserPromptSubmit", "ace_before_task_wrapper.sh", 30),
    ("PostToolUse", "ace_posttooluse_domain_inject.sh", 20),
    ("SubagentStart", "ace_subagent_start_wrapper.sh", 30),
    ("SessionStart", "ace_install_cli.sh", 30),
    ("PreToolUse", "ace_pretooluse_agent_stash.sh", 5),
])
def test_hooks_json_timeouts(event, script, expected):
    assert _hook_timeout(event, script) == expected


def test_sessionend_has_no_timeout():
    assert [h.get("timeout") for g in HOOKS["SessionEnd"] for h in g["hooks"]] == [None]


@pytest.fixture
def proj(tmp_path, monkeypatch):
    p = tmp_path / "proj"
    (p / ".claude").mkdir(parents=True)
    (p / ".claude" / "settings.json").write_text(json.dumps({"projectId": "prj_to", "orgId": "org_to"}))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.chdir(p)
    try:
        import ace_relevance_logger
        monkeypatch.setattr(ace_relevance_logger, "_logger", None)
    except Exception:
        pass
    return p


@pytest.fixture
def spawns(monkeypatch):
    seen = []
    real = subprocess.run

    def fake(cmd, *a, **kw):
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
        if argv and os.path.basename(str(argv[0])) == "ace-cli":
            seen.append((argv, kw.get("timeout")))
            out = json.dumps(RESPONSE) if "search" in argv else "{}"
            return subprocess.CompletedProcess(argv, 0, out if kw.get("text") else out.encode(),
                                               "" if kw.get("text") else b"")
        return real(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", fake)
    return seen


def _load(name):
    spec = importlib.util.spec_from_file_location("wpg_%s" % name, SHARED / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_main(mod, monkeypatch, event, pass_event=False):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    try:
        mod.main(event) if pass_event else mod.main()
    except SystemExit:
        pass


def _check(spawns, event, script, expected):
    searches = [t for argv, t in spawns if "search" in argv]
    assert searches, "no ace-cli search spawned"
    hook_t = _hook_timeout(event, script)
    for t in searches:
        assert t is not None and t == expected, "python search timeout %r, DESIGN §11 A2 wants %r" % (t, expected)
        assert t < hook_t - 2, "python timeout %r must be < hook timeout %r - 2" % (t, hook_t)


def test_ups_search_timeout(proj, spawns, monkeypatch, capsys):
    mod = _load("ace_before_task")
    _run_main(mod, monkeypatch, {"session_id": "s-to", "prompt_id": "p-to", "cwd": str(proj),
                                 "hook_event_name": "UserPromptSubmit",
                                 "transcript_path": str(proj / "t.jsonl"),
                                 "prompt": "refactor the authentication middleware to use JWT"})
    _check(spawns, "UserPromptSubmit", "ace_before_task_wrapper.sh", 25)


def test_domain_shift_search_timeout(proj, spawns, monkeypatch, tmp_path, capsys):
    d = tmp_path / "ace-pd" / "projects" / "prj_to"
    d.mkdir(parents=True)
    (d / "domains.json").write_text(json.dumps({"auth:local": {"count": 2}}))
    mod = _load("ace_domain_shift")
    _run_main(mod, monkeypatch, {"session_id": "s-to", "prompt_id": "p-to", "cwd": str(proj),
                                 "hook_event_name": "PostToolUse", "tool_name": "Read",
                                 "tool_input": {"file_path": str(proj / "src/auth/x.py")},
                                 "tool_response": {"type": "text"}, "tool_use_id": "t"})
    _check(spawns, "PostToolUse", "ace_posttooluse_domain_inject.sh", 17)


def test_subagent_start_search_timeout(proj, spawns, monkeypatch, capsys):
    t = proj / "parent.jsonl"
    t.write_text(json.dumps({"message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Agent",
         "input": {"subagent_type": "Explore", "prompt": "map the auth module endpoints"}}]}}) + "\n")
    mod = _load("ace_subagent_start")
    _run_main(mod, monkeypatch, {"session_id": "s-to", "prompt_id": "p-to", "cwd": str(proj),
                                 "hook_event_name": "SubagentStart", "transcript_path": str(t),
                                 "agent_id": "agent-to", "agent_type": "Explore"}, pass_event=True)
    _check(spawns, "SubagentStart", "ace_subagent_start_wrapper.sh", 25)


def test_run_search_default_is_25():
    sys.path.insert(0, str(SHARED / "utils"))
    import inspect
    import ace_cli
    assert inspect.signature(ace_cli.run_search).parameters["timeout"].default == 25


def test_sessionend_cold_under_half_second(tmp_path):
    """A2: SessionEnd Python < 0.5 s cold (python_path cache present, as after SessionStart)."""
    env = HookEnv(tmp_path, project_id="prj_se")
    (env.pd / "python_path").write_text(sys.executable + "\n")
    sd = env.session_dir("s-end")
    sd.mkdir(parents=True)
    (sd / "patterns-used-main.json").write_text("{}")
    ev = {"session_id": "s-end", "cwd": str(env.proj), "hook_event_name": "SessionEnd", "reason": "exit"}
    best = None
    for _ in range(3):  # best of 3: the bound is about our work, not machine load spikes
        t0 = time.monotonic()
        env.run("ace_sessionend_wrapper.sh", ev)
        dt = time.monotonic() - t0
        best = dt if best is None else min(best, dt)
    assert best < 0.5, "SessionEnd took %.3fs" % best
