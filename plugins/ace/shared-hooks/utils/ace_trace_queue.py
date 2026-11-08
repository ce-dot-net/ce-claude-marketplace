#!/usr/bin/env python3
"""8.1.4 trace delivery (DESIGN "Trace delivery"): the durable retry queue for learn traces, ONE module for both chains.

The Python hooks call settle() after ace_cli.run_learn; the mod's detached learn child imports this file too, so a
failed send is handled the same way whichever chain built the trace. Stdlib only.

<data root>/trace-queue/<id>.json   {"v", "id", "created_at", "next_at", "attempts", "last_error", "meta", "trace"}
<data root>/trace-queue/inflight/   an entry being replayed (claimed by an atomic rename: two replayers never share one)
<data root>/trace-queue/dead/       given up or rejected (4xx); kept 7 days for debugging, never replayed

`trace` is the body the learn would have sent (built and redacted by the chain); `id` is the Idempotency-Key the
engine sends on the first POST and on every replay. Rows (the caller adds timestamp/source) never carry trace content.
`python3 ace_trace_queue.py --replay [--cwd DIR]`: one bounded replay run (async SessionStart, after a good learn).
`python3 -I ace_trace_queue.py --enqueue FILE JOB`: the mod launcher's parent queues a trace no child got.
"""
import json
import os
import stat
import sys
import time
import uuid

MAX_FILES = 200
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
MAX_AGE = 7 * 86400
BACKOFF = (60, 300, 1800, 7200, 43200)  # after failed attempt 1..5
MAX_ATTEMPTS = 6
PER_RUN = 5
CLAIM_STALE = 900  # a replayer sends at most 5 x 60 s; an older claim is a crashed one
REPLAY_TIMEOUT = 60

# Requeue only what provably never reached the trace store: the gateway answered 502/503/504 after the SDK's own
# 4 attempts (dead letter), the connection failed, or nothing was sent at all. A 500, a timeout or anything unknown
# may have been stored: never replayed (learn_lost). 4xx/auth/quota: rejected, to dead/, never replayed.
_REQUEUE = {"gateway_5xx", "network", "not_sent"}
_DEAD = {"4xx", "auth", "quota"}
_NET = ("econnrefused", "enotfound", "eai_again", "econnreset", "ehostunreach", "enetunreach", "fetch failed",
        "socket hang up", "network error")


def enabled():
    return os.environ.get("ACE_TRACE_QUEUE", "1") != "0"


def classify(code, output):
    """(action, error_class): action is ok | requeue | dead | lost."""
    text = str(output or "")
    low = text.lower()
    if "ace_trace_quota_exceeded" in text:
        return "dead", "quota"
    if code == 0:
        return "ok", None
    for line in text.splitlines():
        if "ace_trace_dead_letter" in line:
            try:
                st = json.loads(line[line.index("{"):]).get("status")
            except (ValueError, AttributeError):
                st = None
            if st is None:
                return "requeue", "network"
            if st in (502, 503, 504):
                return "requeue", "gateway_5xx"
            return ("dead", "4xx") if 400 <= st < 500 else ("lost", "server_5xx")
    if "failed to read transcript" in low or low.strip() == "cli_not_found" or low.startswith("nothing sent"):
        return "requeue", "not_sent"
    import re
    m = re.search(r"server error \((\d{3})\)", low)
    if m:
        st = int(m.group(1))
        if 400 <= st < 500:
            return "dead", "4xx"
        return ("requeue", "gateway_5xx") if st in (502, 503, 504) else ("lost", "server_5xx")
    if any(x in low for x in ("unauthorized", "not logged in", "no api token", "token_expired", "401", "403")):
        return "dead", "auth"
    if code is None and "timeout" in low:
        return "lost", "timeout"
    if any(x in low for x in _NET):
        return "requeue", "network"
    if "timeout" in low or "timed out" in low:
        return "lost", "timeout"
    return "lost", "unknown"


