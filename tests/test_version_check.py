#!/usr/bin/env python3
"""
TDD Tests for ACE SessionStart hook VERSION CHECK logic.

Tests the version check logic (sections 1-4) in
plugins/ace/scripts/ace_install_cli.sh (lines 53-97):
  1. CLI Detection (ace-cli vs ce-ace vs missing)
  2. Deprecated Package Detection (@ce-dot-net/ce-ace-cli)
  3. Version Comparison (sort -V -C against MIN_VERSION)
  4. Daily Update Check (cache file + npm show)

Harness Approach:
  - Extract the relevant bash logic into a minimal test harness
  - Stub external commands (command -v, npm, ace-cli --version, sort)
    using PATH manipulation (create fake binaries in a temp bin dir)
  - Test via subprocess.run()
  - Each test is independent (creates its own temp environment)

NOTE: Lines 54-56 of ace_install_cli.sh had a copy-paste bug (fixed in v5.4.27):
  The inner check now correctly uses 'command -v ce-ace' for the deprecated fallback.

Run with: pytest tests/test_version_check.py -v
"""

import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = PROJECT_ROOT / "plugins" / "ace" / "scripts" / "ace_install_cli.sh"

# ---------------------------------------------------------------------------
# Bash Test Harness
# ---------------------------------------------------------------------------
#
# This harness reproduces the version check logic (sections 1-4) from
# ace_install_cli.sh in isolation.  External commands are controlled by
# placing stub scripts in a temporary bin directory that is prepended to PATH.
#
# The harness accepts environment variables to control behavior:
#   FAKE_BIN_DIR   - directory containing stub binaries (prepended to PATH)
#   OUTPUT_LOG     - file where output_warning messages are written
#   DISABLE_FLAG   - file path for the ACE disabled flag
#   CACHE_FILE     - file path for the daily update check cache
#   MIN_VERSION    - minimum required CLI version (defaults to 3.10.3)
#
# Stub binaries the harness expects to find (or not) in FAKE_BIN_DIR:
#   ace-cli        - stub for the ace-cli command
#   ce-ace         - stub for the deprecated ce-ace command
#   npm            - stub for npm list/show commands
#   sort           - stub for sort -V -C (optional; falls through to real sort)
#   jq             - stub for jq (minimal, not needed for version check)

VERSION_CHECK_HARNESS = textwrap.dedent("""\
    #!/usr/bin/env bash
    set -eo pipefail

    # --- Test environment setup ---
    # IMPORTANT: Replace PATH entirely to isolate from system-installed ace-cli/npm.
    # Only include fake bin + core system dirs (no nvm, homebrew node, etc.)
    export PATH="__FAKE_BIN_DIR__:/usr/bin:/bin:/usr/sbin:/sbin"
    OUTPUT_LOG="__OUTPUT_LOG__"
    ACE_DISABLED_FLAG="__DISABLE_FLAG__"
    CACHE_FILE="__CACHE_FILE__"
    MIN_VERSION="__MIN_VERSION__"

    # Helper: Disable ACE hooks by creating flag file
    disable_ace_hooks() {
      local reason="$1"
      echo "$reason" > "$ACE_DISABLED_FLAG"
    }

    # Helper: Output warning (writes to log file instead of JSON for testing)
    output_warning() {
      local msg="$1"
      echo "$msg" >> "$OUTPUT_LOG"
    }

    # Clear any previous disable flag
    rm -f "$ACE_DISABLED_FLAG" 2>/dev/null || true

    # ===== SECTION 1: CLI Detection (lines 53-68 of source) =====
    if ! command -v ace-cli >/dev/null 2>&1; then
      # Fallback: Check old ce-ace command (deprecated)
      if command -v ce-ace >/dev/null 2>&1; then
        output_warning "WARNING_DEPRECATED_CMD"
        CLI_CMD="ce-ace"
      else
        disable_ace_hooks "CLI not installed"
        output_warning "ERROR_CLI_NOT_FOUND"
        exit 0
      fi
    else
      CLI_CMD="ace-cli"
    fi

    # ===== SECTION 2: Deprecated Package Detection (lines 70-77) =====
    if npm list -g @ce-dot-net/ce-ace-cli 2>/dev/null | grep -q "@ce-dot-net"; then
      disable_ace_hooks "Deprecated package @ce-dot-net/ce-ace-cli"
      output_warning "ERROR_DEPRECATED_PKG"
      exit 0
    fi

    # ===== SECTION 3: Version Comparison (lines 79-86) =====
    CURRENT_VERSION=$($CLI_CMD --version 2>/dev/null | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' || echo "0.0.0")
    if ! printf '%s\\n' "$MIN_VERSION" "$CURRENT_VERSION" | sort -V -C 2>/dev/null; then
      disable_ace_hooks "CLI version $CURRENT_VERSION < $MIN_VERSION"
      output_warning "ERROR_VERSION_TOO_OLD:$CURRENT_VERSION"
      exit 0
    fi

    # ===== SECTION 4: Daily Update Check (lines 88-97) =====
    if [ ! -f "$CACHE_FILE" ]; then
      LATEST=$(npm show @ace-sdk/cli version 2>/dev/null || echo "")
      echo "$LATEST" > "$CACHE_FILE" 2>/dev/null || true
    fi
    LATEST=$(cat "$CACHE_FILE" 2>/dev/null || echo "")

    if [ -n "$LATEST" ] && [ "$LATEST" != "$CURRENT_VERSION" ]; then
      output_warning "INFO_UPDATE_AVAILABLE:$LATEST"
    fi

    # Write final state for test inspection
    echo "CLI_CMD=$CLI_CMD" >> "$OUTPUT_LOG"
    echo "CURRENT_VERSION=$CURRENT_VERSION" >> "$OUTPUT_LOG"

    exit 0
""")


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------


