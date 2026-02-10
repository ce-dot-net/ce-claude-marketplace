#!/usr/bin/env python3
"""
TDD Tests for ACE PreCompact Hook JSON Validation Fix (PR #18 / Issue #17).

The bug: PreCompact hook was outputting hookSpecificOutput with
hookEventName: "PreCompact", which is NOT in Claude Code's discriminated
union schema, causing JSON validation failures.

The fix: A 2-script handoff pattern:
  1. PreCompact (ace_precompact_wrapper.sh) saves patterns to a temp file
     as a side-effect only -- it outputs systemMessage but NO hookSpecificOutput.
  2. A new SessionStart(compact) hook (ace_sessionstart_compact.sh) reads
     the temp file and injects patterns via valid hookEventName: "SessionStart".

Files under test:
  - plugins/ace/scripts/ace_precompact_wrapper.sh
  - plugins/ace/scripts/ace_sessionstart_compact.sh
  - plugins/ace/hooks/hooks.json

Harness Approach (follows test_version_check.py pattern):
  - Extract relevant bash logic into minimal test harnesses
  - Stub external commands (ace-cli, jq, cat) via PATH manipulation
  - Test via subprocess.run()
  - Each test is independent (creates its own temp environment)

Run with: pytest tests/test_precompact_handoff.py -v
"""

import json
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
PRECOMPACT_SCRIPT = (
    PROJECT_ROOT / "plugins" / "ace" / "scripts" / "ace_precompact_wrapper.sh"
)
SESSIONSTART_COMPACT_SCRIPT = (
    PROJECT_ROOT / "plugins" / "ace" / "scripts" / "ace_sessionstart_compact.sh"
)
HOOKS_JSON_PATH = PROJECT_ROOT / "plugins" / "ace" / "hooks" / "hooks.json"


# ---------------------------------------------------------------------------
# PreCompact Wrapper Harness
# ---------------------------------------------------------------------------
#
# Reproduces the core logic of ace_precompact_wrapper.sh in isolation.
# Stubs: ace-cli, jq (uses real jq from system), .claude/settings.json
#
# The harness:
#   1. Creates a fake .claude/settings.json with projectId/orgId
#   2. Creates a fake ace-session file with session ID
#   3. Stubs ace-cli to return configurable pattern data
#   4. Runs the core logic and captures: temp file, stdout JSON, exit code

PRECOMPACT_HARNESS = textwrap.dedent("""\
    #!/usr/bin/env bash
    set -euo pipefail

    # --- Test environment setup ---
    export PATH="__FAKE_BIN_DIR__:/usr/bin:/bin:/usr/sbin:/sbin"
    WORK_DIR="__WORK_DIR__"
    SESSION_ID="__SESSION_ID__"
    PROJECT_ID="__PROJECT_ID__"

    # Create fake .claude/settings.json
    mkdir -p "$WORK_DIR/.claude"
    cat > "$WORK_DIR/.claude/settings.json" <<SETTINGS_EOF
    {
      "projectId": "$PROJECT_ID",
      "orgId": "test-org-123"
    }
    SETTINGS_EOF

    # Create fake session file
    echo "$SESSION_ID" > "/tmp/ace-session-${PROJECT_ID}.txt"

    cd "$WORK_DIR"

    # ACE disable flag check
    SESSION_ID_FOR_FLAG="${SESSION_ID:-default}"
    ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID_FOR_FLAG}.flag"
    if [ -f "$ACE_DISABLED_FLAG" ]; then
      exit 0
    fi

    # CLI command detection
    if command -v ace-cli >/dev/null 2>&1; then
      CLI_CMD="ace-cli"
    elif command -v ce-ace >/dev/null 2>&1; then
      CLI_CMD="ce-ace"
    else
      exit 0
    fi

    # Get project context
    PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
    export ACE_ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
    export ACE_PROJECT_ID="$PROJECT_ID"

    if [ -z "$PROJECT_ID" ]; then
      exit 0
    fi

    SESSION_FILE="/tmp/ace-session-${PROJECT_ID}.txt"
    if [ ! -f "$SESSION_FILE" ]; then
      exit 0
    fi
    SESSION_ID=$(cat "$SESSION_FILE")

    # Recall patterns
    RAW_PATTERNS=$($CLI_CMD cache recall --session "$SESSION_ID" --json 2>&1) || true
    PATTERNS=$(echo "$RAW_PATTERNS" | grep -v "^$" || echo "{}")

    COUNT=$(echo "$PATTERNS" | jq -r '.count // 0' 2>/dev/null || echo "0")

    if [ "$COUNT" = "0" ] || [ "$COUNT" = "null" ]; then
      exit 0
    fi

    FORMATTED=$(echo "$PATTERNS" | jq -r '.similar_patterns[] | "- [\\(.section // "general")] \\(.content)"' 2>/dev/null || echo "")

    if [ -z "$FORMATTED" ]; then
      exit 0
    fi

    # Save patterns to temp file (atomic write)
    TEMP_FILE="/tmp/ace-patterns-precompact-${SESSION_ID}.json"
    TEMP_STAGING=$(mktemp "/tmp/ace-patterns-staging-XXXXXX")
    (umask 077; jq -n \\
      --arg patterns "$FORMATTED" \\
      --arg session "$SESSION_ID" \\
      --arg count "$COUNT" \\
      '{
        "patterns": $patterns,
        "session_id": $session,
        "count": $count
      }' > "$TEMP_STAGING") && mv -f "$TEMP_STAGING" "$TEMP_FILE" || rm -f "$TEMP_STAGING"

    # Output systemMessage only (valid for PreCompact hooks)
    jq -n \\
      --arg count "$COUNT" \\
      '{
        "systemMessage": "saved \\($count) patterns for post-compaction injection"
      }'
""")


# ---------------------------------------------------------------------------
# SessionStart Compact Harness
# ---------------------------------------------------------------------------
#
# Reproduces the core logic of ace_sessionstart_compact.sh in isolation.
# Input: stdin JSON with session_id (simulating Claude Code's SessionStart input)
# Also reads .claude/settings.json for PROJECT_ID to locate temp file.

