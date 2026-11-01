#!/usr/bin/env python3
"""v8 Foundation (DESIGN §6): disk search cache in ace_search_cache.py.

- entries live under plugin_data_dir.search_cache_dir() as <sha256>.json
- key = sha256(project_id + agent scope + normalized query); normalization strips
  <task-id>...</task-id>, collapses whitespace, lowercases
- TTL 15 min, atomic write (tempfile + rename), LRU cap 500 by mtime
"""
import importlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))

RESP = {"similar_patterns": [{"id": "ctx-1234567890-abcd"}], "count": 1}


@pytest.fixture
def sc(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "pd"))
    import plugin_data_dir
    import ace_search_cache
    importlib.reload(plugin_data_dir)
    return importlib.reload(ace_search_cache)


def _cache_dir(tmp_path):
    return tmp_path / "pd" / "cache" / "search"


def test_constants(sc):
    assert sc.TTL_SECONDS == 15 * 60
    assert sc.MAX_ENTRIES == 500


def test_normalize_query(sc):
    q = "  Fix   the\n\tAUTH bug <task-id>abc-123</task-id>  now "
    assert sc.normalize_query(q) == "fix the auth bug now"


def test_normalize_strips_multiline_task_id(sc):
    assert sc.normalize_query("<task-id>\nx\n</task-id>Hello  World") == "hello world"


def test_cache_key_is_sha256_hex_and_scoped(sc):
    k = sc.cache_key("prj_1", "main", "Fix bug")
    assert len(k) == 64 and all(c in "0123456789abcdef" for c in k)
    assert k == sc.cache_key("prj_1", "main", "  fix   BUG <task-id>t</task-id>")
    assert k != sc.cache_key("prj_2", "main", "fix bug")
    assert k != sc.cache_key("prj_1", "agent-x", "fix bug")


def test_put_get_on_disk(sc, tmp_path):
    sc.put("prj_1", "main", "fix bug", RESP)
    files = list(_cache_dir(tmp_path).glob("*.json"))
    assert len(files) == 1
    assert files[0].name == sc.cache_key("prj_1", "main", "fix bug") + ".json"
    assert sc.get("prj_1", "main", "FIX   bug") == RESP


def test_survives_new_process_module_reload(sc, tmp_path):
    sc.put("prj_1", "main", "fix bug", RESP)
    mod = importlib.reload(sc)
    assert mod.get("prj_1", "main", "fix bug") == RESP


def test_miss(sc):
    assert sc.get("prj_1", "main", "never stored") is None


def test_ttl_expiry(sc, monkeypatch):
    sc.put("prj_1", "main", "fix bug", RESP)
    real = time.time()
    monkeypatch.setattr(time, "time", lambda: real + 15 * 60 + 5)
    assert sc.get("prj_1", "main", "fix bug") is None


def test_within_ttl_hit(sc, monkeypatch):
    sc.put("prj_1", "main", "fix bug", RESP)
    real = time.time()
    monkeypatch.setattr(time, "time", lambda: real + 14 * 60)
    assert sc.get("prj_1", "main", "fix bug") == RESP


def test_atomic_write_uses_replace(sc, monkeypatch, tmp_path):
    calls = []
    real_replace = os.replace

    def spy(src, dst):
        calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    sc.put("prj_1", "main", "fix bug", RESP)
    assert calls, "write must go through tempfile + os.replace"
    src, dst = calls[-1]
    assert dst.endswith(".json") and src != dst
    assert Path(src).parent == Path(dst).parent, "temp file in the same dir (atomic rename)"
    assert not [p for p in _cache_dir(tmp_path).iterdir() if not p.name.endswith(".json")]


def test_corrupt_entry_is_a_miss(sc, tmp_path):
    sc.put("prj_1", "main", "fix bug", RESP)
    f = next(_cache_dir(tmp_path).glob("*.json"))
    f.write_text("{ broken")
    assert sc.get("prj_1", "main", "fix bug") is None


def test_lru_cap_evicts_oldest_by_mtime(sc, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "MAX_ENTRIES", 5)
    for i in range(5):
        sc.put("prj_1", "main", f"q{i}", {"i": i})
        p = _cache_dir(tmp_path) / (sc.cache_key("prj_1", "main", f"q{i}") + ".json")
        os.utime(p, (1000 + i, 1000 + i))
    sc.put("prj_1", "main", "q-new", {"i": "new"})
    files = list(_cache_dir(tmp_path).glob("*.json"))
    assert len(files) == 5
    oldest = _cache_dir(tmp_path) / (sc.cache_key("prj_1", "main", "q0") + ".json")
    assert not oldest.exists(), "least-recently-used (oldest mtime) entry evicted"


def test_never_raises_on_unwritable_dir(sc, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/dev/null/nope")
    sc.put("prj_1", "main", "fix bug", RESP)  # must not raise
    assert sc.get("prj_1", "main", "fix bug") is None
