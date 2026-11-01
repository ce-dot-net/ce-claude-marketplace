#!/usr/bin/env python3
"""
v8 (DESIGN §4, supersedes the v6.6.6 $CLAUDE_PROJECT_DIR anchor): the
patterns-used state lives under $CLAUDE_PLUGIN_DATA/projects/<project>/
sessions/<session>/, an absolute path independent of any hook's cwd, so the
writer and the reader agree even across cwd changes. An explicit state_dir=
argument always wins.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"
sys.path.insert(0, str(SHARED / "utils"))
sys.path.insert(0, str(REPO / "plugins" / "ace" / "utils"))

import patterns_used_state as pus  # noqa: E402


def test_anchors_to_claude_plugin_data(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    p = pus.state_file_path("sess", None, project_id="prj")
    assert p == tmp_path / "projects" / "prj" / "sessions" / "sess" / "patterns-used-main.json"


def test_claude_project_dir_no_longer_used(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "pd"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "proj"))
    p = pus.state_file_path("sess", None, project_id="prj")
    assert str(tmp_path / "proj") not in str(p)


def test_explicit_state_dir_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/somewhere/else")
    p = pus.state_file_path("sess", None, state_dir=str(tmp_path))
    assert p == tmp_path / "patterns-used-main.json"


def test_writer_reader_consistent_across_cwd_change(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "pd"))
    monkeypatch.delenv("ACE_PROJECT_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    pus.append_patterns_used("s", None, ["ctx-1234567890-abcd"], project_id="prj")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    got = pus.load_playbook_used("s", None, "Stop", project_id="prj")
    assert got == ["ctx-1234567890-abcd"]
