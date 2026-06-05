#!/usr/bin/env python3
"""Tests for background_tasks telemetry (CC v2.1.145 Stop/SubagentStop field).

ADDITIVE ONLY: verifies that the new ``log_stop_telemetry`` helper records the
count of CC-managed background tasks present at session-stop time, plus the
in-flight learn-lock state, into the canonical ace-relevance.jsonl sink.

CRITICAL invariant under test: this is telemetry only. It must NEVER influence
the /tmp/ace-learn-inflight-{SESSION_ID}.lock mechanism or PreCompact blocking.
The lock is verified-working and lives entirely in the bash wrappers; these
tests only assert the telemetry payload shape and graceful degradation.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(
    0, str(REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "utils")
)

import ace_relevance_logger  # noqa: E402
from ace_relevance_logger import ACERelevanceLogger  # noqa: E402

STOP_WRAPPER = (
    REPO_ROOT / "plugins" / "ace" / "scripts" / "ace_stop_wrapper.sh"
)
SUBAGENT_WRAPPER = (
    REPO_ROOT / "plugins" / "ace" / "scripts" / "ace_subagent_stop_wrapper.sh"
)
PRECOMPACT_WRAPPER = (
    REPO_ROOT / "plugins" / "ace" / "scripts" / "ace_precompact_wrapper.sh"
)


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


# ── Static guard: lock mechanism MUST remain intact (regression) ─────────────

def test_stop_wrapper_still_creates_learn_lock():
    src = STOP_WRAPPER.read_text()
    assert 'LEARN_LOCK="/tmp/ace-learn-inflight-${SESSION_ID:-unknown}.lock"' in src
    assert 'touch "$LEARN_LOCK"' in src
    # cleanup still present in bg subshell
    assert '"$LEARN_LOCK"' in src and 'rm -f "$TEMP_INPUT" "$TEMP_OUTPUT" "$LEARN_LOCK"' in src


def test_subagent_wrapper_still_creates_learn_lock():
    src = SUBAGENT_WRAPPER.read_text()
    assert 'LEARN_LOCK="/tmp/ace-learn-inflight-${_ASID}.lock"' in src
    assert 'touch "$LEARN_LOCK"' in src
    assert 'rm -f "$TEMP_INPUT" "$LEARN_LOCK"' in src


def test_precompact_still_blocks_on_lock():
    src = PRECOMPACT_WRAPPER.read_text()
    assert 'LEARN_LOCK="/tmp/ace-learn-inflight-${SESSION_ID}.lock"' in src
    assert 'find "$LEARN_LOCK" -mmin -10' in src
    assert '"decision": "block"' in src or 'decision: "block"' in src
    assert "exit 2" in src


# ── Static guard: wrappers extract background_tasks count additively ─────────

def test_stop_wrapper_extracts_background_tasks_count():
    src = STOP_WRAPPER.read_text()
    assert "background_tasks" in src
    assert "BG_TASK_COUNT" in src
    # additive: must not gate any decision on the count
    assert "log_stop_telemetry" in src


def test_subagent_wrapper_extracts_background_tasks_count():
    src = SUBAGENT_WRAPPER.read_text()
    assert "background_tasks" in src
    assert "BG_TASK_COUNT" in src
    assert "log_stop_telemetry" in src


def test_background_tasks_extraction_does_not_set_exit_on_failure():
    # jq parse of background_tasks must be guarded with `|| echo "0"` so a
    # malformed/null field cannot abort the Stop hook (risk #3 + set -e).
    for w in (STOP_WRAPPER, SUBAGENT_WRAPPER):
        src = w.read_text()
        # the extraction line must tolerate failure
        line = [ln for ln in src.splitlines() if "BG_TASK_COUNT=" in ln and "background_tasks" in ln]
        assert line, f"no BG_TASK_COUNT extraction in {w.name}"
        assert "|| echo" in line[0], f"BG_TASK_COUNT extraction in {w.name} not failure-guarded"


# ── jq behaviour: length on array regardless of element shape ────────────────

@pytest.mark.parametrize(
    "payload,expected",
    [
        ('{"background_tasks": []}', "0"),
        ('{"background_tasks": [{"id": "a"}]}', "1"),
        ('{"background_tasks": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}', "3"),
        ('{"no_field": true}', "0"),
        ('{"background_tasks": null}', "0"),
    ],
)
def test_jq_length_extraction(payload, expected):
    # Mirrors the exact bash extraction expression so element schema is irrelevant.
    cmd = (
        "echo '%s' | jq '.background_tasks | length // 0' 2>/dev/null || echo \"0\""
        % payload
    )
    out = subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True
    ).stdout.strip()
    assert out == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
