"""§24 addendum: the mod's APPEND_SH (core.ts) never follows a planted symlink/dir while rotating the relevance log.

The mod test runner forbids node imports, so the real shell string is extracted from core.ts and run with sh.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "mod" / "core.ts"


def _append_sh():
    src = CORE.read_text()
    body = src[src.index("export const APPEND_SH ="):]
    body = body[:body.index("\n\n")]
    lines = [l for l in body.split("\n") if not l.strip().startswith("//")]
    return "".join(re.findall(r"'((?:[^'\\]|\\.)*)'", "\n".join(lines)))


def _rotate(tmp_path, plant):
    cwd, outside = tmp_path / "cwd", tmp_path / "outside"
    logs = cwd / ".claude" / "data" / "logs"
    logs.mkdir(parents=True)
    outside.mkdir()
    log = logs / "ace-relevance.jsonl"
    log.write_text("x")
    os.truncate(log, 52428801)
    plant(logs, outside)
    r = subprocess.run(["sh", "-c", _append_sh(), "sh", str(log), str(cwd)], input=b'{"row":1}\n',
                       capture_output=True)
    return r, logs, log, outside


def test_symlinked_dot1_drops_row_and_moves_nothing_out(tmp_path):
    r, logs, log, outside = _rotate(tmp_path, lambda l, o: (l / "ace-relevance.1.jsonl").symlink_to(o))
    assert r.returncode == 0
    assert list(outside.iterdir()) == []
    assert log.stat().st_size == 52428801, "log untouched, row dropped"


def test_directory_dot1_drops_row_and_moves_nothing_into_it(tmp_path):
    r, logs, log, outside = _rotate(tmp_path, lambda l, o: (l / "ace-relevance.1.jsonl").mkdir())
    assert list((logs / "ace-relevance.1.jsonl").iterdir()) == []
    assert log.stat().st_size == 52428801


def test_clean_chain_rotates_to_python_name_and_appends(tmp_path):
    r, logs, log, outside = _rotate(tmp_path, lambda l, o: None)
    assert (logs / "ace-relevance.1.jsonl").stat().st_size == 52428801
    assert log.read_text() == '{"row":1}\n'
