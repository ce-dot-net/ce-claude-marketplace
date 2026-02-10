#!/usr/bin/env python3
"""
TDD Tests for ACE CLAUDE.md cleanup_deprecated_claude() function.

Tests the bash function in plugins/ace/scripts/ace_install_cli.sh
that removes deprecated ACE content from user CLAUDE.md files.

KEY FACTS:
  - The cleaner removes the ACE HTML section between markers (any version),
    preserving all surrounding user content.
  - Backup is always created before modification.
  - The file is NEVER deleted, even if the ACE section is the entire file.
  - v5.4.27: Cleaner now handles ALL versions (v3.x, v4.x, v5.x) since
    hooks handle everything and CLAUDE.md instructions are no longer needed.

Run with: pytest tests/test_claude_md_cleaner.py -v
"""

import re
import subprocess
import tempfile
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = PROJECT_ROOT / "plugins" / "ace" / "scripts" / "ace_install_cli.sh"

# Extract just the cleanup_deprecated_claude function + a minimal harness so we
# can test it in isolation without needing ace-cli installed, jq, npm, etc.
CLEANUP_FUNCTION_HARNESS = textwrap.dedent("""\
    #!/usr/bin/env bash
    set -eo pipefail

    # Minimal output_warning stub that collects messages
    OUTPUT_LOG="__OUTPUT_LOG_PLACEHOLDER__"
    output_warning() {
      local msg="$1"
      echo "$msg" >> "$OUTPUT_LOG"
    }

    # --- Begin extracted function (matches v5.4.27 ace_install_cli.sh) ---
    cleanup_deprecated_claude() {
      local file="$1"
      local location="$2"

      if [ ! -f "$file" ]; then
        return
      fi

      if ! grep -q 'ACE_SECTION_START\\|ace-orchestration:ace-\\|# ACE Orchestration Plugin\\|# ACE Plugin' "$file" 2>/dev/null; then
        return
      fi

      local version
      version=$(grep -oE 'ACE_SECTION_START v[0-9]+\\.[0-9]+\\.[0-9]+' "$file" 2>/dev/null | head -1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' || echo "unknown")

      local backup="${file}.ace-backup-$(date +%Y%m%d-%H%M%S)"
      cp "$file" "$backup"

      if grep -q '<!-- ACE_SECTION_START' "$file" && grep -q '<!-- ACE_SECTION_END' "$file"; then
        local start_line end_line
        start_line=$(grep -n '<!-- ACE_SECTION_START' "$file" | head -1 | cut -d: -f1)
        end_line=$(grep -n '<!-- ACE_SECTION_END' "$file" | head -1 | cut -d: -f1)

        if [ -n "$start_line" ] && [ -n "$end_line" ] && [ "$start_line" -lt "$end_line" ]; then
          sed -i '' "${start_line},${end_line}d" "$file"
          sed -i '' '/^$/N;/^\\n$/d' "$file"
          output_warning "REMOVED v${version} instructions from ${location} CLAUDE.md. Backup: $(basename "$backup")"
        fi
      else
        if grep -q 'ace-orchestration:ace-\\|ace:ace-' "$file" 2>/dev/null; then
          output_warning "WARN deprecated ACE instructions in ${location} CLAUDE.md."
          rm -f "$backup" 2>/dev/null || true
        fi
      fi
    }
    # --- End extracted function ---

    # Execute with arguments passed to this script
    cleanup_deprecated_claude "$1" "$2"
""")


