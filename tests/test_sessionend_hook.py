"""
Tests for Task 2: SessionEnd Cleanup Hook

CC SDK documents SessionEnd with reason field.
ACE should clean up per-session temp files on session end.
"""

import json
import os
import stat

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace')
HOOKS_JSON = os.path.join(PLUGIN_DIR, 'hooks', 'hooks.json')
WRAPPER = os.path.join(PLUGIN_DIR, 'scripts', 'ace_sessionend_wrapper.sh')


def _read(path):
    with open(path) as f:
        return f.read()


class TestHooksJsonSessionEnd:
    """hooks.json should have a SessionEnd event."""

    def test_hooks_json_has_sessionend(self):
        """SessionEnd event exists in hooks.json."""
        hooks = json.loads(_read(HOOKS_JSON))
        assert 'SessionEnd' in hooks['hooks'], \
            "hooks.json missing SessionEnd event"

    def test_sessionend_timeout_reasonable(self):
        """SessionEnd timeout should be <= 5000ms (fast cleanup)."""
        hooks = json.loads(_read(HOOKS_JSON))
        session_end = hooks['hooks']['SessionEnd']
        for entry in session_end:
            for hook in entry.get('hooks', []):
                timeout = hook.get('timeout', 0)
                assert timeout <= 5000, \
                    f"SessionEnd timeout {timeout}ms > 5000ms"


class TestSessionEndWrapper:
    """ace_sessionend_wrapper.sh should exist and be properly configured."""

    def test_sessionend_wrapper_exists(self):
        """Script file exists."""
        assert os.path.isfile(WRAPPER), \
            f"ace_sessionend_wrapper.sh not found at {WRAPPER}"

    def test_sessionend_wrapper_executable(self):
        """Script has execute permission."""
        mode = os.stat(WRAPPER).st_mode
        assert mode & stat.S_IXUSR, \
            "ace_sessionend_wrapper.sh is not executable"

    def test_sessionend_wrapper_no_exit_1(self):
        """Script never exits with error (best-effort cleanup)."""
        content = _read(WRAPPER)
        # Should not have bare 'exit 1' — always exits 0
        assert 'exit 1' not in content, \
            "ace_sessionend_wrapper.sh has 'exit 1' — should always exit 0"

    def test_sessionend_wrapper_has_err_trap(self):
        """Script has error trap consistent with ACE pattern (with error logging)."""
        content = _read(WRAPPER)
        assert "trap 'echo" in content and "ERR" in content, \
            "ace_sessionend_wrapper.sh missing ERR trap"

    def test_sessionend_only_cleans_session_keyed_files(self):
        """Script cleans session-keyed files only, NOT project-keyed shared state."""
        content = _read(WRAPPER)
        # Session-keyed files (per-task) should be cleaned
        assert 'ace-disabled-${SESSION_ID}' in content, \
            "ace_sessionend_wrapper.sh doesn't clean session-keyed disabled flag"
        assert 'ace-patterns-precompact-${SESSION_ID}' in content, \
            "ace_sessionend_wrapper.sh doesn't clean session-keyed precompact patterns"
        # Project-keyed files are cross-task shared state — must NOT be cleaned
        assert 'ace-session-${PROJECT_ID}' not in content, \
            "ace_sessionend_wrapper.sh should NOT clean project-keyed ace-session file"
        assert 'ace-domains-${PROJECT_ID}' not in content, \
            "ace_sessionend_wrapper.sh should NOT clean project-keyed ace-domains file"
