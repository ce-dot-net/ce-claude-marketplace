"""TDD: ACE_CLIENT_ID env var for per-extension analytics tracking.

SessionStart sets ACE_CLIENT_ID=claude-code via CLAUDE_ENV_FILE
so the ACE server can distinguish Claude Code plugin traffic.
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / 'plugins' / 'ace'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'
INSTALL_CLI = PLUGIN_ROOT / 'shared-hooks' / 'ace_install_cli.py'  # v8: shim execs this


class TestClientIdInSessionStart:
    """SessionStart must set ACE_CLIENT_ID via CLAUDE_ENV_FILE."""

    def test_sets_ace_client_id(self):
        content = INSTALL_CLI.read_text()
        assert 'ACE_CLIENT_ID' in content, \
            "ace_install_cli.py must set ACE_CLIENT_ID"

    def test_uses_claude_env_file(self):
        content = INSTALL_CLI.read_text()
        assert 'CLAUDE_ENV_FILE' in content, \
            "Must use CLAUDE_ENV_FILE to persist env var across hooks"

    def test_client_id_is_claude_code(self):
        # DESIGN §8: same id as _ace_env.sh, claude-code-plugin/<version>
        assert 'client_id()' in INSTALL_CLI.read_text()
        assert 'claude-code-plugin/' in (PLUGIN_ROOT / 'shared-hooks' / 'utils' / 'ace_env.py').read_text()

    def test_only_sets_if_not_already_set(self):
        """Should not override user's custom ACE_CLIENT_ID."""
        content = INSTALL_CLI.read_text()
        # Should check if ACE_CLIENT_ID is already set before writing
        assert any(p in content for p in ['ACE_CLIENT_ID:-', 'ACE_CLIENT_ID:=', '-z "$ACE_CLIENT_ID"', 'ACE_CLIENT_ID=""', 'get("ACE_CLIENT_ID")']), \
            "Must only set ACE_CLIENT_ID if not already set (respect user override)"
