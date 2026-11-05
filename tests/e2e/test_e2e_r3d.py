"""v8.0.0 round 3d RED (hook-level, ACE_E2E=1): the full chains, routed exactly as hooks.json does.

§16 P2 chain from the 2.1.316 probe (research2/wfprobe/runs/wf.events.jsonl): UPS(human) -> Stop#1
background_tasks=[workflow running] -> SubagentStop x N -> UPS(<task-notification>, new prompt_id) ->
Stop#2 background_tasks=[] -> SessionEnd. §16 P7 fork chain. §23: no npm view/install on any hook.
"""
import json
import os


import pytest

import ace_e2e_harness as H
from test_e2e_r3a import STORED_QUERY, World, _seed_work, w  # noqa: F401

pytestmark = pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1")

HUMAN = "Refactor the billing retry worker so duplicate webhooks are dropped"
FINAL = "Both workflow agents finished; duplicates are now dropped."


def _run_ok(w, ev, **env):
    out = []
    for _h, rc, so, se, _t in w.run(ev, **env):
        assert rc == 0, se
        out.append(so)
    return out


def _state(w, agent="main"):
    return w.session_dir / ("patterns-used-%s.json" % agent)


def _relevance(w, event):
    p = w.proj / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
    return [r for r in rows if r.get("event") == event]


def _human(w):
    _run_ok(w, w.event("UserPromptSubmit_human", prompt=HUMAN, prompt_id=w.prompt_id))
    assert json.loads(_state(w).read_text())["task_session_id"] == w.prompt_id
    _seed_work(w)


def test_stop_with_running_workflow_defers(w):
    _human(w)
    rows = w.tool_rows()
    assert rows
    out = _run_ok(w, w.event("Stop_background_running", prompt_id=w.prompt_id))
    assert out == [""], "deferral is silent"
    assert w.cli_calls("learn") == [], "the 'waiting' turn must not be learned"
    assert _state(w).exists() and w.tool_rows() == rows
    assert _relevance(w, "learn_deferred")
    assert not list(w.session_dir.glob("learn-inflight-*.lock"))


def test_deferred_task_learns_once_with_the_human_prompt_after_the_notification(w):
    _human(w)
    _run_ok(w, w.event("Stop_background_running", prompt_id=w.prompt_id))
    note = str(os.urandom(4).hex())
    _run_ok(w, w.event("UserPromptSubmit_task_notification", prompt_id="note-" + note))
    assert json.loads(_state(w).read_text())["task_session_id"] == w.prompt_id, "the guard must not touch the main state"
    # a tool call in the notification turn (domain shift) must keep the human anchor, not adopt note-<id>
    w.write_domains()
    _run_ok(w, w.event("PostToolUse_Read", prompt_id="note-" + note))
    assert json.loads(_state(w).read_text())["task_session_id"] == w.prompt_id, "domain shift overwrote the anchor"
    _run_ok(w, w.event("Stop", prompt_id="note-" + note, last_assistant_message=FINAL))
    (learn,) = w.cli_calls("learn")
    t = learn["trace"]
    assert HUMAN in t["task"], t["task"]
    assert t["session_id"] == w.prompt_id
    assert t["result"]["summary"].startswith(FINAL)
    assert t["trajectory"], "the full tool trajectory survives the deferral"
    assert "--retrieval-id" in learn["argv"], "the task's own search is credited, not consumed by Stop #1"


@pytest.mark.parametrize("type_", ["monitor", "shell"])
def test_stop_with_long_lived_task_learns(w, type_):
    _human(w)
    _run_ok(w, w.event("Stop", prompt_id=w.prompt_id,
                       background_tasks=[{"id": "m1", "type": type_, "status": "running", "description": "x"}]))
    assert len(w.cli_calls("learn")) == 1


def test_fork_chain_no_search_no_inject_but_learns_with_own_pin(w):
    _run_ok(w, w.event("UserPromptSubmit_human", prompt=HUMAN, prompt_id=w.prompt_id))
    n = len(w.cli_calls("search"))
    w.stash_agent_prompt(subagent_type="fork")  # a query IS available: the skip must be deliberate
    out = _run_ok(w, w.event("SubagentStart_fork", prompt_id=w.prompt_id))
    assert out == [""] and len(w.cli_calls("search")) == n, "forks inherit the parent's injected block"
    tsid = json.loads(_state(w, w.agent_id).read_text())["task_session_id"]
    assert tsid != w.prompt_id
    seed = w.event("PostToolBatch", agent_id=w.agent_id, agent_type="fork", prompt_id=w.prompt_id)
    _run_ok(w, seed)
    _run_ok(w, w.event("SubagentStop", agent_type="fork", prompt_id=w.prompt_id, last_assistant_message="fork done"))
    (learn,) = w.cli_calls("learn")
    assert learn["trace"]["session_id"] == tsid and learn["trace"]["parent_agent_id"] == w.prompt_id


