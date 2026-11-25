"""Layout (a) arm in the Python chain: the hooks (UPS, SubagentStart, domain shift), state key render_layout, the trace field
render_layout, the relevance-log label, queue validity. render_variant itself stays 'budget' | 'full'. Synthetic data only."""
import json
import sys
import uuid
from pathlib import Path

import pytest

from test_stop_v8 import Box, ORG_ID, PROJECT_ID, WORK, box  # noqa: F401  (also puts shared-hooks on sys.path)
from wpd_harness import HookEnv
import ace_pattern_render as A
import ace_trace_queue as Q

IDS = ["ctx-1111111111-aaaa", "ctx-2222222222-bbbb"]


def _pat(pid, rank, content):
    return {"id": pid, "domain": "auth", "content": content, "section": "strategies", "confidence": 0.8, "helpful": 3,
            "harmful": 0, "evidence": ["e \"1\"", "é"], "cumulative_v15_reward": 1.0, "isAtRisk": False,
            "n_hot_pos": 1, "n_hot_neg": 0, "match_factors": {"bandit_rank": rank, "semantic_score": 0.5, "retrieval_log_id": rank + 100}}


RESPONSE = {"count": 2, "retrieval_id": "ret-la", "similar_patterns": [_pat(IDS[0], 2, "second"), _pat(IDS[1], 1, 'first "q" \n é')]}
SID = "sess-layout-a"
ON = {"ACE_RENDER_LAYOUT_A_PCT": "100"}


@pytest.fixture
def henv(tmp_path):
    e = HookEnv(tmp_path, project_id="prj_la_%s" % uuid.uuid4().hex[:6])
    e.set_search_response(RESPONSE)
    e.write_domains({"auth:local": {"count": 3}})
    return e


def _ups(env, **extra):
    ev = {"session_id": SID, "cwd": str(env.proj), "hook_event_name": "UserPromptSubmit",
          "prompt_id": "11111111-1111-4111-8111-111111111111", "transcript_path": str(env.tmp / "t.jsonl"),
          "prompt": "refactor the authentication middleware to use JSON web tokens"}
    p = env.run("ace_before_task_wrapper.sh", ev, extra_env=extra)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout).get("hookSpecificOutput", {}).get("additionalContext") if p.stdout.strip() else None


def _search_row(env):
    return [r for r in env.relevance_rows() if r.get("event") == "search"][-1]


def test_default_is_byte_identical_to_today(henv):
    ctx = _ups(henv)  # no env, no file: the arm is off
    assert '"similar_patterns": [' in ctx and '"fields"' not in ctx
    st = henv.read_state(SID)
    assert st["render_variant"] == "budget" and "render_layout" not in st
    assert _search_row(henv)["render_cohort"] == "budget"


def test_on_renders_layout_and_marks_state_and_log(henv):
    ctx = _ups(henv, **ON)
    lines = ctx.split("\n")
    assert lines[0] == '<ace-patterns shown="2" of="2" agent-type="main">'
    head = json.loads(lines[1])
    assert head["fields"] == A.LAYOUT_A_FIELDS and head["count"] == 2 and head["retrieval_id"] == "ret-la"
    assert json.loads(lines[2])[A.LAYOUT_A_FIELDS.index("id")] == IDS[1]  # bandit_rank 1 first
    st = henv.read_state(SID)
    assert (st["render_variant"], st["render_layout"]) == ("budget", "a")
    assert st["pattern_ids"] == [IDS[1], IDS[0]]
    assert _search_row(henv)["render_cohort"] == "budget+layout_a"


def test_server_share_file_switches_it_on(henv):
    henv.pd.mkdir(parents=True, exist_ok=True)
    import time
    (henv.pd / "render-layout-a-pct.json").write_text(json.dumps({"pct": 100, "at": int(time.time())}))
    assert '"fields"' in _ups(henv)


@pytest.mark.parametrize("arm_env,tag", [({"ACE_AB_CONTROL_PCT": "100"}, None), ({"ACE_AB_COMPACT_PCT": "100"}, "compact")])
def test_control_and_compact_never_get_layout(henv, arm_env, tag):
    ctx = _ups(henv, **ON, **arm_env)
    if tag is None:
        assert ctx is None
    else:
        assert 'mode="compact"' in ctx and '"fields"' not in ctx
    assert "render_layout" not in henv.read_state(SID)
    assert "+layout_a" not in _search_row(henv)["render_cohort"]


