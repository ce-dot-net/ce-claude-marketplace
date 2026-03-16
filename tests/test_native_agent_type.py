"""
Tests for Task 1: Native agent_type/agent_id (Eliminate Temp Files)

CC v2.1.69+ provides agent_type and agent_id natively in ALL hook events.
Remove temp file coordination (/tmp/ace-agent-type-{session_id}.txt).
"""

import os

# Paths
PLUGIN_DIR = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'ace')
INSTALL_CLI = os.path.join(PLUGIN_DIR, 'scripts', 'ace_install_cli.sh')
BEFORE_TASK = os.path.join(PLUGIN_DIR, 'shared-hooks', 'ace_before_task.py')
AFTER_TASK = os.path.join(PLUGIN_DIR, 'shared-hooks', 'ace_after_task.py')


def _read(path):
    with open(path) as f:
        return f.read()


class TestInstallCliNoTempFile:
    """ace_install_cli.sh should NOT write agent_type to temp file."""

    def test_install_cli_no_agent_type_file_write(self):
        """No ACE_AGENT_TYPE_FILE variable in script."""
        content = _read(INSTALL_CLI)
        assert 'ACE_AGENT_TYPE_FILE' not in content, \
            "ace_install_cli.sh still has ACE_AGENT_TYPE_FILE variable"

    def test_install_cli_no_tmp_agent_type(self):
        """No /tmp/ace-agent-type string in script."""
        content = _read(INSTALL_CLI)
        assert '/tmp/ace-agent-type' not in content, \
            "ace_install_cli.sh still references /tmp/ace-agent-type"


class TestBeforeTaskNativeAgentType:
    """ace_before_task.py should read agent_type from event, not temp file."""

    def test_before_task_reads_from_event(self):
        """Uses event.get('agent_type') and has no /tmp/ace-agent-type."""
        content = _read(BEFORE_TASK)
        assert "event.get('agent_type'" in content or 'event.get("agent_type"' in content, \
            "ace_before_task.py does not read agent_type from event"
        assert '/tmp/ace-agent-type' not in content, \
            "ace_before_task.py still references /tmp/ace-agent-type temp file"


class TestAfterTaskNativeAgentType:
    """ace_after_task.py should read agent_type from event, not temp file."""

    def test_after_task_reads_from_event(self):
        """Uses event.get('agent_type') and has no /tmp/ace-agent-type."""
        content = _read(AFTER_TASK)
        assert "event.get('agent_type'" in content or 'event.get("agent_type"' in content, \
            "ace_after_task.py does not read agent_type from event"
        assert '/tmp/ace-agent-type' not in content, \
            "ace_after_task.py still references /tmp/ace-agent-type temp file"


class TestNoTempAgentTypeAnywhere:
    """No temp file references should remain in the entire plugin."""

    def test_no_tmp_agent_type_anywhere(self):
        """Grep entire plugin for /tmp/ace-agent-type — zero matches (excl CHANGELOG)."""
        matches = []
        for root, dirs, files in os.walk(PLUGIN_DIR):
            # Skip __pycache__ and .git
            dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git')]
            for fname in files:
                if fname == 'CHANGELOG.md':
                    continue
                if not (fname.endswith('.py') or fname.endswith('.sh')):
                    continue
                fpath = os.path.join(root, fname)
                content = _read(fpath)
                if '/tmp/ace-agent-type' in content:
                    matches.append(fpath)

        assert len(matches) == 0, \
            f"Found /tmp/ace-agent-type in: {matches}"
