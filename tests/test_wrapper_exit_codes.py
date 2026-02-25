#!/usr/bin/env python3
"""
TDD RED tests for wrapper script exit code safety (v5.5.0).

Ensures no ACE wrapper script can block user actions via exit 1.
Per Claude Code hook protocol: exit 0 = continue, exit 1 = BLOCK.
ACE hooks should NEVER block.
"""

import os
import re
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / 'plugins' / 'ace' / 'scripts'
WRAPPER_SCRIPTS = [
    'ace_before_task_wrapper.sh',
    'ace_after_task_wrapper.sh',
    'ace_stop_wrapper.sh',
    'ace_subagent_stop_wrapper.sh',
    'ace_posttooluse_wrapper.sh',
    'ace_precompact_wrapper.sh',
    'ace_install_cli.sh',
]


class TestWrapperExitCodes(unittest.TestCase):
    """Ensure no wrapper script can block user actions."""

    def test_no_exit_1_in_any_wrapper(self):
        """No wrapper script should contain 'exit 1' - hooks must never block."""
        violations = []
        for script_name in WRAPPER_SCRIPTS:
            script_path = SCRIPTS_DIR / script_name
            if not script_path.exists():
                continue
            content = script_path.read_text()
            # Find all exit 1 occurrences (not in comments)
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if re.search(r'\bexit\s+1\b', stripped):
                    violations.append(f"{script_name}:{i}: {stripped}")

        self.assertEqual(violations, [],
            f"Found 'exit 1' in wrapper scripts (hooks must never block):\n" +
            "\n".join(violations))

    def test_err_trap_in_all_wrappers(self):
        """All wrapper scripts should have ERR trap for safety."""
        missing_trap = []
        for script_name in WRAPPER_SCRIPTS:
            script_path = SCRIPTS_DIR / script_name
            if not script_path.exists():
                continue
            content = script_path.read_text()
            if "trap 'exit 0' ERR" not in content and 'trap "exit 0" ERR' not in content:
                missing_trap.append(script_name)

        self.assertEqual(missing_trap, [],
            f"Missing ERR trap in wrapper scripts:\n" +
            "\n".join(missing_trap))

    def test_no_Euo_pipefail(self):
        """Wrappers should use 'set -euo pipefail' not 'set -Eeuo pipefail'."""
        violations = []
        for script_name in WRAPPER_SCRIPTS:
            script_path = SCRIPTS_DIR / script_name
            if not script_path.exists():
                continue
            content = script_path.read_text()
            if 'set -Eeuo pipefail' in content:
                violations.append(script_name)

        self.assertEqual(violations, [],
            f"Found 'set -Eeuo pipefail' (should be 'set -euo pipefail'):\n" +
            "\n".join(violations))

    def test_all_wrapper_scripts_exist(self):
        """All expected wrapper scripts should exist."""
        missing = []
        for script_name in WRAPPER_SCRIPTS:
            script_path = SCRIPTS_DIR / script_name
            if not script_path.exists():
                missing.append(script_name)

        self.assertEqual(missing, [],
            f"Missing wrapper scripts:\n" + "\n".join(missing))
