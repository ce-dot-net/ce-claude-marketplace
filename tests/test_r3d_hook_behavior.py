#!/usr/bin/env python3
"""Round 3d RED: DESIGN §15 + §16 P1-P10 at hook level (fake ace-cli, tmp plugin data).

Evidence: research2/critic-pass2.md §1, cc_hooks_reference.md:2597 (SubagentHandback), :2750-2757
(background_tasks). P8 lives in test_prompt_id_anchor.py + test_domain_shift_py.py, the full Stop
deferral chain in tests/e2e/test_e2e_r3d.py.
"""
import importlib
import json
import subprocess
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

from r3d_harness import Box3d, system_message
from test_permission_denied_v8 import INFRA_TEXT, _mod as _pd_mod
from test_stop_v8 import Box, ORG_ID, PROJECT_ID, WORK, box  # noqa: F401
from wpd_harness import HookEnv, flag_value
from wpa_harness import Env


# ── P1 SubagentStop summary = last SubagentHandback message ─────────────────────────────

REPORT = "## Findings\n" + "the delivered report body. " * 80


def _handback_transcript(box, agent_id, *messages, closing="Now qdrant_search."):
    """Deferred: box.subagent_event() rewrites the agent transcript, so the handback lines are appended after it."""
    return lambda: _write_handback(box, agent_id, messages, closing)


