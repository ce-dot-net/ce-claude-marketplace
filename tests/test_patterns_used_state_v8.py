#!/usr/bin/env python3
"""v8 Foundation contract C1 (DESIGN §4/§5): patterns_used_state.

- default state file = plugin_data_dir.session_dir(project_id, session_id)
  / "patterns-used-<agent>.json" (agent = agent_id or "main"); replaces
  .claude/data/logs/ace-patterns-used-<session>-<agent>.json
- project_id: explicit kwarg, else ace_context.get_context()['project'], else "default"
- explicit state_dir= stands for the session dir (tests / tooling)
- optional keys: user_prompt (<= 4000 chars), rendered_context (<= 10000 chars),
  hook_event_name -- written by UPS/SubagentStart/domain-shift, read back by
  Stop/SubagentStop and SessionStart(compact)
- CLI flags unchanged
"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
sys.path.insert(0, str(UTILS))

PID_A = "ctx-4338628010-5127"
PID_B = "ctx-6257961166-f081"
SESSION = "sess-v8-1"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("ACE_PROJECT_ID", raising=False)
    monkeypatch.chdir(tmp_path)  # no .claude/settings.json here
    import plugin_data_dir
    import patterns_used_state
    importlib.reload(plugin_data_dir)
    return importlib.reload(patterns_used_state), tmp_path / "ace-pd"


def test_default_path_under_plugin_data(env):
    pus, root = env
    p = pus.state_file_path(SESSION, None, project_id="prj_1")
    assert p == root / "projects" / "prj_1" / "sessions" / SESSION / "patterns-used-main.json"
    p2 = pus.state_file_path(SESSION, "agent-7", project_id="prj_1")
    assert p2.name == "patterns-used-agent-7.json"


def test_project_id_resolved_from_context_then_default(env, monkeypatch):
    pus, root = env
    assert pus.state_file_path(SESSION, None).parts[-4] == "default"
    monkeypatch.setenv("ACE_PROJECT_ID", "prj_env")
    monkeypatch.setenv("ACE_ORG_ID", "org_test")  # 8.1.0: a project needs an org (spec no_org)
    assert pus.state_file_path(SESSION, None).parts[-4] == "prj_env"


def test_explicit_state_dir_is_session_dir(env, tmp_path):
    pus, _ = env
    p = pus.state_file_path(SESSION, None, state_dir=str(tmp_path / "sd"))
    assert p == tmp_path / "sd" / "patterns-used-main.json"


def test_no_legacy_project_log_path(env, tmp_path):
    pus, _ = env
    pus.append_patterns_used(SESSION, None, [PID_A], project_id="prj_1")
    assert not (tmp_path / ".claude" / "data" / "logs").exists()
    assert "ace-patterns-used" not in str(pus.state_file_path(SESSION, None, project_id="prj_1"))


def test_roundtrip_default_path(env):
    pus, _ = env
    pus.append_patterns_used(SESSION, None, [PID_A, PID_B], project_id="prj_1",
                             task_session_id="tsid-1")
    assert pus.load_task_session_id(SESSION, None, "Stop", project_id="prj_1") == "tsid-1"
    assert pus.load_playbook_used(SESSION, None, "Stop", project_id="prj_1") == [PID_A, PID_B]


def test_optional_keys_roundtrip(env):
    pus, _ = env
    pus.append_patterns_used(SESSION, None, [PID_A], project_id="prj_1",
                             user_prompt="implement auth",
                             rendered_context="<ace-patterns>x</ace-patterns>",
                             hook_event_name="UserPromptSubmit")
    st = pus.load_state(SESSION, None, "Stop", project_id="prj_1")
    assert st["user_prompt"] == "implement auth"
    assert st["rendered_context"] == "<ace-patterns>x</ace-patterns>"
    assert st["hook_event_name"] == "UserPromptSubmit"
    assert st["pattern_ids"] == [PID_A]


def test_optional_keys_are_truncated(env):
    pus, _ = env
    pus.append_patterns_used(SESSION, None, [PID_A], project_id="prj_1",
                             user_prompt="p" * 9000, rendered_context="c" * 25000)
    raw = json.loads(pus.state_file_path(SESSION, None, project_id="prj_1").read_text())
    assert len(raw["user_prompt"]) == 4000
    assert len(raw["rendered_context"]) <= 10000


def test_optional_keys_written_even_without_ids(env):
    """A 0-pattern search still records prompt + context for Stop / compact."""
    pus, _ = env
    pus.append_patterns_used(SESSION, None, [], project_id="prj_1", user_prompt="hello there")
    st = pus.load_state(SESSION, None, "Stop", project_id="prj_1")
    assert st["user_prompt"] == "hello there"


def test_optional_keys_absent_by_default(env):
    pus, _ = env
    pus.append_patterns_used(SESSION, None, [PID_A], project_id="prj_1")
    raw = json.loads(pus.state_file_path(SESSION, None, project_id="prj_1").read_text())
    for k in ("pattern_ids", "retrieval_id", "retrieval_log_ids", "task_session_id"):
        assert k in raw


def test_load_state_missing_returns_empty_dict(env):
    pus, _ = env
    assert pus.load_state("nope", None, "Stop", project_id="prj_1") == {}


def test_cli_flags_unchanged(env, tmp_path):
    _, root = env
    script = UTILS / "patterns_used_state.py"
    e = dict(os.environ, CLAUDE_PLUGIN_DATA=str(root), ACE_PROJECT_ID="prj_cli", ACE_ORG_ID="org_cli")
    payload = json.dumps({"similar_patterns": [{"id": PID_A}], "retrieval_id": "r1"})
    r = subprocess.run([sys.executable, str(script), "--session", SESSION, "--agent-id", "",
                        "--task-session-id", "tsid-cli"],
                       input=payload, capture_output=True, text=True, env=e, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    sf = root / "projects" / "prj_cli" / "sessions" / SESSION / "patterns-used-main.json"
    assert sf.exists()
    r2 = subprocess.run([sys.executable, str(script), "--session", SESSION,
                         "--read-task-session-id"],
                        capture_output=True, text=True, env=e, cwd=str(tmp_path))
    assert r2.stdout.strip() == "tsid-cli"
    r3 = subprocess.run([sys.executable, str(script), "--strip-and-gate"],
                        input=payload, capture_output=True, text=True, env=e, cwd=str(tmp_path))
    assert r3.returncode == 0 and "similar_patterns" in json.loads(r3.stdout)


# ── DESIGN §9 G2: prompt_id is the task anchor ──────────────────────────────

PROMPT_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_task_session_id_seed_is_prompt_id(env):
    """G2 (p3 PROVEN: identical prompt_id on UPS -> PreToolUse -> SubagentStart -> ... -> Stop):
    the task_session_id seed is the hook input prompt_id when present."""
    pus, _ = env
    assert pus.task_session_id_for({"prompt_id": PROMPT_ID}) == PROMPT_ID


@pytest.mark.parametrize("event", [{}, {"prompt_id": ""}, {"prompt_id": None}, None])
def test_task_session_id_falls_back_to_uuid4(env, event):
    """G2: headless / older CC without prompt_id -> fresh uuid4 (unique per call)."""
    import uuid
    pus, _ = env
    a, b = pus.task_session_id_for(event), pus.task_session_id_for(event)
    assert uuid.UUID(a).version == 4 and a != b