def test_subagent_start_on_and_off(henv):
    def run(aid, **extra):
        ev = {"session_id": SID, "cwd": str(henv.proj), "hook_event_name": "SubagentStart", "agent_id": aid,
              "agent_type": "general-purpose", "prompt_id": "44444444-4444-4444-8444-444444444444",
              "transcript_path": str(henv.tmp / "t.jsonl"),
              "prompt": "audit the session-end reaper for races between the learn lock and the GC"}
        tr = henv.tmp / "sub-transcript.jsonl"  # CC 2.1.170+: the query comes from the parent's Task tool_use in the transcript
        tr.write_text(json.dumps({"type": "assistantMessage", "uuid": "u0", "timestamp": "2026-06-10T10:00:00.000Z", "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_0000", "name": "Task",
                                              "input": {"subagent_type": "general-purpose", "prompt": ev["prompt"]}}]}}) + "\n")
        ev["transcript_path"] = str(tr)
        henv.write_state(SID, None, task_session_id="44444444-4444-4444-8444-444444444444", user_prompt=ev["prompt"])
        p = henv.run("ace_subagent_start_wrapper.sh", ev, extra_env=extra)
        assert p.returncode == 0, (p.stdout, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    off = run("agent-la-off")
    assert '"similar_patterns": [' in off and "render_layout" not in henv.read_state(SID, "agent-la-off")
    on = run("agent-la-on", **ON)
    assert on.startswith('<ace-patterns-subagent shown="2" of="2" agent-type="general-purpose" agent-id="agent-la-on">\n{"retrieval_id"')
    assert henv.read_state(SID, "agent-la-on")["render_layout"] == "a"


def _read_event(env, path):
    return {"session_id": SID, "transcript_path": str(env.tmp / "t.jsonl"), "cwd": str(env.proj), "permission_mode": "default",
            "hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": path},
            "tool_response": {"type": "text"}, "tool_use_id": "toolu_la"}


