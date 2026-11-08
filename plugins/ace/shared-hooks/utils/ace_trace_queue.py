#!/usr/bin/env python3
"""8.1.4 trace delivery (ARCHITECTURE "Trace delivery"): the durable retry queue for learn traces, ONE module for both
chains. The Python hooks call settle() after ace_cli.run_learn; the mod's detached learn child imports this file too,
so a failed send is handled the same way whichever chain built the trace. Stdlib only.

<data root>/queue.key                per-install random HMAC key (0600, created once, atomically; never in a trace/log)
<data root>/trace-queue/<id>.json    {"v", "created_at", "next_at", "attempts", "last_error", "key_gen", "answered",
                                      "meta", "trace", "hmac"}
<data root>/trace-queue/inflight/    an entry being replayed (claimed by an atomic rename)
<data root>/trace-queue/dead/        given up, rejected, or a broken/unsigned file; kept 7 days, never replayed

The queue id is ONLY the file name (`<id>.json`, 32 hex or a 36-char uuid); content never decides a path or the key.
Every entry carries HMAC-SHA256(key, {id, created_at, meta, trace}); replay sends only entries that verify and pass
the schema. The Idempotency-Key sent is the id (key_gen 0) or `<id>-r<key_gen>` after a `stored:false` answer.
Rows (the caller adds timestamp/source) never carry trace content.

`python3 ace_trace_queue.py --replay [--cwd DIR]`: one bounded replay run (async SessionStart, after a good learn).
`python3 -I ace_trace_queue.py --enqueue FILE JOB`: the mod launcher's parent queues a trace no child got.
"""
import hashlib
import hmac as _hmac
import json
import math
import os
import re
import stat
import sys
import time
import uuid

MAX_FILES = 200
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
# The server de-duplicates an Idempotency-Key per (org, project, key) for 24 h from its FIRST attempt (not extended,
# cleaned hourly): a replay after that could store a duplicate. ONE constant: the replay limit, from the first send.
REPLAY_WINDOW = 23 * 3600
DEAD_KEEP = 7 * 86400
BACKOFF = (60, 300, 1800, 7200, 43200)  # after failed attempt 1..5
MAX_ATTEMPTS = 6
MAX_KEY_GEN = 3            # stored:false -> a new key (the server remembers the old key's stored:false for 24 h)
IN_PROGRESS_WAIT = 75 * 60  # "duplicate in progress": the first request is still writing
QUOTA_WAIT = 12 * 3600      # 429 without Retry-After
PER_RUN = 5
CLAIM_STALE = 900   # a replayer sends at most 5 x 60 s; an older claim is a crashed one
HANDOVER_STALE = 1800  # a learn child runs at most 2 x 310 s; older job/trace files belong to a killed child
REPLAY_TIMEOUT = 60

_ID = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
_META = {"org": 128, "project": 128, "retrieval_id": 128, "hook": 64, "agent_type": 128, "session_id": 512}
_PRECONNECT = re.compile(r"\b(ECONNREFUSED|ENOTFOUND|EAI_AGAIN|EHOSTUNREACH|ENETUNREACH)\b")
_AUTH_CODES = {"not_logged_in", "token_expired", "no_access"}
_REJECT_CODES = {"unbound", "project_not_found", "device_limit_exceeded"}
RESPONSE_TAG = "ace_trace_response "  # engine/learn.js: the last POST /traces answer, one stderr line


def enabled():
    return os.environ.get("ACE_TRACE_QUEUE", "1") != "0"


def valid_id(s):
    return isinstance(s, str) and bool(_ID.match(s))


def send_key(entry_id, key_gen):
    return entry_id if not key_gen else "%s-r%d" % (entry_id, key_gen)


# ---------- classification ----------

def _lines(text):
    """(engine response dict, dead letter dict, ace-cli error dict) found in the output; each the last one, or None."""
    resp = dl = err = None
    for line in text.splitlines():
        if line.startswith(RESPONSE_TAG):
            try:
                o = json.loads(line[len(RESPONSE_TAG):])
                resp = o if isinstance(o, dict) else resp
            except ValueError:
                pass
            continue
        i = line.find("{")
        if i < 0:
            continue
        try:
            o = json.loads(line[i:])
        except ValueError:
            continue
        if not isinstance(o, dict):
            continue
        if o.get("event") == "ace_trace_dead_letter":
            dl = o
        elif isinstance(o.get("error"), dict) and isinstance(o["error"].get("code"), str):
            err = o["error"]
    return resp, dl, err


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def response_of(output):
    """The engine's last POST /traces answer in the output, or None."""
    return _lines(str(output or ""))[0]


