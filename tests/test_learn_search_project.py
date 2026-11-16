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


def _env(a, fake_bin=None):
    env = {k: v for k, v in os.environ.items() if k not in ("ACE_PROJECT_ID", "ACE_ORG_ID", "ACE_CONTEXT")}
    env.update(ACE_LEARN_INLINE="1")
    if a is not None:
        env["CLAUDE_PROJECT_DIR"] = str(a)
    if fake_bin is not None:
        env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    return env


SEARCH_8 = REPO / "tests" / "e2e" / "fixtures" / "mod" / "search_8.json"  # a real search answer (retrieval_id)
TRACE_CLI = r'''#!%s
import json, os, sys
argv = sys.argv[1:]
rec = {"argv": argv}
if "--transcript" in argv:
    rec["trace"] = json.load(open(argv[argv.index("--transcript") + 1]))
with open(os.environ["ACE_FAKE_CLI_LOG"], "a") as fh:
    fh.write(json.dumps(rec) + "\n")
if argv[:1] == ["search"]:
    print(open(%r).read())
else:
    print("{}")
'''


def _trace_cli(tmp_path):
    """A fake ace-cli that also records the learned trace (the shared fake logs argv only)."""
    d = tmp_path / "trace-bin"
    d.mkdir()
    (d / "ace-cli").write_text(TRACE_CLI % (sys.executable, str(SEARCH_8)))
    (d / "ace-cli").chmod(0o755)
    return d


def _sdir(project):
    return pus.state_file_path(SID, AGENT, project_id=project).parent


def _seed_state(state_project, extra=None, rid="ret-A", agent=AGENT):
    """The search-time state of the subagent (or the main agent: agent=None), as a writer leaves it."""
    sf = pus.state_file_path(SID, agent, project_id=state_project)
    sf.parent.mkdir(parents=True, exist_ok=True)
    st = {"pattern_ids": [PID], "retrieval_id": rid, "retrieval_log_ids": {PID: 7}, "task_session_id": "tsid-A",
          "user_prompt": PROMPT, "hook_event_name": "SubagentStart", "render_variant": "full"}
    st.update(extra or {})
    sf.write_text(json.dumps(st))


def _stop(cwd, a, transcript_dir, work=True, hook="SubagentStop", fake_bin=None, prompt_id=None):
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
    ev = {"session_id": SID, "hook_event_name": hook, "cwd": str(cwd), "transcript_path": str(tr),
          "last_assistant_message": "Done.", "stop_hook_active": False, "background_tasks": []}
    if hook == "SubagentStop":
        ev.update(agent_id=AGENT, agent_type="general-purpose", agent_transcript_path=str(tr))
    if prompt_id:
        ev["prompt_id"] = prompt_id  # G2: CC's task anchor, identical from UserPromptSubmit to Stop
    r = subprocess.run([sys.executable, str(SHARED / "ace_after_task.py")], input=json.dumps(ev), text=True,
                       capture_output=True, cwd=str(cwd), env=_env(a, fake_bin), timeout=60)
    assert r.returncode == 0, r.stderr


