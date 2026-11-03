#!/usr/bin/env python3
"""
TDD RED tests — v7.1.2 Change A: PreToolUse domain-shift SESSION PINNING.

Design (from session_reuse_design in the v7.1.2 spec):
  - patterns_used_state.__main__ CLI must accept:
      --read-task-session-id flag: read state file for (session, agent-id),
        print task_session_id to stdout (or empty string if absent), exit 0
        WITHOUT writing.
      --task-session-id <value> flag: pass the value into append_patterns_used
        (stored in state file alongside pattern IDs).
  - the removed v7 PreToolUse wrapper must:
      (1) before searching, read EXISTING_TSID from state file via
          patterns_used_state.py --read-task-session-id
      (2) if non-empty, pass --pin-session $EXISTING_TSID to ace-cli search
      (3) pass --task-session-id $EXISTING_TSID on the append call so the
          state file keeps the same task_session_id (idempotent)
      (4) if EXISTING_TSID is empty, generate a fresh uuid4 and use that

These tests exercise:
  A1. __main__ --read-task-session-id flag in patterns_used_state.py
  A2. __main__ --task-session-id flag stores value via append
  (A3/A4 moved to tests/test_domain_shift_py.py in v8 / WP-D)
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
UTILS = REPO / "plugins" / "ace" / "shared-hooks" / "utils"
PLUGIN_UTILS = REPO / "plugins" / "ace" / "utils"

sys.path.insert(0, str(UTILS))
sys.path.insert(0, str(PLUGIN_UTILS))

import patterns_used_state as pus  # noqa: E402

SESSION = "cc-session-pinning-test-abc123"
AGENT_ID = "sub-agent-pinning-11111111-2222-3333"
TASK_SESSION = "tttt-pinning-1111-2222-3333-4444-5555"
PID_A = "ctx-4338628010-5127"
PID_B = "ctx-6257961166-f081"

PUS_SCRIPT = UTILS / "patterns_used_state.py"


# ════════════════════════════════════════════════════════════════════════════
# A1. __main__ --read-task-session-id flag
# ════════════════════════════════════════════════════════════════════════════

class TestReadTaskSessionIdCLI:
    """patterns_used_state.py __main__ must support --read-task-session-id."""

    def test_read_flag_prints_task_session_id(self, tmp_path):
        """--read-task-session-id prints stored task_session_id to stdout."""
        # Write a state file with a task_session_id
        pus.append_patterns_used(
            SESSION, None, [PID_A],
            state_dir=str(tmp_path),
            task_session_id=TASK_SESSION,
        )
        result = subprocess.run(
            [
                sys.executable, str(PUS_SCRIPT),
                "--session", SESSION,
                "--agent-id", "",
                "--state-dir", str(tmp_path),
                "--read-task-session-id",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"--read-task-session-id must exit 0; got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        printed = result.stdout.strip()
        assert printed == TASK_SESSION, (
            f"Expected stdout={TASK_SESSION!r}, got {printed!r}"
        )

    def test_read_flag_prints_empty_when_no_state_file(self, tmp_path):
        """--read-task-session-id prints empty string when no state file exists."""
        result = subprocess.run(
            [
                sys.executable, str(PUS_SCRIPT),
                "--session", SESSION,
                "--agent-id", "",
                "--state-dir", str(tmp_path),
                "--read-task-session-id",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"Must exit 0 even when state file absent; stderr: {result.stderr}"
        )
        printed = result.stdout.strip()
        assert printed == "", (
            f"Expected empty string when no state file; got {printed!r}"
        )

    def test_read_flag_prints_empty_for_legacy_file(self, tmp_path):
        """--read-task-session-id prints empty string for legacy bare-list state file."""
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps([PID_A]))  # legacy bare list
        result = subprocess.run(
            [
                sys.executable, str(PUS_SCRIPT),
                "--session", SESSION,
                "--agent-id", "",
                "--state-dir", str(tmp_path),
                "--read-task-session-id",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        printed = result.stdout.strip()
        assert printed == "", (
            f"Legacy file has no task_session_id; expected empty, got {printed!r}"
        )

    def test_read_flag_does_not_write_or_unlink(self, tmp_path):
        """--read-task-session-id must NOT write or unlink the state file."""
        pus.append_patterns_used(
            SESSION, None, [PID_A],
            state_dir=str(tmp_path),
            task_session_id=TASK_SESSION,
        )
        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        mtime_before = sf.stat().st_mtime

        subprocess.run(
            [
                sys.executable, str(PUS_SCRIPT),
                "--session", SESSION,
                "--agent-id", "",
                "--state-dir", str(tmp_path),
                "--read-task-session-id",
            ],
            capture_output=True, text=True,
        )
        assert sf.exists(), "--read-task-session-id must not unlink the state file"
        mtime_after = sf.stat().st_mtime
        assert mtime_after == mtime_before, (
            "--read-task-session-id must not write/modify the state file"
        )

    def test_read_flag_subagent_routes_to_agent_file(self, tmp_path):
        """--read-task-session-id with --agent-id reads the agent-specific file."""
        pus.append_patterns_used(
            SESSION, AGENT_ID, [PID_A],
            state_dir=str(tmp_path),
            task_session_id=TASK_SESSION,
        )
        # Also write a 'main' file with different tsid to ensure routing
        pus.append_patterns_used(
            SESSION, None, [PID_B],
            state_dir=str(tmp_path),
            task_session_id="main-tsid-different",
        )
        result = subprocess.run(
            [
                sys.executable, str(PUS_SCRIPT),
                "--session", SESSION,
                "--agent-id", AGENT_ID,
                "--state-dir", str(tmp_path),
                "--read-task-session-id",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        printed = result.stdout.strip()
        assert printed == TASK_SESSION, (
            f"--agent-id routing: expected {TASK_SESSION!r}, got {printed!r}"
        )


# ════════════════════════════════════════════════════════════════════════════
# A2. __main__ --task-session-id flag stores value via append
# ════════════════════════════════════════════════════════════════════════════

class TestTaskSessionIdCLIAppend:
    """--task-session-id flag passes value into append_patterns_used."""

    def _run_append(self, tmp_path, search_result, task_session_id=None,
                    session=SESSION, agent_id=""):
        """Call __main__ with stdin=search_result JSON, optionally passing --task-session-id."""
        cmd = [
            sys.executable, str(PUS_SCRIPT),
            "--session", session,
            "--agent-id", agent_id,
            "--state-dir", str(tmp_path),
        ]
        if task_session_id:
            cmd += ["--task-session-id", task_session_id]
        result = subprocess.run(
            cmd,
            input=json.dumps(search_result),
            capture_output=True, text=True,
        )
        return result

    def test_task_session_id_flag_stored_in_state_file(self, tmp_path):
        """--task-session-id <value> causes that value to appear in state file."""
        search_result = {
            "similar_patterns": [
                {"id": PID_A, "match_factors": {"retrieval_log_id": 42}},
            ],
            "retrieval_id": "ret-abc-001",
        }
        result = self._run_append(tmp_path, search_result, task_session_id=TASK_SESSION)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        assert sf.exists(), "State file must be written when patterns present"
        data = json.loads(sf.read_text())
        assert data.get("task_session_id") == TASK_SESSION, (
            f"--task-session-id value must appear in state file; got {data!r}"
        )

    def test_no_task_session_id_flag_leaves_existing_value(self, tmp_path):
        """Without --task-session-id, existing task_session_id in state is preserved."""
        # First call: write state with task_session_id
        pus.append_patterns_used(
            SESSION, None, [PID_A],
            state_dir=str(tmp_path),
            task_session_id=TASK_SESSION,
        )
        # Second call: append more patterns WITHOUT --task-session-id
        search_result = {
            "similar_patterns": [
                {"id": PID_B, "match_factors": {}},
            ],
        }
        result = self._run_append(tmp_path, search_result)
        assert result.returncode == 0

        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        data = json.loads(sf.read_text())
        # Existing task_session_id must be preserved (not cleared to None)
        assert data.get("task_session_id") == TASK_SESSION, (
            f"Existing task_session_id must be preserved when flag absent; got {data!r}"
        )

    def test_task_session_id_flag_overrides_existing(self, tmp_path):
        """--task-session-id with a new value updates state file (new value wins)."""
        new_tsid = str(uuid.uuid4())
        pus.append_patterns_used(
            SESSION, None, [PID_A],
            state_dir=str(tmp_path),
            task_session_id=TASK_SESSION,
        )
        search_result = {
            "similar_patterns": [{"id": PID_B, "match_factors": {}}],
        }
        result = self._run_append(tmp_path, search_result, task_session_id=new_tsid)
        assert result.returncode == 0

        sf = pus.state_file_path(SESSION, None, state_dir=str(tmp_path))
        data = json.loads(sf.read_text())
        assert data.get("task_session_id") == new_tsid, (
            f"--task-session-id new value must override existing; got {data!r}"
        )


# A3/A4 (bash wrapper pin-session tests) were removed in v8 (WP-D): the
# PreToolUse wrapper is deleted and the PostToolUse domain shift is a Python
# port. Its pin-session reuse / fresh-uuid seeding is pinned behaviorally in
# tests/test_domain_shift_py.py (test_domain_shift_pins_existing_task_session_id,
# test_domain_shift_seeds_fresh_task_session_id_when_state_has_none).
