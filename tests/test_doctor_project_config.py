#!/usr/bin/env python3
"""
TDD Tests for projectId configuration mismatch bugs.

Bug 1: ace-doctor Check 5 reads projectId from the WRONG location.
  - It should read ACE_PROJECT_ID from .claude/settings.json (env var),
    NOT projectId from ~/.config/ace/config.json (global config).
  - The correct jq pattern: '.env.ACE_PROJECT_ID // .projectId // empty'

Bug 2: ace_install_cli.sh SessionStart hook should warn about stale
  projectId in global config (~/.config/ace/config.json).

Run with: pytest tests/test_doctor_project_config.py -v
"""

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DOCTOR_PATH = PROJECT_ROOT / "plugins" / "ace" / "commands" / "ace-doctor.md"
INSTALL_CLI_PATH = PROJECT_ROOT / "plugins" / "ace" / "scripts" / "ace_install_cli.sh"


# ===========================================================================
# Bug 1: ace-doctor Check 5 reads wrong config
# ===========================================================================


class TestDoctorCheck5ProjectConfig:
    """
    Verify that ace-doctor.md Check 5 (ACE Server Connectivity) reads
    ACE_PROJECT_ID from .claude/settings.json using the correct fallback
    pattern, and does NOT read projectId from the global config.
    """

    @pytest.fixture(autouse=True)
    def _load_source(self):
        """Load the doctor command file."""
        self.source = DOCTOR_PATH.read_text()

    def _extract_check5_block(self) -> str:
        """Extract the Check 5 section from the doctor file."""
        # Find Check 5 section
        match = re.search(
            r"### Check 5:.*?(?=### Check 6:|---\s*\n## |\Z)",
            self.source,
            re.DOTALL,
        )
        assert match is not None, "Check 5 section not found in ace-doctor.md"
        return match.group(0)

    def _extract_check5_bash(self) -> str:
        """Extract the bash code block from Check 5."""
        check5 = self._extract_check5_block()
        bash_match = re.search(r"```bash\n(.*?)```", check5, re.DOTALL)
        assert bash_match is not None, "No bash code block in Check 5"
        return bash_match.group(1)

    def test_doctor_check5_reads_project_settings(self):
        """8.1.0: Check 5 gets the binding and the status call from the one core (scripts/ace-context --line)."""
        bash = self._extract_check5_bash()
        assert "scripts/ace-context" in bash
        assert "settings.json" not in bash

    def test_doctor_check5_does_not_read_global_projectid(self):
        """The global config projectId is never a binding (spec: global_project_id_ignored); Check 5 reads none."""
        bash = self._extract_check5_bash()
        assert "config.json" not in bash and "projectId" not in bash
