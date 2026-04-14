#!/usr/bin/env python3
"""
ace_stop_wrapper.sh must early-exit with a 'skipped continuation stop'
systemMessage when the hook event has stop_hook_active=true.
"""
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "plugins" / "ace" / "scripts" / "ace_stop_wrapper.sh"


def test_stop_hook_active_early_exit(tmp_path):
    event = {
        "session_id": "sess-continuation",
        "stop_hook_active": True,
        "transcript_path": str(tmp_path / "transcript.jsonl"),
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert out, f"expected JSON on stdout, got nothing (stderr={proc.stderr!r})"
    parsed = json.loads(out)
    assert parsed.get("continue") is True
    msg = parsed.get("systemMessage", "")
    assert "continuation" in msg.lower() or "skipped" in msg.lower(), msg


def test_stop_hook_active_false_does_not_early_exit(tmp_path, monkeypatch):
    """
    When stop_hook_active is false/missing, the wrapper should NOT print
    the 'continuation stop' skip message. It may short-circuit for other
    reasons (e.g. missing global config), but not with the continuation
    message.
    """
    event = {
        "session_id": "sess-normal",
        "stop_hook_active": False,
        "transcript_path": str(tmp_path / "t.jsonl"),
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert "Skipped continuation stop" not in (proc.stdout or "")