def classify(code, output, keyed=True, answered=False):
    """(action, error_class); action is ok | requeue | dead | lost. keyed = the send carried the queue's stable
    Idempotency-Key (the engine); answered = an earlier attempt with this key got a real 200/202."""
    text = str(output or "")
    resp, dl, err = _lines(text)
    if resp is not None:  # the engine saw the answer itself: decide on status and `stored`/`duplicate`, never `message`
        st = _int(resp.get("status"))
        if st is None:
            return "requeue", "network"
        if st in (200, 202):
            if resp.get("stored") is False:
                return "requeue", "not_stored"
            if "stored" in resp and resp["stored"] is not True:  # null (server fix: the first send still runs) or junk
                return "requeue", "in_progress"
            if resp.get("duplicate") is True:
                msg = str(resp.get("message") or "").lower()
                if "in progress" in msg or not answered:
                    return "requeue", "in_progress"
            return "ok", None
        if st == 429:
            return "requeue", "quota"
        if st in (401, 403):
            return "dead", "auth"
        if st == 422:
            return "dead", "invalid"
        if 400 <= st < 500:
            return "dead", "4xx"
        if st == 503 and resp.get("error_code") == "PG_STATEMENT_TIMEOUT":
            return "requeue", "pg_timeout"
        if st in (502, 503):
            return "requeue", "gateway_5xx"
        return ("requeue", "server_5xx") if keyed else ("lost", "server_5xx")
    if "ace_trace_quota_exceeded" in text:
        return "requeue", "quota"
    if code == 0:
        return "ok", None
    ecode = err.get("code") if err else None
    if ecode in _AUTH_CODES or (ecode is None and not keyed and code in (3, 4)):  # ace-cli: exit 3/4 = auth
        return "dead", "auth"
    if ecode in _REJECT_CODES:
        return "dead", "4xx"
    st = _int(dl.get("status")) if dl else None
    if st is None and err:
        st = _int(err.get("status"))
    if st is None:
        m = re.search(r"Server error \((\d{3})\)", text)
        st = int(m.group(1)) if m else None
    if st is not None:
        if st in (401, 403):
            return "dead", "auth"
        if st == 422:
            return "dead", "invalid"
        if st == 429:
            return "requeue", "quota"
        if 400 <= st < 500:
            return "dead", "4xx"
        if st in (502, 503) and keyed:
            return "requeue", "gateway_5xx"
        return ("requeue", "server_5xx") if keyed else ("lost", "server_5xx")
    low = text.lower()
    if "failed to read transcript" in low or low.strip() == "cli_not_found" or low.startswith("nothing sent"):
        return "requeue", "not_sent"
    if dl is not None or _PRECONNECT.search(text):  # the core's attempts all failed without any answer
        return "requeue", "network"
    if code is None and ("timeout" in low or "timed out" in low):
        return ("requeue", "timeout") if keyed else ("lost", "timeout")
    if "timed out" in low:
        return ("requeue", "timeout") if keyed else ("lost", "timeout")
    return "lost", "unknown"


def _retry_after(output):
    resp = response_of(output) or {}
    ra = resp.get("retry_after")
    try:
        ra = float(ra)
    except (TypeError, ValueError):
        return None
    return ra if math.isfinite(ra) and 0 <= ra <= 7 * 86400 else None


def _next_at(cls, attempts, now, output):
    """When to try again after failed attempt `attempts` (1-based)."""
    base = BACKOFF[min(max(attempts, 1), len(BACKOFF)) - 1]
    ra = _retry_after(output)
    if cls == "in_progress":
        return now + IN_PROGRESS_WAIT
    if cls == "quota":
        return now + (ra if ra is not None else QUOTA_WAIT)
    if ra is not None:
        return now + max(base, ra)
    return now + base


# ---------- rows ----------

def _row(event, entry_id, meta, attempts, cls=None, reason=None):
    meta = meta if isinstance(meta, dict) else {}
    r = {"event": event}
    if reason:
        r["reason"] = reason
    if cls:
        r["error_class"] = cls
    r.update(attempts=attempts, trace_id=entry_id, agent_type=meta.get("agent_type") or "main",
             hook=meta.get("hook"), project_id=meta.get("project"))
    return r