def _write_handback(box, agent_id, messages, closing):
    p = box.agent_transcript(agent_id)
    extra = []
    for i, m in enumerate(messages):
        extra += [{"type": "assistant", "message": {"role": "assistant", "content": [
                      {"type": "tool_use", "id": "toolu_hb_%d" % i, "name": "SubagentHandback",
                       "input": {"message": m}}]}},
                  {"type": "user", "message": {"role": "user", "content": [
                      {"type": "tool_result", "tool_use_id": "toolu_hb_%d" % i, "content": "delivered"}]}}]
    extra.append({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": closing}]}})
    with p.open("a") as f:
        f.write("\n".join(json.dumps(e) for e in extra) + "\n")
    return str(p)


def _subagent_trace(box, agent_id, transcript, last="Now qdrant_search.", agent_type="Explore", **state):
    sid = "s-" + agent_id
    box.write_state(sid, agent_id, task_session_id="own-uuid", user_prompt="refactor the parser module", **state)
    box.seed_tools(sid, WORK, agent_id=agent_id)
    ev = box.subagent_event(sid, agent_id, agent_type=agent_type, last_assistant_message=last)
    if callable(transcript):
        transcript = transcript()
    if transcript:
        ev["agent_transcript_path"] = transcript
    p = box.run_after_task(ev, ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    return learn["trace"]


def test_subagent_summary_is_the_handback_report(box):
    t = _subagent_trace(box, "a1", _handback_transcript(box, "a1", REPORT))
    assert t["result"]["summary"].startswith("## Findings"), t["result"]["summary"][:80]


def test_subagent_summary_uses_the_last_handback(box):
    t = _subagent_trace(box, "a2", _handback_transcript(box, "a2", "first retry-denied", REPORT))
    assert t["result"]["summary"].startswith("## Findings")


def test_subagent_summary_without_handback_is_last_assistant_message(box):
    t = _subagent_trace(box, "a3", str(box.agent_transcript("a3")), last="Refactor done.")
    assert t["result"]["summary"] == "Refactor done."


def test_subagent_summary_cap_is_4000(box):
    t = _subagent_trace(box, "a4", _handback_transcript(box, "a4", "x" * 30000))
    assert len(t["result"]["summary"]) == 4000


def test_subagent_summary_non_string_handback_falls_back(box):
    t = _subagent_trace(box, "a5", _handback_transcript(box, "a5", {"not": "a string"}), last="Refactor done.")
    assert t["result"]["summary"] == "Refactor done."


# ── P2 Stop defers while delegated work of this task is still running ───────────────────

def _bg(type_, status="running", **kw):
    return dict({"id": "w0nda8a8l", "type": type_, "status": status, "description": "x"}, **kw)


def _stop(box, sid, background_tasks):
    f = box.write_state(sid, user_prompt="refactor the parser module", pattern_ids=["p1"], retrieval_id="r-1",
                        retrieval_log_ids={"p1": 7})
    box.seed_tools(sid, WORK)
    p = box.run_after_task(box.stop_event(sid, background_tasks=background_tasks),
                           ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    return p, f


@pytest.mark.parametrize("type_", ["subagent", "workflow"])
def test_stop_defers_on_running_delegated_work(box, type_):
    sid = "s-defer"
    p, state = _stop(box, sid, [_bg(type_)])
    assert p.stdout == "", "deferral is silent"
    assert box.cli_calls("learn") == [], "the 'waiting' turn must not be learned"
    assert state.exists(), "state must survive for the real Stop"
    assert json.loads(state.read_text())["retrieval_id"] == "r-1"
    con = __import__("sqlite3").connect(str(box.session_dir(sid) / "tools.db"))
    assert con.execute("SELECT count(*) FROM tool_uses").fetchone()[0] == len(WORK), "tool rows must survive"
    con.close()
    assert not list(box.session_dir(sid).glob("learn-inflight-*.lock")), "learn lock must be released"


def test_stop_deferral_logs_type_histogram(box):
    _stop(box, "s-hist", [_bg("subagent"), _bg("subagent"), _bg("workflow"), _bg("monitor")])
    (row,) = box.relevance_rows("learn_deferred")
    assert any(isinstance(v, dict) and v.get("subagent") == 2 and v.get("workflow") == 1 for v in row.values()), row


@pytest.mark.parametrize("type_", ["monitor", "shell", "teammate", "cloud session", "MCP task"])
def test_stop_does_not_defer_on_long_lived_tasks(box, type_):
    """ace-agile coach sessions always hold a Monitor: deferring on it would starve learning."""
    _stop(box, "s-long", [_bg(type_)])
    assert len(box.cli_calls("learn")) == 1
    assert box.relevance_rows("learn_deferred") == []


def test_stop_does_not_defer_on_finished_subagent(box):
    _stop(box, "s-done", [_bg("subagent", status="completed")])
    assert len(box.cli_calls("learn")) == 1


def test_stop_defers_when_a_monitor_runs_beside_a_subagent(box):
    _stop(box, "s-mix", [_bg("monitor"), _bg("subagent")])
    assert box.cli_calls("learn") == []


def test_subagent_stop_is_never_deferred(box):
    sid = "s-a-bg2"
    box.write_state(sid, "a-bg2", task_session_id="own", user_prompt="refactor the parser module")
    box.seed_tools(sid, WORK, agent_id="a-bg2")
    box.run_after_task(box.subagent_event(sid, "a-bg2", background_tasks=[_bg("subagent")]),
                       ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert len(box.cli_calls("learn")) == 1


# ── P3 trace field name ─────────────────────────────────────────────────────────────────

def test_trace_carries_parent_agent_id_not_parent_task_id(box):
    t = _subagent_trace(box, "a-p", str(box.agent_transcript("a-p")), parent_task_id="parent-prompt-id")
    assert t["parent_agent_id"] == "parent-prompt-id"
    assert "parent_task_id" not in t, "unknown keys are dropped by the server (pydantic extra=ignore)"


def test_trace_never_carries_agent_transcript_path(box):
    t = _subagent_trace(box, "a-x", str(box.agent_transcript("a-x")), parent_task_id="p")
    assert "agent_transcript_path" not in t, "the server would deref it on its own filesystem"


def test_trace_file_has_the_server_declared_fields(box):
    t = _subagent_trace(box, "a-f", str(box.agent_transcript("a-f")), parent_task_id="p")
    for k in ("render_variant", "session_id", "agent_id", "agent_type", "parent_agent_id"):
        assert k in t, k
    assert t["session_id"] == "own-uuid", "own pin, never the parent's"


# ── P4 (verify): --no-stream also on the PermissionDenied learn ─────────────────────────

def test_permission_denied_learn_uses_no_stream_json(tmp_path):
    env = Env(tmp_path)
    ev = {"session_id": "pd-1", "hook_event_name": "PermissionDenied", "cwd": str(env.project), "tool_name": "Bash",
          "tool_input": {"command": "rm -rf build"}, "tool_use_id": "t1", "reason": "[No destructive] denied",
          "transcript_path": ""}
    assert env.run("ace_permission_denied_wrapper.sh", ev).returncode == 0
    (call,) = env.cli_calls("learn")
    assert "--no-stream" in call[1] and "--json" in call[1], call


# ── P5 foreign CLAUDE_PLUGIN_DATA ───────────────────────────────────────────────────────

@pytest.fixture
def pdd(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    import plugin_data_dir
    return importlib.reload(plugin_data_dir)


@pytest.mark.parametrize("value", ["/x/data/cursor-tomas-cursor", "/x/data/codex-openai-codex", "/x/data/graceful"])
def test_foreign_plugin_data_is_rejected(pdd, monkeypatch, value):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", value)
    root = str(pdd.data_root())
    assert root != value and "cursor" not in root and "codex" not in root


@pytest.mark.parametrize("value", ["/x/data/ace-ce-dot-net-marketplace", "/x/data/ace-inline", "/x/ace"])
def test_own_plugin_data_is_accepted(pdd, monkeypatch, value):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", value)
    assert str(pdd.data_root()) == value


def test_hook_writes_nothing_into_a_foreign_data_dir(tmp_path):
    b = Box3d(tmp_path, local=True)
    foreign = tmp_path / "cursor-tomas-cursor"
    foreign.mkdir()
    assert b.session_start(CLAUDE_PLUGIN_DATA=foreign).returncode == 0
    assert list(foreign.iterdir()) == []


def test_sessionstart_env_file_gets_only_ace_vars(tmp_path):
    b = Box3d(tmp_path, global_version="4.2.2")
    f = tmp_path / "env.sh"
    f.touch()
    b.session_start(CLAUDE_ENV_FILE=f)
    lines = [l for l in f.read_text().splitlines() if l.strip()]
    assert lines and all(l.startswith("export ACE_") for l in lines), lines


# ── §15 / P6 Claude Code floor 2.1.311 ──────────────────────────────────────────────────

@pytest.mark.parametrize("version", ["2.1.250", "2.1.99", "2.1.310", "2.0.999", "1.9.400"])
def test_cc_below_floor_pauses_ace_with_one_message(tmp_path, version):
    b = Box3d(tmp_path, global_version="4.2.2")
    p = b.session_start(sid="s-old-cc", CLAUDE_CODE_VERSION=version)
    assert p.returncode == 0, p.stderr
    msg = system_message(p)
    assert "2.1.311" in msg and version in msg and "paused" in msg, msg
    assert (b.session_dir("s-old-cc") / "disabled.flag").is_file()


def test_cc_below_floor_silences_the_other_hooks(tmp_path):
    b = Box3d(tmp_path, global_version="4.2.2")
    b.session_start(sid="s-old-cc", CLAUDE_CODE_VERSION="2.1.250")
    p = b.ups(sid="s-old-cc", CLAUDE_CODE_VERSION="2.1.250")
    assert p.returncode == 0 and p.stdout == "" and b.cli_calls("search") == []


@pytest.mark.parametrize("version", ["2.1.311", "2.1.316", "2.1.1000", "2.2.0", "3.0.0"])
def test_cc_at_or_above_floor_runs(tmp_path, version):
    b = Box3d(tmp_path, global_version="4.2.2")
    p = b.session_start(CLAUDE_CODE_VERSION=version)
    assert "paused" not in system_message(p) and b.flags() == []


@pytest.mark.parametrize("version", [None, "", "not-a-version"])
def test_cc_version_unknown_never_disables(tmp_path, version):
    b = Box3d(tmp_path, global_version="4.2.2")
    p = b.session_start(CLAUDE_CODE_VERSION=version)
    assert "paused" not in system_message(p) and b.flags() == []


def test_cc_floor_check_beats_the_cli_presence_message(tmp_path):
    """Exactly one message: nothing about installing a CLI while ACE is paused anyway."""
    b = Box3d(tmp_path)
    msg = system_message(b.session_start(CLAUDE_CODE_VERSION="2.1.250"))
    assert "2.1.311" in msg and "/ace:ace-install-cli" not in msg, msg


# ── P7 forks inherit the parent context: own session, no second injection ───────────────

PROMPT_ID = "f486434d-1111-4222-8333-944455556666"
RESPONSE = {"count": 1, "retrieval_id": "r", "similar_patterns": [{
    "id": "ctx-1234567890-abcd", "content": "p", "section": "s", "confidence": 0.9, "helpful": 1, "harmful": 0,
    "cumulative_v15_reward": 1.0, "isAtRisk": False, "match_factors": {"bandit_rank": 1, "retrieval_log_id": 11}}]}
SID = "cc-r3d"


@pytest.fixture
def env(tmp_path):
    e = HookEnv(tmp_path, project_id="prj_r3d_%s" % uuid.uuid4().hex[:6])
    e.set_search_response(RESPONSE)
    return e


def _parent(env, prompt="sibling agent prompt that belongs to someone else"):
    t = env.tmp / "parent.jsonl"
    t.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Agent",
         "input": {"subagent_type": "Explore", "description": "x", "prompt": prompt}},
        {"type": "tool_use", "id": "toolu_2", "name": "Workflow",
         "input": {"script": "agent('secret-script-text-do-not-parse')"}}]}}) + "\n")
    return t


