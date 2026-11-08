"""8.1.4 trace delivery, Python chain (DESIGN "Trace delivery"): a built trace is never lost without a row.

- A send that failed before reaching the server (dead letter 502/503/504, connection) is queued with the exact,
  already redacted body; 4xx goes to dead/ and is never replayed; ACE_TRACE_QUEUE=0 logs learn_lost only.
- Canary secrets never reach a queue file or a log.
- The replay entry point (`ace_trace_queue.py --replay`) sends the queued body and logs learn_replayed.
- Every automatic trace carries result.plugin_version (manifest x.y.z) and result.outcome_rule from OUTCOME_RULES.
- The engine sends the queue id as Idempotency-Key (never the CLI: it has no such flag).
"""
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import engine_harness as E
from test_stop_v8 import AFTER_TASK, ORG_ID, PROJECT_ID, WORK, Box, _main_transcript, _tool_turn  # noqa: F401

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
UTILS = PLUGIN / "shared-hooks" / "utils"
sys.path.insert(0, str(UTILS))
import ace_trace_queue as Q  # noqa: E402

DEAD_502 = '{"event":"ace_trace_dead_letter","attempts":4,"status":502,"error":"Server error (502)","timestamp":"t"}'
# ace-cli has no stable key: only a send that never reached the server is queued (connection refused)
DEAD_NET = '{"event":"ace_trace_dead_letter","attempts":4,"error":"fetch failed","timestamp":"t"}\nError: connect ECONNREFUSED 127.0.0.1:1'
VERSION = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
needs_node = pytest.mark.skipif(E.node_bin() is None, reason="node not installed")


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def _stop(box, sid, **env):
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the retry queue for learn traces please")
    proc = box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_LEARN_INLINE="1", **env)
    assert proc.returncode == 0, proc.stderr
    return proc


def _qfiles(box):
    q = box.pd / "trace-queue"
    return sorted(q.glob("*.json")) if q.is_dir() else []


def _rows(box, ev):
    return box.relevance_rows(ev)


# ---------- requeue / dead / disabled ----------

def test_cli_path_connection_error_queues_the_exact_body_with_a_requeued_row(box):
    _stop(box, "s-q1", ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR=DEAD_NET)
    sent = box.cli_calls("learn")[0]["trace"]
    files = _qfiles(box)
    assert len(files) == 1
    e = json.loads(files[0].read_text())
    assert e["trace"] == sent, "the queue keeps the body that was sent, nothing rebuilt"
    assert "id" not in e and len(e["hmac"]) == 64
    assert e["meta"]["project"] == PROJECT_ID and e["meta"]["org"] == ORG_ID and e["meta"]["hook"] == "Stop"
    r = _rows(box, "learn_requeued")
    assert len(r) == 1 and r[0]["error_class"] == "network" and r[0]["trace_id"] == files[0].stem
    assert r[0]["agent_type"] == "main" and r[0]["attempts"] == 1


def test_cli_path_502_is_lost_not_queued(box):
    """Behind the ace-cli fallback the first send had a random key: a replay could not be merged by the server."""
    _stop(box, "s-q502", ACE_FAKE_LEARN_RC="8", ACE_FAKE_LEARN_ERR=DEAD_502)
    assert _qfiles(box) == []
    r = _rows(box, "learn_lost")
    assert r and r[0]["reason"] == "maybe_sent" and r[0]["error_class"] == "server_5xx"


@pytest.mark.parametrize("rc,err", [("3", '{"error":{"code":"not_logged_in","status":null,"message":"Not logged in"}}'),
                                    ("4", '{"error":{"code":"token_expired","status":401,"message":"expired"}}')])
def test_cli_auth_failure_goes_to_dead_as_never_sent(box, rc, err):
    _stop(box, "s-auth" + rc, ACE_FAKE_LEARN_RC=rc, ACE_FAKE_LEARN_ERR=err)
    assert _qfiles(box) == [] and len(list((box.pd / "trace-queue" / "dead").glob("*.json"))) == 1
    assert _rows(box, "learn_lost")[0]["error_class"] == "auth"


def test_400_goes_to_dead_and_is_never_replayed(box):
    _stop(box, "s-q2", ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR="Server error (400): invalid trace")
    assert _qfiles(box) == [] and len(list((box.pd / "trace-queue" / "dead").glob("*.json"))) == 1
    r = _rows(box, "learn_lost")
    assert r and r[0]["error_class"] == "4xx" and r[0]["reason"] == "rejected"
    assert Q.replay(box.pd / "trace-queue", lambda e: pytest.fail("4xx replayed"), now=10 ** 12) == []


