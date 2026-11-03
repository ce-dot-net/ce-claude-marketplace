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
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    p = pus.state_file_path("sess", None, project_id="prj")
    assert p == tmp_path / "ace-pd" / "projects" / "prj" / "sessions" / "sess" / "patterns-used-main.json"


def test_claude_project_dir_no_longer_used(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "proj"))
    p = pus.state_file_path("sess", None, project_id="prj")
    assert str(tmp_path / "proj") not in str(p)


def test_explicit_state_dir_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/somewhere/ace-else")
    p = pus.state_file_path("sess", None, state_dir=str(tmp_path))
    assert p == tmp_path / "patterns-used-main.json"


def test_writer_reader_consistent_across_cwd_change(monkeypatch, tmp_path):
    """Production resolution: no project_id kwarg; anchored to CLAUDE_PROJECT_DIR."""
    import json
    root = tmp_path / "root"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.json").write_text(json.dumps({"env": {"ACE_PROJECT_ID": "prj_x", "ACE_ORG_ID": "o"}}))
    sub = root / "sub"
    sub.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.delenv("ACE_PROJECT_ID", raising=False)
    monkeypatch.chdir(root)
    pus.append_patterns_used("s", None, ["ctx-1234567890-abcd"])
    assert (tmp_path / "ace-pd" / "projects" / "prj_x" / "sessions" / "s" / "patterns-used-main.json").exists()
    monkeypatch.chdir(sub)  # no settings here
    got = pus.load_playbook_used("s", None, "Stop")
    assert got == ["ctx-1234567890-abcd"]


def test_concurrent_appends_keep_retrieval_log_ids(monkeypatch, tmp_path):
    import threading
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    pus.append_patterns_used("s", None, [], retrieval_id="r1", retrieval_log_ids={"ctx-1234567890-aaaa": 1},
                             task_session_id="t1", project_id="p")
    ids = ["ctx-%010d-abcd" % i for i in range(20)]
    ts = [threading.Thread(target=pus.append_patterns_used, args=("s", None, [i]),
                           kwargs={"project_id": "p"}) for i in ids]
    [t.start() for t in ts]
    [t.join() for t in ts]
    _, rid, rlog, tsid = pus._read_state_file(pus.state_file_path("s", None, project_id="p"))
    assert rid == "r1" and rlog == {"ctx-1234567890-aaaa": 1} and tsid == "t1"
    assert len(pus.load_playbook_used("s", None, "Stop", project_id="p")) == 20
