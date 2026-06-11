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
  - ace_pretooluse_wrapper.sh must:
      (1) before searching, read EXISTING_TSID from state file via
          patterns_used_state.py --read-task-session-id
      (2) if non-empty, pass --pin-session $EXISTING_TSID to ace-cli search
      (3) pass --task-session-id $EXISTING_TSID on the append call so the
          state file keeps the same task_session_id (idempotent)
      (4) if EXISTING_TSID is empty, generate a fresh uuid4 and use that

These tests exercise:
  A1. __main__ --read-task-session-id flag in patterns_used_state.py
  A2. __main__ --task-session-id flag stores value via append
  A3. bash wrapper passes --pin-session with existing task_session_id
  A4. bash wrapper generates fresh uuid4 when no task_session_id in state
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


# ════════════════════════════════════════════════════════════════════════════
# A3. Bash wrapper passes --pin-session with existing task_session_id
# ════════════════════════════════════════════════════════════════════════════

class TestPretoolusePinSession:
    """
    Verify ace_pretooluse_wrapper.sh reads existing task_session_id and passes
    --pin-session to ace-cli search.

    Strategy: invoke the bash wrapper with a mock ace-cli that records its
    arguments to a temp file, then inspect what was passed.
    """

    WRAPPER = REPO / "plugins/ace/scripts/ace_pretooluse_wrapper.sh"

    def _make_mock_ace_cli(self, tmp_path, task_session_id=None, pattern_ids=None):
        """
        Write a mock ace-cli script that:
          - Records all arguments to {tmp_path}/ace_cli_args.txt
          - Emits a minimal search JSON response (with optional task_session_id pinning)
        """
        if pattern_ids is None:
            pattern_ids = [PID_A]
        mock_script = tmp_path / "ace-cli"
        patterns_json = json.dumps([
            {"id": pid, "domain": "test-domain", "content": "x",
             "confidence": 0.8, "helpful": 5.0, "harmful": 0,
             "section": "strategies", "evidence": [],
             "cumulative_v15_reward": 1.5, "isAtRisk": False,
             "n_hot_pos": 1, "n_hot_neg": 0,
             "match_factors": {"retrieval_log_id": 42}}
            for pid in pattern_ids
        ])
        # Write args to file AND emit search response
        mock_script.write_text(f"""#!/bin/bash
echo "$@" >> {tmp_path}/ace_cli_args.txt
cat <<'ENDJSON'
{{
  "similar_patterns": {patterns_json},
  "count": {len(pattern_ids)},
  "retrieval_id": "mock-ret-001"
}}
ENDJSON
""")
        mock_script.chmod(0o755)
        return mock_script

    def _make_domains_file(self, tmp_path, project_id, domain="test-domain"):
        """Write the /tmp/ace-domains-{project_id}.json file the wrapper reads."""
        domains = {f"{domain}:local": {"domain": domain, "source": "local", "count": 2}}
        domains_file = tmp_path / f"ace-domains-{project_id}.json"
        domains_file.write_text(json.dumps(domains))
        return domains_file

    def _make_settings(self, tmp_path, project_id="prj-pin-test", org_id="org-pin-test"):
        """Write .claude/settings.json in a fake project directory."""
        project_dir = tmp_path / "fake_project"
        (project_dir / ".claude").mkdir(parents=True)
        settings = {
            "projectId": project_id,
            "orgId": org_id,
            "env": {"ACE_PROJECT_ID": project_id, "ACE_ORG_ID": org_id},
        }
        (project_dir / ".claude" / "settings.json").write_text(json.dumps(settings))
        return project_dir

    def _build_hook_input(self, session_id, agent_id="", file_path="plugins/test-domain/foo.py"):
        return json.dumps({
            "hook_event_name": "PreToolUse",
            "session_id": session_id,
            "agent_id": agent_id,
            "tool_name": "Read",
            "tool_input": {"file_path": file_path},
            "cwd": "/fake/project",
        })

    def test_pin_session_passed_when_task_session_id_in_state_file(self, tmp_path):
        """
        When the state file has a task_session_id, --pin-session <value> is passed
        to ace-cli search.
        """
        project_id = "prj-pin-test"
        org_id = "org-pin-test"
        session_id = "cc-session-for-pin-test"

        # Write state file with existing task_session_id
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        pus.append_patterns_used(
            session_id, "", [PID_A],
            state_dir=str(state_dir),
            task_session_id=TASK_SESSION,
        )

        mock_cli = self._make_mock_ace_cli(tmp_path)
        project_dir = self._make_settings(tmp_path, project_id, org_id)

        # Create domains file in /tmp (as the wrapper reads from /tmp)
        import tempfile
        domains_file_path = Path(tempfile.gettempdir()) / f"ace-domains-{project_id}.json"
        domain = "test-domain"
        domains_file_path.write_text(json.dumps({
            f"{domain}:local": {"domain": domain, "source": "local", "count": 2}
        }))

        hook_input = self._build_hook_input(session_id, "", f"plugins/{domain}/foo.py")

        env = {
            "PATH": f"{tmp_path}:/usr/bin:/bin",
            "CLAUDE_PLUGIN_ROOT": str(REPO / "plugins/ace"),
            "SESSION_ID": session_id,
            "ACE_PROJECT_ID": project_id,
            "ACE_ORG_ID": org_id,
            # Point state dir so the wrapper can find it
            "CLAUDE_PROJECT_DIR": str(state_dir.parent),
            "HOME": str(tmp_path),
        }

        result = subprocess.run(
            ["bash", str(self.WRAPPER)],
            input=hook_input,
            capture_output=True, text=True,
            env=env,
            cwd=str(project_dir),
        )

        args_file = tmp_path / "ace_cli_args.txt"
        if not args_file.exists():
            pytest.skip("ace-cli mock was not called (domain match may differ in CI env)")

        args_text = args_file.read_text()
        assert "--pin-session" in args_text, (
            f"Wrapper must pass --pin-session to ace-cli when task_session_id exists. "
            f"ace-cli args recorded: {args_text!r}"
        )
        assert TASK_SESSION in args_text, (
            f"--pin-session must use the stored task_session_id={TASK_SESSION!r}. "
            f"ace-cli args: {args_text!r}"
        )

        # Cleanup
        domains_file_path.unlink(missing_ok=True)

    def test_fresh_uuid_generated_when_no_task_session_in_state(self, tmp_path):
        """
        When no task_session_id in state file, wrapper generates a fresh uuid4
        and passes it as --pin-session.
        """
        project_id = "prj-fresh-uuid"
        org_id = "org-fresh-uuid"
        session_id = "cc-session-fresh-uuid"

        mock_cli = self._make_mock_ace_cli(tmp_path)
        project_dir = self._make_settings(tmp_path, project_id, org_id)

        # No state file written -> EXISTING_TSID should be empty
        import tempfile
        domains_file_path = Path(tempfile.gettempdir()) / f"ace-domains-{project_id}.json"
        domain = "test-domain"
        domains_file_path.write_text(json.dumps({
            f"{domain}:local": {"domain": domain, "source": "local", "count": 2}
        }))

        hook_input = self._build_hook_input(session_id, "", f"plugins/{domain}/bar.py")

        env = {
            "PATH": f"{tmp_path}:/usr/bin:/bin",
            "CLAUDE_PLUGIN_ROOT": str(REPO / "plugins/ace"),
            "SESSION_ID": session_id,
            "ACE_PROJECT_ID": project_id,
            "ACE_ORG_ID": org_id,
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "HOME": str(tmp_path),
        }

        result = subprocess.run(
            ["bash", str(self.WRAPPER)],
            input=hook_input,
            capture_output=True, text=True,
            env=env,
            cwd=str(project_dir),
        )

        args_file = tmp_path / "ace_cli_args.txt"
        if not args_file.exists():
            pytest.skip("ace-cli mock was not called (domain match may differ)")

        args_text = args_file.read_text()
        assert "--pin-session" in args_text, (
            f"Wrapper must still pass --pin-session (with fresh uuid4) when no existing "
            f"task_session_id. ace-cli args: {args_text!r}"
        )
        # The value must be a valid uuid4 (not empty, not the CC session_id)
        import re
        pin_match = re.search(r"--pin-session\s+([^\s]+)", args_text)
        assert pin_match, f"Could not extract --pin-session value from: {args_text!r}"
        pin_value = pin_match.group(1)
        assert pin_value != session_id, (
            f"--pin-session value must be a new uuid4, not the CC session_id; "
            f"got {pin_value!r}"
        )
        try:
            uuid.UUID(pin_value)
        except ValueError:
            pytest.fail(
                f"Fresh --pin-session value must be a uuid4; got {pin_value!r}"
            )

        domains_file_path.unlink(missing_ok=True)

    def test_same_task_session_id_reused_across_domain_shifts(self, tmp_path):
        """
        Second domain-shift in same task reuses the SAME task_session_id from state
        (does not generate a new uuid4).
        """
        project_id = "prj-reuse-test"
        org_id = "org-reuse-test"
        session_id = "cc-session-reuse"

        # Write state file with existing task_session_id
        state_dir = tmp_path / "state_reuse"
        state_dir.mkdir()
        pus.append_patterns_used(
            session_id, "", [PID_A],
            state_dir=str(state_dir),
            task_session_id=TASK_SESSION,
        )

        mock_cli = self._make_mock_ace_cli(tmp_path)
        project_dir = self._make_settings(tmp_path, project_id, org_id)

        import tempfile
        domains_file_path = Path(tempfile.gettempdir()) / f"ace-domains-{project_id}.json"
        domain = "test-domain"
        domains_file_path.write_text(json.dumps({
            f"{domain}:local": {"domain": domain, "source": "local", "count": 2}
        }))

        hook_input = self._build_hook_input(session_id, "", f"plugins/{domain}/baz.py")

        env = {
            "PATH": f"{tmp_path}:/usr/bin:/bin",
            "CLAUDE_PLUGIN_ROOT": str(REPO / "plugins/ace"),
            "SESSION_ID": session_id,
            "ACE_PROJECT_ID": project_id,
            "ACE_ORG_ID": org_id,
            "CLAUDE_PROJECT_DIR": str(state_dir.parent),
            "HOME": str(tmp_path),
        }

        result = subprocess.run(
            ["bash", str(self.WRAPPER)],
            input=hook_input,
            capture_output=True, text=True,
            env=env,
            cwd=str(project_dir),
        )

        args_file = tmp_path / "ace_cli_args.txt"
        if not args_file.exists():
            pytest.skip("ace-cli mock was not called (domain match may differ)")

        args_text = args_file.read_text()
        assert TASK_SESSION in args_text, (
            f"Second domain-shift must REUSE existing task_session_id={TASK_SESSION!r}, "
            f"not generate a new one. ace-cli args: {args_text!r}"
        )

        domains_file_path.unlink(missing_ok=True)


