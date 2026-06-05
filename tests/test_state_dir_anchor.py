#!/usr/bin/env python3
"""
v6.6.6: the patterns-used state dir anchors to $CLAUDE_PROJECT_DIR (which CC
provides to hooks since 2.1.141) so the writer and reader resolve the SAME
absolute path even when their hook processes have different cwds. Falls back to
the relative '.claude/data/logs' when CLAUDE_PROJECT_DIR is unset; an explicit
state_dr= argument always wins.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

import patterns_used_state as pus  # noqa: E402


def test_anchors_to_claude_project_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    p = pus.state_file_path("sess", None)
    assert p == tmp_path / ".claude" / "data" / "logs" / "ace-patterns-used-sess-main.json"


def test_relative_fallback_when_unset(monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    p = pus.state_file_path("sess", None)
    assert str(p) == ".claude/data/logs/ace-patterns-used-sess-main.json"


def test_explicit_state_dir_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/somewhere/else")
    p = pus.state_file_path("sess", None, state_dir=str(tmp_path))
    assert p == tmp_path / "ace-patterns-used-sess-main.json"


def test_writer_reader_consistent_across_cwd_change(monkeypatch, tmp_path):
    # THE point of the anchor: write under CLAUDE_PROJECT_DIR, then read from a
    # DIFFERENT cwd -> still found (the relative scheme would have missed it).
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    pus.append_patterns_used("s", None, ["ctx-1234567890-abcd"])
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    got = pus.load_playbook_used("s", None, "Stop")
    assert got == ["ctx-1234567890-abcd"]
