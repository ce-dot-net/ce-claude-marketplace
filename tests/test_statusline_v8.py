"""WP-E (v8.0.0) — ace_statusline.sh: one Python call instead of 13 jq spawns, same output.

DESIGN §6 WP-E; docs-settings-statusline-context §1.2: 13 `jq -r` + 1 python3 per refresh
(0.85–2.7 s) vs CC's 300 ms debounce that cancels in-flight scripts.

The script runs with PATH prefixed by counting wrappers for `jq` and `python3` (each logs
one line, then execs the real binary) and HOME pointed at a tmp dir (no cached python_path).
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "scripts" / "ace_statusline.sh"

CC_INPUT = {
    "model": {"display_name": "Opus"},
    "context_window": {"used_percentage": 42},
    "session_id": "s1",
    "effort": {"level": "high"},
    "rate_limits": {
        "five_hour": {"used_percentage": 30, "resets_at": ""},
        "seven_day": {"used_percentage": 10, "resets_at": ""},
    },
}


def _wrapper(bindir, name, real, log):
    p = bindir / name
    body = '#!/bin/sh\necho %s >> "%s"\n' % (name, log)
    body += ('exec "%s" "$@"\n' % real) if real else "exit 127\n"
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def run(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "spawns.log"
    _wrapper(bindir, "jq", shutil.which("jq"), log)
    _wrapper(bindir, "python3", sys.executable, log)
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "proj"
    logs = proj / ".claude" / "data" / "logs"
    logs.mkdir(parents=True)
    (logs / "ace-relevance.jsonl").write_text(
        json.dumps({"event": "search", "session_id": "s1", "patterns_injected": 7, "avg_confidence": 0.8,
                    "domains": ["a", "b"]}) + "\n"
        + json.dumps({"event": "domain_shift", "session_id": "s1"}) + "\n"
    )
    (logs / "ace-review-result.json").write_text(json.dumps({"quality_pct": 75, "time_saved": "5m"}))

    def _run():
        payload = dict(CC_INPUT, cwd=str(proj))
        env = dict(os.environ, HOME=str(home), PATH=str(bindir) + os.pathsep + os.environ["PATH"])
        env.pop("CLAUDE_PLUGIN_DATA", None)
        proc = subprocess.run(["bash", str(SCRIPT)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=20, env=env)
        spawns = log.read_text().split() if log.exists() else []
        plain = re.sub(r"\033\[[0-9;]*m", "", proc.stdout)
        return proc, spawns, plain
    return _run


def test_statusline_spawns_no_jq(run):
    """DESIGN §6 WP-E: statusline must not spawn jq (13 spawns today)."""
    _, spawns, _ = run()
    assert spawns.count("jq") == 0, "statusline spawned jq %d times" % spawns.count("jq")


def test_statusline_spawns_at_most_one_python(run):
    """DESIGN §6 WP-E: one Python call per refresh (stdin JSON + relevance log + review file)."""
    _, spawns, _ = run()
    assert spawns.count("python3") <= 1, spawns


def test_statusline_output_format_preserved(run):
    """DESIGN §6 WP-E: 'same output format' — 3 lines: model/bar/%, ◆ ACE metrics, limits."""
    proc, _, plain = run()
    assert proc.returncode == 0, proc.stderr
    lines = [l for l in plain.splitlines() if l.strip()]
    assert len(lines) == 3, lines
    assert lines[0].startswith("Opus · ") and "42%" in lines[0] and "[high]" in lines[0]
    assert lines[0].count("█") + lines[0].count("░") == 15
    assert lines[1].startswith("◆ ACE")
    for frag in ("7 injected", "80%", "2 domains", "1 shifts", "75% quality", "~5m"):
        assert frag in lines[1], (frag, lines[1])
    assert lines[2].startswith("limits 5h:30%") and "7d:10%" in lines[2]


def _run_with_log(tmp_path, rows, session_id):
    proj = tmp_path / "proj2"
    logs = proj / ".claude" / "data" / "logs"
    logs.mkdir(parents=True)
    (logs / "ace-relevance.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    payload = {"cwd": str(proj)}
    if session_id:
        payload["session_id"] = session_id
    env = dict(os.environ, HOME=str(tmp_path))
    proc = subprocess.run(["bash", str(SCRIPT)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=20, env=env)
    return re.sub(r"\033\[[0-9;]*m", "", proc.stdout).splitlines()[1]


TWO_SESSIONS = [
    {"event": "search", "session_id": "A", "patterns_injected": 7, "domains": ["a"]},
    {"event": "search", "session_id": "B", "patterns_injected": 3, "domains": ["b", "c"]},
    {"event": "execution", "session_id": "B"},
    {"event": "domain_shift", "session_id": "B"},
    {"event": "search", "session_id": "B", "patterns_injected": 2, "domains": ["d"]},
]


def test_statusline_counts_only_current_session(tmp_path):
    """Another session's execution row must not reset, and its rows must not add to, this session's counts."""
    line = _run_with_log(tmp_path, TWO_SESSIONS, "A")
    assert "7 injected" in line and "1 domains" in line and "shifts" not in line, line


def test_statusline_session_task_boundary(tmp_path):
    """Within the session, counting still starts after that session's own last execution row."""
    line = _run_with_log(tmp_path, TWO_SESSIONS, "B")
    assert "2 injected" in line and "1 domains" in line and "1 shifts" in line, line


def test_statusline_no_session_id_keeps_old_behaviour(tmp_path):
    """No session_id on stdin -> all sessions, since the last execution row of any session."""
    line = _run_with_log(tmp_path, TWO_SESSIONS, None)
    assert "2 injected" in line and "1 shifts" in line, line
    line = _run_with_log(tmp_path / "x", TWO_SESSIONS[:2], None)
    assert "10 injected" in line and "3 domains" in line, line
