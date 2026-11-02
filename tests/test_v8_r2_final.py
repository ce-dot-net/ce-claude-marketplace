#!/usr/bin/env python3
"""v8 round 2 FINAL fix regressions: SessionEnd/Stop race, domain-shift claim, Agent stash
interleave, is_interrupt, denied batch rows, batch ordering, SubagentStop parent_task_id."""
import json
import sqlite3
import subprocess
import sys
import time
import uuid

import pytest

from test_stop_v8 import Box, WORK, PROJECT_ID, ORG_ID, SCRIPTS  # noqa: F401
from wpd_harness import HookEnv, flag_value, SCRIPTS as WPD_SCRIPTS


def _wait(pred, secs=8.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


# ── SessionEnd right after Stop ──────────────────────────────────────────────

@pytest.mark.parametrize("delay", [0, 0.02])
def test_session_end_right_after_stop_still_learns_once(tmp_path, delay):
    box = Box(tmp_path)
    sid = "s-race-%s" % delay
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the race fix for session end")
    env = box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_LEARN_INLINE="")
    stop = subprocess.Popen(["bash", str(SCRIPTS / "ace_stop_wrapper.sh")], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(box.elsewhere), env=env)
    stop.stdin.write(json.dumps(box.stop_event(sid)))
    stop.stdin.close()
    time.sleep(delay)
    se = subprocess.run(["bash", str(SCRIPTS / "ace_sessionend_wrapper.sh")],
                        input=json.dumps({"session_id": sid, "cwd": str(box.project),
                                          "hook_event_name": "SessionEnd", "reason": "other"}),
                        capture_output=True, text=True, cwd=str(box.elsewhere), env=env, timeout=30)
    assert se.returncode == 0
    stop.wait(timeout=30)
    assert _wait(lambda: len(box.cli_calls("learn")) >= 1, 10), "learn lost to SessionEnd"
    time.sleep(0.5)
    assert len(box.cli_calls("learn")) == 1


# ── domain-shift: one search per shift under parallel Reads ──────────────────

def test_parallel_reads_one_domain_shift_search(tmp_path):
    env = HookEnv(tmp_path, project_id="prj_par_%s" % uuid.uuid4().hex[:6])
    env.set_search_response({"count": 1, "retrieval_id": "r", "similar_patterns": [{
        "id": "ctx-1234567890-abcd", "content": "p", "section": "s", "confidence": 0.9,
        "cumulative_v15_reward": 1.0, "isAtRisk": False, "match_factors": {"bandit_rank": 1}}]})
    cli = env.bin / "ace-cli"
    cli.write_text(cli.read_text().replace("log = os.environ", "import time\ntime.sleep(0.6)\nlog = os.environ", 1))
    env.write_domains({"auth:local": {"count": 2}})
    procs = []
    for i in range(3):
        ev = {"session_id": "s-par", "cwd": str(env.proj), "prompt_id": "pid", "hook_event_name": "PostToolUse",
              "tool_name": "Read", "tool_input": {"file_path": str(env.proj / ("src/auth/f%d.py" % i))},
              "tool_response": {}, "tool_use_id": "t%d" % i, "transcript_path": str(env.tmp / "t.jsonl")}
        p = subprocess.Popen(["bash", str(WPD_SCRIPTS / "ace_posttooluse_domain_inject.sh")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             cwd=str(env.elsewhere), env=env.env())
        p.stdin.write(json.dumps(ev))
        p.stdin.close()
        procs.append(p)
    outs = [p.stdout.read() for p in procs]
    for p in procs:
        p.wait(timeout=30)
    searches = [c for c in env.cli_calls() if c["argv"][:1] == ["search"]]
    assert len(searches) == 1, "expected 1 search for 3 parallel reads, got %d" % len(searches)
    assert sum(1 for o in outs if o.strip()) == 1, "expected exactly 1 injection"


def test_failed_domain_search_keeps_domain_retryable(tmp_path):
    env = HookEnv(tmp_path, project_id="prj_retry")
    env.write_domains({"auth:local": {"count": 2}})
    ev = {"session_id": "s-r", "cwd": str(env.proj), "prompt_id": "pid", "hook_event_name": "PostToolUse",
          "tool_name": "Read", "tool_input": {"file_path": str(env.proj / "src/auth/f.py")},
          "tool_response": {}, "tool_use_id": "t", "transcript_path": str(env.tmp / "t.jsonl")}
    env.run("ace_posttooluse_domain_inject.sh", ev, extra_env={"ACE_FAKE_CLI_EXIT": "1"})
    env.run("ace_posttooluse_domain_inject.sh", ev)
    assert len([c for c in env.cli_calls() if c["argv"][:1] == ["search"]]) >= 2
    assert not list(env.session_dir("s-r").glob("domain-claim-*"))


# ── Agent prompt stash interleave ────────────────────────────────────────────

def test_stash_interleave_never_leaks_sibling_prompt(tmp_path):
    env = HookEnv(tmp_path, project_id="prj_stash")
    env.set_search_response({"count": 0, "similar_patterns": []})
    sid, pid = "s-stash", "pid-stash"
    tr = env.tmp / "parent.jsonl"
    tr.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t1", "name": "Agent",
         "input": {"subagent_type": "Explore", "prompt": "transcript fallback prompt about auth"}}]}}) + "\n")

    def pre(tag):
        env.run("ace_pretooluse_agent_stash.sh", {
            "session_id": sid, "cwd": str(env.proj), "prompt_id": pid, "hook_event_name": "PreToolUse",
            "tool_name": "Agent", "tool_use_id": "u" + tag, "transcript_path": str(tr),
            "tool_input": {"prompt": "PROMPT-%s css styling" % tag, "subagent_type": "Explore"}})

    def start(agent):
        env.run("ace_subagent_start_wrapper.sh", {
            "session_id": sid, "cwd": str(env.proj), "prompt_id": pid, "hook_event_name": "SubagentStart",
            "transcript_path": str(tr), "agent_id": agent, "agent_type": "Explore"})

    pre("A"); pre("B"); start("agA"); pre("C"); start("agB")
    for ag in ("agA", "agB"):
        st = env.read_state(sid, ag)
        assert st and st.get('user_prompt'), (ag, st)
        assert "PROMPT-C" not in (st.get("user_prompt") or ""), ag
        assert "PROMPT-B" not in (st.get("user_prompt") or ""), ag


