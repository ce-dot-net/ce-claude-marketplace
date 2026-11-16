"""8.2.6 e2e: a subagent that searched in project A and stops in a cwd bound to project B is learned into A.

Drives the real hooks.json commands (SubagentStart wrapper in A, SubagentStop wrapper with cwd B) against the fake
ace-cli of tests/conftest.py, which records every argv. Gated like the other e2e tests (ACE_E2E=1).
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from ace_e2e_harness import _run_hook, plugin_root, routed_hooks

pytestmark = pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1")

PROMPT = "Refactor the auth login flow and add tests for the token refresh"


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


@pytest.mark.parametrize("stop_in_b", [True, False])
def test_e2e_subagent_learn_goes_to_the_search_project(stop_in_b):
    root = plugin_root()
    sandbox = Path(tempfile.mkdtemp(prefix="ace-e2e-lp-"))
    try:
        a, b = _bound(sandbox / "A", "org_A", "prj_A"), _bound(sandbox / "B", "org_B", "prj_B")
        data, home, xdg = sandbox / "ace-plugin-data", sandbox / "home", sandbox / "xdg"  # data_root(): ace-* only
        for d in (data, home, xdg / "ace"):
            d.mkdir(parents=True)
        (data / "python_path").write_text(sys.executable + "\n")
        (xdg / "ace" / "config.json").write_text(json.dumps({"serverUrl": "http://127.0.0.1:9", "apiToken": "e2e"}))
        log = sandbox / "fake-ace-cli.log"
        env = {k: v for k, v in os.environ.items() if k not in ("ACE_PROJECT_ID", "ACE_ORG_ID", "ACE_CONTEXT")}
        env.update(HOME=str(home), CLAUDE_PLUGIN_DATA=str(data), CLAUDE_PLUGIN_ROOT=str(root), CLAUDE_PROJECT_DIR=str(a),
                   XDG_CONFIG_HOME=str(xdg), TMPDIR=str(sandbox), ACE_FAKE_CLI_LOG=str(log), ACE_LEARN_INLINE="1",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
        sid, aid = "sess-e2e-lp", "a0123456789abcdef"
        stop_cwd = b if stop_in_b else a
        main_tr, agent_tr = sandbox / "main.jsonl", sandbox / ("agent-%s.jsonl" % aid)
        main_tr.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": PROMPT}}) + "\n")
        agent_tr.write_text("".join(json.dumps(x) + "\n" for x in (
            {"type": "user", "message": {"role": "user", "content": PROMPT}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "Write", "input": {"file_path": str(stop_cwd / "f.py"), "content": "x"}},
                {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "pytest -q"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"},
                {"type": "tool_result", "tool_use_id": "toolu_2", "content": "1 passed"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}})))

        # the search: SubagentStart in project A (the real writer leaves the state + its binding)
        _run({"session_id": sid, "transcript_path": str(main_tr), "cwd": str(a), "hook_event_name": "SubagentStart",
              "agent_id": aid, "agent_type": "general-purpose"}, a, env, root)
        sf = data / "projects" / "prj_A" / "sessions" / sid / ("patterns-used-%s.json" % aid)
        st = json.loads(sf.read_text())
        assert (st.get("search_org"), st.get("search_project")) == ("org_A", "prj_A"), st

        # the learn: SubagentStop with the subagent's cwd (B in the bug)
        _run({"session_id": sid, "transcript_path": str(main_tr), "cwd": str(stop_cwd), "hook_event_name": "SubagentStop",
              "stop_hook_active": False, "agent_id": aid, "agent_type": "general-purpose",
              "agent_transcript_path": str(agent_tr), "last_assistant_message": "Done.", "background_tasks": []},
             stop_cwd, env, root)
        calls = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
        learns = [c["argv"] for c in calls if c["argv"][:1] == ["learn"]]
        assert len(learns) == 1, calls
        argv = learns[0]
        print("recorded learn argv:", argv)
        assert argv[argv.index("--project") + 1] == "prj_A" and argv[argv.index("--org") + 1] == "org_A", argv
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