def _ups(cwd, a, prompt, prompt_id, fake_bin=None):
    """The real UserPromptSubmit hook (ace_before_task.py)."""
    ev = {"session_id": SID, "hook_event_name": "UserPromptSubmit", "cwd": str(cwd), "prompt": prompt,
          "prompt_id": prompt_id, "transcript_path": ""}
    r = subprocess.run([sys.executable, str(SHARED / "ace_before_task.py")], input=json.dumps(ev), text=True,
                       capture_output=True, cwd=str(cwd), env=_env(a, fake_bin), timeout=60)
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
    aside. The gates run before the hook touches any lock, so the mod's in-flight lock (mod/handlers/turn.ts
    learn-inflight-<key>.lock) is left alone (b131c31 took the lock first and removed it on the gate exit). The
    lock_present rule itself: test_skip_releases_its_own_lock_but_keeps_a_foreign_one."""
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


@pytest.mark.parametrize("gate", ["session_disabled", "mod"])
def test_gated_cwd_project_does_not_drop_the_search_project_learn(tmp_path, fake_cli_calls, gate):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    if gate == "session_disabled":
        _sdir("prj_B").mkdir(parents=True, exist_ok=True)
        (_sdir("prj_B") / "disabled.flag").write_text("")
    else:
        _sdir("prj_B").mkdir(parents=True, exist_ok=True)
        _mod_markers("prj_B")
    _stop(b, a, tmp_path)
    assert _target(fake_cli_calls) == ("org_X", "prj_A")


def test_project_disabled_flag_on_cwd_project_is_never_rebound_away(tmp_path, fake_cli_calls):
    """TROUBLESHOOTING.md: a project disabled.flag turns ACE off for that whole project; a learn from it never goes
    anywhere else."""
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A)
    pdir = _sdir("prj_B").parent.parent
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "disabled.flag").write_text("")
    _stop(b, a, tmp_path)
    assert _learns(fake_cli_calls) == []


# ---------- the MAIN Stop: no rebind from an unbound / gated cwd (its main state can be an earlier task's) ----------

def _stale_main(project):
    _seed_state(project, {"search_org": "org_X", "search_project": project, "task_session_id": "tsid-OLD",
                          "hook_event_name": "UserPromptSubmit", "user_prompt": "OLD prompt about billing"},
                rid="ret-OLD", agent=None)


def test_main_stop_in_unbound_cwd_skips_despite_a_stale_main_binding(tmp_path, fake_cli_calls):
    _bound(tmp_path / "B", "org_X", "prj_B")
    c = tmp_path / "C"
    c.mkdir()
    _stale_main("prj_B")  # session root B; the UPS in C exits before its anchor write
    _stop(c, tmp_path / "B", tmp_path, hook="Stop", prompt_id="tsid-OLD")  # even a matching anchor: no rebind
    assert _learns(fake_cli_calls) == []


def test_main_stop_in_gated_cwd_does_not_rebind(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _stale_main("prj_A")
    _sdir("prj_B").mkdir(parents=True, exist_ok=True)
    (_sdir("prj_B") / "disabled.flag").write_text("")  # session flag in the cwd project
    _stop(b, a, tmp_path, hook="Stop", prompt_id="tsid-OLD")
    assert _learns(fake_cli_calls) == []


def test_main_stop_in_bound_cwd_with_the_current_binding_rebinds(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A, agent=None)  # task_session_id tsid-A = this task's anchor
    _stop(b, a, tmp_path, hook="Stop", prompt_id="tsid-A")
    assert _target(fake_cli_calls) == ("org_X", "prj_A")


@pytest.mark.parametrize("prompt_id", [None, "pid-other"])
def test_main_stop_without_its_own_anchor_keeps_cwd_project(tmp_path, fake_cli_calls, prompt_id):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", BIND_A, agent=None)
    _stop(b, a, tmp_path, hook="Stop", prompt_id=prompt_id)
    assert _target(fake_cli_calls) == ("org_X", "prj_B")


@pytest.mark.parametrize("prompt", ["fix it", "/ace-status", "<task-notification>x</task-notification>"])
def test_main_stop_after_an_unanchored_ups_keeps_cwd_project(tmp_path, fake_cli_calls, prompt):
    """Task 1 searched in A and was interrupted; task 2 in cwd B is a short / ACE-command / machine prompt, so the
    real UPS exits before its anchor write and the main state still holds task 1's binding. 8.2.5 behaviour: B."""
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", {**BIND_A, "task_session_id": "tsid-OLD", "hook_event_name": "UserPromptSubmit",
                          "user_prompt": "OLD task about billing in A"}, rid="ret-OLD", agent=None)
    _ups(b, a, prompt, "pid-2")
    assert pus.load_state(SID, None, "Stop", project_id="prj_A").get("task_session_id") == "tsid-OLD"
    _stop(b, a, tmp_path, hook="Stop", prompt_id="pid-2")
    assert _target(fake_cli_calls) == ("org_X", "prj_B")


def test_main_stop_rebinds_after_its_ups_searched_in_the_session_project(tmp_path, fake_cli_calls):
    """Positive path with the real hooks: the UPS of this task searched in A (anchor = prompt_id), the Stop runs in
    cwd B -> learned into A; the rejection-downvote side files stay with the UPS's (cwd) project."""
    a, b = _two_projects(tmp_path)
    fake = _trace_cli(tmp_path)
    _ups(a, a, PROMPT, "pid-1", fake_bin=fake)
    st = pus.load_state(SID, None, "Stop", project_id="prj_A")
    assert (st.get("task_session_id"), st.get("search_project")) == ("pid-1", "prj_A"), st
    _stop(b, a, tmp_path, hook="Stop", prompt_id="pid-1", fake_bin=fake)
    learns = _learns(fake_cli_calls)
    assert len(learns) == 1 and (_flag(learns[0], "--org"), _flag(learns[0], "--project")) == ("org_X", "prj_A")
    # ace_feedback: the next UPS in B reads last-main-applied.json under the cwd project (ace_before_task on_human_prompt)
    assert (_sdir("prj_B") / "last-main-applied.json").exists()
    assert not (_sdir("prj_A") / "last-main-applied.json").exists()