def test_subagent_handback_reaches_the_trace(w):
    report = "## Report\n" + "body " * 300
    with w.agent_transcript.open("a") as f:
        f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_hb", "name": "SubagentHandback", "input": {"message": report}}]}}) + "\n")
    w.stash_agent_prompt()
    _run_ok(w, w.event("SubagentStart", prompt_id=w.prompt_id, agent_type="general-purpose"))
    _run_ok(w, w.event("SubagentStop", agent_type="general-purpose", last_assistant_message="closing."))
    (learn,) = w.cli_calls("learn")
    assert learn["trace"]["result"]["summary"].startswith("## Report")


def test_no_hook_ever_runs_npm_view_show_or_install(w):
    """§23: traffic NOT disabled, npm logging on PATH, every fixture through hooks.json."""
    log = w.root / "npm.log"
    npm = w.bin / "npm"
    npm.write_text('#!/bin/sh\necho "$*" >> "%s"\n' % log)
    npm.chmod(0o755)
    for name in H.fixture_names():
        ev = w.event(name)
        for hook in H.routed_hooks(w.hooks_json, ev["hook_event_name"], ev):
            e = dict(w.env)
            e.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
            rc, _o, se, _w, _b = H._run_hook(w.argv_of(hook), json.dumps(ev), str(w.proj), e)
            assert rc == 0, (name, se)
    used = log.read_text().splitlines() if log.exists() else []
    # 8.1.1: besides the rebuild, the background installer's lockfile-only `npm ci --ignore-scripts` (never view/show/install)
    assert [l for l in used if l.split()[:1] != ["rebuild"] and not l.startswith("ci --ignore-scripts")] == [], used


def test_startup_row_has_a_status_message(w):
    (sync,) = [h for g in w.hooks_json["hooks"]["SessionStart"] if g.get("matcher") == "startup|clear|resume" for h in g["hooks"]]
    assert sync.get("statusMessage") == "ACE: checking ace-cli…"


def test_deferred_stop_then_new_human_prompt_records_the_loss(w):
    _human(w)
    _run_ok(w, w.event("Stop_background_running", prompt_id=w.prompt_id))
    assert (w.session_dir / "learn-deferred").exists()
    assert not _relevance(w, "learn_deferred_lost")
    _run_ok(w, w.event("UserPromptSubmit_human", prompt="Now fix the second bug in the importer", prompt_id="p-next"))
    (row,) = _relevance(w, "learn_deferred_lost")
    assert row["reason"] == "new_prompt"
    assert not (w.session_dir / "learn-deferred").exists()


def test_deferred_stop_then_session_end_records_the_loss(w):
    _human(w)
    _run_ok(w, w.event("Stop_background_running", prompt_id=w.prompt_id))
    _run_ok(w, w.event("SessionEnd"))
    (row,) = _relevance(w, "learn_deferred_lost")
    assert row["reason"] == "session_end"


def test_deferred_task_that_learns_leaves_no_loss(w):
    _human(w)
    _run_ok(w, w.event("Stop_background_running", prompt_id=w.prompt_id))
    _run_ok(w, w.event("UserPromptSubmit_task_notification", prompt_id="note-x"))
    _run_ok(w, w.event("Stop", prompt_id="note-x", last_assistant_message=FINAL))
    _run_ok(w, w.event("SessionEnd"))
    assert not _relevance(w, "learn_deferred_lost")


def test_missing_cli_says_nothing_on_prompts(w):
    """§23: SessionStart names /ace:ace-install-cli once; every human prompt after that stays silent."""
    out = _run_ok(w, w.event("UserPromptSubmit_human", prompt=HUMAN, prompt_id=w.prompt_id), PATH="/usr/bin:/bin")
    assert out == [""], out
    assert not w.cli_calls()
    assert not list(w.data.rglob("disabled.flag"))