def run_cleaner(claude_md_content, location="project"):
    """
    Run the cleanup_deprecated_claude function against a temporary CLAUDE.md.

    Returns a dict with:
      - 'content_after': file content after cleanup (or None if file was deleted)
      - 'backup_exists': whether a backup file was created
      - 'backup_content': content of backup file if it exists
      - 'output_messages': list of warning messages emitted
      - 'exit_code': process exit code
      - 'file_exists': whether the original file still exists
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        claude_md = Path(tmpdir) / "CLAUDE.md"
        output_log = Path(tmpdir) / "output.log"
        harness_script = Path(tmpdir) / "test_cleaner.sh"

        # Write the CLAUDE.md content
        if claude_md_content is not None:
            claude_md.write_text(claude_md_content)

        # Write the test harness script
        script_text = CLEANUP_FUNCTION_HARNESS.replace(
            "__OUTPUT_LOG_PLACEHOLDER__", str(output_log)
        )
        harness_script.write_text(script_text)
        harness_script.chmod(0o755)

        # Run the cleaner
        file_arg = str(claude_md) if claude_md_content is not None else str(claude_md)
        result = subprocess.run(
            ["bash", str(harness_script), file_arg, location],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Gather results
        content_after = None
        file_exists = claude_md.exists()
        if file_exists:
            content_after = claude_md.read_text()

        backup_exists = False
        backup_content = None
        for f in Path(tmpdir).iterdir():
            if f.name.startswith("CLAUDE.md.ace-backup-"):
                backup_exists = True
                backup_content = f.read_text()
                break

        output_messages = []
        if output_log.exists():
            output_messages = [
                line for line in output_log.read_text().splitlines() if line.strip()
            ]

        return {
            "content_after": content_after,
            "backup_exists": backup_exists,
            "backup_content": backup_content,
            "output_messages": output_messages,
            "exit_code": result.returncode,
            "stderr": result.stderr,
            "file_exists": file_exists,
        }


def run_cleaner_nonexistent_file():
    """Run the cleaner against a file path that does not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_log = Path(tmpdir) / "output.log"
        harness_script = Path(tmpdir) / "test_cleaner.sh"
        nonexistent = Path(tmpdir) / "does_not_exist.md"

        script_text = CLEANUP_FUNCTION_HARNESS.replace(
            "__OUTPUT_LOG_PLACEHOLDER__", str(output_log)
        )
        harness_script.write_text(script_text)
        harness_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(harness_script), str(nonexistent), "global"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        backup_exists = any(
            f.name.startswith("does_not_exist.md.ace-backup-")
            for f in Path(tmpdir).iterdir()
        )

        output_messages = []
        if output_log.exists():
            output_messages = [
                line for line in output_log.read_text().splitlines() if line.strip()
            ]

        return {
            "exit_code": result.returncode,
            "backup_exists": backup_exists,
            "output_messages": output_messages,
            "file_exists": nonexistent.exists(),
        }


# ---------------------------------------------------------------------------
# Test fixtures for common CLAUDE.md content
# ---------------------------------------------------------------------------

V3_SECTION_WITH_USER_CONTENT = textwrap.dedent("""\
    # My Project

    This is my custom project documentation.

    ## Build Instructions

    Run `make build` to compile.

    <!-- ACE_SECTION_START v3.2.40 -->
    # ACE Orchestration Plugin

    Use /ace-orchestration:ace-search to find patterns.
    Use /ace-orchestration:ace-learn to capture learning.

    ## Commands
    - `/ace-orchestration:ace-search <query>` - Search
    - `/ace-orchestration:ace-learn` - Learn
    <!-- ACE_SECTION_END v3.2.40 -->

    ## Deployment

    Deploy with `kubectl apply -f deploy.yaml`.

    ## Notes

    Remember to update the changelog.
""")

V5_SECTION_ONLY = textwrap.dedent("""\
    # My Project Notes

    Some user content here.

    <!-- ACE_SECTION_START v5.2.0 -->
    # ACE Plugin Instructions

    Automatic pattern learning plugin.

    ## Commands Available
    - `/ace:ace-search <query>` - Search for patterns
    - `/ace:ace-learn` - Capture learning
    <!-- ACE_SECTION_END v5.2.0 -->

    More user content below.
""")

SKILL_REFS_NO_MARKERS = textwrap.dedent("""\
    # My Project

    ## ACE Setup

    Use `/ace-orchestration:ace-search` for patterns.
    Use `/ace-orchestration:ace-learn` for learning.

    ## Other Stuff

    This is important user content.
""")

NO_ACE_CONTENT = textwrap.dedent("""\
    # My Clean Project

    ## Overview

    This project has nothing to do with ACE.

    ## Build

    Run `npm build` to compile.
""")

