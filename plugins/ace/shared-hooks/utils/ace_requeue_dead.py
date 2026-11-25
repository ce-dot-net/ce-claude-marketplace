#!/usr/bin/env python3
"""Recovery: move dead-letter trace entries (default last_error "auth" or "no_access") back into the trace queue, oldest first.

  python3 ace_requeue_dead.py [--root DIR] [--send] [--limit 5] [--reasons auth,no_access] [--margin-seconds 300]
                              [--no-replay] [--verbose]

Default is a DRY RUN (count and plan only; no key is created). --send re-queues (attempts=1, next_at=now,
last_error "requeued_auth"; the HMAC stays valid because it does not cover those fields; the Idempotency-Key is
the unchanged file id), deletes the dead file only AFTER the queue write succeeded, then runs ONE replay
(ace_trace_queue.py --replay, sends up to PER_RUN entries). Output is numbers only; ids only with --verbose.
"""
import argparse
import math
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ace_trace_queue as Q  # noqa: E402

REQUEUED = "requeued_auth"
DEFAULT_REASONS = "auth,no_access"  # no_access = a 403 that survived FORBIDDEN_MAX_ATTEMPTS (often a transient server project check)
PER_ENTRY_S = 4  # estimate only: seconds per sent entry
_now = time.time


def replay_once(root):
    """One synchronous replay run; a warning text when it must not run, else None."""
    if (os.environ.get("ACE_TRACE_SINK") or "").strip():
        return "ACE_TRACE_SINK is set, nothing is sent (no replay)"
    if not os.path.basename(os.path.normpath(root)).startswith("ace"):
        return "root name does not start with 'ace': replay would use another data dir, skipped"
    subprocess.run([sys.executable, os.path.abspath(Q.__file__), "--replay"],
                   env=dict(os.environ, CLAUDE_PLUGIN_DATA=root), timeout=600)
    return None


def _dir_entries(qdir, sub, key):
    d = os.path.join(qdir, sub) if sub else qdir
    out = {}
    for n in Q._names(d):
        e, _ = Q._load(os.path.join(d, n), n, key)
        out[n[:-5]] = e
    return out


def drive(root, qdir, key, o, reasons, out):
    """Loop: requeue what fits, replay once, pause, wait for backoff; stop on the conditions in the docs."""
    stop = os.path.join(root, "requeue.stop")
    ours, sent, idle = set(), 0, 0
    verbose = o.verbose
    for run in range(1, o.max_runs + 1):
        if os.path.exists(stop):
            out("stop file found: abort")
            return 1
        now = _now()
        st, ok = scan(qdir, key, now, reasons, o.margin_seconds)
        cap = max(0, Q.MAX_FILES - len(Q._queued(qdir)))
        added = 0
        for e in ok[:cap]:
            fail = requeue(qdir, e, now)
            if fail:
                out("requeue failed: %s" % fail)
                return 1
            ours.add(e["id"])
            added += 1
            if verbose:
                out("requeue %s" % e["id"])
        auth_before = {i for i, e in _dir_entries(qdir, "dead", key).items() if e and e.get("last_error") == "auth"}
        if not ok and not Q._queued(qdir):
            out("done: nothing eligible in dead/, queue empty (sent=%d)" % sent)
            return 0
        warn = replay_once(root)
        if warn:
            out("warning: " + warn)
            return 0
        now = _now()
        top = _dir_entries(qdir, "", key)
        dead = _dir_entries(qdir, "dead", key)
        inflight = _dir_entries(qdir, "inflight", key)
        new_auth = {i for i, e in dead.items() if e and e.get("last_error") == "auth"} - auth_before
        sent = sum(1 for i in ours if i not in top and i not in dead and i not in inflight)
        due = sum(1 for e in top.values() if e and e["next_at"] <= now)
        waiting = [e for e in top.values() if e and e["next_at"] > now]
        wait_to = min((e["next_at"] for e in waiting if e["created_at"] + Q.REPLAY_WINDOW > e["next_at"]), default=None)
        out("%s run=%d requeued=%d sent=%d in_queue=%d due=%d in_dead=%d no_access=%d waiting_until=%s"
            % (_utc(now), run, added, sent, len(top) + len(inflight), due, len(dead),
               sum(1 for e in dead.values() if e and e.get("last_error") == "no_access"),
               _utc(wait_to) if wait_to else "-"))
        if new_auth:
            out("abort: %d new dead/auth entries after the run (login lost?)" % len(new_auth))
            return 1
        prev = getattr(drive, "_prev", None)
        drive._prev = sent
        if prev is not None and sent == prev and not waiting:
            idle += 1
        else:
            idle = 0
        if idle >= 3:
            out("abort: 3 runs without progress")
            return 1
        if wait_to is not None:
            oldest = min(e["created_at"] for e in top.values() if e)
            out("waiting: hours to window end of oldest queued=%.2f" % ((oldest + Q.REPLAY_WINDOW - now) / 3600))
            time.sleep(max(0, min(wait_to - now, o.max_wait_seconds)))
        else:
            time.sleep(o.pause_seconds)
    out("stopped: --max-runs reached")
    return 1


def estimate(ok, now, pause, out):
    n = len(ok)
    runs = math.ceil(n / Q.PER_RUN)
    dur = n * PER_ENTRY_S + runs * pause
    msg = "ESTIMATE (assumes %ds per entry): runs=%d duration~%ds" % (PER_ENTRY_S, runs, dur)
    if ok:
        end = ok[0]["created_at"] + Q.REPLAY_WINDOW
        msg += " finish~%s oldest window end=%s %s" % (_utc(now + dur), _utc(end), "OK" if now + dur <= end else "TOO SLOW")
    out(msg)