def test_queue_off_logs_learn_lost_only(box):
    _stop(box, "s-q3", ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR=DEAD_NET, ACE_TRACE_QUEUE="0")
    assert not (box.pd / "trace-queue").exists() or not list((box.pd / "trace-queue").rglob("*.json"))
    r = _rows(box, "learn_lost")
    assert r and r[0]["reason"] == "queue_disabled" and r[0]["error_class"] == "network"


def test_a_cli_timeout_is_lost_not_queued(box):
    _stop(box, "s-q4", ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR="Request timed out after 300000ms")
    assert _qfiles(box) == []
    assert _rows(box, "learn_lost")[0]["error_class"] == "timeout"


def test_canary_secrets_never_reach_the_queue_or_a_log(box):
    canary, u, y = "ghp_CANARYcanary0123456789", "CANARYurl", "CANARYyaml"
    sid = "sess-canary-q"
    box.seed_tools(sid, [("Read", {"file_path": "src/app.py"}, {"content": "x"})])
    prompt = "publish the release with token %s, https://u:%s@h, password: %s please" % (canary, u, y)
    entries = [{"type": "user", "message": {"role": "user", "content": prompt}}] + \
        _tool_turn("toolu_sess-canary-q_0", "Read", {"file_path": "src/app.py"}) + \
        _tool_turn("toolu_c1", "Bash", {"command": "GITHUB_TOKEN=%s gh release create v1" % canary}, "token %s ok" % canary) + \
        _tool_turn("toolu_c2", "Bash", {"command": "mysql -uroot -p%s db" % y}, "password: %s" % y)
    box.write_state(sid, user_prompt=prompt)
    proc = box.run_after_task(box.stop_event(sid, transcript_path=_main_transcript(box, entries),
                                             last_assistant_message="done with %s and password: %s" % (canary, y)),
                              ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_LEARN_INLINE="1",
                              ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR=DEAD_NET)
    assert proc.returncode == 0, proc.stderr
    assert _qfiles(box), "the failed send was queued"
    scanned = 0
    for base in (box.pd, box.project / ".claude" / "data" / "logs"):
        for p in base.rglob("*"):
            if p.is_file() and "fake-cli" not in p.name:
                scanned += 1
                assert "CANARY" not in p.read_text(errors="replace"), p
    assert scanned >= 2


# ---------- replay entry point (next session) ----------

def test_replay_entry_point_sends_the_queued_body_and_logs_replayed(box):
    _stop(box, "s-q5", ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR=DEAD_NET)
    f = _qfiles(box)[0]
    e = json.loads(f.read_text())
    e["next_at"] = 0
    f.write_text(json.dumps(e))
    p = subprocess.run([sys.executable, str(UTILS / "ace_trace_queue.py"), "--replay", "--cwd", str(box.project)],
                       capture_output=True, text=True, timeout=60, cwd=str(box.project), env=box.env())
    assert p.returncode == 0, p.stderr
    learns = box.cli_calls("learn")
    assert len(learns) == 2 and learns[1]["trace"] == e["trace"]
    assert "--idempotency-key" not in learns[1]["argv"], "ace-cli has no such flag"
    assert _qfiles(box) == []
    r = _rows(box, "learn_replayed")
    assert len(r) == 1 and r[0]["trace_id"] == f.stem and r[0]["attempts"] == 2


def test_a_good_learn_starts_a_replay_when_the_queue_is_not_empty(box):
    _stop(box, "s-q6", ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR=DEAD_NET)
    f = _qfiles(box)[0]
    e = json.loads(f.read_text())
    e["next_at"] = 0
    f.write_text(json.dumps(e))
    _stop(box, "s-q7")  # this learn succeeds, then a detached replay runs
    import time
    for _ in range(100):
        if not _qfiles(box):
            break
        time.sleep(0.1)
    assert _qfiles(box) == []
    assert len(box.cli_calls("learn")) == 3


# ---------- result.plugin_version / result.outcome_rule ----------

