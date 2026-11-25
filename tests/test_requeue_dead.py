"""ace_requeue_dead.py: re-queue dead-letter 'auth' traces, oldest first. Hermetic: temp queues only."""
import hashlib
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

U = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "shared-hooks" / "utils"
sys.path.insert(0, str(U))
import ace_trace_queue as Q  # noqa: E402
import ace_requeue_dead as R  # noqa: E402

NOW = 1_800_000_000.0
H = 3600
META = {"org": "o", "project": "p", "retrieval_id": "r", "hook": "Stop", "agent_type": "main"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("ACE_TRACE_SINK", raising=False)
    root = tmp_path / "ace-data"
    qdir = root / "trace-queue"
    (qdir / "dead").mkdir(parents=True)
    return root, str(qdir), Q.load_key(str(qdir))


def mk(qdir, key, age_h, reason="auth", sub="dead", bad_hmac=False):
    i = uuid.uuid4().hex
    e = {"v": 1, "created_at": NOW - age_h * H, "next_at": NOW - age_h * H, "attempts": 2, "last_error": reason,
         "key_gen": 0, "answered": False, "meta": META, "trace": {"task": "x"}}
    e["hmac"] = "0" * 64 if bad_hmac else Q.sign(key, Q._signed_part(i, e))
    d = os.path.join(qdir, sub) if sub else qdir
    Q._write(os.path.join(d, i + ".json"), Q._dump(e))
    return i


def run(root, *args):
    return R.main(["--root", str(root)] + list(args), now=NOW)


def tree(root):
    h = hashlib.sha256()
    for dp, dn, fn in sorted(os.walk(root)):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h.update(p.encode() + open(p, "rb").read() + str(os.stat(p).st_mtime_ns).encode())
        h.update(dp.encode())
    return h.hexdigest()


def test_dry_run_changes_nothing(env, capsys):
    root, q, key = env
    for a in (1, 2, 3):
        mk(q, key, a)
    before = tree(root)
    assert run(root) == 0
    assert tree(root) == before
    assert "selected=3" in capsys.readouterr().out


def test_dry_run_creates_no_key(tmp_path, capsys):
    root = tmp_path / "ace-x"
    (root / "trace-queue" / "dead").mkdir(parents=True)
    run(root)
    assert not (root / "queue.key").exists()
    assert "queue.key missing" in capsys.readouterr().out


def test_send_limit_oldest_first(env):
    root, q, key = env
    ids = {a: mk(q, key, a) for a in (1, 5, 3, 9)}
    run(root, "--send", "--limit", "2", "--no-replay")
    for a in (9, 5):
        e, why = Q._load(os.path.join(q, ids[a] + ".json"), ids[a] + ".json", key)
        assert e and e["attempts"] == 1 and e["next_at"] <= NOW and e["last_error"] == "requeued_auth"
        assert e["key"] == ids[a]  # idempotency key unchanged
        assert not os.path.exists(os.path.join(q, "dead", ids[a] + ".json"))
    for a in (1, 3):
        assert os.path.exists(os.path.join(q, "dead", ids[a] + ".json"))
        assert not os.path.exists(os.path.join(q, ids[a] + ".json"))


def test_other_reasons_untouched(env):
    root, q, key = env
    a, b = mk(q, key, 1, "invalid"), mk(q, key, 1, "4xx")
    run(root, "--send", "--limit", "0", "--no-replay")
    for i in (a, b):
        assert os.path.exists(os.path.join(q, "dead", i + ".json"))


def test_expired_skipped_and_counted(env, capsys):
    root, q, key = env
    old = mk(q, key, 22.99)   # < 300 s margin left
    fresh = mk(q, key, 1)
    run(root, "--send", "--limit", "0", "--no-replay")
    assert os.path.exists(os.path.join(q, "dead", old + ".json"))
    assert os.path.exists(os.path.join(q, fresh + ".json"))
    assert "expired=1" in capsys.readouterr().out


def test_tampered_stays(env, capsys):
    root, q, key = env
    bad = mk(q, key, 1, bad_hmac=True)
    run(root, "--send", "--limit", "0", "--no-replay")
    assert os.path.exists(os.path.join(q, "dead", bad + ".json"))
    assert "unsigned=1" in capsys.readouterr().out


def test_capacity(env, monkeypatch):
    root, q, key = env
    monkeypatch.setattr(Q, "MAX_FILES", 3)
    mk(q, key, 1, "x", sub="")
    mk(q, key, 1, "x", sub="")
    ids = [mk(q, key, a) for a in (1, 2, 3)]
    run(root, "--send", "--limit", "0", "--no-replay")
    assert sum(os.path.exists(os.path.join(q, i + ".json")) for i in ids) == 1


def test_put_failure_keeps_dead(env, monkeypatch):
    root, q, key = env
    i = mk(q, key, 1)
    monkeypatch.setattr(Q, "_put", lambda *a: "queue_full")
    assert run(root, "--send", "--no-replay") == 1
    assert os.path.exists(os.path.join(q, "dead", i + ".json"))


def test_idempotent(env, capsys):
    root, q, key = env
    mk(q, key, 1)
    run(root, "--send", "--limit", "0", "--no-replay")
    capsys.readouterr()
    run(root, "--send", "--limit", "0", "--no-replay")
    assert "eligible=0" in capsys.readouterr().out


def test_sink_blocks_replay(env, monkeypatch):
    root, q, key = env
    mk(q, key, 1)
    monkeypatch.setenv("ACE_TRACE_SINK", "/tmp/x")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("replay started"))
    run(root, "--send")


