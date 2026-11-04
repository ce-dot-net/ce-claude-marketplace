"""§24 addendum: the mod's APPEND_SH (lib/sh.ts) never follows a planted symlink/dir while rotating the relevance log.

The mod test runner forbids node imports, so the real shell string is extracted from lib/sh.ts and run with sh.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "mod" / "lib" / "sh.ts"


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


def test_new_log_is_0600(tmp_path):
    """final review: the relevance rows carry prompts; the mod creates the log 0600 like open_project_log."""
    cwd = tmp_path / "cwd"
    log = cwd / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    r = subprocess.run(["sh", "-c", _append_sh(), "sh", str(log), str(cwd)], input=b'{"row":1}\n', capture_output=True)
    assert r.returncode == 0 and log.read_text() == '{"row":1}\n'
    assert oct(log.stat().st_mode & 0o777) == oct(0o600)


@pytest.mark.parametrize("kind", ["symlink", "dir"])
def test_python_rotation_refuses_a_planted_chain_entry_like_the_mod(tmp_path, monkeypatch, kind):
    """§31 §24 addendum: the Python size-rotation applies the same check as APPEND_SH (row dropped, nothing moved)."""
    import sys
    sys.path.insert(0, str(CORE.parent.parent / "shared-hooks" / "utils"))
    import ace_relevance_logger as rl
    cwd, outside = tmp_path / "cwd", tmp_path / "outside"
    logs = cwd / ".claude" / "data" / "logs"
    logs.mkdir(parents=True)
    outside.mkdir()
    monkeypatch.chdir(cwd)
    log = logs / "ace-relevance.jsonl"
    log.write_text("x")
    os.truncate(log, rl.ACERelevanceLogger.MAX_FILE_SIZE + 1)
    planted = logs / "ace-relevance.2.jsonl"
    planted.symlink_to(outside) if kind == "symlink" else planted.mkdir()
    rl.ACERelevanceLogger(log_dir=".claude/data/logs")._write_log({"row": 1})
    assert log.stat().st_size == rl.ACERelevanceLogger.MAX_FILE_SIZE + 1
    assert not (logs / "ace-relevance.1.jsonl").exists() and list(outside.iterdir()) == []
