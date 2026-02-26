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


class TestAceInsightsPermissions(unittest.TestCase):
    """Test that ace-insights commands match permission patterns."""

    def setUp(self):
        self.insights_path = Path(__file__).parent.parent / 'plugins' / 'ace' / 'commands' / 'ace-insights.md'
        self.content = self.insights_path.read_text()

    def test_no_bash_shebang_in_code_blocks(self):
        """ace-insights should not use #!/usr/bin/env bash in code blocks."""
        import re
        code_blocks = re.findall(r'```bash\n(.*?)```', self.content, re.DOTALL)
        for i, block in enumerate(code_blocks):
            self.assertNotIn('#!/usr/bin/env bash', block,
                f"Code block {i+1} uses bash shebang - won't match python3 -c permission pattern")

    def test_step1_uses_python3_c(self):
        """Step 1 extraction should use python3 -c command."""
        import re
        step1_match = re.search(r'### Step 1.*?```bash\n(.*?)```', self.content, re.DOTALL)
        self.assertIsNotNone(step1_match, "Step 1 must have a bash code block")
        code = step1_match.group(1)
        self.assertTrue(code.strip().startswith('python3 -c'),
            "Step 1 code block must start with 'python3 -c' to match permission pattern")

    def test_step3_uses_python3_c(self):
        """Step 3 HTML generation should use python3 -c command."""
        import re
        step3_match = re.search(r'### Step 3.*?```bash\n(.*?)```', self.content, re.DOTALL)
        self.assertIsNotNone(step3_match, "Step 3 must have a bash code block")
        code = step3_match.group(1)
        self.assertTrue(code.strip().startswith('python3 -c'),
            "Step 3 code block must start with 'python3 -c' to match permission pattern")

    def test_no_set_euo_pipefail(self):
        """ace-insights should not use set -euo pipefail (bash-only)."""
        import re
        code_blocks = re.findall(r'```bash\n(.*?)```', self.content, re.DOTALL)
        for i, block in enumerate(code_blocks):
            self.assertNotIn('set -euo pipefail', block,
                f"Code block {i+1} uses set -euo pipefail - not needed for python3 -c commands")


if __name__ == '__main__':
    unittest.main()
