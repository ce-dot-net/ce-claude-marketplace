#!/usr/bin/env python3
"""
TDD RED tests for plugin settings.json (v5.5.0).

Tests that .claude-plugin/settings.json exists with correct permission rules
and env defaults to eliminate the permission prompt storm.
"""

import json
import os
import unittest
from pathlib import Path


# Path to the plugin settings.json
PLUGIN_DIR = Path(__file__).parent.parent / 'plugins' / 'ace' / '.claude-plugin'
SETTINGS_FILE = PLUGIN_DIR / 'settings.json'


class TestPluginSettings(unittest.TestCase):
    """Test plugin settings.json for default permissions."""

    def test_settings_json_exists(self):
        """File exists at .claude-plugin/settings.json."""
        self.assertTrue(
            SETTINGS_FILE.exists(),
            f"settings.json should exist at {SETTINGS_FILE}"
        )

    def test_settings_json_valid(self):
        """Valid JSON with permissions.allow array."""
        self.assertTrue(SETTINGS_FILE.exists(), "settings.json must exist")
        content = SETTINGS_FILE.read_text()
        data = json.loads(content)

        self.assertIn("permissions", data, "Must have 'permissions' key")
        self.assertIn("allow", data["permissions"], "Must have 'permissions.allow' array")
        self.assertIsInstance(data["permissions"]["allow"], list, "'allow' must be a list")
        self.assertGreater(len(data["permissions"]["allow"]), 0, "'allow' must not be empty")

    def test_settings_json_covers_ace_cli(self):
        """Contains Bash(ace-cli *) pattern."""
        data = json.loads(SETTINGS_FILE.read_text())
        allow = data["permissions"]["allow"]
        self.assertIn("Bash(ace-cli *)", allow, "Must pre-approve ace-cli commands")

    def test_settings_json_covers_uv_run(self):
        """Contains Bash(uv run *) pattern."""
        data = json.loads(SETTINGS_FILE.read_text())
        allow = data["permissions"]["allow"]
        self.assertIn("Bash(uv run *)", allow, "Must pre-approve uv run commands")

    def test_settings_json_covers_python3(self):
        """Contains Bash(python3 -c *) pattern."""
        data = json.loads(SETTINGS_FILE.read_text())
        allow = data["permissions"]["allow"]
        self.assertIn("Bash(python3 -c *)", allow, "Must pre-approve python3 -c commands")

    def test_settings_json_has_default_verbosity(self):
        """Contains env.ACE_VERBOSITY set to 'detailed'."""
        data = json.loads(SETTINGS_FILE.read_text())
        self.assertIn("env", data, "Must have 'env' key")
        self.assertEqual(
            data["env"].get("ACE_VERBOSITY"), "detailed",
            "ACE_VERBOSITY should default to 'detailed'"
        )

    def test_settings_json_no_hardcoded_org_or_project(self):
        """Does NOT contain ACE_ORG_ID or ACE_PROJECT_ID (these come from ace-configure)."""
        content = SETTINGS_FILE.read_text()
        self.assertNotIn("ACE_ORG_ID", content, "Must NOT hardcode ACE_ORG_ID")
        self.assertNotIn("ACE_PROJECT_ID", content, "Must NOT hardcode ACE_PROJECT_ID")


if __name__ == '__main__':
    unittest.main()