def _sstart(env, agent_type, agent_id="agent-r3d", prompt_id=PROMPT_ID, **extra_env):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "SubagentStart", "transcript_path": str(_parent(env)),
          "agent_id": agent_id, "agent_type": agent_type, "prompt_id": prompt_id}
    p = env.run("ace_subagent_start_wrapper.sh", ev, extra_env=extra_env or None)
    assert p.returncode == 0, p.stderr
    return p


def test_fork_skips_search_and_injection(env):
    p = _sstart(env, "fork")
    assert env.cli_calls() == [], "the fork's window already holds the parent's rendered block"
    assert p.stdout == ""


def test_fork_gets_own_session_state(env):
    _sstart(env, "fork", agent_id="agent-fork")
    st = env.read_state(SID, "agent-fork")
    assert st, "SubagentStop needs the fork's own pin"
    assert uuid.UUID(st["task_session_id"]).version == 4 and st["task_session_id"] != PROMPT_ID
    assert st["parent_task_id"] == PROMPT_ID


def test_fork_skip_is_logged(env):
    _sstart(env, "fork")
    rows = [r for r in env.relevance_rows() if r.get("reason") == "fork_inherits_context"]
    assert rows, env.relevance_rows()


def test_fork_env_override_restores_the_search(env):
    p = _sstart(env, "fork", ACE_SUBAGENT_INJECT_FORKS="1")
    assert len([c for c in env.cli_calls() if c["argv"][:1] == ["search"]]) == 1
    assert "ace-patterns-subagent" in p.stdout