def test_replay_call(env, monkeypatch):
    root, q, key = env
    mk(q, key, 1)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: calls.append((argv, k)))
    run(root, "--send")
    argv, k = calls[0]
    assert argv[0] == sys.executable and argv[-1] == "--replay" and argv[1].endswith("ace_trace_queue.py")
    assert k["env"]["CLAUDE_PLUGIN_DATA"] == str(root) and k["timeout"] == 600


def test_no_ids_without_verbose(env, capsys, monkeypatch):
    root, q, key = env
    [mk(q, key, a) for a in (1, 2)]
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    run(root, "--send")
    out = capsys.readouterr().out
    assert not re.search(r"[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-", out)
    mk(q, key, 1)
    run(root, "--verbose")
    assert re.search(r"select [0-9a-f]{32}", capsys.readouterr().out)


# ---------- --drive ----------

@pytest.fixture
def drv(env, monkeypatch):
    root, q, key = env
    clock = [NOW]
    sleeps = []
    monkeypatch.setattr(R, "_now", lambda: clock[0])
    monkeypatch.setattr(R.time, "sleep", lambda s: (sleeps.append(s), clock.__setitem__(0, clock[0] + s)))
    state = {"runs": 0}

    def install(behavior):
        def fake(argv, **k):
            state["runs"] += 1
            files = sorted((e["next_at"], p) for p in Q._queued(q)
                           for e in [Q._read_raw(p)] if e and e["next_at"] <= clock[0])
            behavior(files[:Q.PER_RUN], state)
        monkeypatch.setattr(subprocess, "run", fake)
    return root, q, key, clock, sleeps, state, install


def remove(files, st):
    for _, p in files:
        os.unlink(p)


def drive(root, *a):
    return run(root, "--send", "--drive", "--limit", "0", *a)


def dead_count(q):
    return len(Q._names(os.path.join(q, "dead")))


def test_drive_sends_all(drv, capsys):
    root, q, key, clock, sleeps, st, install = drv
    for a in range(1, 13):
        mk(q, key, a)
    install(remove)
    assert drive(root) == 0
    assert st["runs"] == 3 and dead_count(q) == 0 and not Q._queued(q)
    assert "sent=12" in capsys.readouterr().out


def test_drive_capacity_pulls_rest(drv, monkeypatch, capsys):
    root, q, key, clock, sleeps, st, install = drv
    monkeypatch.setattr(Q, "MAX_FILES", 4)
    for a in range(1, 11):
        mk(q, key, a)
    seen = []
    install(lambda f, s: (seen.append(len(Q._queued(q))), remove(f, s)))
    assert drive(root) == 0
    assert max(seen) <= 4 and dead_count(q) == 0
    assert "sent=10" in capsys.readouterr().out


def test_drive_waits_retry_after(drv):
    root, q, key, clock, sleeps, st, install = drv
    mk(q, key, 1)

    def b(files, s):
        for _, p in files:
            if s["runs"] == 1:
                e = Q._read_raw(p)
                e["next_at"] = clock[0] + 2
                Q._write(p, Q._dump(e))
            else:
                os.unlink(p)
    install(b)
    assert drive(root, "--pause-seconds", "0") == 0
    assert st["runs"] == 2 and any(abs(x - 2) < 1e-6 for x in sleeps)


