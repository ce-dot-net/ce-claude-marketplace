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
