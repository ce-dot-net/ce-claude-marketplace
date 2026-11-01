#!/usr/bin/env python3
"""Tests for background_tasks telemetry (CC v2.1.145 Stop/SubagentStop field).

ADDITIVE ONLY: verifies that the new ``log_stop_telemetry`` helper records the
count of CC-managed background tasks present at session-stop time, plus the
in-flight learn-lock state, into the canonical ace-relevance.jsonl sink.

Telemetry only: it never gates learning. These tests assert the payload
shape and graceful degradation of the logger helper.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(
    0, str(REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "utils")
)

import ace_relevance_logger  # noqa: E402
from ace_relevance_logger import ACERelevanceLogger  # noqa: E402

@pytest.fixture
def tmp_logger(tmp_path, monkeypatch):
    log_dir = tmp_path / ".claude" / "data" / "logs"
    logger = ACERelevanceLogger(log_dir=str(log_dir))
    monkeypatch.setattr(ace_relevance_logger, "_logger", logger)
    return logger


def _read_entries(logger):
    with open(logger.log_path) as f:
        return [json.loads(line) for line in f if line.strip()]


# ── Unit: log_stop_telemetry helper ─────────────────────────────────────────

def test_logs_stop_telemetry_event(tmp_logger):
    tmp_logger.log_stop_telemetry(
        session_id="sess-1",
        hook_type="Stop",
        background_tasks_count=2,
        learn_lock_present=True,
        learn_lock_age_seconds=5,
    )
    entries = _read_entries(tmp_logger)
    assert len(entries) == 1
    e = entries[0]
    assert e["event"] == "hook_stop_telemetry"
    assert e["hook_type"] == "Stop"
    assert e["background_tasks_count"] == 2
    assert e["learn_lock_present"] is True
    assert e["learn_lock_age_seconds"] == 5
    assert e["session_id"] == "sess-1"
    assert "timestamp" in e


def test_subagent_stop_hook_type(tmp_logger):
    tmp_logger.log_stop_telemetry(
        session_id="sess-2",
        hook_type="SubagentStop",
        background_tasks_count=0,
        learn_lock_present=False,
        learn_lock_age_seconds=None,
    )
    e = _read_entries(tmp_logger)[0]
    assert e["hook_type"] == "SubagentStop"
    assert e["background_tasks_count"] == 0
    assert e["learn_lock_present"] is False
    # None age is preserved (lock absent → no age)
    assert e["learn_lock_age_seconds"] is None


def test_count_defaults_to_zero_when_field_absent(tmp_logger):
    # Simulates old CC (<2.1.145): background_tasks field missing → count 0.
    tmp_logger.log_stop_telemetry(
        session_id="sess-3",
        hook_type="Stop",
        background_tasks_count=0,
        learn_lock_present=False,
    )
    e = _read_entries(tmp_logger)[0]
    assert e["background_tasks_count"] == 0


def test_multiple_background_tasks(tmp_logger):
    tmp_logger.log_stop_telemetry(
        session_id="sess-4",
        hook_type="SubagentStop",
        background_tasks_count=3,
        learn_lock_present=True,
        learn_lock_age_seconds=1,
    )
    e = _read_entries(tmp_logger)[0]
    assert e["background_tasks_count"] == 3


def test_module_convenience_function_exists():
    # Convenience wrapper mirrors the other log_* helpers.
    assert hasattr(ace_relevance_logger, "log_stop_telemetry")
    ace_relevance_logger.log_stop_telemetry(
        session_id="x",
        hook_type="Stop",
        background_tasks_count=0,
        learn_lock_present=False,
    )  # must not raise


def test_never_raises_on_bad_input(tmp_logger):
    # Telemetry must never throw and break the hook (risk #3).
    tmp_logger.log_stop_telemetry(
        session_id=None,
        hook_type="Stop",
        background_tasks_count=None,  # malformed
        learn_lock_present=None,
    )  # must not raise


# v8 (DESIGN §6 WP-C): the bash-wrapper lock/BG_TASK_COUNT static guards were
# removed — wrappers are thin shims; the real-lock telemetry is pinned by
# tests/test_stop_v8.py::test_stop_telemetry_reports_real_learn_lock.


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