def test_drive_max_wait_caps(drv):
    root, q, key, clock, sleeps, st, install = drv
    mk(q, key, 1)

    def b(files, s):
        for _, p in files:
            if s["runs"] == 1:
                e = Q._read_raw(p)
                e["next_at"] = clock[0] + 5000
                Q._write(p, Q._dump(e))
            else:
                os.unlink(p)
    install(b)
    drive(root, "--max-wait-seconds", "100")
    assert max(sleeps) == 100


def test_drive_new_auth_aborts(drv, capsys):
    root, q, key, clock, sleeps, st, install = drv
    for a in (1, 2, 3):
        mk(q, key, a)

    def b(files, s):
        for _, p in files:  # login gone: the entry goes back to dead/ as auth
            e = Q._read_raw(p)
            e["last_error"] = "auth"
            Q._write(os.path.join(q, "dead", os.path.basename(p)), Q._dump(e))
            os.unlink(p)
    install(b)
    assert drive(root) == 1
    assert st["runs"] == 1
    assert "new dead/auth" in capsys.readouterr().out


def test_drive_stop_file(drv):
    root, q, key, clock, sleeps, st, install = drv
    mk(q, key, 1)
    (root / "requeue.stop").write_text("")
    install(remove)
    assert drive(root) == 1 and st["runs"] == 0


def test_drive_no_progress(drv, capsys):
    root, q, key, clock, sleeps, st, install = drv
    mk(q, key, 1)
    install(lambda f, s: None)
    assert drive(root) == 1
    assert st["runs"] == 4 and "without progress" in capsys.readouterr().out  # 1st sets the baseline, then 3 idle


def test_drive_max_runs(drv):
    root, q, key, clock, sleeps, st, install = drv
    for a in range(1, 12):
        mk(q, key, a)
    install(remove)
    assert drive(root, "--max-runs", "2") == 1 and st["runs"] == 2


def test_drive_dry_run_estimate_only(env, monkeypatch, capsys):
    root, q, key = env
    for a in (1, 2, 3, 4, 5, 6):
        mk(q, key, a)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("replay"))
    before = tree(root)
    assert run(root, "--drive") == 0
    assert tree(root) == before
    out = capsys.readouterr().out
    assert "ESTIMATE" in out and "runs=2" in out and "OK" in out


def test_drive_output_no_ids(drv, capsys):
    root, q, key, clock, sleeps, st, install = drv
    for a in range(1, 8):
        mk(q, key, a)
    install(remove)
    drive(root)
    assert not re.search(r"[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-", capsys.readouterr().out)


# ---------- 8.4.0: no_access (a transient 403) ----------

def test_default_reasons_are_auth_and_no_access(env):
    root, q, key = env
    a, b, c = mk(q, key, 1, "auth"), mk(q, key, 1, "no_access"), mk(q, key, 1, "4xx")
    assert R.DEFAULT_REASONS == "auth,no_access"
    run(root, "--send", "--limit", "0", "--no-replay")
    for i in (a, b):
        assert os.path.exists(os.path.join(q, i + ".json")) and not os.path.exists(os.path.join(q, "dead", i + ".json"))
    assert os.path.exists(os.path.join(q, "dead", c + ".json"))


def test_explicit_reasons_still_narrow(env):
    root, q, key = env
    b = mk(q, key, 1, "no_access")
    run(root, "--send", "--limit", "0", "--no-replay", "--reasons", "auth")
    assert os.path.exists(os.path.join(q, "dead", b + ".json"))


def test_drive_new_no_access_does_not_abort_and_is_counted(drv, capsys):
    root, q, key, clock, sleeps, st, install = drv
    for a in (1, 2):
        mk(q, key, a)

    def b(files, s):
        for n, (_, p) in enumerate(files):  # the project check timed out: one entry goes dead as no_access, the other is sent
            if n == 0:
                e = Q._read_raw(p)
                e["last_error"] = "no_access"
                Q._write(os.path.join(q, "dead", os.path.basename(p)), Q._dump(e))
            os.unlink(p)
    install(b)
    drive(root, "--max-runs", "1")
    out = capsys.readouterr().out
    assert "new dead/auth" not in out
    assert "no_access=1" in out
