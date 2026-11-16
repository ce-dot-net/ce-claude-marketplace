#!/usr/bin/env python3
"""8.2.6: a trace is learned into the project its SEARCH ran in, not the hook cwd's project.

Prod bug: a subagent searched in project A (lifeOS, mod rendered) but its SubagentStop ran with a cwd that resolves
to project B (ace-agile); ace_after_task resolved get_context() from that cwd and sent `ace-cli learn --project B`.
The server joins trace and search on (org, project, retrieval_id), so the search row was never scored and
reflector + curator learned the work into the wrong project.

Fix: the search-time writers store search_org / search_project in the patterns-used state; the learn path uses
them. No stored project (no search, old state files) -> the cwd-resolved project, exactly as before.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

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


def _bound(path, org, project):
    (path / ".claude").mkdir(parents=True)
    (path / ".claude" / "settings.json").write_text(json.dumps({"env": {"ACE_PROJECT_ID": project, "ACE_ORG_ID": org}}))
    return path


def _env(a):
    env = {k: v for k, v in os.environ.items() if k not in ("ACE_PROJECT_ID", "ACE_ORG_ID", "ACE_CONTEXT")}
    env.update(CLAUDE_PROJECT_DIR=str(a), ACE_LEARN_INLINE="1")
    return env


def _seed_state(state_project, extra=None):
    """The search-time state of the subagent, as a writer leaves it (under the session's project dir)."""
    sf = pus.state_file_path(SID, AGENT, project_id=state_project)
    sf.parent.mkdir(parents=True, exist_ok=True)
    st = {"pattern_ids": [PID], "retrieval_id": "ret-A", "retrieval_log_ids": {PID: 7}, "task_session_id": "tsid-A",
          "user_prompt": PROMPT, "hook_event_name": "SubagentStart", "render_variant": "full"}
    st.update(extra or {})
    sf.write_text(json.dumps(st))


def _stop(cwd, a, transcript_dir):
    tr = transcript_dir / ("agent-%s.jsonl" % AGENT)
    lines = [{"type": "user", "message": {"role": "user", "content": PROMPT}},
             {"type": "assistant", "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "id": "toolu_1", "name": "Write", "input": {"file_path": str(cwd / "f.py"), "content": "x"}},
                 {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "pytest -q"}}]}},
             {"type": "user", "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"},
                 {"type": "tool_result", "tool_use_id": "toolu_2", "content": "1 passed"}]}},
             {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}}]
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


def _two_projects(tmp_path):
    return _bound(tmp_path / "A", "org_A", "prj_A"), _bound(tmp_path / "B", "org_B", "prj_B")


# ---------- (1)/(2) mismatch: learned into the SEARCH project ----------

def test_subagent_stop_in_other_project_learns_into_search_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", {"search_org": "org_A", "search_project": "prj_A"})
    _stop(b, a, tmp_path)
    learns = _learns(fake_cli_calls)
    assert len(learns) == 1, fake_cli_calls()
    assert _flag(learns[0], "--project") == "prj_A" and _flag(learns[0], "--org") == "org_A", learns[0]
    assert _flag(learns[0], "--retrieval-id") == "ret-A"


def test_stale_mod_marker_python_render_path_still_learns_into_search_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", {"search_org": "org_A", "search_project": "prj_A"})
    sdir = pus.state_file_path(SID, AGENT, project_id="prj_A").parent
    for m in ("mod-active", "mod-classic"):  # the mod rendered, then went quiet (> 120 s)
        (sdir / m).write_text("0")
        old = time.time() - 600
        os.utime(sdir / m, (old, old))
    _stop(b, a, tmp_path)
    learns = _learns(fake_cli_calls)
    assert len(learns) == 1, fake_cli_calls()
    assert _flag(learns[0], "--project") == "prj_A" and _flag(learns[0], "--org") == "org_A", learns[0]


def test_fresh_mod_in_search_project_owns_the_learn(tmp_path, fake_cli_calls):
    """The mod (search project's session dir) is live and its classic hooks run: it learns, the Python chain
    steps aside. Before 8.2.6 the gate looked in the cwd project's dir and learned a second time into B."""
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A", {"search_org": "org_A", "search_project": "prj_A"})
    sdir = pus.state_file_path(SID, AGENT, project_id="prj_A").parent
    for m in ("mod-active", "mod-classic"):
        (sdir / m).write_text(str(int(time.time() * 1000)))
    _stop(b, a, tmp_path)
    assert _learns(fake_cli_calls) == []


# ---------- (3)/(4) unchanged behaviour ----------

def test_no_stored_search_project_keeps_cwd_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _seed_state("prj_A")  # pre-8.2.6 state file: no search_org / search_project
    _stop(b, a, tmp_path)
    learns = _learns(fake_cli_calls)
    assert len(learns) == 1
    assert _flag(learns[0], "--project") == "prj_B" and _flag(learns[0], "--org") == "org_B"


def test_no_search_state_at_all_keeps_cwd_project(tmp_path, fake_cli_calls):
    a, b = _two_projects(tmp_path)
    _stop(b, a, tmp_path)
    learns = _learns(fake_cli_calls)
    assert len(learns) == 1
    assert _flag(learns[0], "--project") == "prj_B" and _flag(learns[0], "--org") == "org_B"


def test_matching_projects_unchanged(tmp_path, fake_cli_calls):
    a = _bound(tmp_path / "A", "org_A", "prj_A")
    _seed_state("prj_A", {"search_org": "org_A", "search_project": "prj_A"})
    _stop(a, a, tmp_path)
    learns = _learns(fake_cli_calls)
    assert len(learns) == 1
    assert _flag(learns[0], "--project") == "prj_A" and _flag(learns[0], "--org") == "org_A"


# ---------- writers ----------

def test_writer_stores_search_binding_and_keeps_it_on_merge(tmp_path):
    pus.append_patterns_used(SID, AGENT, [], task_session_id="t", project_id="p",
                             binding={"org": "org_A", "project": "prj_A"})
    pus.append_patterns_used(SID, AGENT, [PID], project_id="p")  # a later merge without one keeps it
    st = pus.load_state(SID, AGENT, "SubagentStop", project_id="p")
    assert st["search_org"] == "org_A" and st["search_project"] == "prj_A"
    assert list(st)[-2:] == ["search_org", "search_project"]  # mod parity: last keys (mergeState)


def test_writer_without_binding_writes_no_keys(tmp_path):
    pus.append_patterns_used(SID, AGENT, [PID], project_id="p")
    st = pus.load_state(SID, AGENT, "SubagentStop", project_id="p")
    assert "search_org" not in st and "search_project" not in st
