#!/usr/bin/env python3
"""8.2.6: a trace is learned into the project its SEARCH ran in, not the hook cwd's project.

Prod bug: a subagent searched in project A (lifeOS, mod rendered) but its SubagentStop ran with a cwd that resolves
to project B (ace-agile); ace_after_task resolved get_context() from that cwd and sent `ace-cli learn --project B`.
The server joins trace and search on (org, project, retrieval_id), so the search row was never scored and
reflector + curator learned the work into the wrong project.

Fix: the search-time writers store search_org / search_project (only with a retrieval_id) in the patterns-used
state; the learn uses them when the org is the cwd's (or the cwd is unbound). Another org: the cwd project, logged.
No stored binding (no search, old state files) -> the cwd-resolved project, exactly as before.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

import patterns_used_state as pus  # noqa: E402

SID = "sess-learnproj-1"
AGENT = "a1b2c3d4e5f6a7b8c"
PID = "ctx-1234567890-abcd"
PROMPT = "Refactor the auth login flow and add tests for the token refresh"
BIND_A = {"search_org": "org_X", "search_project": "prj_A"}


def _bound(path, org, project):
    (path / ".claude").mkdir(parents=True)
    (path / ".claude" / "settings.json").write_text(json.dumps({"env": {"ACE_PROJECT_ID": project, "ACE_ORG_ID": org}}))
    return path


def _env(a):
    env = {k: v for k, v in os.environ.items() if k not in ("ACE_PROJECT_ID", "ACE_ORG_ID", "ACE_CONTEXT")}
    env.update(ACE_LEARN_INLINE="1")
    if a is not None:
        env["CLAUDE_PROJECT_DIR"] = str(a)
    return env


def _sdir(project):
    return pus.state_file_path(SID, AGENT, project_id=project).parent


def _seed_state(state_project, extra=None, rid="ret-A"):
    """The search-time state of the subagent, as a writer leaves it (under the session's project dir)."""
    sf = pus.state_file_path(SID, AGENT, project_id=state_project)
    sf.parent.mkdir(parents=True, exist_ok=True)
    st = {"pattern_ids": [PID], "retrieval_id": rid, "retrieval_log_ids": {PID: 7}, "task_session_id": "tsid-A",
          "user_prompt": PROMPT, "hook_event_name": "SubagentStart", "render_variant": "full"}
    st.update(extra or {})
    sf.write_text(json.dumps(st))


def _stop(cwd, a, transcript_dir, work=True):
    tr = transcript_dir / ("agent-%s.jsonl" % AGENT)
    lines = [{"type": "user", "message": {"role": "user", "content": PROMPT}}]
    if work:
        lines += [{"type": "assistant", "message": {"role": "assistant", "content": [
                      {"type": "tool_use", "id": "toolu_1", "name": "Write", "input": {"file_path": str(cwd / "f.py"), "content": "x"}},
                      {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "pytest -q"}}]}},
                  {"type": "user", "message": {"role": "user", "content": [
                      {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"},
                      {"type": "tool_result", "tool_use_id": "toolu_2", "content": "1 passed"}]}}]
    lines += [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}}]
    tr.write_text("".join(json.dumps(x) + "\n" for x in lines))  # the subagent's work (after_task prefers it)
    ev = {"session_id": SID, "hook_event_name": "SubagentStop", "cwd": str(cwd), "agent_id": AGENT,
          "agent_type": "general-purpose", "agent_transcript_path": str(tr), "transcript_path": str(tr),
          "last_assistant_message": "Done.", "stop_hook_active": False, "background_tasks": []}
    r = subprocess.run([sys.executable, str(SHARED / "ace_after_task.py")], input=json.dumps(ev), text=True,
                       capture_output=True, cwd=str(cwd), env=_env(a), timeout=60)
    assert r.returncode == 0, r.stderr


def _learns(fake_cli_calls):
    return [c["argv"] for c in fake_cli_calls() if c["argv"][:1] == ["learn"]]


def _flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def _target(fake_cli_calls):
    learns = _learns(fake_cli_calls)
    assert len(learns) == 1, fake_cli_calls()
    return _flag(learns[0], "--org"), _flag(learns[0], "--project")


def _rows(cwd, event):
    rows = []
    for f in (cwd / ".claude" / "data" / "logs").glob("ace-relevance*.jsonl"):
        rows += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get("event") == event]


def _two_projects(tmp_path, org_b="org_X"):
    """A and B of the same org (the prod case), or B of another org."""
    return _bound(tmp_path / "A", "org_X", "prj_A"), _bound(tmp_path / "B", org_b, "prj_B")


def _mod_markers(project, age_s=0):
    sdir = _sdir(project)
    for m in ("mod-active", "mod-classic"):
        (sdir / m).write_text("0")
        t = time.time() - age_s
        os.utime(sdir / m, (t, t))
    return sdir


# ---------- mismatch, same org: learned into the SEARCH project ----------

def test_subagent_stop_in_other_project_learns_into_search_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_A")
    assert _flag(_learns(fake_cli_calls)[0], "--retrieval-id") == "ret-A"
    row = _rows(b, "learn_rebound")
    assert len(row) == 1 and (row[0]["from_project"], row[0]["to_project"], row[0]["org"]) == ("prj_B", "prj_A", "org_X")


def test_stale_mod_marker_python_render_path_still_learns_into_search_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    _mod_markers("prj_A", age_s=600)  # the mod rendered, then went quiet (> 120 s)
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_A")