# ---------- files ----------

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


def _read_raw(path, limit=MAX_FILE + 4096):
    """Parsed JSON of a regular file, never through a symlink, bounded; None when unusable."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, "rb") as f:
            fd = None
            data = f.read(limit + 1)
        return None if len(data) > limit else json.loads(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def _key_path(qdir):
    return os.path.join(os.path.dirname(str(qdir).rstrip(os.sep)), "queue.key")


def load_key(qdir):
    """The per-install HMAC key (32 bytes), created once (0600, atomic link of a temp file); None when unusable.
    A broken or symlinked key is refused, never replaced: entries signed with it would stop verifying."""
    p = _key_path(qdir)
    if not _safe_dir(os.path.dirname(p)):
        return None
    for _ in range(2):
        raw = None
        try:
            fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode) or stat.S_IMODE(os.fstat(fd).st_mode) & 0o077:
                    return None
                raw = os.read(fd, 200).decode("ascii", "replace").strip()
            finally:
                os.close(fd)
        except FileNotFoundError:
            import secrets
            tmp = "%s.%s.tmp" % (p, uuid.uuid4().hex)
            try:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(secrets.token_hex(32) + "\n")
                try:
                    os.link(tmp, p)  # create-if-absent: two writers never both win
                except FileExistsError:
                    pass
            except OSError:
                return None
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            continue
        except OSError:
            return None
        return bytes.fromhex(raw) if raw and re.fullmatch(r"[0-9a-f]{64}", raw) else None
    return None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")


def sign(key, obj):
    """HMAC-SHA256 hex of a JSON object (sorted, compact); "" without a key."""
    return _hmac.new(key, _canon(obj), hashlib.sha256).hexdigest() if key else ""


def _signed_part(entry_id, e):
    return {"id": entry_id, "created_at": e.get("created_at"), "meta": e.get("meta"), "trace": e.get("trace")}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _valid_meta(m):
    if not isinstance(m, dict) or set(m) - set(_META) - {"applied_log_ids"}:
        return False
    for k, n in _META.items():
        v = m.get(k)
        if v is not None and not (isinstance(v, str) and len(v) <= n):
            return False
    ids = m.get("applied_log_ids", [])
    return isinstance(ids, list) and len(ids) <= 100 and all(_int(x) is not None for x in ids)


def _valid_entry(e):
    return (isinstance(e, dict) and e.get("v") == 1 and _num(e.get("created_at")) and _num(e.get("next_at"))
            and _int(e.get("attempts")) is not None and 1 <= e["attempts"] <= MAX_ATTEMPTS
            and _int(e.get("key_gen", 0)) is not None and 0 <= e.get("key_gen", 0) <= MAX_KEY_GEN
            and isinstance(e.get("answered", False), bool)
            and (e.get("last_error") is None or isinstance(e.get("last_error"), str))
            and _valid_meta(e.get("meta")) and isinstance(e.get("trace"), dict)
            and isinstance(e.get("hmac"), str) and len(e["hmac"]) == 64)


def _load(path, name, key):
    """(entry with "id" from the NAME, None) or (None, "invalid" | "unsigned")."""
    stem = name[:-5] if name.endswith(".json") else ""
    if not valid_id(stem):
        return None, "invalid"
    e = _read_raw(path)
    if not _valid_entry(e):
        return None, "invalid"
    if not key or not _hmac.compare_digest(e["hmac"], sign(key, _signed_part(stem, e))):
        return None, "unsigned"
    e = dict(e)
    e["id"] = stem
    e.setdefault("key_gen", 0)
    e.setdefault("answered", False)
    e["key"] = send_key(stem, e["key_gen"])
    return e, None


def _dump(e):
    return json.dumps({k: v for k, v in e.items() if k not in ("id", "key")}, default=str)


def _names(d):
    try:
        return [n for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return []


def _queued(qdir):
    out = []
    for sub in ("", "inflight"):
        d = os.path.join(str(qdir), sub)
        for n in _names(d):
            p = os.path.join(d, n)
            if not os.path.islink(p) and os.path.isfile(p):
                out.append(p)
    return out


def _dead_name(stem):
    return (stem if valid_id(stem) else "invalid-" + uuid.uuid4().hex) + ".json"


def _to_dead(qdir, src_path, stem, now, entry=None):
    """Move a file (or write an entry) into dead/ under a safe base name; mtime = now (the 7-day clock)."""
    d = os.path.join(str(qdir), "dead")
    if not (_safe_dir(str(qdir)) and _safe_dir(d)):
        if src_path:
            try:
                os.unlink(src_path)
            except OSError:
                pass
        return
    dst = os.path.join(d, _dead_name(stem))
    try:
        if entry is not None:
            _write(dst, _dump(entry))
            if src_path:
                os.unlink(src_path)
        elif src_path:
            os.rename(src_path, dst)
        os.utime(dst, (now, now))
    except OSError:
        if src_path:
            try:
                os.unlink(src_path)
            except OSError:
                pass


def _put(qdir, entry_id, entry):
    """Write an entry under the caps; the reason it was not written, or None."""
    if not _safe_dir(str(qdir)):
        return "unsafe_dir"
    text = _dump(entry)
    size = len(text.encode("utf-8"))
    if size > MAX_FILE:
        return "too_large"
    have = [p for p in _queued(qdir) if os.path.basename(p) != entry_id + ".json"]
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
        _write(os.path.join(str(qdir), entry_id + ".json"), text)
    except OSError:
        return "write_failed"
    return None


# ---------- the original send ----------

def settle(qdir, entry_id, trace, meta, code, output, now=None, on=None, keyed=True):
    """After the ORIGINAL send of a built trace: rows to log (the trace is queued, sent to dead/, or lost)."""
    now = time.time() if now is None else now
    action, cls = classify(code, output, keyed=keyed)
    if action == "ok":
        return []
    if not valid_id(entry_id):
        return [_row("learn_lost", None, meta, 1, cls, "bad_id")]
    if not (enabled() if on is None else on):
        return [_row("learn_lost", entry_id, meta, 1, cls, "queue_disabled")]
    if action == "lost":
        return [_row("learn_lost", entry_id, meta, 1, cls, "maybe_sent")]
    if not _valid_meta(meta) or not isinstance(trace, dict):
        return [_row("learn_lost", entry_id, meta, 1, cls, "invalid_meta")]
    key = load_key(qdir)
    if key is None:
        return [_row("learn_lost", entry_id, meta, 1, cls, "no_key" if _safe_dir(str(qdir)) else "unsafe_dir")]
    e = {"v": 1, "created_at": now, "next_at": _next_at(cls, 1, now, output), "attempts": 1, "last_error": cls,
         "key_gen": 1 if cls == "not_stored" else 0,
         "answered": cls != "not_stored" and _int((response_of(output) or {}).get("status")) in (200, 202), "meta": meta,
         "trace": json.loads(json.dumps(trace, default=str))}
    e["hmac"] = sign(key, _signed_part(entry_id, e))
    if action == "dead":
        _to_dead(qdir, None, entry_id, now, entry=e)
        return [_row("learn_lost", entry_id, meta, 1, cls, "rejected")]
    if e["next_at"] - now > REPLAY_WINDOW:
        return [_row("learn_expired", entry_id, meta, 1, cls, "window")]
    why = _put(qdir, entry_id, e)
    if why:
        return [_row("learn_lost", entry_id, meta, 1, cls, why)]
    return [_row("learn_requeued", entry_id, meta, 1, cls, "send_failed")]


# ---------- replay ----------

def _prune(qdir, now, key):
    rows = []
    infl = os.path.join(qdir, "inflight")
    for n in _names(infl):  # <id>.<claim epoch>.json: the claim time travels with the rename (an mtime would not)
        p = os.path.join(infl, n)
        stem, _, at = n[:-5].rpartition(".")
        try:
            if os.path.islink(p) or not valid_id(stem) or not at.isdigit():
                _to_dead(qdir, p, stem, now)
            elif now - int(at) > CLAIM_STALE:
                os.rename(p, os.path.join(qdir, stem + ".json"))  # a crashed replayer's claim (attempt already counted)
        except OSError:
            pass
    dead = os.path.join(qdir, "dead")
    for n in _names(dead):
        p = os.path.join(dead, n)
        try:
            if now - os.lstat(p).st_mtime > DEAD_KEEP:
                os.unlink(p)
        except OSError:
            pass
    for n in _names(qdir):
        p = os.path.join(qdir, n)
        if os.path.islink(p):
            continue
        e, why = _load(p, n, key)
        if e is None:
            _to_dead(qdir, p, n[:-5], now)
            rows.append(_row("learn_lost", n[:-5] if valid_id(n[:-5]) else None, None, 0, why, why))
        elif now - e["created_at"] > REPLAY_WINDOW:
            try:
                os.unlink(p)
                rows.append(_row("learn_expired", e["id"], e["meta"], e["attempts"], e.get("last_error"), "max_age"))
            except OSError:
                pass
    return rows


def _settle_replay(qdir, name, claimed, e, res, now):
    """The decision after one replay send; returns the row. The claim is resolved by the caller's finally."""
    code, out = res[0], res[1]
    keyed = res[2] if len(res) > 2 else True
    att = e["attempts"]
    action, cls = classify(code, out, keyed=keyed, answered=e["answered"])
    e["last_error"] = cls
    resp = response_of(out) or {}
    if _int(resp.get("status")) in (200, 202):
        e["answered"] = True
    if action == "ok":
        os.unlink(claimed)
        return _row("learn_replayed", e["id"], e["meta"], att)
    if action == "requeue" and cls == "not_stored":
        if e["key_gen"] >= MAX_KEY_GEN:
            _to_dead(qdir, claimed, e["id"], now, entry=e)
            return _row("learn_lost", e["id"], e["meta"], att, cls, "gave_up")
        e["key_gen"] += 1
        e["answered"] = False  # a new key starts a new server-side record
    if action == "requeue" and cls == "in_progress":
        e["attempts"] = att = att - 1  # waiting for the first send is no failed attempt (the 23 h window bounds it)
    if action == "requeue" and (att < MAX_ATTEMPTS or cls == "in_progress"):
        e["next_at"] = _next_at(cls, att, now, out)
        if e["next_at"] - e["created_at"] > REPLAY_WINDOW:
            os.unlink(claimed)
            return _row("learn_expired", e["id"], e["meta"], att, cls, "window")
        _write(os.path.join(qdir, name), _dump(e))
        os.unlink(claimed)
        return _row("learn_requeued", e["id"], e["meta"], att, cls, "replay_failed")
    if action == "lost":
        os.unlink(claimed)
        return _row("learn_lost", e["id"], e["meta"], att, cls, "maybe_sent")
    _to_dead(qdir, claimed, e["id"], now, entry=e)
    return _row("learn_lost", e["id"], e["meta"], att, cls, "rejected" if action == "dead" else "gave_up")


