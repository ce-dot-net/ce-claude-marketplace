"""WP-C review fixes: agent-scoped accumulator, field caps, skip_learning reap safety, run_learn routing."""
import json
import sys
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "shared-hooks"
for p in (SHARED, SHARED / "utils"):
    sys.path.insert(0, str(p))

import ace_tool_accumulator as acc  # noqa: E402


@pytest.fixture
def db(tmp_path):
    return tmp_path / "tools.db"


def _rec(db, aid, n, resp="ok"):
    assert acc.record_tool("s1", aid, "Bash", "{}", resp, True, None, tool_use_id=n, db_path=db)


def test_get_session_tools_scoped_by_agent(db):
    _rec(db, None, "m1")
    _rec(db, "sub-a", "a1")
    assert len(acc.get_session_tools("s1", db_path=db)) == 2  # legacy: all rows
    assert [t[3] for t in acc.get_session_tools("s1", db_path=db, agent_id=None)] == ["m1"]
    assert [t[3] for t in acc.get_session_tools("s1", db_path=db, agent_id="sub-a")] == ["a1"]


def test_clear_session_scoped_keeps_main_rows(db, monkeypatch):
    _rec(db, None, "m1")
    _rec(db, "sub-a", "a1")
    monkeypatch.setattr(acc, "get_db_path", lambda sid, wd=None: db)
    acc.clear_session("s1", agent_id="sub-a")
    assert [t[3] for t in acc.get_session_tools("s1", db_path=db)] == ["m1"]


def test_dump_caps_huge_payloads_and_stays_valid_json():
    big = {"content": "x" * 100000, "file_path": "/a/b.py"}
    out = acc._dump(big)
    assert len(out) <= acc.MAX_FIELD_CHARS
    assert json.loads(out)["file_path"] == "/a/b.py"  # shape kept
    many = acc._dump({"k%d" % i: "y" * 1500 for i in range(30)})
    assert len(many) <= acc.MAX_FIELD_CHARS and "_truncated" in json.loads(many)
    assert len(acc._dump("z" * 50000)) == acc.MAX_FIELD_CHARS


def test_skip_learning_degenerate_subagentstop_never_reaps_main(monkeypatch):
    import ace_after_task as at
    reaped = []
    monkeypatch.setattr(at, "reap_patterns_used", lambda *a: reaped.append(a))
    ev = {"session_id": "s1", "hook_event_name": "SubagentStop", "agent_id": ""}
    at.skip_learning("x", ev)
    assert reaped == []
    at.skip_learning("x", ev, "recovered-id")  # recovered id IS reaped
    assert reaped == [("s1", "recovered-id", "SubagentStop")]


def test_skip_learning_writes_eval_request_on_skipped_stop(monkeypatch):
    import ace_after_task as at
    monkeypatch.setattr(at, "load_state", lambda *a, **k: {"pattern_ids": ["ctx-1-a", "ctx-2-b"]})
    monkeypatch.setattr(at, "reap_patterns_used", lambda *a: None)
    calls = []
    monkeypatch.setattr(at, "write_eval_request", lambda n, t: calls.append((n, t)))
    at.skip_learning("x", {"session_id": "s1", "hook_event_name": "Stop"})
    assert calls == [(2, 0)]


def test_learn_goes_through_run_learn_not_a_private_spawn():
    src = (SHARED / "ace_after_task.py").read_text()
    assert "_learn_via_transcript" not in src
    assert "run_learn(" in src and "from utils.machine_prompts import" in src


def test_agent_transcript_size_guard(tmp_path, monkeypatch):
    import ace_after_task as at
    monkeypatch.setattr(at, "AGENT_TRANSCRIPT_MAX_BYTES", 400)
    lines = [json.dumps({"message": {"content": [
        {"type": "tool_use", "id": "t%d" % i, "name": "Bash", "input": {"command": "echo %d" % i}}]}})
        for i in range(20)]
    f = tmp_path / "agent-x.jsonl"
    f.write_text("\n".join(lines) + "\n")
    ids = [t[3] for t in at.parse_agent_transcript(str(f))]
    assert ids and ids[-1] == "t19" and "t0" not in ids
