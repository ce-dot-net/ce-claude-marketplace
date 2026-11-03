#!/usr/bin/env python3
"""v8 Foundation contract C5 (DESIGN §4/§5): relevance logger.

- every event's timestamp is UTC ISO-8601 ending in 'Z' (v7 wrote '+00:00'
  from the logger and naive local time from ace_cli._log_cli_error)
- log_search(..., patterns_returned, patterns_injected, hook_ms, hook=...)
- log_error(hook, location, ...)
- ace-relevance.jsonl stays in the project (.claude/data/logs) but is NOT moved
  to .prev on startup; archive_relevance_log rotates by size only (>50 MB -> .1)
"""
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "ace" / "shared-hooks" / "utils"))

Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


@pytest.fixture
def arl(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    import ace_relevance_logger
    mod = importlib.reload(ace_relevance_logger)
    mod._logger = None
    return mod


def _entries(tmp_path):
    p = tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def test_log_search_fields(arl, tmp_path):
    arl.log_search(
        session_id="s1", user_prompt="fix it", search_query="fix it",
        patterns_returned=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        patterns_injected=2, hook_ms=123, hook="UserPromptSubmit",
        domains=["d"], project_id="prj_1",
    )
    e = _entries(tmp_path)[-1]
    assert e["event"] == "search"
    assert e["hook"] == "UserPromptSubmit"
    assert e["patterns_returned"] == 3
    assert e["patterns_injected"] == 2
    assert e["hook_ms"] == 123
    assert Z_RE.match(e["timestamp"]), e["timestamp"]


def test_log_search_accepts_lists_for_counts(arl, tmp_path):
    arl.log_search(session_id="s1", patterns_returned=5,
                   patterns_injected=[{"id": "a"}], hook_ms=9, hook="SubagentStart")
    e = _entries(tmp_path)[-1]
    assert (e["patterns_returned"], e["patterns_injected"], e["hook"]) == (5, 1, "SubagentStart")


def test_log_error_takes_hook(arl, tmp_path):
    arl.log_error(hook="PostToolUse", location="domain_shift.search",
                  session_id="s1", project_id="p", error=RuntimeError("x"))
    e = _entries(tmp_path)[-1]
    assert e["event"] == "error" and e["hook"] == "PostToolUse"
    assert e["location"] == "domain_shift.search"
    assert Z_RE.match(e["timestamp"])


def test_every_event_type_uses_utc_z(arl, tmp_path):
    lg = arl.get_relevance_logger()
    lg.log_search_metrics(hook="UserPromptSubmit", session_id="s", user_prompt="p",
                          search_query="q", patterns_returned=[], patterns_injected=[],
                          domains=[])
    lg.log_domain_shift(session_id="s", from_domain="a", to_domain="b", file_path="f",
                        patterns_found=0, search_succeeded=True)
    lg.log_compact_event(session_id="s")
    lg.log_stop_telemetry(session_id="s", hook_type="Stop", background_tasks_count=0,
                          learn_lock_present=False)
    lg.log_execution_metrics(session_id="s", patterns_used=[], tools_executed=0,
                             state_changing_tools=0, success=True,
                             execution_time_seconds=1.0, learning_sent=False)
    lg.log_hook_error(location="l", session_id="s", project_id="p", hook="Stop",
                      error=ValueError("v"))
    entries = _entries(tmp_path)
    assert len(entries) == 6
    bad = [e["timestamp"] for e in entries if not Z_RE.match(e["timestamp"])]
    assert not bad, f"non-'Z' timestamps: {bad}"


def test_archive_small_log_untouched_no_prev(arl, tmp_path):
    d = tmp_path / ".claude" / "data" / "logs"
    d.mkdir(parents=True)
    log = d / "ace-relevance.jsonl"
    log.write_text('{"event":"search"}\n')
    arl.archive_relevance_log(str(d))
    assert log.read_text() == '{"event":"search"}\n', "startup must NOT wipe the log"
    assert not (d / "ace-relevance.prev.jsonl").exists()
    assert not (d / "ace-relevance.1.jsonl").exists()


def test_archive_rotates_by_size_only(arl, tmp_path):
    d = tmp_path / ".claude" / "data" / "logs"
    d.mkdir(parents=True)
    log = d / "ace-relevance.jsonl"
    with open(log, "wb") as f:
        f.truncate(50 * 1024 * 1024 + 1)  # sparse > 50 MB
    arl.archive_relevance_log(str(d))
    assert (d / "ace-relevance.1.jsonl").exists()
    assert not (d / "ace-relevance.prev.jsonl").exists()
    assert not log.exists() or log.stat().st_size == 0
