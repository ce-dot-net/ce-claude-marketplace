"""WP-D review fixes (fix(WP-D): review fixes). Subprocess tests via wpd_harness."""
import json
import os
import uuid
from pathlib import Path

import pytest

from wpd_harness import HookEnv, PLUGIN_ROOT

SID = "sess-wpd-fix"
RENDERED = '<ace-patterns shown="1" of="1">{"similar_patterns": []}</ace-patterns>'


def _pattern(pid, content, rank, domain="auth"):
    return {"id": pid, "domain": domain, "content": content, "section": "strategies",
            "confidence": 0.8, "helpful": 3, "harmful": 0, "evidence": [],
            "cumulative_v15_reward": 1.0, "isAtRisk": False, "n_hot_pos": 1, "n_hot_neg": 0,
            "match_factors": {"bandit_rank": rank, "semantic_score": 0.5,
                              "retrieval_log_id": rank + 100}}


@pytest.fixture
def env(tmp_path):
    return HookEnv(tmp_path, project_id="prj-wpd-fix-%s" % uuid.uuid4().hex[:8])


def _compact_event(env):
    return {"session_id": SID, "transcript_path": str(env.tmp / "t.jsonl"), "cwd": str(env.proj),
            "hook_event_name": "SessionStart", "source": "compact"}


def _read_event(env, file_path):
    return {"session_id": SID, "transcript_path": str(env.tmp / "t.jsonl"), "cwd": str(env.proj),
            "hook_event_name": "PostToolUse", "tool_name": "Read",
            "tool_input": {"file_path": file_path}, "tool_response": {}, "tool_use_id": "t1"}


# ── must_fix: compact re-inject survives Stop's reap ─────────────────────────

@pytest.mark.parametrize("reaper", ["load_playbook_used", "reap_patterns_used"])
def test_compact_reinject_survives_stop_reap(env, monkeypatch, reaper):
    env.write_state(SID, None, rendered_context=RENDERED)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(env.pd))
    import patterns_used_state as pus
    getattr(pus, reaper)(SID, None, 'Stop', project_id=env.project_id)
    assert not env.state_file(SID).exists(), "Stop still reaps the state file"
    proc = env.run("ace_sessionstart_compact.sh", _compact_event(env))
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["additionalContext"] == RENDERED


def test_subagent_stop_reap_does_not_leave_main_sidecar(env, monkeypatch):
    env.write_state(SID, "agent-x", rendered_context=RENDERED)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(env.pd))
    import patterns_used_state as pus
    pus.load_playbook_used(SID, "agent-x", 'SubagentStop', project_id=env.project_id)
    assert not (env.session_dir(SID) / "rendered-main.txt").exists()


# ── SubagentStart ────────────────────────────────────────────────────────────

def _sa_event(env, agent_id="agent-a1"):
    t = env.tmp / "main.jsonl"
    t.write_text(json.dumps({"message": {"content": [{"type": "tool_use", "name": "Agent",
                 "input": {"subagent_type": "coder", "prompt": "Do the thing"}}]}}) + "\n")
    return {"session_id": SID, "transcript_path": str(t), "cwd": str(env.proj),
            "hook_event_name": "SubagentStart", "agent_id": agent_id, "agent_type": "coder"}


def test_subagent_resume_reemits_stored_context_without_search(env):
    env.write_state(SID, "agent-a1", task_session_id="tsid-1", rendered_context=RENDERED)
    proc = env.run("ace_subagent_start_wrapper.sh", _sa_event(env))
    assert env.cli_calls() == []
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["additionalContext"] == RENDERED
    assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStart"


def test_subagent_injection_stores_rendered_context(env):
    env.set_search_response({"count": 1, "retrieval_id": "r1",
                             "similar_patterns": [_pattern("ctx-1111111111-aaaa", "hello", 1)]})
    proc = env.run("ace_subagent_start_wrapper.sh", _sa_event(env))
    ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert env.read_state(SID, "agent-a1")["rendered_context"] == ctx


def test_subagent_no_project_context_writes_no_default_dir(env):
    (env.proj / ".claude" / "settings.json").unlink()
    proc = env.run("ace_subagent_start_wrapper.sh", _sa_event(env))
    assert proc.returncode == 0
    assert not (env.pd / "projects" / "default" / "sessions" / SID).exists()