def _row(event, entry_id, meta, attempts, cls=None, reason=None):
    meta = meta or {}
    r = {"event": event}
    if reason:
        r["reason"] = reason
    if cls:
        r["error_class"] = cls
    r.update(attempts=attempts, trace_id=entry_id, agent_type=meta.get("agent_type") or "main",
             hook=meta.get("hook"), project_id=meta.get("project"))
    return r


def _safe_dir(path):
    """mkdir 0700 and refuse a symlink anywhere we write; True when usable."""
    try:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            return False
    except FileNotFoundError:
        try:
            os.makedirs(path, mode=0o700, exist_ok=True)
        except OSError:
            return False
        if os.path.islink(path):
            return False
    except OSError:
        return False
    try:
        os.chmod(path, 0o700)
    except OSError:
        return False
    return True


def _write(path, text):
    """Atomic private write: O_EXCL|O_NOFOLLOW temp file (0600) + rename. Raises on failure."""
    d = os.path.dirname(path)
    tmp = os.path.join(d, ".w-%s.tmp" % uuid.uuid4().hex)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read(path):
    """An entry dict, never through a symlink; None when unusable."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, "r") as f:
            fd = None
            e = json.load(f)
        return e if isinstance(e, dict) and isinstance(e.get("trace"), dict) else None
    except (OSError, ValueError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def _queued(qdir):
    out = []
    for sub in ("", "inflight"):
        d = os.path.join(qdir, sub)
        try:
            for n in os.listdir(d):
                p = os.path.join(d, n)
                if n.endswith(".json") and not os.path.islink(p) and os.path.isfile(p):
                    out.append(p)
        except OSError:
            pass
    return out


def _put(qdir, entry, now):
    """Write an entry to the queue under the caps; the reason it was not written, or None."""
    if not _safe_dir(str(qdir)):
        return "unsafe_dir"
    text = json.dumps(entry, default=str)
    size = len(text.encode("utf-8"))
    if size > MAX_FILE:
        return "too_large"
    have = [p for p in _queued(str(qdir)) if os.path.basename(p) != entry["id"] + ".json"]
    if len(have) >= MAX_FILES:
        return "queue_full"
    total = 0
    for p in have:
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    if total + size > MAX_TOTAL:
        return "queue_full"
    try:
        _write(os.path.join(str(qdir), entry["id"] + ".json"), text)
    except OSError:
        return "write_failed"
    return None


def _to_dead(qdir, entry, now):
    entry["dead_at"] = now
    d = os.path.join(str(qdir), "dead")
    if _safe_dir(str(qdir)) and _safe_dir(d):
        try:
            _write(os.path.join(d, entry["id"] + ".json"), json.dumps(entry, default=str))
        except (OSError, ValueError):
            pass


def settle(qdir, entry_id, trace, meta, code, output, now=None, on=None):
    """After the ORIGINAL send of a built trace: rows to log (the trace is queued, sent to dead/, or lost)."""
    now = time.time() if now is None else now
    action, cls = classify(code, output)
    if action == "ok":
        return []
    if not (enabled() if on is None else on):
        return [_row("learn_lost", entry_id, meta, 1, cls, "queue_disabled")]
    entry = {"v": 1, "id": entry_id, "created_at": now, "next_at": now + BACKOFF[0], "attempts": 1,
             "last_error": cls, "meta": meta or {}, "trace": trace}
    if action == "dead":
        _to_dead(qdir, entry, now)
        return [_row("learn_lost", entry_id, meta, 1, cls, "rejected")]
    if action == "lost":
        return [_row("learn_lost", entry_id, meta, 1, cls, "maybe_sent")]
    why = _put(qdir, entry, now)
    if why:
        return [_row("learn_lost", entry_id, meta, 1, cls, why)]
    return [_row("learn_requeued", entry_id, meta, 1, cls, "send_failed")]


def _prune(qdir, now):
    rows = []
    infl = os.path.join(str(qdir), "inflight")
    try:
        for n in os.listdir(infl):
            p = os.path.join(infl, n)
            try:
                if n.endswith(".json") and not os.path.islink(p) and now - os.path.getmtime(p) > CLAIM_STALE:
                    os.rename(p, os.path.join(str(qdir), n))  # a crashed replayer's claim
            except OSError:
                pass
    except OSError:
        pass
    dead = os.path.join(str(qdir), "dead")
    try:
        for n in os.listdir(dead):
            p = os.path.join(dead, n)
            try:
                e = _read(p) if not os.path.islink(p) else None
                if now - float((e or {}).get("dead_at") or os.lstat(p).st_mtime) > MAX_AGE:
                    os.unlink(p)
            except OSError:
                pass
    except OSError:
        pass
    for p in _queued(str(qdir)):
        if os.path.dirname(p) != str(qdir).rstrip(os.sep):
            continue
        e = _read(p)
        if e is None:
            continue
        if now - float(e.get("created_at") or 0) > MAX_AGE:
            try:
                os.unlink(p)
                rows.append(_row("learn_expired", e.get("id"), e.get("meta"), e.get("attempts") or 0, e.get("last_error"), "max_age"))
            except OSError:
                pass
    return rows


def replay(qdir, send, now=None, limit=PER_RUN):
    """Send due entries oldest first, at most `limit`; send(entry) -> (exit_code_or_None, output). Rows to log."""
    if not enabled():
        return []
    qdir = str(qdir)
    if not os.path.isdir(qdir) or os.path.islink(qdir):
        return []
    now = time.time() if now is None else now
    rows = _prune(qdir, now)
    due = []
    for p in _queued(qdir):
        if os.path.dirname(p) != qdir.rstrip(os.sep):
            continue
        e = _read(p)
        if e and float(e.get("next_at") or 0) <= now:
            due.append((float(e.get("created_at") or 0), os.path.basename(p)))
    if not due or not _safe_dir(os.path.join(qdir, "inflight")):
        return rows
    n = 0
    for _, name in sorted(due):
        if n >= limit:
            break
        src, claimed = os.path.join(qdir, name), os.path.join(qdir, "inflight", name)
        try:
            os.rename(src, claimed)  # the claim: whoever renames it owns it
        except OSError:
            continue
        os.utime(claimed, None)
        e = _read(claimed)
        if e is None:
            continue
        n += 1
        try:
            code, out = send(e)
        except Exception as ex:  # a broken sender must not lose the entry
            code, out = 1, "cli_not_found" if isinstance(ex, FileNotFoundError) else "unknown: %s" % ex
        att = int(e.get("attempts") or 1) + 1
        action, cls = classify(code, out)
        e.update(attempts=att, last_error=cls)
        if action == "ok":
            rows.append(_row("learn_replayed", e["id"], e.get("meta"), att))
        elif action == "requeue" and att < MAX_ATTEMPTS:
            e["next_at"] = now + BACKOFF[min(att, len(BACKOFF)) - 1]
            try:
                _write(os.path.join(qdir, name), json.dumps(e, default=str))
                rows.append(_row("learn_requeued", e["id"], e.get("meta"), att, cls, "replay_failed"))
            except OSError:
                rows.append(_row("learn_lost", e["id"], e.get("meta"), att, cls, "write_failed"))
        elif action == "lost":
            rows.append(_row("learn_lost", e["id"], e.get("meta"), att, cls, "maybe_sent"))
        else:
            _to_dead(qdir, e, now)
            rows.append(_row("learn_lost", e["id"], e.get("meta"), att, cls, "rejected" if action == "dead" else "gave_up"))
        try:
            os.unlink(claimed)
        except OSError:
            pass
    return rows


def stats(qdir, now=None):
    """{"depth", "oldest_age_s", "dead"} for /ace:ace-doctor."""
    now = time.time() if now is None else now
    qdir = str(qdir)
    ages = []
    for p in _queued(qdir):
        e = _read(p)
        if e:
            ages.append(now - float(e.get("created_at") or now))
    try:
        dead = len([n for n in os.listdir(os.path.join(qdir, "dead")) if n.endswith(".json")])
    except OSError:
        dead = 0
    return {"depth": len(ages), "oldest_age_s": int(max(ages)) if ages else 0, "dead": dead}


def _age(s):
    return "%dm" % (s // 60) if s < 3600 else "%dh" % (s // 3600) if s < 86400 else "%dd" % (s // 86400)


def doctor_line(qdir, logs_dir, now=None):
    """The /ace:ace-doctor line (mod doctor.ts deliveryLine): queue depth, oldest entry, dead/, and the replayed/expired
    rows of the last 7 days in the repo root's log (+ .1)."""
    import datetime
    now = time.time() if now is None else now
    st = stats(qdir, now)
    replayed = expired = 0
    for name in ("ace-relevance.jsonl", "ace-relevance.1.jsonl"):
        try:
            with open(os.path.join(str(logs_dir), name), encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "learn_replayed" not in line and "learn_expired" not in line:
                        continue
                    try:
                        r = json.loads(line)
                        t = datetime.datetime.strptime(r["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=datetime.timezone.utc).timestamp()
                    except (ValueError, KeyError, TypeError):
                        continue
                    if now - t < 7 * 86400:
                        replayed += r.get("event") == "learn_replayed"
                        expired += r.get("event") == "learn_expired"
        except OSError:
            pass
    return "delivery queue %d · oldest %s · 7d replayed %d · dead %d · expired %d" % (
        st["depth"], _age(st["oldest_age_s"]) if st["depth"] else "-", replayed, st["dead"], expired)


def has_entries(qdir):
    try:
        return any(n.endswith(".json") for n in os.listdir(str(qdir)))
    except OSError:
        return False


def spawn_replay(cwd=None, data_root=None):
    """Start one detached replay run (never waits). No-op when the queue is empty or disabled."""
    try:
        if not enabled():
            return
        if data_root is None:
            import plugin_data_dir
            data_root = str(plugin_data_dir.data_root())
        if not has_entries(os.path.join(str(data_root), "trace-queue")):
            return
        import subprocess
        env = dict(os.environ, CLAUDE_PLUGIN_DATA=str(data_root))
        argv = [sys.executable, os.path.abspath(__file__), "--replay"] + (["--cwd", str(cwd)] if cwd else [])
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=env, close_fds=True)
    except Exception:
        pass


def _enqueue(path, job_text):
    """The mod launcher's parent took the trace back (no child got it, nothing was sent): queue it, log the rows."""
    job = json.loads(job_text)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd) as f:
        body = json.load(f)
    rows = settle(os.path.join(job["root"], "trace-queue"), job["id"], body, job["meta"], None,
                  "nothing sent: launcher failed", on=job.get("on", True))
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    text = "".join(json.dumps(dict(timestamp=at, **r, session_id=job["meta"].get("session_id"), source="mod")) + "\n"
                   for r in rows)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plugin_data_dir
    f = plugin_data_dir.open_project_log(job["log"], append=True, base=job.get("cwd") or None)
    if f is not None:
        with f:
            f.write(text)


def _main(argv):
    if argv[:1] == ["--enqueue"] and len(argv) == 3:
        _enqueue(argv[1], argv[2])
        return
    if "--replay" not in argv:
        sys.exit("usage: ace_trace_queue.py --replay [--cwd DIR] | --enqueue FILE JOB")
    if "--cwd" in argv:
        try:
            os.chdir(argv[argv.index("--cwd") + 1])
        except (OSError, IndexError):
            pass
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import plugin_data_dir
    import ace_cli
    from ace_relevance_logger import log_event

    def send(e):
        m = e.get("meta") or {}
        return ace_cli.learn_once(e["trace"], retrieval_id=m.get("retrieval_id"), applied_log_ids=m.get("applied_log_ids"),
                                  org=m.get("org"), project=m.get("project"), timeout=REPLAY_TIMEOUT,
                                  hook_event_name="replay", idempotency_key=e["id"])

    for r in replay(plugin_data_dir.data_root() / "trace-queue", send):
        ev = r.pop("event")
        log_event(ev, **r)


if __name__ == "__main__":
    try:
        _main(sys.argv[1:])
    except SystemExit:
        raise
    except Exception:
        sys.exit(1)  # the mod parent logs learn_lost (enqueue_failed)
    sys.exit(0)