# ── accumulator ──────────────────────────────────────────────────────────────

def _rows(box, sid):
    con = sqlite3.connect(str(box.session_dir(sid) / "tools.db"))
    r = con.execute("SELECT tool_use_id, success, error_first_line FROM tool_uses ORDER BY id").fetchall()
    con.close()
    return r


def _fail(box, sid, tuid, **kw):
    ev = {"session_id": sid, "cwd": str(box.project), "hook_event_name": "PostToolUseFailure",
          "tool_name": "Bash", "tool_input": {"command": "x"}, "tool_use_id": tuid,
          "error": "Exit code 1\nboom", "is_interrupt": False}
    ev.update(kw)
    return box.run_shim("ace_posttoolusefailure_wrapper.sh", ev)


def _batch(box, sid, calls):
    return box.run_shim("ace_posttooluse_wrapper.sh", {
        "session_id": sid, "cwd": str(box.project), "hook_event_name": "PostToolBatch",
        "tool_calls": calls}, args=("--batch",))


def test_interrupt_is_not_a_failure(tmp_path):
    box = Box(tmp_path)
    _fail(box, "s-int", "ti", is_interrupt=True, error="aborted by user")
    assert _rows(box, "s-int") == [("ti", None, "interrupted")]
    from ace_tool_accumulator import get_session_tools
    tools = get_session_tools("s-int", str(box.project), db_path=box.session_dir("s-int") / "tools.db")
    assert "error" not in json.loads(tools[0][2])


def test_denied_batch_call_recorded_as_failure(tmp_path):
    box = Box(tmp_path)
    _batch(box, "s-den", [
        {"tool_name": "Bash", "tool_input": {"command": "rm x"}, "tool_use_id": "d1",
         "tool_response": "Permission to use Bash with command rm x has been denied."},
        {"tool_name": "Read", "tool_input": {}, "tool_use_id": "d2", "tool_response": "fine"}])
    rows = _rows(box, "s-den")
    assert rows[0][1] == 0 and "denied" in rows[0][2] and rows[1][1] == 1


def test_failure_before_batch_keeps_batch_order(tmp_path):
    box = Box(tmp_path)
    _fail(box, "s-ord", "t3")
    _batch(box, "s-ord", [
        {"tool_name": "Edit", "tool_input": {}, "tool_use_id": "t1", "tool_response": "ok"},
        {"tool_name": "Bash", "tool_input": {}, "tool_use_id": "t3", "tool_response": "x"}])
    assert [r[0] for r in _rows(box, "s-ord")] == ["t1", "t3"]
    assert _rows(box, "s-ord")[1][1] == 0  # failure still wins


def test_accumulator_skips_repo_without_ace_config(tmp_path):
    box = Box(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    _batch_ev = {"session_id": "s-plain", "cwd": str(plain), "hook_event_name": "PostToolBatch",
                 "tool_calls": [{"tool_name": "Edit", "tool_input": {}, "tool_use_id": "p1", "tool_response": "ok"}]}
    box.run_shim("ace_posttooluse_wrapper.sh", _batch_ev, args=("--batch",))
    assert not list(box.pd.glob("projects/default/sessions/s-plain/tools.db"))


# ── SubagentStop: own id + parent_task_id ────────────────────────────────────

def test_subagent_stop_learn_uses_subagent_id_and_parent(tmp_path):
    box = Box(tmp_path)
    sid = "s-sub"
    box.write_state(sid, "agent-p1", task_session_id="own-uuid", parent_task_id="parent-prompt-id",
                    user_prompt="refactor the parser module")
    box.seed_tools(sid, WORK, agent_id="agent-p1")
    p = box.run_after_task(box.subagent_event(sid, "agent-p1", prompt_id="parent-prompt-id"),
                           ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1
    tr = learns[0]["trace"]
    assert tr["session_id"] == "own-uuid" and tr["parent_task_id"] == "parent-prompt-id"


def test_main_stop_falls_back_to_prompt_id_without_state_tsid(tmp_path):
    box = Box(tmp_path)
    sid = "s-fb"
    box.seed_tools(sid, WORK)
    box.write_state(sid, task_session_id=None, user_prompt="implement the fallback anchor")
    p = box.run_after_task(box.stop_event(sid, prompt_id="pid-fallback"),
                           ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 1 and learns[0]["trace"]["session_id"] == "pid-fallback"


def test_session_end_keeps_dir_with_fresh_state_and_cleans_old(tmp_path):
    import os
    from wpa_harness import Env
    env = Env(tmp_path)
    d = env.session_dir("s-fresh")
    d.mkdir(parents=True)
    f = d / "patterns-used-main.json"
    f.write_text("{}")
    ev = {"session_id": "s-fresh", "hook_event_name": "SessionEnd", "reason": "other", "cwd": str(env.project)}
    env.run("ace_sessionend_wrapper.sh", ev)
    assert d.exists(), "fresh state must survive (Stop may not have consumed it yet)"
    os.utime(str(f), (time.time() - 300, time.time() - 300))
    env.run("ace_sessionend_wrapper.sh", ev)
    assert not d.exists()