def test_non_fork_subagent_still_searches(env):
    _sstart(env, "Explore")
    assert len([c for c in env.cli_calls() if c["argv"][:1] == ["search"]]) == 1


# ── P9 correctness one-liners ───────────────────────────────────────────────────────────

@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    import ace_cli
    return importlib.reload(ace_cli)


def _res(rc, out=b"", err=b""):
    r = MagicMock()
    r.returncode, r.stdout, r.stderr = rc, out, err
    return r


def test_token_expired_is_an_auth_failure(cli):
    with patch("subprocess.run", return_value=_res(1, err=b'{"error":"token_expired"}')):
        res, _ = cli.run_search("q")
    assert res and res.get("error") == "not_authenticated", res


def test_check_auth_status_unauthenticated_with_rc_zero_warns(cli):
    r = MagicMock(returncode=0, stdout='{"authenticated":false,"message":"Not logged in"}', stderr="")
    with patch("subprocess.run", return_value=r):
        assert "Not authenticated" in (cli.check_auth_status() or "")


def test_check_auth_status_authenticated_is_silent(cli):
    r = MagicMock(returncode=0, stdout='{"authenticated":true}', stderr="")
    with patch("subprocess.run", return_value=r):
        assert cli.check_auth_status() is None


def test_missing_sqlite_binary_suspends_pins_like_the_lock(cli):
    """Measured on `npm ci --ignore-scripts` of 4.2.2 (what CC installs): before the rebuild, --pin-session
    exits 1 with empty stdout. Search still works unpinned, but must not cost two spawns on every prompt."""
    binding = _res(1, err=b'{"level":"warn","message":"SQLite cache disabled (Could not locate the bindings file."}')
    good = _res(0, out=json.dumps(RESPONSE).encode())
    with patch("subprocess.run", side_effect=[binding, good]) as run:
        res, _ = cli.run_search("q", session_id="pin-1")
        assert res["retrieval_id"] == "r" and run.call_count == 2
    with patch("subprocess.run", return_value=good) as run:
        cli.run_search("q", session_id="pin-2")
    assert run.call_count == 1 and "--pin-session" not in run.call_args[0][0]