def replay(qdir, send, now=None, limit=PER_RUN):
    """Send due entries oldest first, at most `limit`; send(entry) -> (exit_code_or_None, output[, keyed]).
    A broken or unsigned file goes to dead/ and never blocks the others. attempts rises BEFORE the send, so a replayer
    that dies mid-send cannot loop: its claim comes back after CLAIM_STALE and ends in dead/ after MAX_ATTEMPTS."""
    if not enabled():
        return []
    qdir = str(qdir).rstrip(os.sep)
    if not os.path.isdir(qdir) or os.path.islink(qdir):
        return []
    now = time.time() if now is None else now
    key = load_key(qdir)
    rows = _prune(qdir, now, key)
    due = []
    for n in _names(qdir):
        e, _ = _load(os.path.join(qdir, n), n, key)
        if e and e["next_at"] <= now:
            due.append((e["created_at"], n))
    if not due or not _safe_dir(os.path.join(qdir, "inflight")):
        return rows
    sent = 0
    for _, name in sorted(due):
        if sent >= limit:
            break
        claimed = os.path.join(qdir, "inflight", "%s.%d.json" % (name[:-5], int(now)))
        try:
            os.rename(os.path.join(qdir, name), claimed)  # the claim: whoever renames it owns it, with its time
        except OSError:
            continue
        e = None
        try:
            e, why = _load(claimed, name, key)
            if e is None:
                _to_dead(qdir, claimed, name[:-5], now)
                rows.append(_row("learn_lost", name[:-5], None, 0, why, why))
                continue
            if e["attempts"] >= MAX_ATTEMPTS:
                _to_dead(qdir, claimed, e["id"], now, entry=e)
                rows.append(_row("learn_lost", e["id"], e["meta"], e["attempts"], e.get("last_error"), "gave_up"))
                continue
            e["attempts"] += 1
            _write(claimed, _dump(e))  # counted before the send
            sent += 1
            try:
                res = send(e)
            except Exception as ex:  # a broken sender is a failed attempt, never a lost entry
                res = (1, "cli_not_found" if isinstance(ex, FileNotFoundError) else "unknown")
            rows.append(_settle_replay(qdir, name, claimed, e, tuple(res), now))
        except Exception:
            if os.path.lexists(claimed):
                _to_dead(qdir, claimed, name[:-5], now, entry=e if e else None)
            rows.append(_row("learn_lost", name[:-5], e["meta"] if e else None, e["attempts"] if e else 0,
                             "replay_error", "replay_error"))
    return rows