def test_outcome_rules_list_and_parity_with_the_mod():
    from ace_trace_meta import OUTCOME_RULES
    assert OUTCOME_RULES == ("end-outcome-1", "permission-gate-1")
    ts = (PLUGIN / "mod" / "lib" / "trace.ts").read_text()
    m = re.search(r"export const OUTCOME_RULES = \[([^\]]*)\]", ts)
    assert m, "mod lib/trace.ts exports OUTCOME_RULES"
    assert tuple(re.findall(r"'([^']+)'", m.group(1))) == OUTCOME_RULES


def test_stop_and_subagent_traces_carry_version_and_rule(box):
    from ace_trace_meta import OUTCOME_RULES
    _stop(box, "s-v1")
    sid = "s-v2"
    box.write_state(sid, agent="agent-9", user_prompt="refactor the parser module please now")
    proc = box.run_after_task(box.subagent_event(sid, "agent-9"), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert proc.returncode == 0, proc.stderr
    traces = [c["trace"] for c in box.cli_calls("learn")]
    assert len(traces) == 2
    for t in traces:
        assert t["result"]["plugin_version"] == VERSION and re.fullmatch(r"\d+\.\d+\.\d+", VERSION)
        assert t["result"]["outcome_rule"] == "end-outcome-1" and t["result"]["outcome_rule"] in OUTCOME_RULES
        assert "plugin_version" not in t and "outcome_rule" not in t, "only inside result (the server keeps result)"


def test_permission_denied_trace_carries_the_permission_gate_rule(monkeypatch):
    sys.path.insert(0, str(PLUGIN / "shared-hooks"))
    import ace_permission_denied as P
    importlib.reload(P)
    t = P._build_trace({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}, "session_id": "s"})
    assert t["result"]["outcome_rule"] == "permission-gate-1" and t["result"]["plugin_version"] == VERSION


def test_every_rule_used_by_the_code_is_in_the_list():
    from ace_trace_meta import OUTCOME_RULES
    used = set()
    for f in list((PLUGIN / "shared-hooks").rglob("*.py")) + list((PLUGIN / "mod").rglob("*.ts")):
        if "tests" in f.parts:
            continue
        used |= set(re.findall(r"outcome_rule['\"]?\s*[:=]\s*['\"]([a-z0-9-]+)['\"]", f.read_text()))
        used |= set(re.findall(r"RULE_[A-Z_]+ = ['\"]([a-z0-9-]+)['\"]", f.read_text()))
    assert used and used <= set(OUTCOME_RULES), used - set(OUTCOME_RULES)


# ---------- engine: idempotency key, quota ----------

def test_learn_command_idempotency_key_only_for_the_engine():
    import ace_engine
    lib = ace_engine.learn_command("/t.json", node="/n", idempotency_key="k-1")
    assert lib[lib.index("--idempotency-key") + 1] == "k-1"
    assert "--idempotency-key" not in ace_engine.learn_command("/t.json", idempotency_key="k-1")


