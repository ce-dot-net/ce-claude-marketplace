#!/usr/bin/env python3
"""v8 disk search cache (DESIGN §6 Foundation).

Entries: <plugin-data>/cache/search/<sha256>.json, TTL 15 min, atomic write
(tempfile in the same dir + os.replace), FIFO cap by write mtime. Cross-process so a
repeated prompt / sibling subagent skips the ace-cli spawn. Never raises.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

_UTILS = str(Path(__file__).resolve().parent)
if _UTILS not in sys.path:
    sys.path.insert(0, _UTILS)
import plugin_data_dir  # noqa: E402

TTL_SECONDS = 15 * 60
MAX_ENTRIES = 500

_TASK_ID = re.compile(r"<task-id>.*?</task-id>", re.S | re.I)


def normalize_query(query: str) -> str:
    return " ".join(_TASK_ID.sub(" ", query or "").split()).lower()


def cache_key(project_id: str, agent_scope: str, query: str) -> str:
    raw = "\x1f".join([str(project_id or ""), str(agent_scope or ""), normalize_query(query)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _path(project_id, agent_scope, query) -> Path:
    return plugin_data_dir.search_cache_dir() / (cache_key(project_id, agent_scope, query) + ".json")


def get(project_id: str, agent_scope: str, query: str) -> Optional[Any]:
    try:
        p = _path(project_id, agent_scope, query)
        if time.time() - p.stat().st_mtime > TTL_SECONDS:
            return None
        return json.loads(p.read_text())
    except Exception:  # missing, corrupt, unreadable -> miss
        return None


def put(project_id: str, agent_scope: str, query: str, value: Any) -> None:
    try:
        p = _path(project_id, agent_scope, query)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(value, f)
            os.replace(tmp, p)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        _evict(p.parent)
    except Exception:
        pass


def _evict(d: Path) -> None:
    # FIFO by write time (get() does not touch mtime, so TTL stays fixed).
    # Callers must NOT put error dicts ({"error": ...}) - only real results.
    for t in d.glob("*.tmp"):  # orphans from a crashed put
        try:
            if time.time() - t.stat().st_mtime > 60:
                t.unlink()
        except OSError:
            pass
    files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime)
    for f in files[: max(0, len(files) - MAX_ENTRIES)]:
        try:
            f.unlink()
        except OSError:
            pass


# ── DESIGN §32: hybrid local reuse (domain-shift + SubagentStart; the main UPS search never reads this) ──

def reuse_enabled(kind: str) -> bool:
    raw = os.environ.get("ACE_LOCAL_REUSE")
    allowed = {x.strip() for x in ("domain,subagent" if raw is None else raw).split(",")}
    return kind in allowed


def _real(value: Any) -> bool:
    return (isinstance(value, dict) and not value.get("error")
            and isinstance(value.get("similar_patterns"), list) and bool(value["similar_patterns"]))


def _mark_used(project_id, kind, query, agent_id) -> bool:
    """True the first time this agent claims this entry (atomic O_EXCL marker beside the entry)."""
    try:
        base = _path(project_id, kind, query)
        who = hashlib.sha256(str(agent_id or "").encode("utf-8")).hexdigest()[:16]
        fd = os.open(str(base.with_suffix(".used-" + who)), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except Exception:
        return False


def reuse_get(project_id: str, kind: str, query: str, agent_id: str) -> Optional[Any]:
    """A real hit (same project, exact normalized query, < 15 min, >= 1 pattern) not yet served to this agent."""
    if not reuse_enabled(kind) or not project_id or not normalize_query(query):
        return None
    hit = get(project_id, kind, query)
    if _real(hit) and _mark_used(project_id, kind, query, agent_id):
        return hit
    return None


def reuse_put(project_id: str, kind: str, query: str, agent_id: str, value: Any) -> None:
    """A server result refreshes the entry; the agent that fetched it has used it (no second local serve)."""
    if reuse_enabled(kind) and project_id and _real(value):
        put(project_id, kind, query, value)
        try:  # a refresh starts a new use-cycle for the other agents
            base = _path(project_id, kind, query)
            for m in base.parent.glob(base.stem + ".used-*"):
                m.unlink()
        except OSError:
            pass
        _mark_used(project_id, kind, query, agent_id)