# ---------- orphans of a killed learn child ----------

def sweep_orphans(data_root, now=None, stale=HANDOVER_STALE):
    """Async SessionStart: leftovers of a learn child that was killed. A signed Python job file (the child never
    started: nothing was sent) is queued; mod trace files (`.owned`: the child may have sent) and anything unsigned are
    a learn_lost row (reason child_killed). Files younger than `stale` belong to a live child and stay."""
    now = time.time() if now is None else now
    root = str(data_root)
    qdir = os.path.join(root, "trace-queue")
    rows = []
    tmp = os.path.join(root, "tmp")
    seen = set()
    try:
        names = os.listdir(tmp)
    except OSError:
        names = []
    for n in names:
        if not n.startswith("ace-trace-"):
            continue
        p = os.path.join(tmp, n)
        try:
            if now - os.lstat(p).st_mtime <= stale:
                continue
            os.unlink(p)
        except OSError:
            continue
        base = n.split(".json")[0][len("ace-trace-"):]
        if base not in seen and not n.endswith(".result"):
            seen.add(base)
            rows.append(_row("learn_lost", base if valid_id(base) else None, None, 1, "child_killed", "child_killed"))
    import glob
    key = None
    for p in glob.glob(os.path.join(root, "projects", "*", "sessions", "*", "learn-job-*.json"))[:200]:
        try:
            if os.path.islink(p) or now - os.lstat(p).st_mtime <= stale:
                continue
        except OSError:
            continue
        job = _read_raw(p)
        try:
            os.unlink(p)
        except OSError:
            continue
        key = key or load_key(qdir)
        ok = (isinstance(job, dict) and isinstance(job.get("sig"), str) and key is not None and _hmac.compare_digest(
            job["sig"], sign(key, {k: v for k, v in job.items() if k != "sig"})) and isinstance(job.get("trace"), dict))
        meta = {"org": job.get("org"), "project": job.get("project"), "retrieval_id": job.get("retrieval_id"),
                "applied_log_ids": job.get("applied_log_ids") or [], "hook": job.get("hook_event_name"),
                "agent_type": (job.get("metrics") or {}).get("agent_type") or "main"} if isinstance(job, dict) else {}
        if ok and _valid_meta(meta):
            for r in settle(qdir, uuid.uuid4().hex, job["trace"], meta, None, "nothing sent: learn child never started", now=now):
                r["reason"] = "child_killed"
                rows.append(r)
        else:
            rows.append(_row("learn_lost", None, meta, 1, "child_killed", "child_killed"))
    return rows


# ---------- doctor ----------

def stats(qdir, now=None):
    """{"depth", "oldest_age_s", "dead"} for /ace:ace-doctor (display only)."""
    now = time.time() if now is None else now
    ages = []
    for p in _queued(qdir):
        e = _read_raw(p)
        if isinstance(e, dict) and _num(e.get("created_at")):
            ages.append(now - e["created_at"])
    return {"depth": len(ages), "oldest_age_s": int(max(ages)) if ages else 0,
            "dead": len(_names(os.path.join(str(qdir), "dead")))}


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
    return bool(_names(str(qdir)))


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
    body = _read_raw(path)
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
        m = e["meta"]
        return ace_cli.learn_once(e["trace"], retrieval_id=m.get("retrieval_id"), applied_log_ids=m.get("applied_log_ids"),
                                  org=m.get("org"), project=m.get("project"), timeout=REPLAY_TIMEOUT,
                                  hook_event_name="replay", idempotency_key=e["key"])

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