V3_SECTION_IS_ENTIRE_FILE = textwrap.dedent("""\
    <!-- ACE_SECTION_START v3.4.10 -->
    # ACE Orchestration Plugin

    Use /ace-orchestration:ace-search to find patterns.

    ## Commands
    - `/ace-orchestration:ace-search <query>` - Search
    <!-- ACE_SECTION_END v3.4.10 -->
""")

V4_SECTION_WITH_CONTENT = textwrap.dedent("""\
    # My Project

    Some notes here.

    <!-- ACE_SECTION_START v4.1.5 -->
    # ACE Plugin v4

    Some v4 content here.
    <!-- ACE_SECTION_END v4.1.5 -->

    More user content.
""")

V3_MARKER_ON_LINE_ONE = textwrap.dedent("""\
    <!-- ACE_SECTION_START v3.5.0 -->
    # ACE Orchestration Plugin

    Old v3 instructions.
    <!-- ACE_SECTION_END v3.5.0 -->

    # My Actual Project

    This is the real content that must survive.

    ## Important Section

    Do not lose this.
""")

V3_WITH_MULTIPLE_BLANK_LINES = textwrap.dedent("""\
    # Header



    <!-- ACE_SECTION_START v3.2.0 -->
    # ACE Old Content
    <!-- ACE_SECTION_END v3.2.0 -->



    # Footer
""")


# ===========================================================================
# TEST CLASSES
# ===========================================================================