def _denied_then_api_requests(tmp_path, n, size):
    """2.1.300+ transcripts record each API request's system prompt/tools after the denied result."""
    p = tmp_path / "t.jsonl"
    lines = [json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": INFRA_TEXT, "is_error": True, "tool_use_id": "t1"}]}})]
    lines += [json.dumps({"type": "api-request", "system": "s" * size}) for _ in range(n)]
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_permission_denied_tail_reaches_past_32kb(tmp_path):
    t = _denied_then_api_requests(tmp_path, 8, 10000)
    assert _pd_mod()._is_classifier_infra_denial({"tool_name": "Bash", "transcript_path": t}) is True


def test_permission_denied_api_request_lines_do_not_eat_the_entry_window(tmp_path):
    t = _denied_then_api_requests(tmp_path, 40, 100)
    assert _pd_mod()._is_classifier_infra_denial({"tool_name": "Bash", "transcript_path": t}) is True


def test_permission_denied_tail_stays_bounded_at_256kb():
    assert _pd_mod()._TAIL_BYTES == 262144


# ── P10 workflow agents: own transcript -> parent main state -> parent scan ─────────────

def _main_state(env, tsid=PROMPT_ID, prompt="audit the payment webhook retry logic for idempotency bugs"):
    env.write_state(SID, None, task_session_id=tsid, user_prompt=prompt)
    return prompt


def _query_sent(env):
    (c,) = [c for c in env.cli_calls() if c["argv"][:1] == ["search"]]
    return c["stdin"]


def test_workflow_agent_falls_back_to_parent_task_prompt(env):
    prompt = _main_state(env)
    _sstart(env, "workflow-subagent", agent_id="agent-wf")
    assert _query_sent(env) == prompt, "a sibling Agent prompt from the parent scan is the wrong query"
    st = env.read_state(SID, "agent-wf")
    assert st["user_prompt"] == prompt and st["query_source"] not in (None, "parent_scan", "stash", "own_transcript")


def test_workflow_agent_own_transcript_wins_over_parent_state(env):
    _main_state(env)
    d = env.tmp / SID / "subagents" / "workflows" / "wf1"
    d.mkdir(parents=True)
    (d / "agent-agent-wf2.jsonl").write_text(json.dumps({"type": "user", "message": {
        "role": "user", "content": "harness note\nThe computed task text follows:\nreview the invoice exporter"}}) + "\n")
    _sstart(env, "workflow-subagent", agent_id="agent-wf2")
    assert _query_sent(env) == "review the invoice exporter"
    assert env.read_state(SID, "agent-wf2")["query_source"] == "own_transcript"


def test_workflow_agent_ignores_main_state_of_another_prompt(env):
    _main_state(env, tsid="an-earlier-prompt-id", prompt="the earlier prompt")
    _sstart(env, "workflow-subagent", agent_id="agent-wf3")
    assert "the earlier prompt" not in _query_sent(env)


def test_workflow_agent_never_parses_the_workflow_script(env):
    _sstart(env, "workflow-subagent", agent_id="agent-wf4")
    assert "secret-script-text" not in json.dumps(env.cli_calls())


def test_explore_agent_keeps_the_parent_scan(env):
    _main_state(env)
    _sstart(env, "Explore", agent_id="agent-ex")
    assert _query_sent(env).startswith("sibling agent prompt"), "fallback order is for workflow agents only"


def test_subagent_search_row_logs_query_source(env):
    _main_state(env)
    _sstart(env, "workflow-subagent", agent_id="agent-wf5")
    rows = [r for r in env.relevance_rows() if r.get("hook") == "SubagentStart"]
    assert rows and rows[-1].get("query_source"), rows
