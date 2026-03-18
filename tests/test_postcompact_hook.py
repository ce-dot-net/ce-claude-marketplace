"""
Tests for Task 3: PostCompact Hook

CC v2.1.76 added PostCompact hook that fires after compaction completes.
ACE should log compact events for insights analysis.
"""

import json
import os
import stat

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace')
HOOKS_JSON = os.path.join(PLUGIN_DIR, 'hooks', 'hooks.json')
WRAPPER = os.path.join(PLUGIN_DIR, 'scripts', 'ace_postcompact_wrapper.sh')
RELEVANCE_LOGGER = os.path.join(PLUGIN_DIR, 'shared-hooks', 'utils', 'ace_relevance_logger.py')


def _read(path):
    with open(path) as f:
        return f.read()


class TestHooksJsonPostCompact:
    """hooks.json should have a PostCompact event."""

    def test_postcompact_not_in_hooks_json(self):
        """PostCompact removed from hooks.json — CC 2.1.78 plugin schema doesn't support it.
        Pattern restoration handled by SessionStart(compact) source routing instead.
        Script remains in repo for when CC adds PostCompact to plugin schema."""
        hooks = json.loads(_read(HOOKS_JSON))
        assert 'PostCompact' not in hooks['hooks'], \
            "PostCompact should not be in hooks.json (CC 2.1.78 rejects it)"


class TestPostCompactWrapper:
    """ace_postcompact_wrapper.sh should exist and be properly configured."""

    def test_postcompact_wrapper_exists(self):
        """Script file exists."""
        assert os.path.isfile(WRAPPER), \
            f"ace_postcompact_wrapper.sh not found at {WRAPPER}"

    def test_postcompact_wrapper_executable(self):
        """Script has execute permission."""
        mode = os.stat(WRAPPER).st_mode
        assert mode & stat.S_IXUSR, \
            "ace_postcompact_wrapper.sh is not executable"

    def test_postcompact_wrapper_no_exit_1(self):
        """Script never exits with error (best-effort logging)."""
        content = _read(WRAPPER)
        assert 'exit 1' not in content, \
            "ace_postcompact_wrapper.sh has 'exit 1' — should always exit 0"


class TestRelevanceLoggerCompactFunction:
    """ace_relevance_logger.py should have log_compact_event function."""

    def test_relevance_logger_has_compact_function(self):
        """log_compact_event function exists in relevance logger."""
        content = _read(RELEVANCE_LOGGER)
        assert 'def log_compact_event' in content, \
            "ace_relevance_logger.py missing log_compact_event function"