class TestV3MarkersWithUserContent:
    """
    Scenario 1: v3.x markers present with surrounding user content.
    The ACE section MUST be removed. All user content MUST be preserved.
    """

    def test_ace_section_is_removed(self):
        """After cleanup, no ACE_SECTION markers should remain."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert result["exit_code"] == 0, f"Script failed: {result['stderr']}"
        assert "ACE_SECTION_START" not in result["content_after"]
        assert "ACE_SECTION_END" not in result["content_after"]

    def test_user_content_before_section_preserved(self):
        """Content before the ACE section must be intact."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert "# My Project" in result["content_after"]
        assert "This is my custom project documentation." in result["content_after"]
        assert "Run `make build` to compile." in result["content_after"]

    def test_user_content_after_section_preserved(self):
        """Content after the ACE section must be intact."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert "## Deployment" in result["content_after"]
        assert "Deploy with `kubectl apply -f deploy.yaml`." in result["content_after"]
        assert "Remember to update the changelog." in result["content_after"]

    def test_ace_instructions_removed(self):
        """The actual ACE instructions between markers must be gone."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert "ace-orchestration:ace-search" not in result["content_after"]
        assert "ace-orchestration:ace-learn" not in result["content_after"]
        assert "# ACE Orchestration Plugin" not in result["content_after"]

    def test_removal_warning_emitted(self):
        """A warning message should be emitted about the removal."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT, location="project")
        assert len(result["output_messages"]) >= 1
        msgs = " ".join(result["output_messages"])
        assert "REMOVED" in msgs or "Removed" in msgs
        assert "project" in msgs


class TestV5MarkersNowCleaned:
    """
    Scenario 2: v5.x markers are present.
    v5.4.27 fix: The cleaner now removes ALL versions since hooks handle everything.
    """

    def test_v5_section_is_removed(self):
        """v5.x section must be removed (v5.4.27 fix)."""
        result = run_cleaner(V5_SECTION_ONLY)
        assert result["exit_code"] == 0
        assert "ACE_SECTION_START" not in result["content_after"]
        assert "ACE_SECTION_END" not in result["content_after"]

    def test_v5_removal_warning_emitted(self):
        """A removal warning should be emitted for v5.x content."""
        result = run_cleaner(V5_SECTION_ONLY)
        removal_msgs = [m for m in result["output_messages"] if "REMOVED" in m]
        assert len(removal_msgs) >= 1, (
            f"v5.x content should trigger removal. Messages: {result['output_messages']}"
        )

    def test_v5_user_content_preserved(self):
        """All user content around v5.x section remains intact."""
        result = run_cleaner(V5_SECTION_ONLY)
        assert "# My Project Notes" in result["content_after"]
        assert "Some user content here." in result["content_after"]
        assert "More user content below." in result["content_after"]

    def test_v5_ace_instructions_removed(self):
        """The actual ACE instructions between markers must be gone."""
        result = run_cleaner(V5_SECTION_ONLY)
        assert "Automatic pattern learning plugin." not in result["content_after"]
        assert "ace:ace-search" not in result["content_after"]


class TestSkillReferencesNoMarkers:
    """
    Scenario 3: File has ace-orchestration skill references but no HTML markers.
    The cleaner should WARN but NOT modify the file.
    """

    def test_file_not_modified(self):
        """File content must remain exactly the same."""
        result = run_cleaner(SKILL_REFS_NO_MARKERS)
        assert result["content_after"] == SKILL_REFS_NO_MARKERS

    def test_warning_emitted(self):
        """A deprecation warning should be emitted."""
        result = run_cleaner(SKILL_REFS_NO_MARKERS, location="global")
        assert len(result["output_messages"]) >= 1
        msgs = " ".join(result["output_messages"])
        assert "WARN" in msgs or "deprecated" in msgs.lower()

    def test_backup_removed_since_no_modification(self):
        """
        Since the file is not modified, the backup should be cleaned up.
        The function creates a backup then deletes it if no modification occurs
        in the skill-refs-only path.
        """
        result = run_cleaner(SKILL_REFS_NO_MARKERS)
        assert result["backup_exists"] is False, (
            "Backup should be deleted when file is not modified (skill refs only path)"
        )


class TestNoAceContentAtAll:
    """
    Scenario 4: CLAUDE.md has no ACE references whatsoever.
    The cleaner must not touch it and must not create a backup.
    """

    def test_file_not_modified(self):
        """File content must be completely unchanged."""
        result = run_cleaner(NO_ACE_CONTENT)
        assert result["content_after"] == NO_ACE_CONTENT

    def test_no_backup_created(self):
        """No backup file should be created."""
        result = run_cleaner(NO_ACE_CONTENT)
        assert result["backup_exists"] is False, (
            "No backup should be created when file has no ACE content"
        )

    def test_no_warnings_emitted(self):
        """No warning messages should be emitted."""
        result = run_cleaner(NO_ACE_CONTENT)
        assert len(result["output_messages"]) == 0, (
            f"No warnings expected for clean file. Got: {result['output_messages']}"
        )

    def test_exit_code_zero(self):
        """Script should exit cleanly."""
        result = run_cleaner(NO_ACE_CONTENT)
        assert result["exit_code"] == 0


class TestFileDoesNotExist:
    """
    Scenario 5: The target file does not exist.
    The function must return gracefully without errors.
    """

    def test_graceful_return(self):
        """Function should return without error when file is missing."""
        result = run_cleaner_nonexistent_file()
        assert result["exit_code"] == 0

    def test_no_backup_created(self):
        """No backup should be created for nonexistent file."""
        result = run_cleaner_nonexistent_file()
        assert result["backup_exists"] is False

    def test_no_warnings_emitted(self):
        """No warnings should be emitted for nonexistent file."""
        result = run_cleaner_nonexistent_file()
        assert len(result["output_messages"]) == 0

    def test_file_not_created(self):
        """The function must not create the file if it didn't exist."""
        result = run_cleaner_nonexistent_file()
        assert result["file_exists"] is False


