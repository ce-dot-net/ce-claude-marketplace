#!/usr/bin/env python3
"""Item #17 — LRU cache for ace-cli search results.

Plugin-side caching layer for repeated search calls (PreToolUse, PostToolUse
Bash-error injection). TTL=60s, max=100 entries, LRU eviction.

Why this exists:
- ace-cli search costs 150-400ms per call (cache-miss; Qdrant + embedding roundtrip).
- Same Bash error in a session triggers identical search query repeatedly.
- 60s TTL is long enough for in-session reuse, short enough to stay fresh.

Key composition: sha256(query + "|" + domain + "|" + section)[:16] — stable hashes
across processes; ace-cli search is deterministic-enough for this to be safe.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any, Optional


class AceSearchCache:
    """In-memory LRU with TTL.

    Not thread-safe — hooks are single-process per invocation, no concurrent access.
    Process-local: cache does not persist across hook invocations. The benefit comes
    within a single hook execution that does multiple searches (e.g., subagent_stop).
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 60) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    @staticmethod
    def make_key(*parts: Optional[str]) -> str:
        """Variadic cache key: sha256 of '|'-joined parts.

        Callers pass whatever discriminators matter (query, org, project, section,
        domain, agent_type, …). Keeping it variadic avoids the v6.5.0 naming
        mismatch where the function advertised (query, domain, section) but
        was actually called with (query, org, project) — PR-review I1.
        """
        raw = "|".join("" if p is None else str(p) for p in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        inserted_at, value = entry
        if time.time() - inserted_at > self._ttl:
            # Expired — evict and miss
            self._store.pop(key, None)
            return None
        # Move to end (most-recently-used)
        self._store.move_to_end(key)
        return value

    def put(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.time(), value)
        # Evict oldest if over capacity
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()


# Module-level singleton for use across hooks within the same process.
_GLOBAL_CACHE = AceSearchCache()


def get_global_cache() -> AceSearchCache:
    return _GLOBAL_CACHE
