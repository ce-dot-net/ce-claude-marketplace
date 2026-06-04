#!/usr/bin/env python3
"""
Regression: the learn step must send the ExecutionTrace via `ace-cli learn
--transcript <file>`, NOT `--stdin`.

ace-cli `learn --stdin` cannot read payloads larger than the ~64KB OS pipe
buffer — it errors {"message":"Failed to read from stdin"} and the producer gets
a BrokenPipe, so ANY trace over ~64KB silently fails to learn (empirically
confirmed: 64KB succeeds, 80KB fails; a --transcript file of 3.25MB succeeds).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

import ace_after_task as at  # noqa: E402


def test_learn_uses_transcript_file_not_stdin(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        ti = argv.index("--transcript")
        tpath = Path(argv[ti + 1])
        captured["existed_during_call"] = tpath.exists()
        captured["trace"] = json.loads(tpath.read_text())
        captured["path"] = tpath

        class _R:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return _R()

    monkeypatch.setattr(at.subprocess, "run", fake_run)

    # a trace far larger than the 64KB stdin cliff must still go through
    big = "X" * 4000
    trace = {
        "task": "t",
        "trajectory": [{"step": i, "tool": "Bash", "result": big} for i in range(100)],
        "result": {"success": True},
        "playbook_used": ["ctx-1234567890-abcd"],
    }
    assert len(json.dumps(trace)) > 64 * 1024  # > the 64KB stdin limit

    result = at._learn_via_transcript(trace, env={}, verbosity="detailed")

    assert result.returncode == 0
    assert "--transcript" in captured["argv"], captured["argv"]
    assert "--stdin" not in captured["argv"], "must not use the 64KB-limited --stdin"
    assert "input" not in captured["kwargs"], "must not pipe the trace via stdin"
    assert captured["existed_during_call"] is True, "temp file must exist during the call"
    assert captured["trace"] == trace, "temp file must contain the exact trace"
    assert not captured["path"].exists(), "temp file must be cleaned up after the call"