# ── domain-shift ─────────────────────────────────────────────────────────────

def _ds_env(env, patterns, domains=None):
    env.write_domains(domains or {"auth:local": {"count": 3}})
    env.set_search_response({"count": len(patterns), "retrieval_id": "ret-1",
                             "similar_patterns": patterns})


def test_domain_shift_cap_trim_credits_only_injected_ids(env):
    pats = [_pattern("ctx-%010d-aaaa" % i, "x" * 2500, i) for i in range(1, 9)]
    _ds_env(env, pats)
    proc = env.run("ace_posttooluse_domain_inject.sh", _read_event(env, str(env.proj / "src/auth/login.py")))
    ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert len(ctx) <= 10000
    inner = ctx.split('">', 1)[1].rsplit("</ace-patterns-domain-shift>", 1)[0]
    injected = {p["id"] for p in json.loads(inner)["similar_patterns"]}
    assert 0 < len(injected) < 8
    st = env.read_state(SID)
    assert set(st["pattern_ids"]) == injected
    assert set(st["retrieval_log_ids"]) == injected


def test_domain_shift_row_hook_is_posttooluse(env):
    _ds_env(env, [_pattern("ctx-1111111111-aaaa", "hello", 1)])
    env.run("ace_posttooluse_domain_inject.sh", _read_event(env, str(env.proj / "src/auth/login.py")))
    rows = [r for r in env.relevance_rows() if r.get("event") == "domain_shift"]
    assert rows and all(r["hook"] == "PostToolUse" for r in rows)
    assert rows[0]["search_succeeded"] is True


def test_domain_shift_search_ok_zero_patterns_still_succeeded(env):
    _ds_env(env, [])
    env.run("ace_posttooluse_domain_inject.sh", _read_event(env, str(env.proj / "src/auth/login.py")))
    rows = [r for r in env.relevance_rows() if r.get("event") == "domain_shift"]
    assert rows and rows[0]["search_succeeded"] is True and rows[0]["patterns_found"] == 0


def test_domain_shift_exception_is_logged_not_swallowed(env):
    _ds_env(env, ["not-a-dict"])
    proc = env.run("ace_posttooluse_domain_inject.sh", _read_event(env, str(env.proj / "src/auth/login.py")))
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    errs = [r for r in env.relevance_rows() if r.get("event") == "error"]
    assert errs and errs[0]["hook"] == "PostToolUse"


def test_domain_shift_domain_name_is_attribute_escaped(env):
    _ds_env(env, [_pattern("ctx-1111111111-aaaa", "hello", 1)], domains={'au"th>x:local': {}})
    proc = env.run("ace_posttooluse_domain_inject.sh", _read_event(env, str(env.proj / "src/au_thx/login.py")))
    if proc.stdout.strip():
        ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        head = ctx.split(">", 1)[0]
        assert head.count('"') == 2, head


def test_compact_exception_is_logged(env):
    env.write_state(SID, None, rendered_context=RENDERED)
    proc = env.run("ace_sessionstart_compact.sh", None, raw_stdin="{not json")
    assert proc.returncode == 0 and proc.stdout.strip() == ""


# ── hooks.json guard ─────────────────────────────────────────────────────────

def test_every_hooks_json_command_path_exists():
    data = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
    missing = []
    for entries in data["hooks"].values():
        for e in entries:
            for h in e["hooks"]:
                rel = h["command"].replace("${CLAUDE_PLUGIN_ROOT}/", "").split()[0]
                if not (PLUGIN_ROOT / rel).exists():
                    missing.append(rel)
    assert not missing, missing


def test_compact_shim_registered_for_sessionstart_compact():
    data = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
    assert any(e.get("matcher") == "compact" and
               any("ace_sessionstart_compact.sh" in h["command"] for h in e["hooks"])
               for e in data["hooks"]["SessionStart"])


def test_stale_precompact_shell_test_removed():
    assert not (PLUGIN_ROOT / "tests" / "test_precompact_sessionstart_handoff.sh").exists()