class VersionCheckHarness:
    """
    Creates a temporary environment with stub binaries and runs the
    version check harness script.
    """

    def __init__(self, tmpdir: Path):
        self.tmpdir = tmpdir
        self.fake_bin = tmpdir / "bin"
        self.fake_bin.mkdir()
        self.output_log = tmpdir / "output.log"
        self.disable_flag = tmpdir / "ace-disabled.flag"
        self.cache_file = tmpdir / "update-cache.txt"
        self.harness_script = tmpdir / "test_harness.sh"
        self.min_version = "3.10.3"

        # Track which stubs have been created
        self._stubs_created = set()

    def add_ace_cli(self, version: str = "3.10.3"):
        """Add a fake ace-cli that reports the given version."""
        self._write_stub("ace-cli", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [ "$1" = "--version" ]; then
              echo "ace-cli v{version}"
              exit 0
            fi
            exit 0
        """))

    def add_ce_ace(self, version: str = "3.10.3"):
        """Add a fake ce-ace (deprecated command) that reports the given version."""
        self._write_stub("ce-ace", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [ "$1" = "--version" ]; then
              echo "ce-ace v{version}"
              exit 0
            fi
            exit 0
        """))

    def add_ace_cli_broken_version(self):
        """Add an ace-cli that fails on --version (outputs garbage)."""
        self._write_stub("ace-cli", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [ "$1" = "--version" ]; then
              echo "error: cannot determine version"
              exit 1
            fi
            exit 0
        """))

    def add_npm(self, global_list_output: str = "", show_version: str = ""):
        """
        Add a fake npm stub.

        Args:
            global_list_output: What 'npm list -g @ce-dot-net/ce-ace-cli' returns.
                                If it contains "@ce-dot-net", deprecated pkg is detected.
            show_version: What 'npm show @ace-sdk/cli version' returns.
        """
        self._write_stub("npm", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [ "$1" = "list" ] && [ "$2" = "-g" ]; then
              echo '{global_list_output}'
              exit 0
            fi
            if [ "$1" = "show" ] && [ "$2" = "@ace-sdk/cli" ]; then
              echo '{show_version}'
              exit 0
            fi
            exit 1
        """))

    def add_npm_failing(self):
        """Add a fake npm that always fails."""
        self._write_stub("npm", textwrap.dedent("""\
            #!/usr/bin/env bash
            exit 1
        """))

    def add_npm_list_empty_show_version(self, show_version: str = ""):
        """Add npm where list returns empty but show returns a version."""
        self._write_stub("npm", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            if [ "$1" = "list" ] && [ "$2" = "-g" ]; then
              echo '(empty)'
              exit 0
            fi
            if [ "$1" = "show" ] && [ "$2" = "@ace-sdk/cli" ]; then
              echo '{show_version}'
              exit 0
            fi
            exit 1
        """))

    def set_cache_file(self, content: str):
        """Pre-populate the update check cache file."""
        self.cache_file.write_text(content)

    def set_min_version(self, version: str):
        """Override the minimum version for testing."""
        self.min_version = version

    def run(self) -> dict:
        """
        Write and execute the harness script.

        Returns a dict with:
          - exit_code: process exit code
          - stderr: stderr output
          - warnings: list of warning messages emitted
          - disable_flag_exists: whether the disable flag was created
          - disable_flag_reason: content of the disable flag (if exists)
          - cache_file_exists: whether the cache file exists after run
          - cache_file_content: content of the cache file (if exists)
          - cli_cmd: the CLI_CMD value chosen by the script
          - current_version: the CURRENT_VERSION detected
        """
        # Ensure npm stub exists (default: empty list, no show)
        if "npm" not in self._stubs_created:
            self.add_npm()

        # Write the harness script with placeholders filled
        script_text = (
            VERSION_CHECK_HARNESS
            .replace("__FAKE_BIN_DIR__", str(self.fake_bin))
            .replace("__OUTPUT_LOG__", str(self.output_log))
            .replace("__DISABLE_FLAG__", str(self.disable_flag))
            .replace("__CACHE_FILE__", str(self.cache_file))
            .replace("__MIN_VERSION__", self.min_version)
        )
        self.harness_script.write_text(script_text)
        self.harness_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(self.harness_script)],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Parse output log
        warnings = []
        cli_cmd = ""
        current_version = ""
        if self.output_log.exists():
            for line in self.output_log.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("CLI_CMD="):
                    cli_cmd = line.split("=", 1)[1]
                elif line.startswith("CURRENT_VERSION="):
                    current_version = line.split("=", 1)[1]
                else:
                    warnings.append(line)

        # Parse disable flag
        disable_flag_exists = self.disable_flag.exists()
        disable_flag_reason = ""
        if disable_flag_exists:
            disable_flag_reason = self.disable_flag.read_text().strip()

        # Parse cache file
        cache_file_exists = self.cache_file.exists()
        cache_file_content = ""
        if cache_file_exists:
            cache_file_content = self.cache_file.read_text().strip()

        return {
            "exit_code": result.returncode,
            "stderr": result.stderr,
            "warnings": warnings,
            "disable_flag_exists": disable_flag_exists,
            "disable_flag_reason": disable_flag_reason,
            "cache_file_exists": cache_file_exists,
            "cache_file_content": cache_file_content,
            "cli_cmd": cli_cmd,
            "current_version": current_version,
        }

    def _write_stub(self, name: str, content: str):
        """Write an executable stub script to the fake bin directory."""
        stub_path = self.fake_bin / name
        stub_path.write_text(content)
        stub_path.chmod(0o755)
        self._stubs_created.add(name)


@pytest.fixture
def harness(tmp_path):
    """Create a fresh VersionCheckHarness for each test."""
    return VersionCheckHarness(tmp_path)


# ===========================================================================
# SECTION 1: CLI Detection Tests
# ===========================================================================


class TestCLIDetection:
    """
    Section 1: CLI Detection (lines 53-68).
    Tests whether ace-cli, ce-ace, or no CLI is found.
    """

    def test_ace_cli_found_sets_cli_cmd(self, harness):
        """When ace-cli is on PATH, CLI_CMD should be 'ace-cli' with no warnings."""
        harness.add_ace_cli(version="3.10.3")
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["cli_cmd"] == "ace-cli"
        assert result["disable_flag_exists"] is False
        # No error/warning messages about CLI detection
        cli_warnings = [w for w in result["warnings"] if "CLI_NOT_FOUND" in w or "DEPRECATED_CMD" in w]
        assert len(cli_warnings) == 0

    def test_no_cli_at_all_disables_hooks(self, harness):
        """When neither ace-cli nor ce-ace is on PATH, hooks are disabled."""
        # Don't add any CLI stubs
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is True
        assert "CLI not installed" in result["disable_flag_reason"]
        assert "ERROR_CLI_NOT_FOUND" in result["warnings"]

    def test_no_cli_emits_exactly_one_error(self, harness):
        """When no CLI is found, exactly one error warning is emitted."""
        result = harness.run()

        error_msgs = [w for w in result["warnings"] if "ERROR_CLI_NOT_FOUND" in w]
        assert len(error_msgs) == 1

    def test_only_ce_ace_found_deprecated_fallback(self, harness):
        """
        When only ce-ace is on PATH (deprecated command), the script should:
        - Detect it via 'command -v ce-ace'
        - Emit a deprecation warning
        - Set CLI_CMD="ce-ace" and continue (transition period)
        """
        harness.add_ce_ace(version="3.10.3")
        result = harness.run()

        # ce-ace found as fallback - warns but does NOT disable
        assert "WARNING_DEPRECATED_CMD" in result["warnings"]
        assert result["disable_flag_exists"] is False


# ===========================================================================
# SECTION 2: Deprecated Package Detection Tests
# ===========================================================================


class TestDeprecatedPackageDetection:
    """
    Section 2: Deprecated Package Detection (lines 70-77).
    Tests npm list -g @ce-dot-net/ce-ace-cli detection.
    """

    def test_deprecated_package_installed_disables_hooks(self, harness):
        """When @ce-dot-net/ce-ace-cli is installed globally, hooks are disabled."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm(
            global_list_output="/usr/local/lib\n`-- @ce-dot-net/ce-ace-cli@1.0.14",
            show_version="3.10.3",
        )
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is True
        assert "Deprecated package" in result["disable_flag_reason"]
        assert "ERROR_DEPRECATED_PKG" in result["warnings"]

    def test_deprecated_package_not_installed_continues(self, harness):
        """When the old package is NOT installed, script continues normally."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm(
            global_list_output="(empty)",
            show_version="3.10.3",
        )
        result = harness.run()

        assert result["disable_flag_exists"] is False
        deprecated_warnings = [w for w in result["warnings"] if "DEPRECATED_PKG" in w]
        assert len(deprecated_warnings) == 0

    def test_npm_list_fails_continues_normally(self, harness):
        """When npm list fails/errors, grep -q does not match, script continues."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_failing()
        result = harness.run()

        # npm failing means no deprecated package detected -> continue
        # But npm show also fails -> cache file will be empty
        assert result["disable_flag_exists"] is False
        deprecated_warnings = [w for w in result["warnings"] if "DEPRECATED_PKG" in w]
        assert len(deprecated_warnings) == 0

    def test_npm_list_partial_match_does_not_trigger(self, harness):
        """When npm list output does NOT contain @ce-dot-net, no disable."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm(
            global_list_output="/usr/local/lib\n`-- @ace-sdk/cli@3.10.3",
            show_version="3.10.3",
        )
        result = harness.run()

        assert result["disable_flag_exists"] is False


# ===========================================================================
# SECTION 3: Version Comparison Tests (CRITICAL)
# ===========================================================================


class TestVersionComparison:
    """
    Section 3: Version Comparison (lines 79-86).
    Tests the sort -V -C based version comparison logic.
    This is the most critical section -- sort -V -C returns 0 when input
    is already sorted (i.e., MIN_VERSION <= CURRENT_VERSION).
    """

    def test_version_equal_passes(self, harness):
        """CURRENT_VERSION == MIN_VERSION (3.10.3 == 3.10.3) should pass."""
        harness.add_ace_cli(version="3.10.3")
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is False
        assert result["current_version"] == "3.10.3"
        version_warnings = [w for w in result["warnings"] if "VERSION_TOO_OLD" in w]
        assert len(version_warnings) == 0

    def test_version_greater_minor_passes(self, harness):
        """CURRENT_VERSION > MIN_VERSION (3.11.0 > 3.10.3) should pass."""
        harness.add_ace_cli(version="3.11.0")
        result = harness.run()

        assert result["disable_flag_exists"] is False
        assert result["current_version"] == "3.11.0"

    def test_version_less_disables(self, harness):
        """CURRENT_VERSION < MIN_VERSION (3.9.0 < 3.10.3) should disable."""
        harness.add_ace_cli(version="3.9.0")
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is True
        assert "3.9.0" in result["disable_flag_reason"]
        assert "ERROR_VERSION_TOO_OLD:3.9.0" in result["warnings"]

    def test_version_zero_on_cli_failure_disables(self, harness):
        """When --version fails, CURRENT_VERSION = '0.0.0' which should disable."""
        harness.add_ace_cli_broken_version()
        result = harness.run()

        assert result["disable_flag_exists"] is True
        assert "0.0.0" in result["disable_flag_reason"]
        assert "ERROR_VERSION_TOO_OLD:0.0.0" in result["warnings"]

    def test_major_version_ahead_passes(self, harness):
        """CURRENT_VERSION = 4.0.0 (major ahead of 3.10.3) should pass."""
        harness.add_ace_cli(version="4.0.0")
        result = harness.run()

        assert result["disable_flag_exists"] is False
        assert result["current_version"] == "4.0.0"

    def test_one_patch_behind_disables(self, harness):
        """CURRENT_VERSION = 3.10.2 (one patch behind 3.10.3) should disable."""
        harness.add_ace_cli(version="3.10.2")
        result = harness.run()

        assert result["disable_flag_exists"] is True
        assert "3.10.2" in result["disable_flag_reason"]

    def test_higher_patch_passes(self, harness):
        """CURRENT_VERSION = 3.10.30 (higher patch than 3.10.3) should pass."""
        harness.add_ace_cli(version="3.10.30")
        result = harness.run()

        assert result["disable_flag_exists"] is False
        assert result["current_version"] == "3.10.30"

    def test_much_older_version_disables(self, harness):
        """CURRENT_VERSION = 1.0.0 (very old) should disable."""
        harness.add_ace_cli(version="1.0.0")
        result = harness.run()

        assert result["disable_flag_exists"] is True
        assert "1.0.0" in result["disable_flag_reason"]

    def test_disable_flag_includes_version_info(self, harness):
        """When version is too old, disable reason includes both versions."""
        harness.add_ace_cli(version="2.5.0")
        result = harness.run()

        assert result["disable_flag_exists"] is True
        assert "2.5.0" in result["disable_flag_reason"]
        assert "3.10.3" in result["disable_flag_reason"]


# ===========================================================================
# SECTION 4: Daily Update Check Tests
# ===========================================================================


class TestDailyUpdateCheck:
    """
    Section 4: Daily Update Check (lines 88-97).
    Tests cache file creation and update-available warnings.
    """

    def test_no_cache_file_creates_one(self, harness):
        """When no cache file exists, it should be created with latest version."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="3.11.0")
        result = harness.run()

        assert result["cache_file_exists"] is True
        assert result["cache_file_content"] == "3.11.0"

    def test_cache_file_different_version_warns(self, harness):
        """When cache has a different version than current, show update warning."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="3.10.3")
        harness.set_cache_file("3.11.0")
        result = harness.run()

        update_warnings = [w for w in result["warnings"] if "UPDATE_AVAILABLE" in w]
        assert len(update_warnings) == 1
        assert "3.11.0" in update_warnings[0]

    def test_cache_file_same_version_no_warning(self, harness):
        """When cache version matches current version, no update warning."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="3.10.3")
        harness.set_cache_file("3.10.3")
        result = harness.run()

        update_warnings = [w for w in result["warnings"] if "UPDATE_AVAILABLE" in w]
        assert len(update_warnings) == 0

    def test_cache_file_empty_no_warning(self, harness):
        """When cache file exists but is empty, no update warning (empty string check)."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="3.10.3")
        harness.set_cache_file("")
        result = harness.run()

        update_warnings = [w for w in result["warnings"] if "UPDATE_AVAILABLE" in w]
        assert len(update_warnings) == 0

    def test_npm_show_fails_creates_empty_cache(self, harness):
        """When npm show fails, cache file is created with empty string, no warning."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_failing()
        result = harness.run()

        assert result["cache_file_exists"] is True
        # Cache content should be empty (npm failed)
        assert result["cache_file_content"] == ""
        update_warnings = [w for w in result["warnings"] if "UPDATE_AVAILABLE" in w]
        assert len(update_warnings) == 0

    def test_existing_cache_not_overwritten(self, harness):
        """When cache file already exists, npm show is NOT called (cache preserved)."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="9.9.9")
        # Pre-populate cache with a specific value
        harness.set_cache_file("3.12.0")
        result = harness.run()

        # Cache should still have original value, not overwritten with 9.9.9
        assert result["cache_file_content"] == "3.12.0"

    def test_new_cache_triggers_warning_if_different(self, harness):
        """When cache is freshly created with a newer version, warning is shown."""
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="4.0.0")
        result = harness.run()

        assert result["cache_file_content"] == "4.0.0"
        update_warnings = [w for w in result["warnings"] if "UPDATE_AVAILABLE" in w]
        assert len(update_warnings) == 1
        assert "4.0.0" in update_warnings[0]


# ===========================================================================
# Integration / Combined Tests
# ===========================================================================


class TestIntegrationScenarios:
    """
    End-to-end scenarios combining multiple sections.
    """

    def test_full_happy_path_clean_exit(self, harness):
        """
        Full happy path: ace-cli present, correct version, up-to-date.
        Should produce clean exit with no warnings and no disable flag.
        """
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="3.10.3")
        harness.set_cache_file("3.10.3")
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is False
        assert result["cli_cmd"] == "ace-cli"
        assert result["current_version"] == "3.10.3"
        assert len(result["warnings"]) == 0

    def test_full_sad_path_no_cli(self, harness):
        """
        Full sad path: no CLI at all.
        Should create flag file, emit warning, and exit 0.
        """
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is True
        assert "CLI not installed" in result["disable_flag_reason"]
        assert "ERROR_CLI_NOT_FOUND" in result["warnings"]
        # CLI_CMD and CURRENT_VERSION should not be set (early exit)
        assert result["cli_cmd"] == ""
        assert result["current_version"] == ""

    def test_happy_path_with_update_available(self, harness):
        """
        ace-cli present, correct version, but update available.
        Should show update warning but NOT disable hooks.
        """
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm_list_empty_show_version(show_version="4.0.0")
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is False
        assert result["cli_cmd"] == "ace-cli"
        update_warnings = [w for w in result["warnings"] if "UPDATE_AVAILABLE" in w]
        assert len(update_warnings) == 1

    def test_deprecated_pkg_exits_before_version_check(self, harness):
        """
        When deprecated package is found, script exits BEFORE version check.
        Even with a valid ace-cli version, deprecated pkg takes precedence.
        """
        harness.add_ace_cli(version="3.10.3")
        harness.add_npm(
            global_list_output="/usr/local/lib\n`-- @ce-dot-net/ce-ace-cli@1.0.14",
            show_version="3.10.3",
        )
        result = harness.run()

        assert result["disable_flag_exists"] is True
        assert "Deprecated package" in result["disable_flag_reason"]
        # Version check output should NOT appear (exited before reaching it)
        assert result["current_version"] == ""

    def test_old_version_exits_before_update_check(self, harness):
        """
        When version is too old, script exits BEFORE daily update check.
        Cache file should NOT be created.
        """
        harness.add_ace_cli(version="2.0.0")
        harness.add_npm_list_empty_show_version(show_version="4.0.0")
        result = harness.run()

        assert result["disable_flag_exists"] is True
        assert "2.0.0" in result["disable_flag_reason"]
        # Cache file should NOT exist (exited before update check)
        assert result["cache_file_exists"] is False

    def test_newer_version_with_no_network(self, harness):
        """
        ace-cli present with good version but npm fails.
        Should pass version check, create empty cache, no update warning.
        """
        harness.add_ace_cli(version="4.0.0")
        harness.add_npm_failing()
        result = harness.run()

        assert result["exit_code"] == 0
        assert result["disable_flag_exists"] is False
        assert result["current_version"] == "4.0.0"
        update_warnings = [w for w in result["warnings"] if "UPDATE_AVAILABLE" in w]
        assert len(update_warnings) == 0


# ===========================================================================
# Source Code Analysis Tests
# ===========================================================================


class TestSourceCodeAnalysis:
    """
    Static analysis of the actual ace_install_cli.sh to verify the version
    check logic patterns, constants, and structural properties.
    """

    @pytest.fixture(autouse=True)
    def _load_source(self):
        """Load the source script once for all tests in this class."""
        self.source = SCRIPT_PATH.read_text()

    def test_script_exists(self):
        """The script file must exist at the expected path."""
        assert SCRIPT_PATH.exists(), f"Script not found at {SCRIPT_PATH}"

    def test_min_version_is_3_10_3(self):
        """MIN_VERSION in the source must be '3.10.3'."""
        assert 'MIN_VERSION="3.10.3"' in self.source, (
            "Expected MIN_VERSION to be 3.10.3 in source"
        )

    def test_uses_sort_v_c_for_version_comparison(self):
        """Script must use 'sort -V -C' for version comparison (not string compare)."""
        assert "sort -V -C" in self.source, (
            "Expected 'sort -V -C' for version sorting, not string comparison"
        )

    def test_uses_grep_oE_for_version_extraction(self):
        """Script must use 'grep -oE' to extract semver version number."""
        assert "grep -oE" in self.source, (
            "Expected 'grep -oE' for version number extraction"
        )

    def test_flag_file_path_includes_session_id(self):
        """The disable flag file path must include the session ID variable."""
        assert 'ace-disabled-${SESSION_ID}.flag' in self.source, (
            "Expected flag file path to include ${SESSION_ID}"
        )

    def test_output_warning_produces_json_with_systemmessage(self):
        """output_warning must produce JSON with systemMessage key."""
        # Find the output_warning function
        func_match_start = self.source.index("output_warning()")
        func_region = self.source[func_match_start:func_match_start + 200]
        assert "systemMessage" in func_region, (
            "output_warning must output JSON with systemMessage key"
        )
        assert "jq -n" in func_region, (
            "output_warning should use jq to produce valid JSON"
        )

    def test_version_fallback_is_0_0_0(self):
        """When --version fails, fallback must be '0.0.0'."""
        assert '|| echo "0.0.0"' in self.source, (
            "Expected fallback version to be 0.0.0 when --version fails"
        )

    def test_cache_file_uses_daily_date(self):
        """The cache file path must include a date component for daily caching."""
        assert "$(date +%Y%m%d)" in self.source, (
            "Expected cache file to use date-based naming for daily check"
        )

    def test_npm_show_package_name(self):
        """npm show command must check @ace-sdk/cli (new package name)."""
        assert "npm show @ace-sdk/cli version" in self.source, (
            "Expected npm show to check @ace-sdk/cli package"
        )

    def test_npm_list_checks_deprecated_package(self):
        """npm list must check for @ce-dot-net/ce-ace-cli (deprecated package)."""
        assert "npm list -g @ce-dot-net/ce-ace-cli" in self.source, (
            "Expected npm list to check @ce-dot-net/ce-ace-cli"
        )

    def test_exit_codes_are_zero(self):
        """All exit statements in the version check sections should be exit 0."""
        # The script uses exit 0 to avoid disrupting Claude Code
        lines = self.source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("exit ") and not stripped.startswith("#"):
                # Strip trailing comments before comparison
                code_part = stripped.split("#")[0].strip()
                assert code_part == "exit 0", (
                    f"Line {i+1}: Expected 'exit 0' but found '{code_part}'. "
                    f"Non-zero exits would disrupt Claude Code."
                )

    def test_disable_flag_cleared_on_new_session(self):
        """The script must clear any previous disable flag at the start."""
        # Find the rm -f of the disable flag before section 1
        flag_clear_idx = self.source.index('rm -f "$ACE_DISABLED_FLAG"')
        section1_idx = self.source.index("# 1. Check if ace-cli exists")
        assert flag_clear_idx < section1_idx, (
            "Disable flag must be cleared BEFORE CLI detection (new session)"
        )

    def test_cli_detection_uses_ce_ace_fallback(self):
        """
        Verifies the deprecated ce-ace fallback uses 'command -v ce-ace'
        (fixed in v5.4.27 - was previously a copy-paste bug checking ace-cli twice).
        """
        lines = self.source.splitlines()
        ce_ace_checks = [
            i + 1 for i, line in enumerate(lines)
            if "command -v ce-ace" in line and not line.strip().startswith("#")
        ]
        assert len(ce_ace_checks) >= 1, (
            f"Expected 'command -v ce-ace' for deprecated fallback. "
            f"Found none -- the fix may have regressed."
        )


# ===========================================================================
# Edge Case Tests
# ===========================================================================


class TestEdgeCases:
    """
    Additional edge cases and boundary conditions.
    """

    def test_version_with_prefix_text_extracted(self, harness):
        """
        ace-cli --version might output 'ace-cli v3.10.3' or similar.
        The grep -oE should extract just the numeric version.
        """
        harness.add_ace_cli(version="3.10.3")
        result = harness.run()

        assert result["current_version"] == "3.10.3"

    def test_sort_v_c_semantics_10_vs_9(self, harness):
        """
        Verify sort -V handles numeric sorting correctly:
        3.10.3 > 3.9.0 (not string-based where "10" < "9").
        """
        harness.add_ace_cli(version="3.10.3")
        harness.set_min_version("3.9.0")
        result = harness.run()

        assert result["disable_flag_exists"] is False, (
            "3.10.3 should be >= 3.9.0 with version sort (not string sort)"
        )

    def test_exact_patch_boundary(self, harness):
        """Test the exact boundary: 3.10.3 should pass, 3.10.2 should fail."""
        # Test pass
        harness.add_ace_cli(version="3.10.3")
        result = harness.run()
        assert result["disable_flag_exists"] is False

    def test_exact_patch_boundary_fail(self, harness):
        """Test the exact boundary failure: 3.10.2 should fail."""
        harness.add_ace_cli(version="3.10.2")
        result = harness.run()
        assert result["disable_flag_exists"] is True

    def test_very_high_version_passes(self, harness):
        """A very high version number should still pass."""
        harness.add_ace_cli(version="99.99.99")
        result = harness.run()

        assert result["disable_flag_exists"] is False
        assert result["current_version"] == "99.99.99"

    def test_script_always_exits_zero(self, harness):
        """The harness should always exit 0, regardless of the outcome."""
        # No CLI
        result = harness.run()
        assert result["exit_code"] == 0

    def test_script_always_exits_zero_with_old_version(self, harness):
        """Even with version mismatch, exit code should be 0."""
        harness.add_ace_cli(version="1.0.0")
        result = harness.run()
        assert result["exit_code"] == 0

    def test_multiple_runs_clear_previous_flag(self, harness):
        """
        The script clears any previous disable flag at startup.
        Simulated by pre-creating the flag file.
        """
        # Pre-create a flag file
        harness.disable_flag.write_text("old reason")

        harness.add_ace_cli(version="3.10.3")
        result = harness.run()

        # Flag should be cleared (good version, no issues)
        assert result["disable_flag_exists"] is False


# ===========================================================================
# Entry point for running without pytest
# ===========================================================================


def run_tests():
    """Run all tests manually (no pytest dependency required)."""
    print("=" * 72)
    print("  ACE SessionStart Hook - Version Check TDD Tests")
    print("=" * 72)

    test_classes = [
        TestCLIDetection,
        TestDeprecatedPackageDetection,
        TestVersionComparison,
        TestDailyUpdateCheck,
        TestIntegrationScenarios,
        TestSourceCodeAnalysis,
        TestEdgeCases,
    ]

    passed = 0
    failed = 0

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
                    # Handle fixtures
                    if "harness" in method.__code__.co_varnames:
                        h = VersionCheckHarness(Path(tmpdir))
                        method(instance, h)
                    elif hasattr(instance, "_load_source"):
                        instance.source = SCRIPT_PATH.read_text()
                        method(instance)
                    else:
                        method(instance)
                print(f"  PASS  {method_name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {method_name}")
                print(f"        {e}")
                failed += 1

    print(f"\n{'=' * 72}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 72}")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