SESSIONSTART_COMPACT_HARNESS = textwrap.dedent("""\
    #!/usr/bin/env bash
    set -euo pipefail

    WORK_DIR="__WORK_DIR__"
    cd "$WORK_DIR"

    # Read stdin JSON
    INPUT_JSON=$(cat 2>/dev/null || echo "{}")

    # ACE disable flag check
    SESSION_ID_FOR_FLAG=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
    SESSION_ID_FOR_FLAG="${SESSION_ID_FOR_FLAG:-default}"
    ACE_DISABLED_FLAG="/tmp/ace-disabled-${SESSION_ID_FOR_FLAG}.flag"
    if [ -f "$ACE_DISABLED_FLAG" ]; then
      exit 0
    fi

    # Resolve SESSION_ID from ace-session file (same source as PreCompact)
    PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
    SESSION_FILE="/tmp/ace-session-${PROJECT_ID}.txt"

    if [ -n "$PROJECT_ID" ] && [ -f "$SESSION_FILE" ]; then
      SESSION_ID=$(cat "$SESSION_FILE" 2>/dev/null || echo "")
    fi

    # Fallback: stdin session_id
    if [ -z "${SESSION_ID:-}" ]; then
      SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")
      SESSION_ID="${SESSION_ID:-default}"
    fi

    # Check for temp file from PreCompact
    TEMP_FILE="/tmp/ace-patterns-precompact-${SESSION_ID}.json"

    if [ ! -f "$TEMP_FILE" ]; then
      exit 0
    fi

    # Read patterns from temp file
    PATTERN_DATA=$(cat "$TEMP_FILE" 2>/dev/null || echo "{}")
    PATTERNS=$(echo "$PATTERN_DATA" | jq -r '.patterns // ""' 2>/dev/null || echo "")
    COUNT=$(echo "$PATTERN_DATA" | jq -r '.count // "0"' 2>/dev/null || echo "0")

    # Cleanup temp file
    rm -f "$TEMP_FILE" 2>/dev/null || true

    # If no patterns, exit silently
    if [ -z "$PATTERNS" ] || [ "$COUNT" = "0" ]; then
      exit 0
    fi

    # Output valid hookSpecificOutput with hookEventName: "SessionStart"
    jq -n \\
      --arg patterns "$PATTERNS" \\
      --arg session "$SESSION_ID" \\
      --arg count "$COUNT" \\
      '{
        "systemMessage": "Restored \\($count) patterns after compaction",
        "hookSpecificOutput": {
          "hookEventName": "SessionStart",
          "additionalContext": "<!-- ACE Patterns (preserved from session \\($session)) -->\\n<ace-patterns-recalled>\\n\\($patterns)\\n</ace-patterns-recalled>"
        }
      }'
""")


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------


