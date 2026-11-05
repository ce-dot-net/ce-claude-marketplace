"""fix 5a: a Bash call with a non-zero exit code makes the trace success false (PostToolUse or transcript shape)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "plugins" / "ace" / "shared-hooks"))
from ace_after_task import tool_failed  # noqa: E402


def test_non_zero_exit_code_is_a_failure():
    assert tool_failed({"stdout": "", "stderr": "", "exit_code": 6}) is True
    assert tool_failed({"stdout": "", "stderr": "", "exitCode": 6}) is True
    assert tool_failed({"content": "Exit code 6\ncurl: (6) Could not resolve host"}) is True


def test_success_and_interpreted_exits_are_not():
    assert tool_failed({"stdout": "ok", "stderr": ""}) is False
    assert tool_failed({"stdout": "", "exitCode": 0}) is False
    assert tool_failed({"exitCode": 1, "returnCodeInterpretation": "No matches found"}) is False
    assert tool_failed({"content": "Exit code 0"}) is False
    assert tool_failed({}) is False


def test_error_fails_stderr_alone_does_not():
    """8.1.3: stderr alone is not a failure (git progress, npm/pip notices, node warnings write there on success)."""
    assert tool_failed({"error": "boom"}) is True
    assert tool_failed({"stderr": "warn"}) is False
    assert tool_failed({"stderr": "warn", "exit_code": 0}) is False