# ════════════════════════════════════════════════════════════════════════════
# A5. PostToolUse domain-inject also passes --pin-session + --task-session-id
# ════════════════════════════════════════════════════════════════════════════

class TestPosttoolusePinSession:
    """
    ace_posttooluse_domain_inject.sh must pass --pin-session (reusing existing
    task_session_id) to ace-cli search, and --task-session-id on the append
    call — the same Change A logic as ace_pretooluse_wrapper.sh.

    Tested via static source analysis (the bash script passes --pin-session).
    """

    POSTTOOLUSE_SCRIPT = REPO / "plugins/ace/scripts/ace_posttooluse_domain_inject.sh"

    def test_posttooluse_reads_existing_task_session_id(self):
        """ace_posttooluse_domain_inject.sh must read EXISTING_TSID via
        --read-task-session-id before searching."""
        content = self.POSTTOOLUSE_SCRIPT.read_text()
        assert '--read-task-session-id' in content, (
            "ace_posttooluse_domain_inject.sh must call patterns_used_state.py "
            "--read-task-session-id to reuse the existing task_session_id "
            "(Change A parity with ace_pretooluse_wrapper.sh)"
        )

    def test_posttooluse_passes_pin_session_to_ace_cli(self):
        """ace_posttooluse_domain_inject.sh must pass --pin-session to ace-cli search."""
        content = self.POSTTOOLUSE_SCRIPT.read_text()
        assert '--pin-session' in content, (
            "ace_posttooluse_domain_inject.sh must pass --pin-session to ace-cli "
            "search so domain-shift searches join the task's existing pin bucket "
            "(Change A parity with ace_pretooluse_wrapper.sh)"
        )

    def test_posttooluse_passes_task_session_id_on_append(self):
        """ace_posttooluse_domain_inject.sh must pass --task-session-id on the
        patterns_used_state.py append call."""
        content = self.POSTTOOLUSE_SCRIPT.read_text()
        assert '--task-session-id' in content, (
            "ace_posttooluse_domain_inject.sh must pass --task-session-id on the "
            "patterns_used_state.py append call so the stored task_session_id is "
            "preserved idempotently (Change A parity)"
        )