def _utc(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scan(qdir, key, now, reasons, margin):
    """(stats Counter, eligible entries oldest first). Only HMAC-valid entries are ever eligible."""
    dead = os.path.join(qdir, "dead")
    st, ok = Counter(), []
    for n in Q._names(dead):
        p = os.path.join(dead, n)
        if os.path.islink(p) or not os.path.isfile(p):
            st["invalid"] += 1
            continue
        e, why = Q._load(p, n, key)
        st["dead"] += 1
        if e is None:
            st[why] += 1
            continue
        st["reason:%s" % e.get("last_error")] += 1
        if e.get("last_error") not in reasons:
            continue
        if now - e["created_at"] > Q.REPLAY_WINDOW - margin:
            st["expired"] += 1
            continue
        ok.append(e)
    ok.sort(key=lambda e: e["created_at"])
    return st, ok


def requeue(qdir, e, now):
    """Queue write first, dead file removed only after it succeeded. Returns None or the failure reason."""
    new = {k: v for k, v in e.items() if k not in ("id", "key")}
    new.update(attempts=1, next_at=now, last_error=REQUEUED)
    why = Q._put(qdir, e["id"], new)
    if why:
        return why
    try:
        os.unlink(os.path.join(qdir, "dead", e["id"] + ".json"))
    except OSError:
        return "dead_unlink_failed"
    return None


def main(argv=None, now=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--root")
    a.add_argument("--send", action="store_true")
    a.add_argument("--limit", type=int, default=5)
    a.add_argument("--reasons", default=DEFAULT_REASONS)
    a.add_argument("--margin-seconds", type=int, default=300)
    a.add_argument("--no-replay", action="store_true")
    a.add_argument("--verbose", action="store_true")
    a.add_argument("--drive", action="store_true", help="with --send: loop requeue+replay until done")
    a.add_argument("--pause-seconds", type=float, default=3)
    a.add_argument("--max-wait-seconds", type=float, default=900)
    a.add_argument("--max-runs", type=int, default=100)
    o = a.parse_args(argv)
    now = time.time() if now is None else now
    if o.root:
        root = o.root
    else:
        import plugin_data_dir
        root = os.environ.get("CLAUDE_PLUGIN_DATA") or str(plugin_data_dir.data_root())
    qdir = os.path.join(root, "trace-queue")
    reasons = {r for r in o.reasons.split(",") if r}
    out = lambda s: print(s)  # noqa: E731

    if o.send:
        key = Q.load_key(qdir)
    else:  # dry run: never create a key
        key = None
        if os.path.exists(Q._key_path(qdir)):
            key = Q.load_key(qdir)
        else:
            out("queue.key missing: cannot verify entries (dry run does not create one)")
    st, ok = scan(qdir, key, now, reasons, o.margin_seconds)
    cap = max(0, Q.MAX_FILES - len(Q._queued(qdir)))
    n = min(len(ok), cap) if o.limit == 0 else min(len(ok), cap, o.limit)
    chosen = ok[:n]
    out("dead=%d invalid=%d unsigned=%d expired=%d eligible=%d capacity=%d selected=%d"
        % (st["dead"], st["invalid"], st["unsigned"], st["expired"], len(ok), cap, len(chosen)))
    out("dead by last_error: " + (", ".join("%s=%d" % (k[7:], v) for k, v in sorted(st.items()) if k.startswith("reason:")) or "-"))
    if ok:
        out("oldest=%s newest=%s hours_to_window_end_of_oldest=%.2f"
            % (_utc(ok[0]["created_at"]), _utc(ok[-1]["created_at"]),
               (ok[0]["created_at"] + Q.REPLAY_WINDOW - now) / 3600))
    if o.verbose:
        for e in chosen:
            out("select %s" % e["id"])
    if o.drive:
        estimate(ok, now, o.pause_seconds, out)
    if not o.send:
        out("dry run: nothing changed (use --send)")
        return 0
    if key is None:
        out("no usable key: abort")
        return 1

    if o.drive:
        drive._prev = None
        return drive(root, qdir, key, o, reasons, out)
    done, fail = [], None
    for e in chosen:
        fail = requeue(qdir, e, now)
        if fail:
            break
        done.append(e["id"])
    out("requeued=%d%s" % (len(done), " failed=%s" % fail if fail else ""))
    if fail or not done or o.no_replay:
        return 1 if fail else 0
    if (os.environ.get("ACE_TRACE_SINK") or "").strip():
        out("warning: ACE_TRACE_SINK is set, nothing is sent (no replay)")
        return 0
    if not os.path.basename(os.path.normpath(root)).startswith("ace"):
        out("warning: root name does not start with 'ace': replay would use another data dir, skipped")
        return 0
    subprocess.run([sys.executable, os.path.abspath(Q.__file__), "--replay"],
                   env=dict(os.environ, CLAUDE_PLUGIN_DATA=root), timeout=600)
    queued = {os.path.basename(p)[:-5] for p in Q._queued(qdir)}
    dead = set(n[:-5] for n in Q._names(os.path.join(qdir, "dead")))
    cnt = Counter()
    for n in Q._names(os.path.join(qdir, "dead")):
        e, _ = Q._load(os.path.join(qdir, "dead", n), n, key)
        cnt[e.get("last_error") if e else "unreadable"] += 1
    out("after replay: sent=%d still_queued=%d back_in_dead=%d"
        % (sum(1 for i in done if i not in queued and i not in dead),
           sum(1 for i in done if i in queued), sum(1 for i in done if i in dead)))
    out("dead by last_error now: " + (", ".join("%s=%d" % kv for kv in sorted(cnt.items())) or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