@pytest.fixture
def eng(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ACE_FAKE_CORE_LOG", str(tmp_path / "core.log"))
    monkeypatch.setenv("ACE_FAKE_CLI_LOG", str(tmp_path / "cli.log"))
    monkeypatch.delenv("ACE_ENGINE", raising=False)
    monkeypatch.setenv("PATH", E.path_with(E.make_prefix(tmp_path)))
    import plugin_data_dir
    importlib.reload(plugin_data_dir)
    import ace_relevance_logger
    ace_relevance_logger._logger = None
    import ace_engine
    importlib.reload(ace_engine)
    import ace_cli
    return importlib.reload(ace_cli)


@needs_node
def test_engine_sends_the_queue_id_as_idempotency_key(eng, tmp_path):
    out, _ = eng.run_learn({"task": "t", "trajectory": [], "result": {}}, org="o", project="p")
    assert out
    ops = [r for r in E.read_jsonl(tmp_path / "core.log") if r.get("op") == "learn"]
    assert re.fullmatch(r"[0-9a-f]{32}", ops[0]["opts"]["idempotencyKey"])


@needs_node
def test_engine_dead_letter_is_queued_under_the_key_it_sent(eng, tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "deadletter")
    out, _ = eng.run_learn({"task": "t", "trajectory": [], "result": {}}, org="o", project="p", hook_event_name="Stop")
    assert out is None
    import plugin_data_dir
    files = list((plugin_data_dir.data_root() / "trace-queue").glob("*.json"))
    ops = [r for r in E.read_jsonl(tmp_path / "core.log") if r.get("op") == "learn"]
    assert len(files) == 1 and files[0].stem == ops[0]["opts"]["idempotencyKey"]
    assert [c for c in E.read_jsonl(tmp_path / "cli.log") if c["argv"][:1] == ["learn"]] == [], "no CLI re-post"


@needs_node
def test_engine_quota_exceeded_is_not_counted_as_sent(eng, tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "quota")
    out, _ = eng.run_learn({"task": "t", "trajectory": [], "result": {}}, org="o", project="p", hook_event_name="Stop")
    assert out is None
    rows = E.read_jsonl(tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl")
    assert any(r.get("event") == "learn_requeued" and r.get("error_class") == "quota" for r in rows), rows


def test_async_session_start_replays_the_queue(box):
    """The next session: the async SessionStart row (ace_install_cli --update-check) starts the replay."""
    _stop(box, "s-ss", ACE_FAKE_LEARN_RC="1", ACE_FAKE_LEARN_ERR=DEAD_NET)
    f = _qfiles(box)[0]
    e = json.loads(f.read_text())
    e["next_at"] = 0
    f.write_text(json.dumps(e))
    ev = {"session_id": "s-next", "cwd": str(box.project), "hook_event_name": "SessionStart", "source": "startup"}
    p = subprocess.run([sys.executable, str(PLUGIN / "shared-hooks" / "ace_install_cli.py"), "--update-check"],
                       input=json.dumps(ev), capture_output=True, text=True, timeout=60, cwd=str(box.project),
                       env=box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID))
    assert p.returncode == 0, p.stderr
    import time
    for _ in range(100):
        if not _qfiles(box):
            break
        time.sleep(0.1)
    assert _qfiles(box) == [] and len(box.cli_calls("learn")) == 2
    assert _rows(box, "learn_replayed")



def test_session_start_requeues_a_signed_orphan_job_of_a_killed_child(box):
    """Should-fix c: the detached Python learn child died before it read its job file: nothing was sent."""
    sid = "s-orphan"
    sdir = box.session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=True)
    job = {"trace": {"task": "User request: orphan", "trajectory": [], "result": {}}, "retrieval_id": None,
           "applied_log_ids": [], "org": ORG_ID, "project": PROJECT_ID, "hook_event_name": "Stop", "lock": "x",
           "metrics": {"agent_type": "main"}}
    job["sig"] = Q.sign(Q.load_key(box.pd / "trace-queue"), job)
    f = sdir / "learn-job-orphan.json"
    f.write_text(json.dumps(job))
    old = __import__("time").time() - Q.HANDOVER_STALE - 10
    os.utime(str(f), (old, old))
    ev = {"session_id": "s-next2", "cwd": str(box.project), "hook_event_name": "SessionStart", "source": "startup"}
    p = subprocess.run([sys.executable, str(PLUGIN / "shared-hooks" / "ace_install_cli.py"), "--update-check"],
                       input=json.dumps(ev), capture_output=True, text=True, timeout=60, cwd=str(box.project),
                       env=box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID))
    assert p.returncode == 0, p.stderr
    assert not f.exists()
    r = [x for x in _rows(box, "learn_requeued") if x.get("reason") == "child_killed"]
    assert len(r) == 1


def test_the_python_job_file_is_signed(box, monkeypatch):
    """dispatch_learn signs the job (the orphan sweep queues only signed jobs)."""
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(box.pd))
    monkeypatch.delenv("ACE_LEARN_INLINE", raising=False)
    sys.path.insert(0, str(PLUGIN / "shared-hooks"))
    import plugin_data_dir
    importlib.reload(plugin_data_dir)
    import ace_after_task as A
    monkeypatch.setattr(A.subprocess, "Popen", lambda *a, **k: None)  # the child never starts: the job file stays
    job = {"trace": {"task": "t"}, "org": ORG_ID, "project": PROJECT_ID, "hook_event_name": "Stop",
           "lock": str(box.root / "lock"), "metrics": {"agent_type": "main"}}
    A.dispatch_learn(job, "s-sig")
    f = next(box.session_dir("s-sig").glob("learn-job-*.json"))
    j = json.loads(f.read_text())
    assert j["sig"] == Q.sign(Q.load_key(box.pd / "trace-queue"), {k: v for k, v in j.items() if k != "sig"})