def test_domain_shift_on_and_off(henv):
    def run(path, **extra):
        p = henv.run("ace_posttooluse_domain_inject.sh", _read_event(henv, path), extra_env=extra)
        assert p.returncode == 0, (p.stdout, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    off = run(str(henv.proj / "src/auth/a.py"))
    assert off.startswith('<ace-patterns-domain-shift domain="auth">{') and '"fields"' not in off
    henv.disable  # noqa: B018  (fresh domain visit below: another conversation)
    on_ev = _read_event(henv, str(henv.proj / "src/auth/b.py"))
    on_ev["session_id"] = SID + "-2"
    p = henv.run("ace_posttooluse_domain_inject.sh", on_ev, extra_env=ON)
    on = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    lines = on.split("\n")
    assert lines[0] == '<ace-patterns-domain-shift domain="auth">' and lines[-1] == "</ace-patterns-domain-shift>"
    assert json.loads(lines[1])["fields"] == A.LAYOUT_A_FIELDS and len(lines) == 2 + 1 + 2


# ---------- learn: the trace field render_layout (own optional field, next to render_variant / render_path) ----------
def _learn(box, **state):
    box.write_state("s-la", "main", user_prompt="refactor the parser module", **state)
    box.seed_tools("s-la", WORK)
    p = box.run_after_task(box.stop_event("s-la"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    return learn["trace"]


def test_trace_carries_render_layout_only_when_the_arm_rendered(box):
    t = _learn(box, pattern_ids=IDS, retrieval_log_ids={IDS[0]: 7}, render_variant="budget", render_layout="a")
    assert (t["render_variant"], t["render_path"], t["render_layout"]) == ("budget", "python", "a")
    rows = box.relevance_rows("execution")
    assert rows[-1]["render_cohort"] == "budget+layout_a"


@pytest.mark.parametrize("stored", [{}, {"render_layout": "b"}, {"render_layout": None}, {"render_layout": True}])
def test_trace_omits_render_layout_otherwise(box, stored):
    t = _learn(box, pattern_ids=IDS, retrieval_log_ids={IDS[0]: 7}, render_variant="budget", **stored)
    assert "render_layout" not in t and t["render_variant"] == "budget"
    assert box.relevance_rows("execution")[-1]["render_cohort"] == "budget"


# ---------- the queue: a trace field is no queue meta; _valid_meta (8.3.0) is untouched ----------
def test_queue_entries_with_the_new_trace_field_stay_valid(tmp_path, monkeypatch):
    monkeypatch.delenv("ACE_TRACE_QUEUE", raising=False)
    qdir = tmp_path / "data" / "trace-queue"
    meta = {"org": "org_t", "project": "prj_t", "retrieval_id": "rid-1", "applied_log_ids": [1, 2], "hook": "Stop", "agent_type": "main"}
    assert Q._valid_meta(meta) and not Q._valid_meta(dict(meta, render_layout="a"))  # meta stays closed: the field lives in the trace
    trace = {"task": "t", "trajectory": [], "result": {"success": True}, "playbook_used": [], "timestamp": "x",
             "render_variant": "budget", "render_path": "python", "render_layout": "a"}
    dead = '{"event":"ace_trace_dead_letter","attempts":4,"status":502,"error":"Server error (502)","timestamp":"x"}\n{"error":{"code":"server_error","status":502,"message":"Server error (502): "}}'
    rows = Q.settle(qdir, "%032x" % 1, trace, meta, 1, dead, now=1_800_000_000.0)
    assert rows[0]["event"] == "learn_requeued", rows
    assert not (qdir / "dead").exists() or not list((qdir / "dead").glob("*.json"))
    f = qdir / ("%032x.json" % 1)
    e = json.loads(f.read_text())
    assert e["trace"]["render_layout"] == "a" and Q._valid_entry(e)


# ---------- review fixes: W1 domain-shift marks state, W2 no sticky field, I3 recap rows, I8 hint value ----------
HINT = {"ACE_RENDER_LAYOUT_A_HINT": "1"}


def _ds(env, sid, path, **extra):
    ev = _read_event(env, str(env.proj / path))
    ev["session_id"] = sid
    p = env.run("ace_posttooluse_domain_inject.sh", ev, extra_env=extra)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout).get("hookSpecificOutput", {}).get("additionalContext") if p.stdout.strip() else None


def test_w1_domain_shift_only_turn_marks_state(henv):
    assert '"fields"' in _ds(henv, "ds-only", "src/auth/a.py", **ON)
    assert henv.read_state("ds-only")["render_layout"] == "a"
    assert '"fields"' in _ds(henv, "ds-hint", "src/auth/a.py", **ON, **HINT)
    assert henv.read_state("ds-hint")["render_layout"] == "a+hint"


def test_w1_domain_shift_non_member_or_control_or_compact_sets_nothing(henv):
    _ds(henv, "ds-off", "src/auth/a.py")
    assert "render_layout" not in henv.read_state("ds-off")
    for i, arm in enumerate(({"ACE_AB_CONTROL_PCT": "100"}, {"ACE_AB_COMPACT_PCT": "100"})):
        sid = "ds-arm-%d" % i
        _ds(henv, sid, "src/auth/a.py", **ON, **arm)
        st = henv.read_state(sid)
        assert "render_layout" not in st, arm


def test_w2_render_without_layout_clears_an_earlier_value(henv):
    _ups(henv, **ON)
    assert henv.read_state(SID)["render_layout"] == "a"
    _ups(henv)  # the next task renders today's layout
    assert "render_layout" not in henv.read_state(SID)
    _ups(henv, **ON)
    _ups(henv, **ON, ACE_AB_CONTROL_PCT="100")  # control renders nothing: no layout either
    assert "render_layout" not in henv.read_state(SID)


def test_w2_state_writer_clears_and_keeps(tmp_path):
    """append_patterns_used: '' = rendered without layout (removes the key), None = keep."""
    import patterns_used_state as pus
    kw = dict(state_dir=str(tmp_path), retrieval_id="r", task_session_id="t", user_prompt="p", render_variant="budget")
    def st():
        return json.loads(next(tmp_path.rglob("patterns-used-main.json")).read_text())
    pus.append_patterns_used("s", None, [], render_layout="a+hint", **kw)
    assert st()["render_layout"] == "a+hint"
    pus.append_patterns_used("s", None, [], retrieval_id="r", task_session_id="t", state_dir=str(tmp_path))  # a merge that passes none keeps it
    assert st()["render_layout"] == "a+hint"
    pus.append_patterns_used("s", None, [], render_layout="", **kw)
    assert "render_layout" not in st()


def test_i8_hint_value_in_state_log_and_trace(henv, box):
    _ups(henv, **ON, **HINT)
    assert henv.read_state(SID)["render_layout"] == "a+hint"
    assert _search_row(henv)["render_cohort"] == "budget+layout_a+hint"
    t = _learn(box, pattern_ids=IDS, retrieval_log_ids={IDS[0]: 7}, render_variant="budget", render_layout="a+hint")
    assert t["render_layout"] == "a+hint" and t["render_variant"] == "budget"
    assert box.relevance_rows("execution")[-1]["render_cohort"] == "budget+layout_a+hint"
    assert A.LAYOUT_A_VALUES == ("a", "a+hint")


def test_i8_queue_accepts_the_hint_value(tmp_path, monkeypatch):
    monkeypatch.delenv("ACE_TRACE_QUEUE", raising=False)
    qdir = tmp_path / "data" / "trace-queue"
    meta = {"org": "org_t", "project": "prj_t", "retrieval_id": "rid-1", "applied_log_ids": [1], "hook": "Stop", "agent_type": "main"}
    trace = {"task": "t", "trajectory": [], "result": {"success": True}, "playbook_used": [], "timestamp": "x", "render_layout": "a+hint"}
    dead = '{"event":"ace_trace_dead_letter","attempts":4,"status":502,"error":"Server error (502)","timestamp":"x"}\n{"error":{"code":"server_error","status":502,"message":"Server error (502): "}}'
    assert Q.settle(qdir, "%032x" % 2, trace, meta, 1, dead, now=1_800_000_000.0)[0]["event"] == "learn_requeued"
    assert Q._valid_entry(json.loads((qdir / ("%032x.json" % 2)).read_text()))


def test_i3_recap_lists_layout_arms_as_own_rows():
    import time
    import ace_insights_analyzer as I
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    rows = []
    for arm in ("budget", "full", "budget+layout_a", "full+layout_a+hint"):
        rows.append({"timestamp": now, "event": "execution", "agent_type": "main", "render_cohort": arm,
                     "used_ids_count": 2, "patterns_used_count": 5, "used_source": "tokens", "task_session_id": "t-" + arm})
    out = I.generate_text_report(rows, hours=1)
    for arm in ("budget", "full", "budget+layout_a", "full+layout_a+hint"):
        assert "  %s: 1/1 tasks with evidenced use" % arm in out, (arm, out)


# ---------- re-review: zero rendered patterns stamp nothing; PermissionDenied trace carries the stored value ----------
def test_domain_shift_with_an_oversize_single_pattern_renders_nothing_and_stamps_nothing(henv):
    big = dict(_pat(IDS[0], 1, "x" * 12000))
    henv.set_search_response({"count": 1, "retrieval_id": "ret-big", "similar_patterns": [big]})
    assert _ds(henv, "ds-big", "src/auth/a.py", **ON) is None  # nothing fits the 10,000 cap: no header-only block
    assert "render_layout" not in (henv.read_state("ds-big") or {})


def test_domain_shift_normal_case_still_stamps_a(henv):
    assert '"fields"' in _ds(henv, "ds-ok", "src/auth/a.py", **ON)
    assert henv.read_state("ds-ok")["render_layout"] == "a"


@pytest.mark.parametrize("stored,want", [("a", "a"), ("a+hint", "a+hint"), (None, None), ("b", None)])
def test_permission_denied_trace_carries_render_layout_only_when_stored(tmp_path, monkeypatch, stored, want):
    from test_permission_denied_v8 import _stored
    m = _stored(tmp_path, monkeypatch, "budget")
    f = next(tmp_path.rglob("patterns-used-main.json"))
    st = json.loads(f.read_text())
    if stored is not None:
        st["render_layout"] = stored
    f.write_text(json.dumps(st))
    t = m._build_trace({"session_id": "pd-rv", "tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert t.get("render_layout") == want and t["render_variant"] == "budget"
