"""8.1.4 trace delivery: the durable retry queue (shared-hooks/utils/ace_trace_queue.py, ARCHITECTURE "Trace delivery").

One Python module serves BOTH chains (the Python hooks call it in-process, the mod's detached learn child imports it),
so the behaviour is identical by construction. Covered here: classification (structured codes only), the keyed/unkeyed
policy, caps, the 24 h replay window, backoff, claim lock, symlink refusal, atomic private writes, never replay on 4xx,
ACE_TRACE_QUEUE=0, and (review must-fix 1) hostile or broken queue files: the id comes only from the file name, every
entry is schema-checked and HMAC-signed with a per-install key, a bad file goes to dead/ and never blocks the others.
Limits are pinned with literal values so that a change by a factor of 10 fails.
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
DEAD_502 = '{"event":"ace_trace_dead_letter","attempts":4,"status":502,"error":"Server error (502)","timestamp":"x"}\n{"error":{"code":"server_error","status":502,"message":"Server error (502): "}}'
DEAD_504 = DEAD_502.replace("502", "504")
DEAD_NET = '{"event":"ace_trace_dead_letter","attempts":4,"error":"fetch failed","timestamp":"x"}\nfetch failed'
HOUR = 3600


def qid(n=1):
    return "%032x" % n


def trace(n=1):
    return {"task": "t%d" % n, "trajectory": [], "result": {"success": True}, "playbook_used": [], "timestamp": "x"}


@pytest.fixture
def qdir(tmp_path, monkeypatch):
    monkeypatch.delenv("ACE_TRACE_QUEUE", raising=False)
    return tmp_path / "data" / "trace-queue"


def entries(qdir):
    return sorted(p.name for p in qdir.glob("*.json")) if qdir.is_dir() else []


def dead(qdir):
    d = qdir / "dead"
    return sorted(p.name for p in d.glob("*.json")) if d.is_dir() else []


def queue(qdir, n, now=T0, t=None):
    rows = Q.settle(qdir, qid(n), t or trace(n), META, 1, DEAD_502, now=now)
    assert rows[0]["event"] == "learn_requeued", rows
    return qdir / (qid(n) + ".json")


def ok_send(log):
    return lambda e: (log.append(e["id"]), (0, "{}"))[1]


# ---------- classification ----------

@pytest.mark.parametrize("code,out,keyed,action,cls", [
    (0, '{"success": true}', True, "ok", None),
    (1, DEAD_502, True, "requeue", "gateway_5xx"),
    (1, DEAD_502.replace("502", "503"), True, "requeue", "gateway_5xx"),
    (1, DEAD_504, True, "requeue", "server_5xx"),            # keyed: a committed 504 replays as a duplicate answer
    (1, DEAD_504, False, "lost", "server_5xx"),              # ace-cli: no stable key
    (1, DEAD_502, False, "lost", "server_5xx"),              # ace-cli: random key, the server cannot merge a replay
    (1, DEAD_NET, True, "requeue", "network"),
    (1, DEAD_NET, False, "requeue", "network"),
    (1, "Error: connect ECONNREFUSED 127.0.0.1:9", False, "requeue", "network"),
    (1, '{"level":"error","message":"Failed to read transcript file"}', False, "requeue", "not_sent"),
    (None, "cli_not_found", False, "requeue", "not_sent"),
    (1, '{"error":{"code":"generic","status":400,"message":"Server error (400): bad"}}', True, "dead", "4xx"),
    (1, "Server error (422): x", True, "dead", "invalid"),
    (3, '{"error":{"code":"not_logged_in","status":null,"message":"Not logged in"}}', False, "dead", "auth"),
    (4, '{"error":{"code":"token_expired","status":401,"message":"expired"}}', False, "dead", "auth"),
    (3, "", False, "dead", "auth"),                          # ace-cli exit 3 = not_logged_in
    (4, "", False, "dead", "auth"),                          # ace-cli exit 4 = token_expired
    (1, '{"error":{"code":"no_access","status":403,"message":"x"}}', False, "dead", "auth"),
    (5, "ace_trace_quota_exceeded", True, "requeue", "quota"),
    (1, '{"error":{"code":"server_error","status":500,"message":"Server error (500): boom"}}', True, "requeue", "server_5xx"),
    (1, '{"error":{"code":"server_error","status":500,"message":"Server error (500): boom"}}', False, "lost", "server_5xx"),
    (None, "timeout", True, "requeue", "timeout"),
    (None, "timeout", False, "lost", "timeout"),
    (1, "took 4013ms request-id 401abc 403def unauthorized-looking text", True, "lost", "unknown"),  # no substring auth
    (1, "something odd", True, "lost", "unknown"),
])
def test_classify(code, out, keyed, action, cls):
    assert Q.classify(code, out, keyed=keyed) == (action, cls)


# ---------- settle: the original send ----------

def test_settle_ok_writes_nothing(qdir):
    assert Q.settle(qdir, qid(), trace(), META, 0, "{}", now=T0) == []
    assert entries(qdir) == []


def test_settle_gateway_failure_requeues_the_exact_body_signed_and_private(qdir):
    t = trace()
    rows = Q.settle(qdir, qid(), t, META, 1, DEAD_502, now=T0)
    assert rows == [{"event": "learn_requeued", "reason": "send_failed", "error_class": "gateway_5xx", "attempts": 1,
                     "trace_id": qid(), "agent_type": "main", "hook": "Stop", "project_id": "prj_t"}]
    e = json.loads((qdir / (qid() + ".json")).read_text())
    assert e["trace"] == t and e["meta"] == META and e["attempts"] == 1 and e["next_at"] == T0 + 60
    assert "id" not in e, "the id is the file name, never content"
    assert len(e["hmac"]) == 64
    key = qdir.parent / "queue.key"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600 and len(key.read_text().strip()) == 64
    assert stat.S_IMODE(qdir.stat().st_mode) == 0o700
    assert stat.S_IMODE((qdir / (qid() + ".json")).stat().st_mode) == 0o600
    assert not [p for p in qdir.iterdir() if p.name.startswith(".")], "no temp file left (atomic temp+rename)"


def test_settle_refuses_an_id_that_is_not_a_queue_id(qdir):
    rows = Q.settle(qdir, "../../../ESCAPED", trace(), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "bad_id"
    rows = Q.settle(qdir, "../../../ESCAPED", trace(), META, 1, "Server error (400): x", now=T0)
    assert rows[0]["event"] == "learn_lost"
    assert not list(qdir.parent.parent.rglob("ESCAPED*"))


def test_mod_uuid_ids_are_queue_ids_too(qdir):
    u = "0b7e6c1a-2f3d-4e5f-8a9b-0c1d2e3f4a5b"
    assert Q.settle(qdir, u, trace(), META, 1, DEAD_502, now=T0)[0]["event"] == "learn_requeued"


def test_settle_4xx_goes_to_dead_and_is_logged_lost(qdir):
    rows = Q.settle(qdir, qid(), trace(), META, 1, "Server error (400): bad", now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "rejected" and rows[0]["error_class"] == "4xx"
    assert entries(qdir) == [] and dead(qdir) == [qid() + ".json"]


def test_settle_auth_goes_to_dead_as_never_sent(qdir):
    rows = Q.settle(qdir, qid(), trace(), META, 3, '{"error":{"code":"not_logged_in","status":null,"message":"x"}}', now=T0, keyed=False)
    assert rows[0]["error_class"] == "auth" and rows[0]["reason"] == "rejected"
    assert dead(qdir) == [qid() + ".json"]


def test_settle_unkeyed_timeout_is_lost_never_queued(qdir):
    rows = Q.settle(qdir, qid(), trace(), META, None, "timeout", now=T0, keyed=False)
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "timeout"
    assert not qdir.exists() or not any(qdir.rglob("*.json"))


def test_settle_unkeyed_502_is_lost(qdir):
    rows = Q.settle(qdir, qid(), trace(), META, 8, DEAD_502, now=T0, keyed=False)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "maybe_sent"
    assert entries(qdir) == []


def test_queue_disabled_logs_lost_only(qdir, monkeypatch):
    monkeypatch.setenv("ACE_TRACE_QUEUE", "0")
    rows = Q.settle(qdir, qid(), trace(), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "queue_disabled"
    assert not qdir.exists() or not any(qdir.rglob("*.json"))
    assert Q.replay(qdir, lambda e: pytest.fail("replayed while disabled"), now=T0 + 99999) == []


# ---------- pinned limits (a change by a factor of 10 fails) ----------

def test_cap_200_files(qdir):
    for i in range(200):
        queue(qdir, i + 1)
    rows = Q.settle(qdir, qid(999), trace(), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "queue_full"
    assert len(entries(qdir)) == 200


def test_cap_20_files_would_fail_this(qdir):
    for i in range(21):
        queue(qdir, i + 1)  # 21 < 200: all queued (a cap of 20 fails here)
    assert len(entries(qdir)) == 21


def test_cap_5mb_per_file(qdir):
    mb = 1024 * 1024
    assert Q.settle(qdir, qid(1), dict(trace(), blob="x" * int(4.9 * mb)), META, 1, DEAD_502, now=T0)[0]["event"] == "learn_requeued"
    rows = Q.settle(qdir, qid(2), dict(trace(), blob="x" * int(5.1 * mb)), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "too_large"
    assert entries(qdir) == [qid(1) + ".json"]


def test_cap_50mb_total(qdir):
    blob = "y" * int(4.9 * 1024 * 1024)
    rows = [Q.settle(qdir, qid(i + 1), dict(trace(i), blob=blob), META, 1, DEAD_502, now=T0)[0] for i in range(11)]
    assert [r["event"] for r in rows] == ["learn_requeued"] * 10 + ["learn_lost"]
    assert rows[-1]["reason"] == "queue_full"
    assert sum(p.stat().st_size for p in qdir.glob("*.json")) <= 50 * 1024 * 1024


def test_replay_window_is_23_hours_from_the_first_send(qdir):
    queue(qdir, 1, now=T0)
    queue(qdir, 2, now=T0 + 2 * HOUR)
    sent = []
    rows = Q.replay(qdir, ok_send(sent), now=T0 + 23 * HOUR + 60)  # #1 is 23 h 1 min old: expired; #2 21 h: sent
    assert sent == [qid(2)]
    assert [r["event"] for r in rows] == ["learn_expired", "learn_replayed"] and rows[0]["trace_id"] == qid(1)
    assert entries(qdir) == []


def test_dead_entries_are_kept_7_days_then_pruned(qdir):
    Q.settle(qdir, qid(), trace(), META, 1, "Server error (400): x", now=T0)
    Q.replay(qdir, lambda e: (0, "{}"), now=T0 + 6 * 86400)
    assert dead(qdir) == [qid() + ".json"]
    Q.replay(qdir, lambda e: (0, "{}"), now=T0 + 7 * 86400 + 1)
    assert dead(qdir) == []


def test_backoff_schedule_and_give_up_after_6_attempts(qdir):
    queue(qdir, 1)
    f = qdir / (qid(1) + ".json")
    now, waits, rows = T0, [], []
    for _ in range(5):
        e = json.loads(f.read_text())
        waits.append(e["next_at"] - now)
        now = e["next_at"]
        rows = Q.replay(qdir, lambda e: (1, DEAD_502), now=now)
    assert waits == [60, 300, 1800, 7200, 43200]
    assert rows[-1]["event"] == "learn_lost" and rows[-1]["reason"] == "gave_up" and rows[-1]["attempts"] == 6
    assert entries(qdir) == [] and dead(qdir) == [qid(1) + ".json"]


# ---------- replay: order, limit, 4xx, lock ----------

def test_replay_oldest_first_at_most_5_and_only_due(qdir):
    for i in range(7):
        queue(qdir, i + 1, now=T0 + i)
    sent = []
    assert Q.replay(qdir, ok_send(sent), now=T0 + 30) == []  # not due (1 min)
    rows = Q.replay(qdir, ok_send(sent), now=T0 + 120)
    assert sent == [qid(i + 1) for i in range(5)]
    assert [r["event"] for r in rows] == ["learn_replayed"] * 5 and rows[0]["attempts"] == 2
    assert entries(qdir) == [qid(6) + ".json", qid(7) + ".json"]


def test_replay_passes_trace_meta_and_the_file_name_id(qdir):
    t = trace()
    queue(qdir, 1, t=t)
    got = []
    Q.replay(qdir, lambda e: (got.append(e), (0, "{}"))[1], now=T0 + 61)
    assert got[0]["id"] == qid(1) and got[0]["trace"] == t and got[0]["meta"] == META


def test_replay_never_retries_after_4xx(qdir):
    queue(qdir, 1)
    calls = []
    rows = Q.replay(qdir, lambda e: (calls.append(1), (1, "Server error (400): bad"))[1], now=T0 + 61)
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "4xx"
    Q.replay(qdir, lambda e: (calls.append(1), (0, "{}"))[1], now=T0 + 3 * HOUR)
    assert calls == [1] and dead(qdir) == [qid(1) + ".json"]


def test_replay_unkeyed_timeout_is_not_replayed_again(qdir):
    queue(qdir, 1)
    rows = Q.replay(qdir, lambda e: (None, "timeout", False), now=T0 + 61)
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "timeout"
    assert entries(qdir) == []


def test_an_unkeyed_replay_502_is_lost_not_retried(qdir):
    queue(qdir, 1)
    rows = Q.replay(qdir, lambda e: (8, DEAD_502, False), now=T0 + 61)
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "server_5xx"
    assert entries(qdir) == []


def test_two_concurrent_replays_never_send_the_same_entry(qdir):
    for i in range(5):
        queue(qdir, i + 1)
    sent, gate = [], threading.Barrier(2)

    def run():
        gate.wait()
        Q.replay(qdir, ok_send(sent), now=T0 + 61)

    ts = [threading.Thread(target=run) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(sent) == [qid(i + 1) for i in range(5)]


def test_a_stale_claim_of_a_crashed_replayer_is_taken_back_with_its_attempt_counted(qdir):
    queue(qdir, 1)

    def crash(e):
        raise KeyboardInterrupt  # the replayer dies mid-send (SIGKILL-like)

    with pytest.raises(KeyboardInterrupt):
        Q.replay(qdir, crash, now=T0 + 61)
    claimed = qdir / "inflight" / ("%s.%d.json" % (qid(1), T0 + 61))
    assert json.loads(claimed.read_text())["attempts"] == 2, "attempts rose BEFORE the send"
    sent = []
    rows = Q.replay(qdir, ok_send(sent), now=T0 + 61 + Q.CLAIM_STALE + 1)
    assert sent == [qid(1)] and rows[-1]["attempts"] == 3


def test_a_crash_loop_ends_in_dead_after_6_attempts(qdir):
    queue(qdir, 1)
    now = T0 + 61
    for _ in range(10):
        try:
            Q.replay(qdir, lambda e: (_ for _ in ()).throw(KeyboardInterrupt()), now=now)
        except KeyboardInterrupt:
            pass
        now += Q.CLAIM_STALE + 1  # the crashed claim comes back; its next_at has passed
    assert entries(qdir) == [] and not list((qdir / "inflight").glob("*.json")) and dead(qdir) == [qid(1) + ".json"]


# ---------- hostile or broken files (review must-fix 1) ----------

def _plant(qdir, name, obj, sign=True):
    """A file in the queue dir; sign=True signs it with the real key over (file-name id, content) as the plugin would."""
    qdir.mkdir(parents=True, exist_ok=True)
    if sign and isinstance(obj, dict) and isinstance(obj.get("meta"), dict) and isinstance(obj.get("trace"), dict):
        stem = name[:-5]
        obj = dict(obj, hmac=Q.sign(Q.load_key(qdir), {"id": stem, "created_at": obj.get("created_at"),
                                                       "meta": obj["meta"], "trace": obj["trace"]}))
    (qdir / name).write_text(json.dumps(obj) if not isinstance(obj, str) else obj)


GOOD = {"v": 1, "created_at": T0, "next_at": T0, "attempts": 1, "last_error": "network", "meta": META, "trace": trace()}


@pytest.mark.parametrize("name,obj,cls", [
    (qid(9) + ".json", dict(GOOD, next_at="abc"), "invalid"),
    (qid(9) + ".json", dict(GOOD, created_at="abc"), "invalid"),
    (qid(9) + ".json", dict(GOOD, attempts="many"), "invalid"),
    (qid(9) + ".json", dict(GOOD, attempts=True), "invalid"),
    (qid(9) + ".json", dict(GOOD, meta=["x"]), "invalid"),
    (qid(9) + ".json", dict(GOOD, meta=dict(META, project=5)), "invalid"),
    (qid(9) + ".json", dict(GOOD, meta=dict(META, applied_log_ids=["1"])), "invalid"),
    (qid(9) + ".json", dict(GOOD, meta=dict(META, extra="x")), "invalid"),
    (qid(9) + ".json", dict(GOOD, trace="not a dict"), "invalid"),
    (qid(9) + ".json", "{not json", "invalid"),
    (qid(9) + ".json", [1, 2], "invalid"),
    ("../../../ESCAPED.json", GOOD, "invalid"),
    ("ESCAPED.json", GOOD, "invalid"),
    (qid(9) + ".json", {"task": "FORGED"}, "invalid"),
    (qid(9) + ".json", dict(GOOD, id="../../../ESCAPED"), "invalid"),
])
def test_a_broken_file_goes_to_dead_and_never_blocks_the_others(qdir, name, obj, cls):
    queue(qdir, 1)
    queue(qdir, 2)
    if name.startswith(".."):
        name = "x" + qid(9)[:8] + ".json"  # a name cannot hold a path separator; any non-id name is the same case
    _plant(qdir, name, obj, sign=False)
    sent = []
    rows = Q.replay(qdir, ok_send(sent), now=T0 + 61)
    assert sent == [qid(1), qid(2)], "the good entries still go out"
    bad = [r for r in rows if r["event"] == "learn_lost"]
    assert len(bad) == 1 and bad[0]["error_class"] in (cls, "unsigned")
    assert entries(qdir) == [] and len(dead(qdir)) == 1
    assert not list(qdir.parent.parent.rglob("ESCAPED*")), "nothing written outside the queue"
    assert all("/" not in n and n.endswith(".json") for n in dead(qdir))
    Q.replay(qdir, ok_send(sent), now=T0 + 10 * HOUR)
    assert sent == [qid(1), qid(2)], "no loop"


def test_a_forged_well_formed_file_without_a_valid_hmac_is_never_sent(qdir):
    queue(qdir, 1)
    _plant(qdir, qid(9) + ".json", dict(GOOD, trace={"task": "FORGED"}, hmac="0" * 64), sign=False)
    sent = []
    rows = Q.replay(qdir, lambda e: (sent.append(e["trace"]), (0, "{}"))[1], now=T0 + 61)
    assert {"task": "FORGED"} not in sent and len(sent) == 1
    assert [r["error_class"] for r in rows if r["event"] == "learn_lost"] == ["unsigned"]
    assert dead(qdir) == [qid(9) + ".json"]


def test_a_signed_file_renamed_to_another_id_is_unsigned(qdir):
    f = queue(qdir, 1)
    os.rename(str(f), str(qdir / (qid(7) + ".json")))
    sent = []
    Q.replay(qdir, ok_send(sent), now=T0 + 61)
    assert sent == [] and dead(qdir) == [qid(7) + ".json"]


def test_a_tampered_trace_is_unsigned(qdir):
    f = queue(qdir, 1)
    e = json.loads(f.read_text())
    e["trace"]["task"] = "TAMPERED"
    f.write_text(json.dumps(e))
    sent = []
    Q.replay(qdir, ok_send(sent), now=T0 + 61)
    assert sent == [] and dead(qdir) == [qid(1) + ".json"]


def test_the_key_is_created_once_atomically_and_never_overwritten(qdir):
    k1 = Q.load_key(qdir)
    k2 = Q.load_key(qdir)
    assert k1 == k2 and len(k1) == 32
    key = qdir.parent / "queue.key"
    key.write_text("garbage")
    assert Q.load_key(qdir) is None, "a broken key is refused, never replaced silently"
    assert Q.settle(qdir, qid(), trace(), META, 1, DEAD_502, now=T0)[0]["reason"] == "no_key"


def test_a_symlinked_key_is_refused(qdir, tmp_path):
    qdir.parent.mkdir(parents=True)
    other = tmp_path / "attacker.key"
    other.write_text("a" * 64)
    os.symlink(str(other), str(qdir.parent / "queue.key"))
    assert Q.load_key(qdir) is None


def test_the_key_never_reaches_a_row_or_an_entry(qdir):
    rows = Q.settle(qdir, qid(), trace(), META, 1, DEAD_502, now=T0)
    rows += Q.replay(qdir, lambda e: (0, "{}"), now=T0 + 61)
    k = (qdir.parent / "queue.key").read_text().strip()
    assert k not in json.dumps(rows)
    for p in qdir.rglob("*.json"):
        assert k not in p.read_text()


# ---------- security ----------

def test_symlinked_queue_dir_is_refused(qdir, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    qdir.parent.mkdir(parents=True)
    os.symlink(str(target), str(qdir))
    rows = Q.settle(qdir, qid(), trace(), META, 1, DEAD_502, now=T0)
    assert rows[0]["event"] == "learn_lost" and rows[0]["reason"] == "unsafe_dir"
    assert list(target.iterdir()) == []


def test_symlinked_entry_is_never_read(qdir, tmp_path):
    queue(qdir, 1)
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps(GOOD))
    os.symlink(str(secret), str(qdir / (qid(5) + ".json")))
    sent = []
    Q.replay(qdir, ok_send(sent), now=T0 + 61)
    assert sent == [qid(1)]
    assert secret.exists()


def test_stats(qdir):
    queue(qdir, 1, now=T0)
    queue(qdir, 2, now=T0 + 100)
    Q.settle(qdir, qid(3), trace(), META, 1, "Server error (400): x", now=T0)
    assert Q.stats(qdir, now=T0 + 400) == {"depth": 2, "oldest_age_s": 400, "dead": 1}


def test_rows_never_carry_trace_content(qdir):
    t = dict(trace(), task="SECRET-TASK-TEXT")
    rows = Q.settle(qdir, qid(), t, META, 1, DEAD_502, now=T0)
    rows += Q.replay(qdir, lambda e: (0, "{}"), now=T0 + 61)
    assert "SECRET-TASK-TEXT" not in json.dumps(rows)


# ---------- orphans of a killed learn child (review should-fix c) ----------

def _old(p, now):
    os.utime(str(p), (now - Q.HANDOVER_STALE - 1, now - Q.HANDOVER_STALE - 1))


def test_sweep_requeues_a_signed_job_file_and_logs_a_killed_child(tmp_path):
    root = tmp_path / "data"
    sdir = root / "projects" / "prj_t" / "sessions" / "s1"
    sdir.mkdir(parents=True)
    now = T0
    job = {"trace": trace(), "retrieval_id": "rid-1", "applied_log_ids": [1], "org": "org_t", "project": "prj_t",
           "hook_event_name": "Stop", "lock": "x", "metrics": {"agent_type": "main"}}
    job["sig"] = Q.sign(Q.load_key(root / "trace-queue"), job)
    good = sdir / "learn-job-aa.json"
    good.write_text(json.dumps(job))
    unsigned = sdir / "learn-job-bb.json"
    unsigned.write_text(json.dumps(dict(job, sig="0" * 64)))
    (root / "tmp").mkdir()
    owned = root / "tmp" / ("ace-trace-%s.json.owned" % "0b7e6c1a-2f3d-4e5f-8a9b-0c1d2e3f4a5b")
    owned.write_text("{}")
    fresh = root / "tmp" / "ace-trace-fresh.json"
    fresh.write_text("{}")
    for p in (good, unsigned, owned):
        _old(p, now)
    os.utime(str(fresh), (now, now))
    rows = Q.sweep_orphans(root, now=now)
    ev = sorted((r["event"], r.get("reason")) for r in rows)
    assert ev == [("learn_lost", "child_killed"), ("learn_lost", "child_killed"), ("learn_requeued", "child_killed")]
    assert len(list((root / "trace-queue").glob("*.json"))) == 1
    assert not good.exists() and not unsigned.exists() and not owned.exists() and fresh.exists()


# ---------- doctor ----------

def test_doctor_line_matches_the_mod_format(tmp_path):
    """Same data and line as mod/tests/policy.test.ts 'doctor: delivery queue ...'."""
    T = 1_800_000_000
    q = tmp_path / "trace-queue"
    (q / "dead").mkdir(parents=True)
    for i, age in ((qid(1), 7200), (qid(2), 60)):
        (q / ("%s.json" % i)).write_text(json.dumps({"v": 1, "created_at": T - age, "next_at": T, "attempts": 1, "meta": {}, "trace": {}}))
    (q / "dead" / (qid(3) + ".json")).write_text(json.dumps({"trace": {}}))
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


# ---------- the server's answer (engine: ace_trace_response line; stored/duplicate, never message) ----------

def R(status, **kw):
    return Q.RESPONSE_TAG + json.dumps(dict(status=status, **kw))


@pytest.mark.parametrize("out,answered,action,cls", [
    (R(200, stored=True), False, "ok", None),
    (R(202, stored=True), False, "ok", None),
    (R(200, stored=True, message="anything at all"), False, "ok", None),
    (R(200, stored=False, message="Trace stored."), False, "requeue", "not_stored"),   # never trust message
    (R(200, stored=True, duplicate=True, message="duplicate in progress"), True, "requeue", "in_progress"),
    (R(200, stored=True, duplicate=True, message="Trace stored."), False, "requeue", "in_progress"),  # after an unclear try
    (R(200, stored=True, duplicate=True, message="Trace stored."), True, "ok", None),
    (R(429, retry_after="120"), False, "requeue", "quota"),
    (R(401), False, "dead", "auth"),
    (R(422), False, "dead", "invalid"),
    (R(400), False, "dead", "4xx"),
    (R(503, error_code="PG_STATEMENT_TIMEOUT", retry_after="30"), False, "requeue", "pg_timeout"),
    (R(503), False, "requeue", "gateway_5xx"),
    (R(502), False, "requeue", "gateway_5xx"),
    (R(504), False, "requeue", "server_5xx"),
    (R(500), False, "requeue", "server_5xx"),
    (R(None, network=True), False, "requeue", "network"),
])
def test_classify_engine_response(out, answered, action, cls):
    assert Q.classify(6, out, keyed=True, answered=answered) == (action, cls)


def test_waits_quota_in_progress_retry_after(qdir):
    assert Q.settle(qdir, qid(1), trace(), META, 5, R(429, retry_after="900"), now=T0)[0]["error_class"] == "quota"
    assert json.loads((qdir / (qid(1) + ".json")).read_text())["next_at"] == T0 + 900
    Q.settle(qdir, qid(2), trace(), META, 5, R(429), now=T0)
    assert json.loads((qdir / (qid(2) + ".json")).read_text())["next_at"] == T0 + 12 * HOUR
    Q.settle(qdir, qid(3), trace(), META, 6, R(200, stored=True, duplicate=True, message="duplicate in progress"), now=T0)
    assert json.loads((qdir / (qid(3) + ".json")).read_text())["next_at"] == T0 + 75 * 60
    Q.settle(qdir, qid(4), trace(), META, 1, R(503, error_code="PG_STATEMENT_TIMEOUT", retry_after="600"), now=T0)
    assert json.loads((qdir / (qid(4) + ".json")).read_text())["next_at"] == T0 + 600


def test_a_wait_beyond_the_window_expires(qdir):
    rows = Q.settle(qdir, qid(1), trace(), META, 5, R(429, retry_after=str(24 * HOUR)), now=T0)
    assert rows[0]["event"] == "learn_expired" and entries(qdir) == []


def test_stored_false_replays_with_a_new_key_at_most_3_times(qdir):
    Q.settle(qdir, qid(1), trace(), META, 6, R(200, stored=False), now=T0)
    keys, now = [], T0
    for _ in range(4):
        now += 3 * HOUR
        Q.replay(qdir, lambda e: (keys.append(e["key"]), (6, R(200, stored=False)))[1], now=now)
    assert keys == [qid(1) + "-r1", qid(1) + "-r2", qid(1) + "-r3"]
    assert dead(qdir) == [qid(1) + ".json"]


def test_in_progress_then_duplicate_deletes_only_after_a_real_answer(qdir):
    Q.settle(qdir, qid(1), trace(), META, None, "timeout", now=T0)   # unclear first try (keyed)
    now = T0 + 61
    rows = Q.replay(qdir, lambda e: (6, R(200, stored=True, duplicate=True, message="Trace stored.")), now=now)
    assert rows[-1]["event"] == "learn_requeued" and rows[-1]["error_class"] == "in_progress"
    e = json.loads((qdir / (qid(1) + ".json")).read_text())
    assert e["answered"] is True and e["next_at"] >= now + 75 * 60
    rows = Q.replay(qdir, lambda e: (6, R(200, stored=True, duplicate=True, message="Trace stored.")), now=e["next_at"])
    assert rows[-1]["event"] == "learn_replayed" and entries(qdir) == []


# ---------- the `stored` field (server fix: stored:null while the first send runs) ----------

STORED_CASES = json.loads((Path(__file__).resolve().parent.parent / "plugins" / "ace" / "tests-fixtures" / "trace-delivery"
                           / "stored_cases.json").read_text())


def _engine_line(c):
    """What engine/learn.js writes for an answer: `stored` only when the key is present (null when not a boolean)."""
    b = c["body"]
    r = {"status": c["status"], "duplicate": b.get("duplicate") is True, "message": b.get("message")}
    if "stored" in b:
        r["stored"] = b["stored"] if isinstance(b["stored"], bool) else None
    return Q.RESPONSE_TAG + json.dumps(r)


@pytest.mark.parametrize("c", STORED_CASES, ids=[c["name"] for c in STORED_CASES])
def test_stored_field_cases(c):
    assert Q.classify(c["engine_exit"], _engine_line(c)) == (c["action"], c["cls"])


def test_in_progress_waits_75_min_and_is_not_a_failed_attempt(qdir):
    Q.settle(qdir, qid(1), trace(), META, 1, DEAD_NET, now=T0)
    now = T0 + 61
    for _ in range(8):  # more than MAX_ATTEMPTS waits: never given up for it
        rows = Q.replay(qdir, lambda e: (6, _engine_line({"status": 200, "body": {"stored": None}})), now=now)
        e = json.loads((qdir / (qid(1) + ".json")).read_text())
        assert rows[-1]["error_class"] == "in_progress" and e["next_at"] == now + 75 * 60 and e["attempts"] == 1
        now = e["next_at"]
    assert dead(qdir) == []


def test_a_fresh_claim_is_never_taken_back_even_when_the_entry_file_is_old(qdir):
    """rename() keeps the entry's old mtime: the claim time must come from the claim, or a second replayer's stale
    sweep could take a live claim back and send it twice."""
    f = queue(qdir, 1, now=T0)
    old = T0 - 10 * HOUR
    os.utime(str(f), (old, old))
    seen = []

    def send(e):
        seen.append(Q.replay(qdir, lambda e2: pytest.fail("sent twice"), now=T0 + 120))  # a second replayer, mid-send
        return 0, "{}"

    Q.replay(qdir, send, now=T0 + 120)
    assert seen == [[]] and entries(qdir) == []