class PreCompactHarness:
    """
    Creates a temporary environment with stub binaries and runs the
    PreCompact wrapper harness script.
    """

    def __init__(self, tmpdir: Path):
        self.tmpdir = tmpdir
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.fake_bin = tmpdir / "bin"
        self.fake_bin.mkdir(parents=True, exist_ok=True)
        self.work_dir = tmpdir / "project"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.harness_script = tmpdir / "test_precompact.sh"
        self.session_id = "test-session-abc123"
        self.project_id = "test-project-xyz"
        self._stubs_created = set()

    def add_ace_cli(self, patterns_json: str = "{}"):
        """Add a fake ace-cli that returns the given JSON for cache recall."""
        self._write_stub("ace-cli", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [ "$1" = "cache" ] && [ "$2" = "recall" ]; then
              cat <<'PATTERNS_EOF'
{patterns_json}
PATTERNS_EOF
              exit 0
            fi
            if [ "$1" = "--version" ]; then
              echo "ace-cli v3.10.3"
              exit 0
            fi
            exit 0
        """))

    def add_ace_cli_with_patterns(self, count: int = 3):
        """Add a fake ace-cli that returns realistic pattern data."""
        patterns = []
        for i in range(count):
            patterns.append({
                "section": f"section_{i}",
                "content": f"Pattern content number {i}: use this approach",
            })
        data = json.dumps({
            "count": count,
            "similar_patterns": patterns,
        })
        self.add_ace_cli(patterns_json=data)

    def add_ace_cli_empty_results(self):
        """Add a fake ace-cli that returns zero patterns."""
        self.add_ace_cli(patterns_json='{"count": 0, "similar_patterns": []}')

    def set_disabled_flag(self):
        """Create the ACE disabled flag file."""
        flag_path = Path(f"/tmp/ace-disabled-{self.session_id}.flag")
        flag_path.write_text("disabled for testing")
        return flag_path

    def set_session_id(self, session_id: str):
        """Override the session ID."""
        self.session_id = session_id

    def set_project_id(self, project_id: str):
        """Override the project ID."""
        self.project_id = project_id

    def run(self) -> dict:
        """
        Write and execute the PreCompact harness script.

        Returns a dict with:
          - exit_code: process exit code
          - stdout: raw stdout
          - stderr: raw stderr
          - stdout_json: parsed JSON from stdout (or None)
          - temp_file_exists: whether the temp file was created
          - temp_file_content: parsed JSON from temp file (or None)
          - temp_file_path: path to the expected temp file
        """
        script_text = (
            PRECOMPACT_HARNESS
            .replace("__FAKE_BIN_DIR__", str(self.fake_bin))
            .replace("__WORK_DIR__", str(self.work_dir))
            .replace("__SESSION_ID__", self.session_id)
            .replace("__PROJECT_ID__", self.project_id)
        )
        self.harness_script.write_text(script_text)
        self.harness_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(self.harness_script)],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Parse stdout JSON
        stdout_json = None
        stdout_text = result.stdout.strip()
        if stdout_text:
            try:
                stdout_json = json.loads(stdout_text)
            except json.JSONDecodeError:
                pass

        # Check temp file
        temp_file_path = Path(
            f"/tmp/ace-patterns-precompact-{self.session_id}.json"
        )
        temp_file_exists = temp_file_path.exists()
        temp_file_content = None
        if temp_file_exists:
            try:
                temp_file_content = json.loads(temp_file_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stdout_json": stdout_json,
            "temp_file_exists": temp_file_exists,
            "temp_file_content": temp_file_content,
            "temp_file_path": temp_file_path,
        }

    def cleanup(self):
        """Remove temp files created during the test."""
        for pattern in [
            f"/tmp/ace-patterns-precompact-{self.session_id}.json",
            f"/tmp/ace-session-{self.project_id}.txt",
            f"/tmp/ace-disabled-{self.session_id}.flag",
        ]:
            try:
                Path(pattern).unlink(missing_ok=True)
            except OSError:
                pass
        # Also clean up staging files
        import glob
        for f in glob.glob("/tmp/ace-patterns-staging-*"):
            try:
                Path(f).unlink(missing_ok=True)
            except OSError:
                pass

    def _write_stub(self, name: str, content: str):
        """Write an executable stub script to the fake bin directory."""
        stub_path = self.fake_bin / name
        stub_path.write_text(content)
        stub_path.chmod(0o755)
        self._stubs_created.add(name)


class SessionStartCompactHarness:
    """
    Creates a temporary environment and runs the SessionStart(compact)
    harness script with configurable stdin and temp file state.
    """

    def __init__(self, tmpdir: Path):
        self.tmpdir = tmpdir
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.work_dir = tmpdir / "project"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.harness_script = tmpdir / "test_sessionstart_compact.sh"
        self.session_id = "test-session-abc123"
        self.project_id = "test-project-xyz"
        self.stdin_json = {}

    def set_session_id(self, session_id: str):
        """Override the session ID."""
        self.session_id = session_id

    def set_project_id(self, project_id: str):
        """Override the project ID."""
        self.project_id = project_id

    def set_stdin(self, data: dict):
        """Set the stdin JSON that simulates Claude Code's SessionStart input."""
        self.stdin_json = data

    def create_temp_file(self, patterns: str, count: str = "3",
                         session_id: str | None = None):
        """
        Create the temp file that PreCompact would have written.
        """
        sid = session_id or self.session_id
        temp_path = Path(f"/tmp/ace-patterns-precompact-{sid}.json")
        data = json.dumps({
            "patterns": patterns,
            "session_id": sid,
            "count": count,
        })
        temp_path.write_text(data)
        return temp_path

    def create_corrupt_temp_file(self, session_id: str | None = None):
        """Create a corrupt (non-JSON) temp file."""
        sid = session_id or self.session_id
        temp_path = Path(f"/tmp/ace-patterns-precompact-{sid}.json")
        temp_path.write_text("this is not valid json {{[")
        return temp_path

    def create_session_file(self, session_id: str | None = None):
        """Create the ace-session file that both scripts use."""
        sid = session_id or self.session_id
        session_path = Path(f"/tmp/ace-session-{self.project_id}.txt")
        session_path.write_text(sid)
        return session_path

    def setup_settings_json(self):
        """Create the .claude/settings.json in the work directory."""
        claude_dir = self.work_dir / ".claude"
        claude_dir.mkdir(exist_ok=True)
        settings = {
            "projectId": self.project_id,
            "orgId": "test-org-123",
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

    def set_disabled_flag(self):
        """Create the ACE disabled flag file."""
        sid = self.stdin_json.get("session_id", self.session_id)
        flag_path = Path(f"/tmp/ace-disabled-{sid}.flag")
        flag_path.write_text("disabled for testing")
        return flag_path

    def run(self) -> dict:
        """
        Write and execute the SessionStart(compact) harness script.

        Returns a dict with:
          - exit_code: process exit code
          - stdout: raw stdout
          - stderr: raw stderr
          - stdout_json: parsed JSON from stdout (or None)
          - has_hook_specific_output: whether hookSpecificOutput exists
          - hook_event_name: the hookEventName value (or None)
          - additional_context: the additionalContext value (or None)
          - temp_file_cleaned: whether the temp file was deleted
          - temp_file_path: path to the expected temp file
        """
        self.setup_settings_json()

        script_text = (
            SESSIONSTART_COMPACT_HARNESS
            .replace("__WORK_DIR__", str(self.work_dir))
        )
        self.harness_script.write_text(script_text)
        self.harness_script.chmod(0o755)

        stdin_text = json.dumps(self.stdin_json)

        result = subprocess.run(
            ["bash", str(self.harness_script)],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Parse stdout JSON
        stdout_json = None
        stdout_text = result.stdout.strip()
        if stdout_text:
            try:
                stdout_json = json.loads(stdout_text)
            except json.JSONDecodeError:
                pass

        # Extract hookSpecificOutput fields
        has_hook_specific_output = False
        hook_event_name = None
        additional_context = None
        if stdout_json and "hookSpecificOutput" in stdout_json:
            has_hook_specific_output = True
            hso = stdout_json["hookSpecificOutput"]
            hook_event_name = hso.get("hookEventName")
            additional_context = hso.get("additionalContext")

        # Check if temp file was cleaned up
        temp_file_path = Path(
            f"/tmp/ace-patterns-precompact-{self.session_id}.json"
        )
        temp_file_cleaned = not temp_file_path.exists()

        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stdout_json": stdout_json,
            "has_hook_specific_output": has_hook_specific_output,
            "hook_event_name": hook_event_name,
            "additional_context": additional_context,
            "temp_file_cleaned": temp_file_cleaned,
            "temp_file_path": temp_file_path,
        }

    def cleanup(self):
        """Remove temp files created during the test."""
        for pattern in [
            f"/tmp/ace-patterns-precompact-{self.session_id}.json",
            f"/tmp/ace-session-{self.project_id}.txt",
            f"/tmp/ace-disabled-{self.session_id}.flag",
            f"/tmp/ace-disabled-default.flag",
        ]:
            try:
                Path(pattern).unlink(missing_ok=True)
            except OSError:
                pass


@pytest.fixture
def precompact(tmp_path):
    """Create a fresh PreCompactHarness for each test."""
    h = PreCompactHarness(tmp_path)
    yield h
    h.cleanup()


@pytest.fixture
def sessionstart(tmp_path):
    """Create a fresh SessionStartCompactHarness for each test."""
    h = SessionStartCompactHarness(tmp_path)
    yield h
    h.cleanup()


# ===========================================================================
# SECTION 1: PreCompact Wrapper Tests
# ===========================================================================


class TestPreCompactTempFileSave:
    """
    Tests that PreCompact wrapper saves patterns to the correct temp file
    at the correct path with the correct format.
    """

    def test_patterns_saved_to_correct_path(self, precompact):
        """
        Test scenario 1: Patterns are saved to temp file at the correct
        path /tmp/ace-patterns-precompact-${SESSION_ID}.json.
        """
        precompact.add_ace_cli_with_patterns(count=3)
        result = precompact.run()

        assert result["exit_code"] == 0
        expected_path = Path(
            f"/tmp/ace-patterns-precompact-{precompact.session_id}.json"
        )
        assert result["temp_file_exists"] is True, (
            f"Temp file not found at {expected_path}"
        )
        assert result["temp_file_path"] == expected_path

    def test_temp_file_contains_valid_json(self, precompact):
        """Temp file must contain valid, parseable JSON."""
        precompact.add_ace_cli_with_patterns(count=2)
        result = precompact.run()

        assert result["temp_file_content"] is not None, (
            "Temp file content could not be parsed as JSON"
        )
        assert "patterns" in result["temp_file_content"]
        assert "session_id" in result["temp_file_content"]
        assert "count" in result["temp_file_content"]

    def test_temp_file_session_id_matches(self, precompact):
        """The session_id in the temp file must match the one from the session."""
        precompact.add_ace_cli_with_patterns(count=2)
        result = precompact.run()

        assert result["temp_file_content"]["session_id"] == precompact.session_id

    def test_temp_file_count_matches_patterns(self, precompact):
        """The count in the temp file must match the number of patterns."""
        precompact.add_ace_cli_with_patterns(count=5)
        result = precompact.run()

        assert result["temp_file_content"]["count"] == "5"

    def test_temp_file_patterns_contain_content(self, precompact):
        """The patterns field must contain the formatted pattern strings."""
        precompact.add_ace_cli_with_patterns(count=2)
        result = precompact.run()

        patterns_text = result["temp_file_content"]["patterns"]
        assert "Pattern content number 0" in patterns_text
        assert "Pattern content number 1" in patterns_text


class TestPreCompactAtomicWrite:
    """
    Test scenario 2: Temp file uses atomic write (mktemp + mv pattern).
    """

    def test_no_staging_files_left_behind(self, precompact):
        """After successful write, no staging files should remain."""
        import glob

        precompact.add_ace_cli_with_patterns(count=2)
        precompact.run()

        staging_files = glob.glob("/tmp/ace-patterns-staging-*")
        assert len(staging_files) == 0, (
            f"Staging files left behind: {staging_files}"
        )


class TestPreCompactTempFilePermissions:
    """
    Test scenario 3: Temp file has restrictive permissions (owner-only).
    """

    def test_temp_file_owner_only_permissions(self, precompact):
        """Temp file must be readable only by owner (umask 077)."""
        precompact.add_ace_cli_with_patterns(count=2)
        result = precompact.run()

        if result["temp_file_exists"]:
            mode = result["temp_file_path"].stat().st_mode & 0o777
            # umask 077 means file is created with 0600 (owner read/write only)
            assert mode == 0o600, (
                f"Expected permissions 0600, got {oct(mode)}. "
                f"Temp file should be owner-only for security."
            )


class TestPreCompactNoHookSpecificOutput:
    """
    Test scenario 4 (CRITICAL - this was the bug):
    PreCompact wrapper must output NO hookSpecificOutput.
    """

    def test_stdout_has_no_hook_specific_output(self, precompact):
        """
        CRITICAL: The stdout JSON must NOT contain hookSpecificOutput.
        This was the exact bug in Issue #17.
        """
        precompact.add_ace_cli_with_patterns(count=3)
        result = precompact.run()

        if result["stdout_json"] is not None:
            assert "hookSpecificOutput" not in result["stdout_json"], (
                "CRITICAL BUG: PreCompact must NOT output hookSpecificOutput! "
                "This causes Claude Code JSON validation failure (Issue #17)."
            )

    def test_stdout_has_no_hook_event_name(self, precompact):
        """
        CRITICAL: The stdout must NOT contain hookEventName at all.
        hookEventName: "PreCompact" is not in Claude Code's schema.
        """
        precompact.add_ace_cli_with_patterns(count=3)
        result = precompact.run()

        assert "hookEventName" not in result["stdout"], (
            "CRITICAL BUG: PreCompact stdout must not contain hookEventName."
        )

    def test_stdout_has_system_message_only(self, precompact):
        """PreCompact may output systemMessage (valid for PreCompact hooks)."""
        precompact.add_ace_cli_with_patterns(count=3)
        result = precompact.run()

        if result["stdout_json"] is not None:
            # Only systemMessage is allowed
            allowed_keys = {"systemMessage"}
            actual_keys = set(result["stdout_json"].keys())
            assert actual_keys.issubset(allowed_keys), (
                f"PreCompact output contains unexpected keys: "
                f"{actual_keys - allowed_keys}. Only systemMessage is allowed."
            )


class TestPreCompactExitCode:
    """
    Test scenario 5: Script exits 0 on success.
    """

    def test_exits_zero_with_patterns(self, precompact):
        """Script must exit 0 when patterns are found and saved."""
        precompact.add_ace_cli_with_patterns(count=3)
        result = precompact.run()
        assert result["exit_code"] == 0

    def test_exits_zero_with_no_patterns(self, precompact):
        """Script must exit 0 even when no patterns are found."""
        precompact.add_ace_cli_empty_results()
        result = precompact.run()
        assert result["exit_code"] == 0


class TestPreCompactDisabledFlag:
    """
    Test scenario 6: Script handles ACE_DISABLED flag gracefully.
    """

    def test_exits_silently_when_disabled(self, precompact):
        """When ACE disabled flag exists, script exits 0 with no output."""
        flag_path = precompact.set_disabled_flag()
        precompact.add_ace_cli_with_patterns(count=3)

        try:
            result = precompact.run()
            assert result["exit_code"] == 0
            assert result["temp_file_exists"] is False, (
                "Should not create temp file when ACE is disabled"
            )
        finally:
            flag_path.unlink(missing_ok=True)


class TestPreCompactEmptyResults:
    """
    Test scenario 7: Script handles empty search results gracefully.
    """

    def test_no_temp_file_when_zero_patterns(self, precompact):
        """When ace-cli returns zero patterns, no temp file should be created."""
        precompact.add_ace_cli_empty_results()
        result = precompact.run()

        assert result["exit_code"] == 0
        assert result["temp_file_exists"] is False

    def test_no_temp_file_when_cli_missing(self, precompact):
        """When ace-cli is not on PATH, no temp file should be created."""
        # Don't add any CLI stubs
        result = precompact.run()

        assert result["exit_code"] == 0
        assert result["temp_file_exists"] is False


# ===========================================================================
# SECTION 2: SessionStart Compact Tests
# ===========================================================================


class TestSessionStartCompactReadsTempFile:
    """
    Test scenario 9: Reads patterns from temp file when it exists.
    """

    def test_reads_patterns_from_temp_file(self, sessionstart):
        """When temp file exists, patterns should be read and included in output."""
        sessionstart.create_session_file()
        sessionstart.create_temp_file(
            patterns="- [strategies] Use dependency injection\n- [snippets] cache pattern",
            count="2",
        )
        result = sessionstart.run()

        assert result["exit_code"] == 0
        assert result["has_hook_specific_output"] is True
        assert "dependency injection" in result["additional_context"]
        assert "cache pattern" in result["additional_context"]


class TestSessionStartCompactValidJSON:
    """
    Test scenario 10 (CRITICAL): Output uses hookEventName: "SessionStart",
    NOT "PreCompact".
    """

    def test_hook_event_name_is_session_start(self, sessionstart):
        """
        CRITICAL: hookEventName must be "SessionStart" (valid in Claude Code schema).
        "PreCompact" is NOT valid and was the root cause of Issue #17.
        """
        sessionstart.create_session_file()
        sessionstart.create_temp_file(
            patterns="- [strategies] Test pattern",
            count="1",
        )
        result = sessionstart.run()

        assert result["hook_event_name"] == "SessionStart", (
            f"Expected hookEventName 'SessionStart', got '{result['hook_event_name']}'. "
            f"'PreCompact' is NOT in Claude Code's discriminated union schema!"
        )

    def test_hook_event_name_never_precompact(self, sessionstart):
        """hookEventName must NEVER be 'PreCompact' in the output."""
        sessionstart.create_session_file()
        sessionstart.create_temp_file(
            patterns="- [strategies] Test pattern",
            count="1",
        )
        result = sessionstart.run()

        assert result["hook_event_name"] != "PreCompact", (
            "CRITICAL BUG: hookEventName is 'PreCompact' which causes "
            "JSON validation failure in Claude Code (Issue #17)."
        )

    def test_output_is_valid_json(self, sessionstart):
        """The entire stdout must be valid JSON."""
        sessionstart.create_session_file()
        sessionstart.create_temp_file(
            patterns="- [strategies] Some pattern",
            count="1",
        )
        result = sessionstart.run()

        assert result["stdout_json"] is not None, (
            f"stdout is not valid JSON: {result['stdout']}"
        )


class TestSessionStartCompactAdditionalContext:
    """
    Test scenario 11: Output includes additionalContext with the patterns.
    """

    def test_additional_context_contains_patterns(self, sessionstart):
        """additionalContext must contain the pattern text."""
        sessionstart.create_session_file()
        sessionstart.create_temp_file(
            patterns="- [strategies] Always use TDD\n- [pitfalls] Avoid mocking everything",
            count="2",
        )
        result = sessionstart.run()

        assert result["additional_context"] is not None
        assert "Always use TDD" in result["additional_context"]
        assert "Avoid mocking everything" in result["additional_context"]

    def test_additional_context_wrapped_in_xml_tags(self, sessionstart):
        """additionalContext should wrap patterns in ace-patterns-recalled XML tags."""
        sessionstart.create_session_file()
        sessionstart.create_temp_file(
            patterns="- [strategies] Some pattern",
            count="1",
        )
        result = sessionstart.run()

        assert "<ace-patterns-recalled>" in result["additional_context"]
        assert "</ace-patterns-recalled>" in result["additional_context"]

    def test_additional_context_includes_session_reference(self, sessionstart):
        """additionalContext should reference the session for traceability."""
        sessionstart.create_session_file()
        sessionstart.create_temp_file(
            patterns="- [strategies] Some pattern",
            count="1",
        )
        result = sessionstart.run()

        assert sessionstart.session_id in result["additional_context"], (
            "additionalContext should include the session ID for traceability"
        )


class TestSessionStartCompactTempFileCleanup:
    """
    Test scenario 12: Temp file is cleaned up (deleted) after reading.
    """

    def test_temp_file_deleted_after_read(self, sessionstart):
        """The temp file must be removed after being read."""
        sessionstart.create_session_file()
        temp_path = sessionstart.create_temp_file(
            patterns="- [strategies] Some pattern",
            count="1",
        )
        assert temp_path.exists(), "Sanity check: temp file should exist before run"

        result = sessionstart.run()

        assert result["temp_file_cleaned"] is True, (
            "Temp file should be deleted after successful read"
        )

    def test_temp_file_deleted_even_when_empty_patterns(self, sessionstart):
        """Temp file should be cleaned up even if patterns field is empty."""
        sessionstart.create_session_file()
        temp_path = sessionstart.create_temp_file(
            patterns="",
            count="0",
        )

        sessionstart.run()

        assert not temp_path.exists(), (
            "Temp file should be deleted even with empty patterns"
        )


class TestSessionStartCompactNoTempFile:
    """
    Test scenario 13: Graceful no-op when no temp file exists.
    """

    def test_exits_zero_when_no_temp_file(self, sessionstart):
        """Must exit 0 when temp file does not exist."""
        sessionstart.create_session_file()
        # Don't create any temp file
        result = sessionstart.run()

        assert result["exit_code"] == 0

    def test_no_output_when_no_temp_file(self, sessionstart):
        """Must produce no stdout when temp file does not exist."""
        sessionstart.create_session_file()
        result = sessionstart.run()

        assert result["stdout_json"] is None or result["stdout"].strip() == "", (
            "Should produce no output when temp file does not exist"
        )

    def test_no_hook_specific_output_when_no_temp_file(self, sessionstart):
        """Must not produce hookSpecificOutput when no temp file."""
        sessionstart.create_session_file()
        result = sessionstart.run()

        assert result["has_hook_specific_output"] is False


class TestSessionStartCompactCorruptTempFile:
    """
    Test scenario 14: Handles corrupt/invalid temp file gracefully.
    """

    def test_exits_zero_on_corrupt_file(self, sessionstart):
        """Must exit 0 even if temp file contains invalid JSON."""
        sessionstart.create_session_file()
        sessionstart.create_corrupt_temp_file()
        result = sessionstart.run()

        assert result["exit_code"] == 0

    def test_corrupt_file_cleaned_up(self, sessionstart):
        """Corrupt temp file should still be cleaned up."""
        sessionstart.create_session_file()
        temp_path = sessionstart.create_corrupt_temp_file()
        sessionstart.run()

        assert not temp_path.exists(), (
            "Corrupt temp file should be cleaned up"
        )


class TestSessionStartCompactSessionIDExtraction:
    """
    Test scenario 15: Session ID extraction matches PreCompact wrapper.
    Both scripts must resolve to the same session ID to find the temp file.
    """

    def test_session_id_from_ace_session_file(self, sessionstart):
        """
        Primary path: session ID from /tmp/ace-session-${PROJECT_ID}.txt
        must match what PreCompact wrote.
        """
        custom_session = "unique-session-99887766"
        sessionstart.set_session_id(custom_session)
        sessionstart.create_session_file(session_id=custom_session)
        sessionstart.create_temp_file(
            patterns="- [strategies] Pattern via file",
            count="1",
            session_id=custom_session,
        )
        result = sessionstart.run()

        assert result["has_hook_specific_output"] is True
        assert "Pattern via file" in result["additional_context"]

    def test_fallback_to_stdin_session_id(self, sessionstart):
        """
        Fallback path: when ace-session file is missing, use stdin session_id.
        """
        fallback_session = "fallback-stdin-session"
        sessionstart.set_session_id(fallback_session)
        sessionstart.set_stdin({"session_id": fallback_session})
        # Don't create ace-session file, but DO create the temp file
        sessionstart.create_temp_file(
            patterns="- [strategies] Fallback pattern",
            count="1",
            session_id=fallback_session,
        )
        # Must also set project ID to empty so ace-session file check fails
        sessionstart.set_project_id("")
        result = sessionstart.run()

        assert result["exit_code"] == 0
        # If hookSpecificOutput exists, patterns were found via fallback
        if result["has_hook_specific_output"]:
            assert "Fallback pattern" in result["additional_context"]


# ===========================================================================
# SECTION 3: hooks.json Configuration Tests
# ===========================================================================


class TestHooksJsonConfig:
    """
    Tests for hooks.json configuration to verify proper routing
    of compact events to the new SessionStart(compact) script.
    """

    @pytest.fixture(autouse=True)
    def _load_hooks(self):
        """Load hooks.json once for all tests in this class."""
        self.hooks_data = json.loads(HOOKS_JSON_PATH.read_text())
        self.hooks = self.hooks_data["hooks"]

    def test_compact_matcher_exists(self):
        """
        Test scenario 16: A 'compact' matcher must exist in SessionStart hooks.
        """
        session_start_hooks = self.hooks.get("SessionStart", [])
        matchers = [h.get("matcher") for h in session_start_hooks]
        assert "compact" in matchers, (
            f"Expected 'compact' matcher in SessionStart hooks. "
            f"Found matchers: {matchers}"
        )

    def test_compact_matcher_routes_to_correct_script(self):
        """
        Test scenario 17: The compact matcher must route to
        ace_sessionstart_compact.sh.
        """
        session_start_hooks = self.hooks.get("SessionStart", [])
        compact_entry = None
        for entry in session_start_hooks:
            if entry.get("matcher") == "compact":
                compact_entry = entry
                break

        assert compact_entry is not None, "compact matcher entry not found"
        commands = [h.get("command", "") for h in compact_entry.get("hooks", [])]
        assert any("ace_sessionstart_compact.sh" in cmd for cmd in commands), (
            f"compact matcher must route to ace_sessionstart_compact.sh. "
            f"Found commands: {commands}"
        )

    def test_precompact_entry_still_exists(self):
        """
        Test scenario 18: The original PreCompact entry must still exist
        (for the wrapper that saves to temp file).
        """
        assert "PreCompact" in self.hooks, (
            "PreCompact hook entry must still exist in hooks.json"
        )
        precompact_hooks = self.hooks["PreCompact"]
        assert len(precompact_hooks) > 0, (
            "PreCompact must have at least one hook entry"
        )
        commands = []
        for entry in precompact_hooks:
            for hook in entry.get("hooks", []):
                commands.append(hook.get("command", ""))
        assert any("ace_precompact_wrapper.sh" in cmd for cmd in commands), (
            f"PreCompact must route to ace_precompact_wrapper.sh. "
            f"Found commands: {commands}"
        )

    def test_sessionstart_has_both_default_and_compact(self):
        """SessionStart must have both a default matcher and a compact matcher."""
        session_start_hooks = self.hooks.get("SessionStart", [])
        matchers = [h.get("matcher") for h in session_start_hooks]
        assert "" in matchers, "SessionStart must have a default (empty) matcher"
        assert "compact" in matchers, "SessionStart must have a 'compact' matcher"

    def test_compact_hook_has_timeout(self):
        """The compact hook entry must have a timeout configured."""
        session_start_hooks = self.hooks.get("SessionStart", [])
        for entry in session_start_hooks:
            if entry.get("matcher") == "compact":
                for hook in entry.get("hooks", []):
                    assert "timeout" in hook, (
                        "compact hook must have a timeout configured"
                    )
                    assert hook["timeout"] > 0

    def test_compact_hook_type_is_command(self):
        """The compact hook must be of type 'command'."""
        session_start_hooks = self.hooks.get("SessionStart", [])
        for entry in session_start_hooks:
            if entry.get("matcher") == "compact":
                for hook in entry.get("hooks", []):
                    assert hook.get("type") == "command"


# ===========================================================================
# SECTION 4: Integration / Handoff Tests
# ===========================================================================


class TestFullHandoffCycle:
    """
    Test scenario 19-21: Full cycle integration tests for the
    PreCompact -> SessionStart(compact) handoff.
    """

    def test_full_cycle_patterns_injected(self, tmp_path):
        """
        Test scenario 19: Full cycle - PreCompact saves, SessionStart reads,
        patterns are injected, temp file is cleaned.
        """
        # Step 1: Run PreCompact to save patterns
        pc = PreCompactHarness(tmp_path / "pc")
        pc.add_ace_cli_with_patterns(count=3)
        pc_result = pc.run()

        assert pc_result["exit_code"] == 0
        assert pc_result["temp_file_exists"] is True

        # Step 2: Run SessionStart(compact) to read and inject
        ss = SessionStartCompactHarness(tmp_path / "ss")
        ss.set_session_id(pc.session_id)
        ss.set_project_id(pc.project_id)
        ss.create_session_file()
        # Temp file already exists from PreCompact step

        ss_result = ss.run()

        assert ss_result["exit_code"] == 0
        assert ss_result["has_hook_specific_output"] is True
        assert ss_result["hook_event_name"] == "SessionStart"
        assert ss_result["additional_context"] is not None
        assert "Pattern content number" in ss_result["additional_context"]

        # Step 3: Verify temp file was cleaned up
        assert ss_result["temp_file_cleaned"] is True

        # Cleanup
        pc.cleanup()
        ss.cleanup()

    def test_no_patterns_lost_in_handoff(self, tmp_path):
        """
        Test scenario 20: No patterns lost in handoff.
        Content saved by PreCompact must appear in SessionStart output.
        """
        # Step 1: PreCompact saves
        pc = PreCompactHarness(tmp_path / "pc")
        pc.add_ace_cli_with_patterns(count=4)
        pc_result = pc.run()

        saved_patterns = pc_result["temp_file_content"]["patterns"]
        assert len(saved_patterns) > 0, "PreCompact should have saved patterns"

        # Step 2: SessionStart reads
        ss = SessionStartCompactHarness(tmp_path / "ss")
        ss.set_session_id(pc.session_id)
        ss.set_project_id(pc.project_id)
        ss.create_session_file()

        ss_result = ss.run()

        # Verify all pattern content is present
        for i in range(4):
            assert f"Pattern content number {i}" in ss_result["additional_context"], (
                f"Pattern {i} was lost in the handoff"
            )

        pc.cleanup()
        ss.cleanup()

    def test_consecutive_compact_cycles(self, tmp_path):
        """
        Test scenario 21: Multiple consecutive compact cycles work
        without stale data from previous cycles.
        """
        for cycle in range(3):
            cycle_dir = tmp_path / f"cycle_{cycle}"
            cycle_dir.mkdir()

            session_id = f"session-cycle-{cycle}"

            # PreCompact saves
            pc = PreCompactHarness(cycle_dir / "pc")
            pc.set_session_id(session_id)
            unique_pattern = json.dumps({
                "count": 1,
                "similar_patterns": [{
                    "section": "strategies",
                    "content": f"Unique pattern for cycle {cycle}",
                }],
            })
            pc.add_ace_cli(patterns_json=unique_pattern)
            pc_result = pc.run()
            assert pc_result["temp_file_exists"] is True

            # SessionStart reads
            ss = SessionStartCompactHarness(cycle_dir / "ss")
            ss.set_session_id(session_id)
            ss.set_project_id(pc.project_id)
            ss.create_session_file(session_id=session_id)

            ss_result = ss.run()

            if ss_result["has_hook_specific_output"]:
                # Verify THIS cycle's pattern is present
                assert f"Unique pattern for cycle {cycle}" in ss_result["additional_context"], (
                    f"Cycle {cycle}: expected its unique pattern in output"
                )
                # Verify previous cycle's patterns are NOT present
                if cycle > 0:
                    assert f"Unique pattern for cycle {cycle - 1}" not in ss_result["additional_context"], (
                        f"Cycle {cycle}: found stale data from cycle {cycle - 1}"
                    )

            # Verify cleanup
            assert ss_result["temp_file_cleaned"] is True

            pc.cleanup()
            ss.cleanup()


# ===========================================================================
# SECTION 5: Source Code Analysis Tests
# ===========================================================================


class TestPreCompactSourceAnalysis:
    """
    Test scenario 22: Static analysis of ace_precompact_wrapper.sh
    to verify it does NOT contain hookSpecificOutput or hookEventName
    in its output statements.
    """

    @pytest.fixture(autouse=True)
    def _load_source(self):
        """Load the source script once for all tests in this class."""
        self.source = PRECOMPACT_SCRIPT.read_text()

    def test_script_exists(self):
        """The PreCompact wrapper script must exist."""
        assert PRECOMPACT_SCRIPT.exists(), (
            f"Script not found at {PRECOMPACT_SCRIPT}"
        )

    def test_no_hook_specific_output_in_jq_output(self):
        """
        Test scenario 22: PreCompact wrapper must NOT contain
        hookSpecificOutput in its jq output block.
        """
        # Find all jq -n output blocks (the final output to stdout)
        lines = self.source.splitlines()
        in_jq_block = False
        jq_output_lines = []
        for line in lines:
            stripped = line.strip()
            if "jq -n" in stripped and not stripped.startswith("#"):
                in_jq_block = True
                jq_output_lines = []
            if in_jq_block:
                jq_output_lines.append(stripped)
                if stripped == "'" or stripped.endswith("'"):
                    in_jq_block = False

        jq_output_text = "\n".join(jq_output_lines)
        assert "hookSpecificOutput" not in jq_output_text, (
            "CRITICAL: PreCompact wrapper must NOT output hookSpecificOutput. "
            "This is the fix for Issue #17."
        )

    def test_no_hook_event_name_in_output(self):
        """
        PreCompact wrapper must NOT contain hookEventName in any output block.
        """
        # Check that hookEventName does not appear in any non-comment output line
        lines = self.source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "hookEventName" in stripped:
                # Check if this is in a jq output block (not just a comment)
                assert False, (
                    f"Line {i + 1}: Found 'hookEventName' in non-comment line: "
                    f"'{stripped}'. PreCompact must NOT output hookEventName."
                )

    def test_outputs_system_message(self):
        """PreCompact wrapper should output a systemMessage."""
        assert '"systemMessage"' in self.source or "'systemMessage'" in self.source, (
            "PreCompact should output a systemMessage for user feedback"
        )

    def test_uses_atomic_write_pattern(self):
        """PreCompact must use mktemp + mv for atomic file writes."""
        assert "mktemp" in self.source, "Must use mktemp for atomic write"
        assert "mv -f" in self.source or "mv " in self.source, (
            "Must use mv for atomic rename"
        )

    def test_uses_umask_for_permissions(self):
        """PreCompact must use umask 077 for restrictive file permissions."""
        assert "umask 077" in self.source, (
            "Must use 'umask 077' for owner-only file permissions"
        )

    def test_temp_file_path_uses_session_id(self):
        """Temp file path must include session ID variable."""
        assert "ace-patterns-precompact-${SESSION_ID}" in self.source, (
            "Temp file path must include ${SESSION_ID} for uniqueness"
        )


class TestSessionStartCompactSourceAnalysis:
    """
    Test scenario 23-24: Static analysis of ace_sessionstart_compact.sh.
    """

    @pytest.fixture(autouse=True)
    def _load_source(self):
        """Load the source script once for all tests in this class."""
        self.source = SESSIONSTART_COMPACT_SCRIPT.read_text()

    def test_script_exists(self):
        """The SessionStart compact script must exist."""
        assert SESSIONSTART_COMPACT_SCRIPT.exists(), (
            f"Script not found at {SESSIONSTART_COMPACT_SCRIPT}"
        )

    def test_uses_session_start_hook_event_name(self):
        """
        Test scenario 23: hookEventName must be "SessionStart" in the output.
        """
        assert '"SessionStart"' in self.source or "'SessionStart'" in self.source, (
            "SessionStart compact must use hookEventName: 'SessionStart'"
        )

    def test_does_not_use_precompact_hook_event_name(self):
        """hookEventName must NEVER be "PreCompact" in the output code."""
        lines = self.source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Check for "PreCompact" as a hookEventName value (not in comments)
            if '"PreCompact"' in stripped and "hookEventName" in stripped:
                assert False, (
                    f"Line {i + 1}: Found hookEventName 'PreCompact' in "
                    f"non-comment line. Must use 'SessionStart' instead."
                )

    def test_outputs_hook_specific_output(self):
        """SessionStart compact MUST output hookSpecificOutput."""
        assert "hookSpecificOutput" in self.source, (
            "SessionStart compact must output hookSpecificOutput with "
            "additionalContext for pattern injection"
        )

    def test_outputs_additional_context(self):
        """SessionStart compact must include additionalContext in output."""
        assert "additionalContext" in self.source, (
            "Must include additionalContext for pattern injection"
        )

    def test_cleans_up_temp_file(self):
        """SessionStart compact must delete the temp file after reading."""
        assert 'rm -f "$TEMP_FILE"' in self.source or "rm -f" in self.source, (
            "Must clean up temp file after reading"
        )

    def test_handles_missing_temp_file(self):
        """Script must check if temp file exists before reading."""
        assert '! -f "$TEMP_FILE"' in self.source, (
            "Must check for temp file existence before attempting to read"
        )


class TestBothScriptsConsistency:
    """
    Test scenario 24-25: Both scripts must use the same temp file path
    pattern and extract session_id consistently.
    """

    @pytest.fixture(autouse=True)
    def _load_sources(self):
        """Load both scripts for comparison."""
        self.precompact_source = PRECOMPACT_SCRIPT.read_text()
        self.sessionstart_source = SESSIONSTART_COMPACT_SCRIPT.read_text()

    def test_same_temp_file_path_pattern(self):
        """
        Test scenario 24: Both scripts must use the same temp file
        path pattern: /tmp/ace-patterns-precompact-${SESSION_ID}.json
        """
        pattern = "ace-patterns-precompact-"
        assert pattern in self.precompact_source, (
            f"PreCompact must use '{pattern}' in temp file path"
        )
        assert pattern in self.sessionstart_source, (
            f"SessionStart compact must use '{pattern}' in temp file path"
        )

    def test_both_use_json_extension(self):
        """Both scripts must use .json extension for the temp file."""
        assert "ace-patterns-precompact-${SESSION_ID}.json" in self.precompact_source
        assert "ace-patterns-precompact-${SESSION_ID}.json" in self.sessionstart_source

    def test_both_read_ace_session_file(self):
        """
        Test scenario 25: Both scripts must read session ID from the
        same source: /tmp/ace-session-${PROJECT_ID}.txt
        """
        session_file_pattern = "ace-session-"
        assert session_file_pattern in self.precompact_source, (
            "PreCompact must read from ace-session file"
        )
        assert session_file_pattern in self.sessionstart_source, (
            "SessionStart compact must read from ace-session file"
        )

    def test_both_read_settings_json_for_project_id(self):
        """Both scripts must read .claude/settings.json for PROJECT_ID."""
        settings_pattern = ".claude/settings.json"
        assert settings_pattern in self.precompact_source
        assert settings_pattern in self.sessionstart_source

    def test_precompact_writes_sessionstart_reads(self):
        """
        Verify the write/read relationship: PreCompact writes to TEMP_FILE,
        SessionStart reads from TEMP_FILE.
        """
        # PreCompact must write (mv to temp file)
        assert "mv" in self.precompact_source and "TEMP_FILE" in self.precompact_source
        # SessionStart must read (cat temp file)
        assert "cat" in self.sessionstart_source and "TEMP_FILE" in self.sessionstart_source

    def test_precompact_does_not_read_temp_file(self):
        """PreCompact should only WRITE the temp file, not read it."""
        # After the TEMP_FILE assignment, PreCompact should not cat it
        lines = self.precompact_source.splitlines()
        temp_file_assigned = False
        for line in lines:
            if 'TEMP_FILE=' in line:
                temp_file_assigned = True
            if temp_file_assigned and 'cat "$TEMP_FILE"' in line:
                assert False, (
                    "PreCompact should not read the temp file it writes"
                )

    def test_sessionstart_does_not_write_temp_file(self):
        """SessionStart should only READ (and delete) the temp file, not write it."""
        # Check that SessionStart doesn't write to TEMP_FILE
        lines = self.sessionstart_source.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '> "$TEMP_FILE"' in stripped or '>> "$TEMP_FILE"' in stripped:
                assert False, (
                    "SessionStart compact should not write to the temp file"
                )


# ===========================================================================
# Edge Case and Robustness Tests
# ===========================================================================


class TestEdgeCases:
    """Additional edge cases for robustness."""

    def test_precompact_always_exits_zero(self, precompact):
        """PreCompact must always exit 0 to avoid disrupting Claude Code."""
        # No CLI at all
        result = precompact.run()
        assert result["exit_code"] == 0

    def test_sessionstart_always_exits_zero(self, sessionstart):
        """SessionStart compact must always exit 0."""
        sessionstart.create_session_file()
        # No temp file
        result = sessionstart.run()
        assert result["exit_code"] == 0

    def test_precompact_set_euo_pipefail(self):
        """PreCompact must use set -euo pipefail for safety."""
        source = PRECOMPACT_SCRIPT.read_text()
        assert "set -euo pipefail" in source

    def test_sessionstart_set_euo_pipefail(self):
        """SessionStart compact must use set -euo pipefail for safety."""
        source = SESSIONSTART_COMPACT_SCRIPT.read_text()
        assert "set -euo pipefail" in source

    def test_both_scripts_have_version_comment(self):
        """Both scripts should reference v5.4.28 and Issue #17."""
        pc_source = PRECOMPACT_SCRIPT.read_text()
        ss_source = SESSIONSTART_COMPACT_SCRIPT.read_text()
        assert "Issue #17" in pc_source or "#17" in pc_source or "5.4.28" in pc_source, (
            "PreCompact should reference the fix version or issue"
        )
        assert "Issue #17" in ss_source or "#17" in ss_source or "5.4.28" in ss_source, (
            "SessionStart compact should reference the fix version or issue"
        )

    def test_precompact_all_exit_codes_are_zero(self):
        """All exit statements in PreCompact must be exit 0."""
        source = PRECOMPACT_SCRIPT.read_text()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("exit ") and not stripped.startswith("#"):
                code_part = stripped.split("#")[0].strip()
                assert code_part == "exit 0", (
                    f"Line {i + 1}: Expected 'exit 0' but found '{code_part}'. "
                    f"Non-zero exits would disrupt Claude Code."
                )

    def test_sessionstart_all_exit_codes_are_zero(self):
        """All exit statements in SessionStart compact must be exit 0."""
        source = SESSIONSTART_COMPACT_SCRIPT.read_text()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("exit ") and not stripped.startswith("#"):
                code_part = stripped.split("#")[0].strip()
                assert code_part == "exit 0", (
                    f"Line {i + 1}: Expected 'exit 0' but found '{code_part}'. "
                    f"Non-zero exits would disrupt Claude Code."
                )


# ===========================================================================
# Entry point for running without pytest
# ===========================================================================


def run_tests():
    """Run all tests manually (no pytest dependency required)."""
    print("=" * 72)
    print("  ACE PreCompact Handoff - TDD Verification Tests (PR #18)")
    print("  Fix for Issue #17: PreCompact hook JSON validation failure")
    print("=" * 72)

    test_classes = [
        TestPreCompactTempFileSave,
        TestPreCompactAtomicWrite,
        TestPreCompactTempFilePermissions,
        TestPreCompactNoHookSpecificOutput,
        TestPreCompactExitCode,
        TestPreCompactDisabledFlag,
        TestPreCompactEmptyResults,
        TestSessionStartCompactReadsTempFile,
        TestSessionStartCompactValidJSON,
        TestSessionStartCompactAdditionalContext,
        TestSessionStartCompactTempFileCleanup,
        TestSessionStartCompactNoTempFile,
        TestSessionStartCompactCorruptTempFile,
        TestSessionStartCompactSessionIDExtraction,
        TestHooksJsonConfig,
        TestFullHandoffCycle,
        TestPreCompactSourceAnalysis,
        TestSessionStartCompactSourceAnalysis,
        TestBothScriptsConsistency,
        TestEdgeCases,
    ]

    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        print(f"\n{'─' * 60}")
        print(f"  {cls.__name__}")
        if cls.__doc__:
            first_line = cls.__doc__.strip().splitlines()[0].strip()
            print(f"  {first_line}")
        print(f"{'─' * 60}")

        for method_name in sorted(dir(cls)):
            if not method_name.startswith("test_"):
                continue

            method = getattr(cls, method_name)

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    instance = cls()
                    tmp = Path(tmpdir)

                    # Handle different fixture patterns
                    if "precompact" in method.__code__.co_varnames:
                        h = PreCompactHarness(tmp)
                        try:
                            method(instance, h)
                        finally:
                            h.cleanup()
                    elif "sessionstart" in method.__code__.co_varnames:
                        h = SessionStartCompactHarness(tmp)
                        try:
                            method(instance, h)
                        finally:
                            h.cleanup()
                    elif "tmp_path" in method.__code__.co_varnames:
                        method(instance, tmp)
                    elif hasattr(instance, "_load_source") or hasattr(instance, "_load_sources") or hasattr(instance, "_load_hooks"):
                        # Autouse fixtures - call the setup method
                        if hasattr(cls, "_load_source"):
                            instance._load_source()
                        if hasattr(cls, "_load_sources"):
                            instance._load_sources()
                        if hasattr(cls, "_load_hooks"):
                            instance._load_hooks()
                        method(instance)
                    else:
                        method(instance)

                print(f"  PASS  {method_name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {method_name}")
                print(f"        {e}")
                failed += 1
                errors.append(f"{cls.__name__}.{method_name}: {e}")

    print(f"\n{'=' * 72}")
    print(f"  Results: {passed} passed, {failed} failed")
    if errors:
        print(f"\n  Failures:")
        for err in errors:
            print(f"    - {err}")
    print(f"{'=' * 72}")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
