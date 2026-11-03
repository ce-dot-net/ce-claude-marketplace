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


REPO = Path(__file__).parent.parent
SETTINGS_FILE = REPO / 'plugins' / 'ace' / '.claude-plugin' / 'settings.json'
RELEASE_MANAGER = REPO / '.claude' / 'agents' / 'release-manager.md'


class TestPluginSettingsRemoved(unittest.TestCase):
    """v8 (WP-A, critic T25): .claude-plugin/settings.json was dead config: only
    `agent`/`subagentStatusLine` are honored in a plugin settings.json, so the
    `Bash(ace-cli *)` allow-rules it carried never applied. Deleted.
    (Replaces the v5.5 tests that pinned its existence.)"""

    def test_settings_json_deleted(self):
        self.assertFalse(SETTINGS_FILE.exists(), f"{SETTINGS_FILE} must be deleted")


class TestReleaseManagerDoc(unittest.TestCase):
    """DESIGN §6 WP-A: release-manager = 3 manifests, CHANGELOG mandatory, no
    `claude plugin tag`, no plugin.local.json."""

    def setUp(self):
        self.doc = RELEASE_MANAGER.read_text()

    def test_no_plugin_local_json(self):
        self.assertNotIn('plugin.local.json', self.doc)

    def test_no_claude_plugin_tag(self):
        self.assertNotIn('claude plugin tag', self.doc)

    def test_changelog_mandatory(self):
        self.assertRegex(self.doc, r'(?i)CHANGELOG\.md[^\n]*\b(mandatory|must|required)\b')

    def test_three_manifests_listed(self):
        for m in ('.claude-plugin/plugin.json', 'plugin.template.json', 'marketplace.json'):
            self.assertIn(m, self.doc)


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
