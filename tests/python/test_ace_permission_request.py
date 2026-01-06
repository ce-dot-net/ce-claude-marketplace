#!/usr/bin/env python3
"""
Unit tests for ace_permission_request.py - Security Gate Logic

CRITICAL: Tests the ACTUAL security decisions, not just "hook forwards to Python".
This is a security gate - bugs here could allow destructive commands.

Found bugs: 8 security bypasses where ce-ace (legacy CLI) commands are not in safe/dangerous lists.
"""

import json
import sys
from pathlib import Path
from io import StringIO
import pytest

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "plugins/ace/shared-hooks"))

from ace_permission_request import main


class CaptureOutput:
    """Capture stdout/stderr for testing"""
    def __init__(self):
        self.stdout = None
        self.stderr = None
        self._old_stdout = None
        self._old_stderr = None

    def __enter__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        return self

    def __exit__(self, *args):
        self.stdout = sys.stdout.getvalue()
        self.stderr = sys.stderr.getvalue()
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr


def run_permission_hook(event_data):
    """Helper to run the permission hook with test data"""
    old_stdin = sys.stdin
    sys.stdin = StringIO(json.dumps(event_data))

    with CaptureOutput() as output:
        try:
            main()
        except SystemExit:
            pass

    sys.stdin = old_stdin

    if output.stdout.strip():
        return json.loads(output.stdout.strip())
    return {}


# ============================================================================
# Test: Safe Commands (Auto-Approve)
# ============================================================================

@pytest.mark.parametrize("cli_variant,command", [
    ("ace-cli", "ace-cli search 'authentication'"),
    ("ce-ace", "ce-ace search 'authentication'"),
    ("ace-cli", "ace-cli status"),
    ("ce-ace", "ce-ace status"),
    ("ace-cli", "ace-cli patterns"),
    ("ce-ace", "ce-ace patterns"),
    ("ace-cli", "ace-cli top"),
    ("ce-ace", "ce-ace top"),
    ("ace-cli", "ace-cli get-playbook"),
    ("ce-ace", "ce-ace get-playbook"),
    ("ace-cli", "ace-cli doctor"),
    ("ce-ace", "ce-ace doctor"),
    ("ace-cli", "ace-cli tune"),
    ("ce-ace", "ce-ace tune"),
])
def test_safe_commands_auto_approved(cli_variant, command):
    """CRITICAL: Safe read-only commands must be auto-approved"""
    event = {"tool_name": "Bash", "command": command}
    result = run_permission_hook(event)

    assert result.get("decision", {}).get("behavior") == "allow", \
        f"Safe command '{command}' should be auto-approved"

    message = result.get("decision", {}).get("message", "")
    assert "Auto-approved" in message or "approved" in message.lower()


# ============================================================================
# Test: Dangerous Commands (Auto-Deny)
# ============================================================================

@pytest.mark.parametrize("cli_variant,command", [
    ("ace-cli", "ace-cli clear"),
    ("ce-ace", "ce-ace clear"),
])
def test_dangerous_commands_auto_denied(cli_variant, command):
    """CRITICAL: Destructive commands must be auto-denied"""
    event = {"tool_name": "Bash", "command": command}
    result = run_permission_hook(event)

    assert result.get("decision", {}).get("behavior") == "deny", \
        f"Dangerous command '{command}' should be auto-denied"


# ============================================================================
# Test: Passthrough Commands
# ============================================================================

@pytest.mark.parametrize("command", [
    "ace-cli learn",
    "ce-ace learn",
    "ace-cli bootstrap",
    "ce-ace bootstrap",
])
def test_modifying_commands_pass_through(command):
    """Commands that modify data should pass through for user decision"""
    event = {"tool_name": "Bash", "command": command}
    result = run_permission_hook(event)

    assert result == {} or result.get("decision") is None


@pytest.mark.parametrize("command", [
    "ls -la",
    "git status",
    "npm install",
])
def test_non_ace_commands_pass_through(command):
    """Non-ACE commands should pass through"""
    event = {"tool_name": "Bash", "command": command}
    result = run_permission_hook(event)

    assert result == {}


@pytest.mark.parametrize("tool_name", ["Read", "Write", "Edit"])
def test_non_bash_tools_pass_through(tool_name):
    """Non-Bash tools should pass through"""
    event = {"tool_name": tool_name, "command": "ace-cli search 'test'"}
    result = run_permission_hook(event)

    assert result == {}


# ============================================================================
# Test: Edge Cases & Security
# ============================================================================

def test_command_injection_attempt():
    """Ensure command injection attempts don't bypass security"""
    event = {"tool_name": "Bash", "command": "ace-cli clear && echo 'hacked'"}
    result = run_permission_hook(event)

    assert result.get("decision", {}).get("behavior") == "deny"


def test_case_sensitivity():
    """Commands should be case-sensitive"""
    event = {"tool_name": "Bash", "command": "ACE-CLI SEARCH 'test'"}
    result = run_permission_hook(event)

    assert result == {}  # Uppercase doesn't match


def test_malformed_event_graceful():
    """Malformed events should fail gracefully"""
    event = {}  # Missing fields
    result = run_permission_hook(event)

    assert result == {}  # Fail-open for safety
