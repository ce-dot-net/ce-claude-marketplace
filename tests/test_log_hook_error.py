#!/usr/bin/env python3
"""Tests for log_hook_error helper in ace_relevance_logger."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add plugin shared-hooks/utils to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(
    0, str(REPO_ROOT / "plugins" / "ace" / "shared-hooks" / "utils")
)

import ace_relevance_logger  # noqa: E402
from ace_relevance_logger import ACERelevanceLogger  # noqa: E402


@pytest.fixture
def tmp_logger(tmp_path, monkeypatch):
    """Create an ACERelevanceLogger rooted in a tmp dir and reset singleton."""
    log_dir = tmp_path / ".claude" / "data" / "logs"
    logger = ACERelevanceLogger(log_dir=str(log_dir))
    monkeypatch.setattr(ace_relevance_logger, "_logger", logger)
    return logger


def _read_entries(logger):
    with open(logger.log_path) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_basic_writes_error_event(tmp_logger):
    try:
        raise ValueError("boom")
    except ValueError as e:
        ace_relevance_logger.log_hook_error(
            location="module.func:42",
            session_id="sess-1",
            project_id="proj-1",
            hook="UserPromptSubmit",
            error=e,
        )
    entries = _read_entries(tmp_logger)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["event"] == "error"
    assert entry["hook"] == "UserPromptSubmit"
    assert entry["location"] == "module.func:42"
    assert entry["session_id"] == "sess-1"
    assert entry["project_id"] == "proj-1"
    assert entry["error_type"] == "ValueError"
    assert entry["error_message"] == "boom"
    assert "timestamp" in entry


def test_error_message_truncated(tmp_logger):
    long_msg = "x" * 1000
    try:
        raise RuntimeError(long_msg)
    except RuntimeError as e:
        ace_relevance_logger.log_hook_error(
            location="loc", session_id="s", project_id="p",
            hook="Stop", error=e,
        )
    entry = _read_entries(tmp_logger)[0]
    assert len(entry["error_message"]) <= 500


def test_extra_dict_passthrough_without_clobbering(tmp_logger):
    try:
        raise KeyError("k")
    except KeyError as e:
        ace_relevance_logger.log_hook_error(
            location="loc", session_id="s", project_id="p",
            hook="Stop", error=e,
            extra={"custom_field": "v", "hook": "SHOULD_NOT_OVERRIDE"},
        )
    entry = _read_entries(tmp_logger)[0]
    assert entry["custom_field"] == "v"
    # Required fields not clobbered
    assert entry["hook"] == "Stop"
    assert entry["event"] == "error"


def test_parent_dir_created(tmp_path, monkeypatch):
    log_dir = tmp_path / "does" / "not" / "exist" / "logs"
    assert not log_dir.exists()
    logger = ACERelevanceLogger(log_dir=str(log_dir))
    monkeypatch.setattr(ace_relevance_logger, "_logger", logger)
    try:
        raise ValueError("x")
    except ValueError as e:
        ace_relevance_logger.log_hook_error(
            location="l", session_id="s", project_id="p",
            hook="H", error=e,
        )
    assert log_dir.exists()
    assert logger.log_path.exists()


def test_never_raises_on_unwritable(tmp_path, monkeypatch):
    logger = ACERelevanceLogger(log_dir=str(tmp_path))
    monkeypatch.setattr(ace_relevance_logger, "_logger", logger)
    # Force _write_log to blow up to simulate unwritable path
    with patch.object(logger, "_write_log", side_effect=OSError("nope")):
        try:
            raise ValueError("e")
        except ValueError as e:
            # Should not raise
            ace_relevance_logger.log_hook_error(
                location="l", session_id="s", project_id="p",
                hook="H", error=e,
            )


def test_valid_jsonl(tmp_logger):
    for i in range(3):
        try:
            raise ValueError(f"err-{i}")
        except ValueError as e:
            ace_relevance_logger.log_hook_error(
                location=f"l{i}", session_id="s", project_id="p",
                hook="H", error=e,
            )
    with open(tmp_logger.log_path) as f:
        lines = [l for l in f if l.strip()]
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert obj["event"] == "error"


def test_required_fields_present_when_none(tmp_logger):
    try:
        raise ValueError("x")
    except ValueError as e:
        ace_relevance_logger.log_hook_error(
            location="l", session_id=None, project_id=None,
            hook="H", error=e,
        )
    entry = _read_entries(tmp_logger)[0]
    assert "session_id" in entry and entry["session_id"] is None
    assert "project_id" in entry and entry["project_id"] is None


def test_error_type_preserved(tmp_logger):
    class CustomError(Exception):
        pass

    try:
        raise CustomError("msg")
    except CustomError as e:
        ace_relevance_logger.log_hook_error(
            location="l", session_id="s", project_id="p",
            hook="H", error=e,
        )
    entry = _read_entries(tmp_logger)[0]
    assert entry["error_type"] == "CustomError"

    try:
        raise ValueError("v")
    except ValueError as e:
        ace_relevance_logger.log_hook_error(
            location="l", session_id="s", project_id="p",
            hook="H", error=e,
        )
    entry = _read_entries(tmp_logger)[1]
    assert entry["error_type"] == "ValueError"