def test_ups_search_then_domain_shift_keep_the_ups_credit(tmp_path, monkeypatch):
    """A stale main file of another project must not capture the UPS writes (no project_id): the Stop then reads
    the UPS retrieval_id and prompt, as on 8.2.5."""
    a = _bound(tmp_path / "A", "org_X", "prj_A")
    _bound(tmp_path / "B", "org_X", "prj_B")
    _stale_main("prj_B")
    stale = pus.state_file_path(SID, None, project_id="prj_B")
    before = stale.read_text()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(a))
    for k in ("ACE_PROJECT_ID", "ACE_ORG_ID", "ACE_CONTEXT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(a)
    pus.append_patterns_used(SID, None, [], task_session_id="tsid-NEW", user_prompt="NEW",
                             hook_event_name="UserPromptSubmit", reset=True)
    pus.append_patterns_used(SID, None, [PID], retrieval_id="ret-NEW", task_session_id="tsid-NEW", user_prompt="NEW",
                             hook_event_name="UserPromptSubmit", binding={"org": "org_X", "project": "prj_A"})
    sf = pus.state_file_path(SID, None, None, "prj_A")  # ace_domain_shift: explicit project, rid kept when present
    has_rid = sf.exists() and bool(pus._read_state_file(sf)[1])
    pus.append_patterns_used(SID, None, ["ctx-1234567890-ffff"], retrieval_id=None if has_rid else "ret-DS",
                             task_session_id="tsid-NEW", project_id="prj_A",
                             binding=None if has_rid else {"org": "org_X", "project": "prj_A"})
    st = pus.load_state(SID, None, "Stop")
    assert (st.get("retrieval_id"), st.get("user_prompt")) == ("ret-NEW", "NEW"), st
    assert stale.read_text() == before


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


def test_cross_org_drops_the_other_orgs_f080_fields(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path, org_b="org_Y")
    _seed_state("prj_A", BIND_A)
    _stop(b, a, tmp_path, fake_bin=_trace_cli(tmp_path))
    calls = [c for c in fake_cli_calls() if c["argv"][:1] == ["learn"]]
    assert len(calls) == 1
    argv, trace = calls[0]["argv"], calls[0]["trace"]
    assert (_flag(argv, "--org"), _flag(argv, "--project")) == ("org_Y", "prj_B")
    assert "--retrieval-id" not in argv and "--applied-log-ids" not in argv, argv
    assert not trace.get("retrieval_id") and not trace.get("applied_log_ids") and not trace.get("playbook_used"), trace
    assert trace.get("session_id") != "tsid-A", trace  # the other org's task pin
    assert len(_rows(b, "learn_rebound_skipped_cross_org")) == 1


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
    lock.write_text("")  # another learn of this agent is in flight (or a stale one)
    old = time.time() - 3600
    os.utime(lock, (old, old))
    _stop(b, a, tmp_path, work=False)
    assert lock.exists(), "a lock that was there before the hook is never removed by it"
    assert abs(lock.stat().st_mtime - old) < 1, "an existing lock is not refreshed by a skipping hook"


# ---------- writers ----------

def test_writer_stores_search_binding_with_a_retrieval_id_and_keeps_it_on_merge(tmp_path):
    pus.append_patterns_used(SID, AGENT, [], task_session_id="t", project_id="p", retrieval_id="r",
                             binding={"org": "org_X", "project": "prj_A"})
    pus.append_patterns_used(SID, AGENT, [PID], project_id="p")  # a later merge without one keeps it
    st = pus.load_state(SID, AGENT, "SubagentStop", project_id="p")
    assert st["search_org"] == "org_X" and st["search_project"] == "prj_A"
    assert list(st)[-2:] == ["search_org", "search_project"]  # mod parity: last keys (mergeState)


def test_writer_takes_the_binding_as_a_pair(tmp_path):
    pus.append_patterns_used(SID, AGENT, [], project_id="p", retrieval_id="r", binding={"org": "org_X", "project": "prj_A"})
    pus.append_patterns_used(SID, AGENT, [], project_id="p", binding={"org": "org_Z", "project": None})
    st = pus.load_state(SID, AGENT, "SubagentStop", project_id="p")
    assert (st["search_org"], st["search_project"]) == ("org_X", "prj_A")


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
    assert pus.state_file_path(SID, AGENT, find=True) == pus.state_file_path(SID, AGENT, project_id="prj_A")
    assert pus.load_state(SID, AGENT, "SubagentStop").get("retrieval_id") == "ret-A"
    assert pus.state_file_path(SID, "other-agent", find=True) != pus.state_file_path(SID, "other-agent", project_id="prj_A")
    assert pus.state_file_path(SID, AGENT) != pus.state_file_path(SID, AGENT, project_id="prj_A"), "writers never follow"
    _seed_state("prj_A", agent=None)
    assert pus.state_file_path(SID, None, find=True) != pus.state_file_path(SID, None, project_id="prj_A"), "never main"