def test_fresh_mod_in_search_project_owns_the_learn_and_keeps_its_lock(tmp_path, fake_cli_calls):
    """The mod (search project's session dir) is live and its classic hooks run: it learns, the Python chain steps
    aside and leaves the mod's in-flight lock (mod/handlers/turn.ts learn-inflight-<key>.lock) alone."""
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    sdir = _mod_markers("prj_A")
    lock = sdir / ("learn-inflight-%s.lock" % AGENT)
    lock.write_text("")
    _stop(b, a, tmp_path)
    assert _learns(fake_cli_calls) == []
    assert lock.exists(), "the Python SubagentStop deleted the mod's in-flight learn lock"


def test_unbound_cwd_learns_into_search_project(tmp_path, fake_cli_calls):
    a = _bound(tmp_path / "A", "org_X", "prj_A")
    c = tmp_path / "C"
    c.mkdir()
    _seed_state("prj_A", BIND_A)
    _stop(c, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_A")


@pytest.mark.parametrize("gate", ["disabled", "mod"])
def test_gated_cwd_project_does_not_drop_the_search_project_learn(tmp_path, fake_cli_calls, gate):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    if gate == "disabled":
        _sdir("prj_B").mkdir(parents=True, exist_ok=True)
        (_sdir("prj_B") / "disabled.flag").write_text("")
    else:
        _sdir("prj_B").mkdir(parents=True, exist_ok=True)
        _mod_markers("prj_B")
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_A")


def test_no_claude_project_dir_still_finds_the_search_state(tmp_path, fake_cli_calls):
    _a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    _stop(b, None, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_A")


# ---------- another org: never into that org's corpus ----------

def test_cross_org_keeps_cwd_project_and_logs(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path, org_b="org_Y")
    _seed_state("prj_A", BIND_A)
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_Y", "prj_B")
    row = _rows(b, "learn_rebound_skipped_cross_org")
    assert len(row) == 1
    assert (row[0]["cwd_org"], row[0]["cwd_project"], row[0]["search_org"], row[0]["search_project"]) == \
        ("org_Y", "prj_B", "org_X", "prj_A")
    assert _rows(b, "learn_rebound") == []


# ---------- unchanged behaviour ----------

def test_no_stored_search_project_keeps_cwd_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A")  # pre-8.2.6 state file: no search_org / search_project
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_B")
    assert _rows(b, "learn_rebound") == []


def test_binding_without_retrieval_id_is_ignored(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A, rid=None)  # no search answered: nothing on the server to join
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_B")


def test_no_search_state_at_all_keeps_cwd_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_B")


def test_matching_projects_unchanged(tmp_path, fake_cli_calls):
    a = _bound(tmp_path / "A", "org_X", "prj_A")
    _seed_state("prj_A", BIND_A)
    _stop(a, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_A")
    assert _rows(a, "learn_rebound") == []


# ---------- the learn lock ----------

def test_rebound_learn_leaves_no_lock_behind(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    _stop(b, a, tmp_path)
    assert len(_learns(fake_cli_calls)) == 1
    for p in ("prj_A", "prj_B"):
        assert not (_sdir(p) / ("learn-inflight-%s.lock" % AGENT)).exists(), p


def test_skip_releases_its_own_lock_but_keeps_a_foreign_one(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    _stop(b, a, tmp_path, work=False)  # no substantial work -> skip after the lock was taken
    assert _learns(fake_cli_calls) == []
    lock = _sdir("prj_A") / ("learn-inflight-%s.lock" % AGENT)
    assert not lock.exists(), "the hook's own lock must be released on a skip"
    _seed_state("prj_A", BIND_A)
    lock.write_text("")  # another learn of this agent is in flight
    _stop(b, a, tmp_path, work=False)
    assert lock.exists(), "a lock that was there before the hook is never removed by it"


# ---------- writers ----------

def test_writer_stores_search_binding_with_a_retrieval_id_and_keeps_it_on_merge(tmp_path):
    pus.append_patterns_used(SID, AGENT, [], task_session_id="t", project_id="p", retrieval_id="r",
                             binding={"org": "org_X", "project": "prj_A"})
    pus.append_patterns_used(SID, AGENT, [PID], project_id="p")  # a later merge without one keeps it
    st = pus.load_state(SID, AGENT, "SubagentStop", project_id="p")
    assert st["search_org"] == "org_X" and st["search_project"] == "prj_A"
    assert list(st)[-2:] == ["search_org", "search_project"]  # mod parity: last keys (mergeState)


def test_writer_without_retrieval_id_stores_no_binding(tmp_path):
    """Anchor / fork / failed search: no search answered, so the learn is not bound to it."""
    pus.append_patterns_used(SID, AGENT, [], task_session_id="t", project_id="p",
                             binding={"org": "org_X", "project": "prj_A"}, reset=True)
    st = pus.load_state(SID, AGENT, "SubagentStop", project_id="p")
    assert "search_org" not in st and "search_project" not in st


def test_writer_without_binding_writes_no_keys(tmp_path):
    pus.append_patterns_used(SID, AGENT, [PID], project_id="p", retrieval_id="r")
    st = pus.load_state(SID, AGENT, "SubagentStop", project_id="p")
    assert "search_org" not in st and "search_project" not in st


def test_state_path_finds_the_session_file_in_another_project(tmp_path, monkeypatch):
    """Without $CLAUDE_PROJECT_DIR the default project is the cwd's; the session's one state file elsewhere wins."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    _seed_state("prj_A")
    assert pus.state_file_path(SID, AGENT) == pus.state_file_path(SID, AGENT, project_id="prj_A")
    assert pus.state_file_path(SID, "other-agent") != pus.state_file_path(SID, "other-agent", project_id="prj_A")
