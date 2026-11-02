"""v8 final review fixes: async hooks print nothing, detached learn, own-transcript task for
SubagentStop, log-dir litter, domain-shift Grep pattern."""
import json
import subprocess
import sys
import time

import pytest

from test_stop_v8 import box, WORK, PROJECT_ID, ORG_ID, AFTER_TASK, SCRIPTS  # noqa: F401


def _env(box, **kw):
    return box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, **kw)


def test_stop_prints_only_the_learn_line_on_learn_and_nothing_on_skip(box):
    box.seed_tools("s-quiet", WORK)
    box.write_state("s-quiet", user_prompt="implement the quiet feature properly")
    p = box.run_after_task(box.stop_event("s-quiet"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert json.loads(p.stdout) == {"systemMessage": "ACE · learning sent"} and len(box.cli_calls("learn")) == 1  # item 2
    box.write_state("s-skip", user_prompt="<task-notification>x</task-notification>")
    p = box.run_after_task(box.stop_event("s-skip"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.stdout == ""


def test_subagent_stop_prefers_stored_query_over_transcript(box):
    sid = "s-sib"
    agent = "aaa111"
    box.seed_tools(sid, WORK, agent_id=agent)
    # §13.2 (r3a) flipped the r2 order: SubagentStart's stored query wins, transcript is the fallback
    box.write_state(sid, agent=agent, user_prompt="Audit the CSS theme tokens for dark mode", query_source="stash")
    p = box.run_after_task(box.subagent_event(sid, agent), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.stdout == ""
    task = box.cli_calls("learn")[0]["trace"]["task"]
    assert "CSS theme tokens" in task and "refactor the parser module" not in task


def test_learn_is_detached_by_default(box):
    """cc_hooks_reference.md:4086: the hook returns at once, the learn finishes on its own."""
    box.seed_tools("s-det", WORK)
    box.write_state("s-det", user_prompt="implement the detached learn path")
    p = box.run_after_task(box.stop_event("s-det"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID,
                           ACE_LEARN_INLINE="")
    assert p.returncode == 0 and json.loads(p.stdout) == {"systemMessage": "ACE · learning sent"}
    for _ in range(100):
        if box.cli_calls("learn"):
            break
        time.sleep(0.1)
    assert len(box.cli_calls("learn")) == 1
    assert not list(box.session_dir("s-det").glob("learn-job-*.json"))


def test_machine_prompt_env_prefixes(monkeypatch):
    sys.path.insert(0, str(AFTER_TASK.parent / "utils"))
    from machine_prompts import is_machine_prompt
    assert not is_machine_prompt("ZUSTELLUNG abc")
    monkeypatch.setenv("ACE_MACHINE_PROMPT_PREFIXES", "zustellung, coachd:")
    assert is_machine_prompt("ZUSTELLUNG abc")


def test_ups_machine_prompt_in_unconfigured_dir_creates_no_logs(tmp_path):
    hook = AFTER_TASK.parent / "ace_before_task.py"
    ev = {"prompt": "<task-notification>x</task-notification>", "cwd": str(tmp_path),
          "session_id": "s", "hook_event_name": "UserPromptSubmit"}
    subprocess.run([sys.executable, str(hook)], input=json.dumps(ev), text=True, capture_output=True,
                   cwd=str(tmp_path), timeout=30)
    assert not (tmp_path / ".claude").exists()
