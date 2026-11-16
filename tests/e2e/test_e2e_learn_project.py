"""8.2.6 e2e: a subagent that searched in project A and stops in a cwd bound to project B (same org) is learned
into A; the main search stores its binding too.

Drives the real hooks.json commands (UserPromptSubmit / SubagentStart wrappers in A, SubagentStop wrapper with cwd
B) against a fake ace-cli that answers searches with a real search response (retrieval_id + patterns) and records
every argv. Gated like the other e2e tests (ACE_E2E=1).
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from ace_e2e_harness import FIXTURES, _run_hook, plugin_root, routed_hooks

pytestmark = pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1")

PROMPT = "Refactor the auth login flow and add tests for the token refresh"
SEARCH = FIXTURES / "mod" / "search_8.json"
FAKE = r'''#!%(python)s
import json, os, sys
argv = sys.argv[1:]
stdin = sys.stdin.read() if "--stdin" in argv else ""
with open(os.environ["ACE_FAKE_CLI_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": argv, "stdin": stdin[:4000]}) + "\n")
if "--version" in argv:
    print("4.2.2")
elif argv and argv[0] == "search":
    print(open(%(search)r).read())
else:
    print("{}")
'''
# render arms of the SubagentStart writer (control / compact / budget each have their own state write)
ARMS = {"control": {"ACE_AB_CONTROL_PCT": "100"}, "compact": {"ACE_AB_COMPACT_PCT": "100"},
        "budget": {"ACE_RENDER_FULL_PCT": "0"}}


def _bound(path, org, project):
    (path / ".claude").mkdir(parents=True)
    (path / ".claude" / "settings.json").write_text(json.dumps({"env": {"ACE_PROJECT_ID": project, "ACE_ORG_ID": org}}))
    return path


def _run(event, cwd, env, root):
    hooks = json.loads((root / "hooks" / "hooks.json").read_text())
    sub = lambda s: s.replace("${CLAUDE_PLUGIN_ROOT}", str(root)).replace("${CLAUDE_PLUGIN_DATA}", env["CLAUDE_PLUGIN_DATA"])
    for h in routed_hooks(hooks, event["hook_event_name"], event):
        argv = [sub(h["command"])] + [sub(a) for a in h.get("args") or []]
        rc, _out, err, _wall, _bg = _run_hook(argv, json.dumps(event), str(cwd), env)
        assert rc == 0, err


def _sandbox(arm):
    root = plugin_root()
    sandbox = Path(tempfile.mkdtemp(prefix="ace-e2e-lp-"))
    a, b = _bound(sandbox / "A", "org_X", "prj_A"), _bound(sandbox / "B", "org_X", "prj_B")
    data, home, xdg, fbin = sandbox / "ace-plugin-data", sandbox / "home", sandbox / "xdg", sandbox / "bin"  # data_root(): ace-*
    for d in (data, home, xdg / "ace", fbin):
        d.mkdir(parents=True)
    (data / "python_path").write_text(sys.executable + "\n")
    (xdg / "ace" / "config.json").write_text(json.dumps({"serverUrl": "http://127.0.0.1:9", "apiToken": "e2e"}))
    (fbin / "ace-cli").write_text(FAKE % {"python": sys.executable, "search": str(SEARCH)})
    (fbin / "ace-cli").chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if k not in ("ACE_PROJECT_ID", "ACE_ORG_ID", "ACE_CONTEXT", "ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT",
                        "ACE_RENDER_FULL_PCT")}
    env.update(HOME=str(home), CLAUDE_PLUGIN_DATA=str(data), CLAUDE_PLUGIN_ROOT=str(root), CLAUDE_PROJECT_DIR=str(a),
               XDG_CONFIG_HOME=str(xdg), TMPDIR=str(sandbox), ACE_FAKE_CLI_LOG=str(sandbox / "cli.log"),
               ACE_LEARN_INLINE="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
               PATH=str(fbin) + os.pathsep + os.environ.get("PATH", ""), **ARMS.get(arm, {}))
    return root, sandbox, a, b, data, env


def _calls(sandbox):
    log = sandbox / "cli.log"
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()] if log.exists() else []


@pytest.mark.parametrize("arm", sorted(ARMS))
def test_e2e_subagent_learn_goes_to_the_search_project(arm):
    root, sandbox, a, b, data, env = _sandbox(arm)
    try:
        sid, aid = "sess-e2e-lp", "a0123456789abcdef"
        main_tr, agent_tr = sandbox / "main.jsonl", sandbox / ("agent-%s.jsonl" % aid)
        main_tr.write_text("".join(json.dumps(x) + "\n" for x in (  # the parent's Agent call: SubagentStart's query
            {"type": "user", "message": {"role": "user", "content": PROMPT}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_0", "name": "Agent",
                 "input": {"subagent_type": "general-purpose", "prompt": PROMPT}}]}})))
        agent_tr.write_text("".join(json.dumps(x) + "\n" for x in (
            {"type": "user", "message": {"role": "user", "content": PROMPT}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "Write", "input": {"file_path": str(b / "f.py"), "content": "x"}},
                {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "pytest -q"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"},
                {"type": "tool_result", "tool_use_id": "toolu_2", "content": "1 passed"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}})))

        # the search: SubagentStart in project A; the post-search writer of this arm leaves the binding
        _run({"session_id": sid, "transcript_path": str(main_tr), "cwd": str(a), "hook_event_name": "SubagentStart",
              "agent_id": aid, "agent_type": "general-purpose"}, a, env, root)
        assert any(c["argv"][:1] == ["search"] for c in _calls(sandbox)), _calls(sandbox)
        st = json.loads((data / "projects" / "prj_A" / "sessions" / sid / ("patterns-used-%s.json" % aid)).read_text())
        assert st.get("retrieval_id")
        assert (st.get("search_org"), st.get("search_project")) == ("org_X", "prj_A"), st

        # the learn: SubagentStop with the subagent's cwd in B
        _run({"session_id": sid, "transcript_path": str(main_tr), "cwd": str(b), "hook_event_name": "SubagentStop",
              "stop_hook_active": False, "agent_id": aid, "agent_type": "general-purpose",
              "agent_transcript_path": str(agent_tr), "last_assistant_message": "Done.", "background_tasks": []},
             b, env, root)
        learns = [c["argv"] for c in _calls(sandbox) if c["argv"][:1] == ["learn"]]
        assert len(learns) == 1, _calls(sandbox)
        argv = learns[0]
        print("recorded learn argv:", argv)
        assert argv[argv.index("--project") + 1] == "prj_A" and argv[argv.index("--org") + 1] == "org_X", argv
        assert argv[argv.index("--retrieval-id") + 1] == st["retrieval_id"], argv
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def test_e2e_main_search_state_carries_its_binding():
    root, sandbox, a, _b, data, env = _sandbox(None)
    try:
        sid = "sess-e2e-ups"
        tr = sandbox / "main.jsonl"
        tr.write_text("")
        _run({"session_id": sid, "transcript_path": str(tr), "cwd": str(a), "permission_mode": "default",
              "hook_event_name": "UserPromptSubmit", "prompt": PROMPT, "prompt_id": "p-1"}, a, env, root)
        st = json.loads((data / "projects" / "prj_A" / "sessions" / sid / "patterns-used-main.json").read_text())
        assert st.get("retrieval_id")
        assert (st.get("search_org"), st.get("search_project")) == ("org_X", "prj_A"), st
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
