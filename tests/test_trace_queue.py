"""8.1.4 trace delivery: the durable retry queue (shared-hooks/utils/ace_trace_queue.py, DESIGN "Trace delivery").

One Python module serves BOTH chains (the Python hooks call it in-process, the mod's detached learn child imports it),
so the behaviour is identical by construction. Covered here: classification, caps, age, backoff, claim lock,
symlink refusal, atomic private writes, never replay on 4xx, ACE_TRACE_QUEUE=0.
"""
import json
import os
import stat
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "ace" / "shared-hooks" / "utils"))
import ace_trace_queue as Q  # noqa: E402

T0 = 1_800_000_000.0
META = {"org": "org_t", "project": "prj_t", "retrieval_id": "rid-1", "applied_log_ids": [1, 2], "hook": "Stop",
        "agent_type": "main"}
DEAD_502 = '{"event":"ace_trace_dead_letter","attempts":4,"status":502,"error":"Server error (502)","timestamp":"x"}\nServer error (502): '
DEAD_NET = '{"event":"ace_trace_dead_letter","attempts":4,"error":"fetch failed","timestamp":"x"}\nfetch failed'


def trace(n=1):
    return {"task": "t%d" % n, "trajectory": [], "result": {"success": True}, "playbook_used": [], "timestamp": "x"}


@pytest.fixture
def qdir(tmp_path, monkeypatch):
    monkeypatch.delenv("ACE_TRACE_QUEUE", raising=False)
    return tmp_path / "data" / "trace-queue"


def entries(qdir):
    return sorted(p.name for p in qdir.glob("*.json")) if qdir.is_dir() else []


# ---------- classification ----------

@pytest.mark.parametrize("code,out,action,cls", [
    (0, '{"success": true}', "ok", None),
    (1, DEAD_502, "requeue", "gateway_5xx"),
    (1, DEAD_502.replace("502", "503"), "requeue", "gateway_5xx"),
    (1, DEAD_NET, "requeue", "network"),
    (1, "Error: connect ECONNREFUSED 127.0.0.1:9", "requeue", "network"),
    (1, '{"level":"error","message":"Failed to read transcript file"}', "requeue", "not_sent"),
    (None, "cli_not_found", "requeue", "not_sent"),
    (1, "Server error (400): bad trace", "dead", "4xx"),
    (1, "Server error (422): x", "dead", "4xx"),
    (1, "Unauthorized: token_expired", "dead", "auth"),
    (5, "ace_trace_quota_exceeded", "dead", "quota"),
    (1, "Server error (500): boom", "lost", "server_5xx"),
    (None, "timeout", "lost", "timeout"),
    (1, "something odd", "lost", "unknown"),
])
def test_classify(code, out, action, cls):
    assert Q.classify(code, out) == (action, cls)


# ---------- settle: the original send ----------

def test_settle_ok_writes_nothing(qdir):
    assert Q.settle(qdir, "q1", trace(), META, 0, "{}", now=T0) == []
    assert entries(qdir) == []


def test_settle_gateway_failure_requeues_the_exact_body_privately(qdir):
    t = trace()
    rows = Q.settle(qdir, "q1", t, META, 1, DEAD_502, now=T0)
    assert rows == [{"event": "learn_requeued", "reason": "send_failed", "error_class": "gateway_5xx", "attempts": 1,
                     "trace_id": "q1", "agent_type": "main", "hook": "Stop", "project_id": "prj_t"}]
    e = json.loads((qdir / "q1.json").read_text())
    assert e["trace"] == t and e["meta"] == META and e["attempts"] == 1 and e["next_at"] == T0 + 60
    assert stat.S_IMODE(qdir.stat().st_mode) == 0o700
    assert stat.S_IMODE((qdir / "q1.json").stat().st_mode) == 0o600
    assert not [p for p in qdir.iterdir() if p.name.startswith(".")], "no temp file left (atomic temp+rename)"


