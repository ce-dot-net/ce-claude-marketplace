#!/usr/bin/env python3
"""DESIGN §32: hybrid local reuse of ace_search_cache for domain-shift + SubagentStart (Python chain).

Hit = same project + exact normalized query + < 15 min + >= 1 pattern; each agent uses an entry at most once;
otherwise the server, and a server result refreshes the cache. Main UPS search stays server-only.
"""
import os
import time
import uuid

import pytest

from test_domain_shift_py import RESPONSE, SHIM, SID, _read_event, _search_calls  # noqa: F401
from wpd_harness import HookEnv


@pytest.fixture
def env(tmp_path):
    e = HookEnv(tmp_path, project_id="prj-s32-%s" % uuid.uuid4().hex[:8])
    e.write_domains({"auth:local": {"count": 3}, "database:local": {"count": 1}})
    e.set_search_response(RESPONSE)
    return e


def _read(env, rel, agent=None):
    return env.run(SHIM, _read_event(env, str(env.proj / rel), agent_id=agent))


def test_miss_goes_to_the_server_and_refreshes_the_cache(env):
    _read(env, "src/auth/login_handler.py")
    assert len(_search_calls(env)) == 1
    assert list((env.pd / "cache" / "search").glob("*.json"))


def test_hit_for_a_different_agent_spawns_nothing_and_still_injects(env):
    _read(env, "src/auth/login_handler.py")
    p = _read(env, "src/auth/login_handler.py", agent="a1")
    assert len(_search_calls(env)) == 1
    assert "additionalContext" in p.stdout
    rows = [r for r in env.relevance_rows() if r.get("event") == "domain_shift"]
    assert [r.get("cache_hit") for r in rows] == [False, True]


def test_the_same_agent_never_gets_the_same_entry_twice(env):
    _read(env, "src/auth/login_handler.py")
    _read(env, "src/database/other_thing.py")
    _read(env, "src/auth/login_handler.py")  # same agent, same query, entry already used by it -> server
    assert len(_search_calls(env)) == 3


def test_stale_entry_goes_to_the_server(env):
    _read(env, "src/auth/login_handler.py")
    for f in (env.pd / "cache" / "search").glob("*.json"):
        old = time.time() - 16 * 60
        os.utime(f, (old, old))
    _read(env, "src/auth/login_handler.py", agent="a1")
    assert len(_search_calls(env)) == 2


def test_empty_result_is_never_cached_or_served(env):
    env.set_search_response({"count": 0, "similar_patterns": [], "retrieval_id": "r0"})
    _read(env, "src/auth/login_handler.py")
    _read(env, "src/auth/login_handler.py", agent="a1")
    assert len(_search_calls(env)) == 2


def test_different_query_goes_to_the_server(env):
    _read(env, "src/auth/login_handler.py")
    _read(env, "src/auth/session_store.py", agent="a1")
    assert len(_search_calls(env)) == 2


def test_env_switch_turns_domain_reuse_off(env):
    _read(env, "src/auth/login_handler.py")
    env.run(SHIM, _read_event(env, str(env.proj / "src/auth/login_handler.py"), agent_id="a1"),
            extra_env={"ACE_LOCAL_REUSE": "subagent"})
    assert len(_search_calls(env)) == 2


# ── SubagentStart ───────────────────────────────────────────────────────────

def _subagent(monkeypatch, tmp_path, agent_id, calls):
    from test_subagent_start_search import (GOOD_CONTEXT, SAMPLE_PATTERNS_RESPONSE, _load_subagent_start,
                                            _make_event, _make_transcript)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-plugin-data"))
    monkeypatch.setenv("ACE_PROJECT_ID", GOOD_CONTEXT["project"])
    monkeypatch.setenv("ACE_ORG_ID", "org_test")  # 8.1.0: a project needs an org (spec no_org)
    monkeypatch.chdir(tmp_path)
    tp = _make_transcript(tmp_path, [{"subagent_type": "coder", "prompt": "Implement the SubagentStart hook"}])
    mod = _load_subagent_start()

    def fake(query, **kw):
        calls.append(query)
        return dict(SAMPLE_PATTERNS_RESPONSE), 5
    mod.run_search = fake
    try:
        mod.main(_make_event(tmp_path, transcript_path=tp, agent_type="coder", agent_id=agent_id))
    except SystemExit:
        pass


def test_subagent_same_task_text_new_agent_reuses_and_keeps_the_cached_retrieval_id(monkeypatch, tmp_path, capsys):
    calls = []
    _subagent(monkeypatch, tmp_path, "agent-1", calls)
    _subagent(monkeypatch, tmp_path, "agent-2", calls)
    assert len(calls) == 1
    from patterns_used_state import load_state
    assert load_state("sess-abc123", "agent-2", "SubagentStop", project_id="prj-test-01")["retrieval_id"] == "ret-abc-001"


def test_subagent_reuse_off_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ACE_LOCAL_REUSE", "domain")
    calls = []
    _subagent(monkeypatch, tmp_path, "agent-1", calls)
    _subagent(monkeypatch, tmp_path, "agent-2", calls)
    assert len(calls) == 2