class TestBackupCreation:
    """
    Scenario 6: Verify backup file is created before any modification.
    """

    def test_backup_created_on_v3_removal(self):
        """A backup must exist after v3.x section removal."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert result["backup_exists"] is True

    def test_backup_contains_original_content(self):
        """The backup must contain the exact original file content."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert result["backup_content"] == V3_SECTION_WITH_USER_CONTENT

    def test_backup_preserves_ace_section(self):
        """The backup must still have the ACE section for recovery."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert "ACE_SECTION_START v3.2.40" in result["backup_content"]
        assert "ACE_SECTION_END v3.2.40" in result["backup_content"]


class TestMultipleBlankLinesCleanup:
    """
    Scenario 7: After section removal, consecutive blank lines should be collapsed.
    """

    def test_no_triple_blank_lines_after_removal(self):
        """After removal, there should be no runs of 3+ consecutive blank lines."""
        result = run_cleaner(V3_WITH_MULTIPLE_BLANK_LINES)
        assert result["exit_code"] == 0
        content = result["content_after"]
        # Check there are no 3+ consecutive newlines (which would mean 2+ blank lines)
        assert "\n\n\n" not in content, (
            f"Found triple+ blank lines in cleaned output:\n---\n{content}\n---"
        )

    def test_structural_content_preserved(self):
        """Header and Footer sections must survive the cleanup."""
        result = run_cleaner(V3_WITH_MULTIPLE_BLANK_LINES)
        assert "# Header" in result["content_after"]
        assert "# Footer" in result["content_after"]

    def test_ace_section_removed(self):
        """The v3.2.0 ACE section must be removed."""
        result = run_cleaner(V3_WITH_MULTIPLE_BLANK_LINES)
        assert "ACE_SECTION_START" not in result["content_after"]
        assert "ACE Old Content" not in result["content_after"]


class TestV4MarkersNowCleaned:
    """
    Scenario 8: v4.x markers are present.
    v5.4.27 fix: The cleaner now removes ALL versions.
    """

    def test_v4_section_is_removed(self):
        """v4.x section must be removed (v5.4.27 fix)."""
        result = run_cleaner(V4_SECTION_WITH_CONTENT)
        assert result["exit_code"] == 0
        assert "ACE_SECTION_START" not in result["content_after"]
        assert "ACE_SECTION_END" not in result["content_after"]

    def test_v4_backup_created(self):
        """Backup must be created before removal."""
        result = run_cleaner(V4_SECTION_WITH_CONTENT)
        assert result["backup_exists"] is True

    def test_v4_user_content_preserved(self):
        """User content around v4.x section must survive."""
        result = run_cleaner(V4_SECTION_WITH_CONTENT)
        assert "# My Project" in result["content_after"]
        assert "Some notes here." in result["content_after"]
        assert "More user content." in result["content_after"]

    def test_v4_ace_instructions_removed(self):
        """v4.x ACE instructions must be gone."""
        result = run_cleaner(V4_SECTION_WITH_CONTENT)
        assert "# ACE Plugin v4" not in result["content_after"]
        assert "Some v4 content here." not in result["content_after"]


class TestEntireFileSafety:
    """
    Scenario 9 (CRITICAL): The ACE section IS the entire file content.
    After cleanup the file must still exist (possibly empty), NOT be deleted.
    """

    def test_file_still_exists(self):
        """The file must NOT be deleted -- it should remain on disk."""
        result = run_cleaner(V3_SECTION_IS_ENTIRE_FILE)
        assert result["file_exists"] is True, (
            "CRITICAL: File was deleted! The cleaner must never delete the file."
        )

    def test_ace_content_removed(self):
        """All ACE content should be removed from the file."""
        result = run_cleaner(V3_SECTION_IS_ENTIRE_FILE)
        assert "ACE_SECTION_START" not in result["content_after"]
        assert "ACE_SECTION_END" not in result["content_after"]
        assert "ace-orchestration:ace-search" not in result["content_after"]

    def test_file_is_empty_or_minimal(self):
        """
        The file should be empty or contain only whitespace after removal,
        since the ACE section was the entire content.
        """
        result = run_cleaner(V3_SECTION_IS_ENTIRE_FILE)
        stripped = result["content_after"].strip()
        assert stripped == "", (
            f"Expected empty file after removing entire ACE section. "
            f"Got: '{stripped}'"
        )

    def test_backup_has_original(self):
        """Backup must contain the full original content for recovery."""
        result = run_cleaner(V3_SECTION_IS_ENTIRE_FILE)
        assert result["backup_exists"] is True
        assert "ACE_SECTION_START v3.4.10" in result["backup_content"]


class TestMarkerOnFirstLine:
    """
    Scenario 10: ACE_SECTION_START is on line 1, user content only after ACE_SECTION_END.
    """

    def test_ace_section_removed(self):
        """The v3 section starting on line 1 must be removed."""
        result = run_cleaner(V3_MARKER_ON_LINE_ONE)
        assert "ACE_SECTION_START" not in result["content_after"]
        assert "ACE_SECTION_END" not in result["content_after"]
        assert "Old v3 instructions." not in result["content_after"]

    def test_user_content_after_section_preserved(self):
        """All user content after the ACE section must survive."""
        result = run_cleaner(V3_MARKER_ON_LINE_ONE)
        assert "# My Actual Project" in result["content_after"]
        assert "This is the real content that must survive." in result["content_after"]
        assert "Do not lose this." in result["content_after"]

    def test_user_content_structure_intact(self):
        """The heading hierarchy of user content must be preserved."""
        result = run_cleaner(V3_MARKER_ON_LINE_ONE)
        content = result["content_after"]
        assert "## Important Section" in content


# ===========================================================================
# Source code analysis tests -- verify the actual script's logic
# ===========================================================================


class TestSourceCodeAnalysis:
    """
    Static analysis of the actual ace_install_cli.sh to verify the cleanup
    logic patterns and detect potential issues.
    """

    def test_script_exists(self):
        """The script file must exist at the expected path."""
        assert SCRIPT_PATH.exists(), f"Script not found at {SCRIPT_PATH}"

    def test_cleanup_function_exists(self):
        """The cleanup_deprecated_claude function must be defined."""
        source = SCRIPT_PATH.read_text()
        assert "cleanup_deprecated_claude()" in source

    def test_initial_guard_matches_all_versions(self):
        """
        v5.4.27: The initial grep guard matches ANY ACE_SECTION_START marker,
        not just v3.x. This ensures v4.x and v5.x content is also detected.
        """
        source = SCRIPT_PATH.read_text()
        func_start = source.index("cleanup_deprecated_claude()")
        func_body = source[func_start:func_start + 2000]
        # Should match generic ACE_SECTION_START (not v3-specific)
        assert "ACE_SECTION_START" in func_body
        # Should NOT have the v3-only gate anymore
        assert "ACE_SECTION_START v3\\." not in func_body, (
            "Initial guard should match all versions, not just v3.x"
        )

    def test_no_version_specific_removal_gate(self):
        """
        v5.4.27: There should be no version-specific gate before sed removal.
        All versions with markers should be cleaned.
        """
        source = SCRIPT_PATH.read_text()
        func_start = source.index("cleanup_deprecated_claude()")
        func_body = source[func_start:func_start + 2000]
        # Should NOT have the old v3-only marker_version check
        assert "grep -q 'v3\\.'" not in func_body, (
            "Should not have v3-only version gate - all versions should be cleaned"
        )

    def test_sed_uses_line_range_not_file_delete(self):
        """
        The sed command must use line range deletion, NOT file-level operations.
        This ensures only the marked section is removed.
        """
        source = SCRIPT_PATH.read_text()
        # Pattern: sed -i '' "${start_line},${end_line}d"
        assert '${start_line},${end_line}d' in source, (
            "Expected sed to use line range deletion for safety"
        )

    def test_backup_created_before_sed(self):
        """
        The backup (cp) must appear BEFORE the sed deletion in the function.
        """
        source = SCRIPT_PATH.read_text()
        # Extract just the function body
        func_start = source.index("cleanup_deprecated_claude()")
        func_section = source[func_start:func_start + 2000]
        cp_pos = func_section.index('cp "$file" "$backup"')
        sed_pos = func_section.index("sed -i ''")
        assert cp_pos < sed_pos, (
            "Backup (cp) must occur BEFORE sed modification"
        )

    def test_no_rm_of_original_file(self):
        """
        The function must NEVER use 'rm' on the original file.
        Only 'rm -f "$backup"' is acceptable (for the no-modification path).
        """
        source = SCRIPT_PATH.read_text()
        func_start = source.index("cleanup_deprecated_claude()")
        # Find the closing brace by counting
        func_end = source.index("\n}", func_start) + 2
        func_body = source[func_start:func_end]

        # Check all rm commands in the function
        rm_lines = [
            line.strip()
            for line in func_body.splitlines()
            if "rm " in line and not line.strip().startswith("#")
        ]
        for rm_line in rm_lines:
            assert "$backup" in rm_line, (
                f"Found 'rm' command that does NOT target backup: {rm_line}. "
                f"The cleaner must never delete the original file!"
            )

    def test_no_v3_only_gates(self):
        """
        v5.4.27: Verify the function has NO v3-only gates.
        All versions should be cleaned since hooks handle everything.
        """
        source = SCRIPT_PATH.read_text()
        func_start = source.index("cleanup_deprecated_claude()")
        func_end = source.index("\n}", func_start) + 2
        func_body = source[func_start:func_end]

        v3_checks = re.findall(r"v3\\?\.", func_body)
        assert len(v3_checks) == 0, (
            f"Found {len(v3_checks)} v3-only gates in function. "
            f"All versions should be cleaned now."
        )


# ===========================================================================
# Gap analysis summary tests
# ===========================================================================


class TestAllVersionsCleaned:
    """
    v5.4.27: Verify ALL ACE versions are now cleaned.
    Previous gaps (v4.x, v5.x not cleaned) are now fixed.
    """

    def test_v5_markers_now_cleaned(self):
        """v5.x markers are now cleaned (gap fixed in v5.4.27)."""
        result = run_cleaner(V5_SECTION_ONLY)
        assert "ACE_SECTION_START" not in result["content_after"]
        assert result["backup_exists"] is True

    def test_v4_markers_now_cleaned(self):
        """v4.x markers are now cleaned (gap fixed in v5.4.27)."""
        result = run_cleaner(V4_SECTION_WITH_CONTENT)
        assert "ACE_SECTION_START" not in result["content_after"]
        assert result["backup_exists"] is True

    def test_v3_markers_still_cleaned(self):
        """v3.x markers continue to be cleaned as before."""
        result = run_cleaner(V3_SECTION_WITH_USER_CONTENT)
        assert "ACE_SECTION_START" not in result["content_after"]
        assert result["backup_exists"] is True


# ===========================================================================
# Entry point for running without pytest
# ===========================================================================


def run_tests():
    """Run all tests manually (no pytest dependency required)."""
    print("=" * 72)
    print("  ACE CLAUDE.md Cleaner - TDD Verification Tests")
    print("=" * 72)

    test_classes = [
        TestV3MarkersWithUserContent,
        TestV5MarkersNowCleaned,
        TestSkillReferencesNoMarkers,
        TestNoAceContentAtAll,
        TestFileDoesNotExist,
        TestBackupCreation,
        TestMultipleBlankLinesCleanup,
        TestV4MarkersNowCleaned,
        TestEntireFileSafety,
        TestMarkerOnFirstLine,
        TestSourceCodeAnalysis,
        TestAllVersionsCleaned,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for cls in test_classes:
        instance = cls()
        print(f"\n{'─' * 60}")
        print(f"  {cls.__name__}")
        if cls.__doc__:
            first_line = cls.__doc__.strip().splitlines()[0].strip()
            print(f"  {first_line}")
        print(f"{'─' * 60}")

        for method_name in sorted(dir(instance)):
            if not method_name.startswith("test_"):
                continue

            method = getattr(instance, method_name)

            # Skip xfail tests in manual mode
            if hasattr(method, "pytestmark"):
                marks = [m for m in method.pytestmark if m.name == "xfail"]
                if marks:
                    print(f"  SKIP  {method_name} (xfail)")
                    skipped += 1
                    continue

            try:
                method()
                print(f"  PASS  {method_name}")
                passed += 1
            except (AssertionError, Exception) as e:
                print(f"  FAIL  {method_name}")
                print(f"        {e}")
                failed += 1

    print(f"\n{'=' * 72}")
    print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'=' * 72}")
    return failed == 0


if __name__ == "__main__":
    import sys

    success = run_tests()
    sys.exit(0 if success else 1)
