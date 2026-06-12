#!/usr/bin/env python3
"""
Floor-bump tests (Problem 5 / former v7.1.2 Feature C).

C) FLOOR BUMP:
   - ace_install_cli.sh MIN_VERSION must be 4.1.2 (not 4.1.1)
   - plugin.json description must mention CC >= 2.1.163 (not 2.1.139)
   - plugin.json description must mention ace-cli >= 4.1.2 (not 4.1.1)
   - plugin.json description must mention @ace-sdk/core >= 3.2.2 (not 3.2.0)
   - ace-doctor.md floor version string must be 4.1.2 (not 4.1.1)
   - test_version_check.py source analysis must pass (4.1.2 in source)

NOTE: The former v7.1.2 D (Stop eval-loop refactor) and E (terminalSequence)
test classes were intentionally dropped — that work is parked in the
`v7.1.2-WIP` git stash and is NOT part of the problems 1-5 rebuild.
"""

import json
import re
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO / "plugins" / "ace"
SCRIPTS = PLUGIN_ROOT / "scripts"
COMMANDS = PLUGIN_ROOT / "commands"

INSTALL_CLI = SCRIPTS / "ace_install_cli.sh"
PLUGIN_JSON = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
ACE_DOCTOR_MD = COMMANDS / "ace-doctor.md"


# ═══════════════════════════════════════════════════════════════════════════════
# C. FLOOR BUMP
# ═══════════════════════════════════════════════════════════════════════════════

class TestFloorBump:
    """
    ace_install_cli.sh MIN_VERSION must be 4.1.2.
    plugin.json description must have CC >= 2.1.163, ace-cli >= 4.1.2,
    @ace-sdk/core >= 3.2.2.
    ace-doctor.md must reference 4.1.2.
    """

    def test_install_cli_min_version_is_4_1_2(self):
        """MIN_VERSION in ace_install_cli.sh must be 4.1.2."""
        source = INSTALL_CLI.read_text()
        assert 'MIN_VERSION="4.1.2"' in source, (
            f"ace_install_cli.sh must have MIN_VERSION=\"4.1.2\"; "
            f"currently has: {[l for l in source.splitlines() if 'MIN_VERSION' in l]}"
        )

    def test_install_cli_no_stale_min_version_4_1_1(self):
        """The old active MIN_VERSION=4.1.1 must not remain as the active value."""
        source = INSTALL_CLI.read_text()
        # Find the active MIN_VERSION line (not a comment)
        active_lines = [
            l for l in source.splitlines()
            if 'MIN_VERSION=' in l and not l.strip().startswith('#')
        ]
        for line in active_lines:
            assert '4.1.1' not in line, (
                f"Stale MIN_VERSION=4.1.1 still active in ace_install_cli.sh: {line!r}"
            )

    def test_plugin_json_description_cc_floor_2_1_163(self):
        """plugin.json description must mention Claude Code >= 2.1.163."""
        data = json.loads(PLUGIN_JSON.read_text())
        desc = data['description']
        # Must reference 2.1.163 as CC floor
        assert '2.1.163' in desc, (
            f"plugin.json description must mention CC floor 2.1.163; current desc: {desc!r}"
        )

    def test_plugin_json_description_no_stale_cc_floor_2_1_139(self):
        """plugin.json description must NOT still reference 2.1.139 as the CC floor."""
        data = json.loads(PLUGIN_JSON.read_text())
        desc = data['description']
        # The old floor 2.1.139 must not appear as the Requires: floor
        # (it may appear in historical notes but the Requires: line must be updated)
        requires_match = re.search(r'Requires:.*?Claude Code\s*>=\s*([\d.]+)', desc)
        if requires_match:
            assert requires_match.group(1) != '2.1.139', (
                f"plugin.json Requires: CC floor is still 2.1.139; must be updated to 2.1.163"
            )

    def test_plugin_json_description_ace_cli_floor_4_1_2(self):
        """plugin.json description Requires: line must mention ace-cli >= 4.1.2."""
        data = json.loads(PLUGIN_JSON.read_text())
        desc = data['description']
        # The active Requires: line must have 4.1.2
        requires_match = re.search(r'Requires:.*?ace-cli\s*>=\s*([\d.]+)', desc)
        assert requires_match is not None, (
            f"plugin.json description has no 'Requires: ... ace-cli >= ...' line; desc: {desc!r}"
        )
        assert requires_match.group(1) == '4.1.2', (
            f"plugin.json Requires: ace-cli floor is {requires_match.group(1)!r}; "
            f"must be 4.1.2"
        )

    def test_plugin_json_description_ace_sdk_core_3_2_2(self):
        """plugin.json description Requires: line must mention @ace-sdk/core >= 3.2.2."""
        data = json.loads(PLUGIN_JSON.read_text())
        desc = data['description']
        # The active Requires: line must have 3.2.2
        requires_match = re.search(r'Requires:.*?@ace-sdk/core\s*>=\s*([\d.]+)', desc)
        assert requires_match is not None, (
            f"plugin.json description has no 'Requires: ... @ace-sdk/core >= ...' pattern; desc: {desc!r}"
        )
        assert requires_match.group(1) == '3.2.2', (
            f"plugin.json Requires: @ace-sdk/core floor is {requires_match.group(1)!r}; "
            f"must be 3.2.2"
        )

    def test_ace_doctor_md_cli_floor_4_1_2(self):
        """ace-doctor.md must reference 4.1.2 as the ace-cli floor."""
        doc = ACE_DOCTOR_MD.read_text()
        assert '4.1.2' in doc, (
            "ace-doctor.md must mention ace-cli floor 4.1.2"
        )

    def test_ace_doctor_md_no_stale_4_1_1_as_minimum(self):
        """ace-doctor.md floor requirement bullet must not still use 4.1.1."""
        doc = ACE_DOCTOR_MD.read_text()
        # The requirement bullet like "- ace-cli: v4.1.1+" must be updated
        has_old_floor_as_requirement = bool(
            re.search(r'ace-cli:\s*v?4\.1\.1\+', doc)
        )
        assert not has_old_floor_as_requirement, (
            "ace-doctor.md still uses 'ace-cli: v4.1.1+' as requirement; must be 4.1.2+"
        )

    def test_version_check_harness_uses_4_1_2(self):
        """
        test_version_check.py VERSION_CHECK_HARNESS default MIN_VERSION must be
        updated to 4.1.2 so the source-analysis test passes.
        This test checks the *harness source code* in test_version_check.py itself
        (since that file has a DEFAULT_MIN_VERSION that is used in test assertions).
        """
        test_file = REPO / "tests" / "test_version_check.py"
        content = test_file.read_text()
        assert '"4.1.2"' in content or "'4.1.2'" in content, (
            "test_version_check.py must reference 4.1.2 (for test_min_version_is_4_1_2 "
            "and the harness default MIN_VERSION). Currently hardcoded to 4.1.1."
        )