def test_settle_4xx_goes_to_dead_and_is_logged_lost(qdir):
    rows = Q.settle(qdir, "q1", trace(), META, 1, "Server error (400): bad", now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "rejected" and rows[0]["error_class"] == "4xx"
    assert entries(qdir) == [] and (qdir / "dead" / "q1.json").exists()


def test_settle_timeout_is_lost_never_queued(qdir):
    rows = Q.settle(qdir, "q1", trace(), META, None, "timeout", now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "timeout"
    assert not qdir.exists() or not any(qdir.rglob("*.json"))


def test_queue_disabled_logs_lost_only(qdir, monkeypatch):
    monkeypatch.setenv("ACE_TRACE_QUEUE", "0")
    rows = Q.settle(qdir, "q1", trace(), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "queue_disabled"
    assert not qdir.exists() or not any(qdir.rglob("*.json"))
    assert Q.replay(qdir, lambda e: pytest.fail("replayed while disabled"), now=T0 + 99999) == []


# ---------- caps and age ----------

def test_cap_200_files(qdir):
    for i in range(Q.MAX_FILES):
        Q.settle(qdir, "q%03d" % i, trace(i), META, 1, DEAD_502, now=T0)
    rows = Q.settle(qdir, "over", trace(), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "queue_full"
    assert len(entries(qdir)) == Q.MAX_FILES


def test_cap_5mb_per_file(qdir):
    big = dict(trace(), blob="x" * (Q.MAX_FILE + 1))
    rows = Q.settle(qdir, "big", big, META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "too_large"
    assert entries(qdir) == []


def test_cap_50mb_total(qdir, monkeypatch):
    monkeypatch.setattr(Q, "MAX_TOTAL", 3000)
    for i in range(10):
        Q.settle(qdir, "q%d" % i, dict(trace(), pad="y" * 900), META, 1, DEAD_502, now=T0)
    assert 1 <= len(entries(qdir)) < 10
    assert sum(p.stat().st_size for p in qdir.glob("*.json")) <= 3000


def test_entries_older_than_7_days_expire_logged(qdir):
    Q.settle(qdir, "old", trace(), META, 1, DEAD_502, now=T0)
    rows = Q.replay(qdir, lambda e: pytest.fail("expired entry sent"), now=T0 + Q.MAX_AGE + 1)
    assert [r["event"] for r in rows] == ["learn_expired"] and rows[0]["trace_id"] == "old"
    assert entries(qdir) == []


def test_dead_entries_are_kept_7_days_then_pruned(qdir):
    Q.settle(qdir, "d", trace(), META, 1, "Server error (400): x", now=T0)
    dead = qdir / "dead" / "d.json"
    Q.replay(qdir, lambda e: (0, "{}"), now=T0 + 3600)
    assert dead.exists()
    os.utime(str(dead), (T0, T0))
    Q.replay(qdir, lambda e: (0, "{}"), now=T0 + Q.MAX_AGE + 1)
    assert not dead.exists()


# ---------- replay: order, limit, backoff, give up, 4xx ----------

def test_replay_oldest_first_at_most_5_and_only_due(qdir):
    for i in range(7):
        Q.settle(qdir, "q%d" % i, trace(i), META, 1, DEAD_502, now=T0 + i)
    sent = []
    assert Q.replay(qdir, lambda e: (sent.append(e["id"]), (0, "{}"))[1], now=T0 + 30) == []  # not due (1 min)
    rows = Q.replay(qdir, lambda e: (sent.append(e["id"]), (0, "{}"))[1], now=T0 + 120)
    assert sent == ["q0", "q1", "q2", "q3", "q4"]
    assert [r["event"] for r in rows] == ["learn_replayed"] * 5 and rows[0]["attempts"] == 2
    assert entries(qdir) == ["q5.json", "q6.json"]


def test_replay_passes_trace_meta_and_stable_id(qdir):
    t = trace()
    Q.settle(qdir, "qid-1", t, META, 1, DEAD_502, now=T0)
    got = []
    Q.replay(qdir, lambda e: (got.append(e), (0, "{}"))[1], now=T0 + 61)
    assert got[0]["id"] == "qid-1" and got[0]["trace"] == t and got[0]["meta"] == META


def test_backoff_schedule_and_give_up_after_6_attempts(qdir):
    Q.settle(qdir, "q", trace(), META, 1, DEAD_502, now=T0)
    now, waits = T0, []
    for _ in range(5):
        e = json.loads((qdir / "q.json").read_text())
        waits.append(e["next_at"] - now)
        now = e["next_at"]
        rows = Q.replay(qdir, lambda e: (1, DEAD_502), now=now)
    assert waits == [60, 300, 1800, 7200, 43200]
    assert rows[-1]["event"] == "learn_lost" and rows[-1]["reason"] == "gave_up" and rows[-1]["attempts"] == 6
    assert entries(qdir) == [] and (qdir / "dead" / "q.json").exists()


def test_replay_never_retries_after_4xx(qdir):
    Q.settle(qdir, "q", trace(), META, 1, DEAD_502, now=T0)
    calls = []
    rows = Q.replay(qdir, lambda e: (calls.append(1), (1, "Server error (400): bad"))[1], now=T0 + 61)
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "4xx"
    Q.replay(qdir, lambda e: (calls.append(1), (0, "{}"))[1], now=T0 + 86400)
    assert calls == [1] and (qdir / "dead" / "q.json").exists()


def test_replay_timeout_is_not_replayed_again(qdir):
    Q.settle(qdir, "q", trace(), META, 1, DEAD_502, now=T0)
    rows = Q.replay(qdir, lambda e: (None, "timeout"), now=T0 + 61)
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "timeout"
    assert entries(qdir) == []


def test_two_concurrent_replays_never_send_the_same_entry(qdir):
    for i in range(5):
        Q.settle(qdir, "q%d" % i, trace(i), META, 1, DEAD_502, now=T0)
    sent, gate = [], threading.Barrier(2)

    def send(e):
        sent.append(e["id"])
        return 0, "{}"

    def run():
        gate.wait()
        Q.replay(qdir, send, now=T0 + 61)

    ts = [threading.Thread(target=run) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(sent) == ["q%d" % i for i in range(5)]


def test_a_stale_claim_of_a_crashed_replayer_is_taken_back(qdir):
    Q.settle(qdir, "q", trace(), META, 1, DEAD_502, now=T0)
    (qdir / "inflight").mkdir(mode=0o700)
    os.rename(str(qdir / "q.json"), str(qdir / "inflight" / "q.json"))
    os.utime(str(qdir / "inflight" / "q.json"), (T0, T0))
    sent = []
    Q.replay(qdir, lambda e: (sent.append(e["id"]), (0, "{}"))[1], now=T0 + Q.CLAIM_STALE + 61)
    assert sent == ["q"]


# ---------- security ----------

def test_symlinked_queue_dir_is_refused(qdir, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    qdir.parent.mkdir(parents=True)
    os.symlink(str(target), str(qdir))
    rows = Q.settle(qdir, "q", trace(), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "unsafe_dir"
    assert list(target.iterdir()) == []


def test_symlinked_entry_is_never_read(qdir, tmp_path):
    Q.settle(qdir, "q", trace(), META, 1, DEAD_502, now=T0)
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"id": "x", "created_at": T0, "next_at": T0, "attempts": 1, "meta": META, "trace": {"stolen": 1}}))
    os.symlink(str(secret), str(qdir / "evil.json"))
    sent = []
    Q.replay(qdir, lambda e: (sent.append(e["id"]), (0, "{}"))[1], now=T0 + 61)
    assert sent == ["q"]
    assert secret.exists()


def test_stats(qdir):
    Q.settle(qdir, "a", trace(), META, 1, DEAD_502, now=T0)
    Q.settle(qdir, "b", trace(), META, 1, DEAD_502, now=T0 + 100)
    Q.settle(qdir, "c", trace(), META, 1, "Server error (400): x", now=T0)
    s = Q.stats(qdir, now=T0 + 400)
    assert s == {"depth": 2, "oldest_age_s": 400, "dead": 1}


def test_rows_never_carry_trace_content(qdir):
    t = dict(trace(), task="SECRET-TASK-TEXT")
    rows = Q.settle(qdir, "q", t, META, 1, DEAD_502, now=T0)
    rows += Q.replay(qdir, lambda e: (0, "{}"), now=T0 + 61)
    assert "SECRET-TASK-TEXT" not in json.dumps(rows)


def test_doctor_line_matches_the_mod_format(tmp_path):
    """Same data and line as mod/tests/policy.test.ts 'doctor: delivery queue ...'."""
    T = 1_800_000_000
    q = tmp_path / "trace-queue"
    (q / "dead").mkdir(parents=True)
    for i, age in (("a", 7200), ("b", 60)):
        (q / ("%s.json" % i)).write_text(json.dumps({"v": 1, "id": i, "created_at": T - age, "next_at": T, "attempts": 1, "meta": {}, "trace": {}}))
    (q / "dead" / "c.json").write_text(json.dumps({"id": "c", "trace": {}}))
    logs = tmp_path / "logs"
    logs.mkdir()
    import datetime as dt
    iso = lambda a: dt.datetime.fromtimestamp(T - a, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    (logs / "ace-relevance.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (
        {"event": "learn_replayed", "timestamp": iso(100)}, {"event": "learn_replayed", "timestamp": iso(8 * 86400)},
        {"event": "learn_expired", "timestamp": iso(100)})))
    assert Q.doctor_line(q, logs, now=T) == "delivery queue 2 · oldest 2h · 7d replayed 1 · dead 1 · expired 1"


def test_ace_doctor_md_shows_the_delivery_and_policy_lines():
    md = (Path(__file__).resolve().parent.parent / "plugins" / "ace" / "commands" / "ace-doctor.md").read_text()
    assert "ace_trace_queue" in md and "doctor_line" in md
    assert "client_policy_line" in md
