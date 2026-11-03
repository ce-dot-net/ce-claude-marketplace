#!/usr/bin/env python3
"""v8.0.1: learn retries (@ace-sdk/cli 4.3.4 / core 3.7.0) become `learn_retry` relevance rows.

The SDK retries POST /traces up to 4 attempts (same Idempotency-Key) and writes one stderr line per retry:
`[ace] trace retry attempt=N/4 reason=<status|error> idempotency_key=<uuid> at=<ISO-UTC>` (ace-cli --json wraps
it in {"level":"warn","message":...}; the engine passes a logger whose warn() writes the bare line).
Python chain: ace_cli.run_learn parses the captured stderr of every spawn and appends one row per retry.
The real tests run the PINNED deps (plugins/ace/node_modules) against tests/engine_fake_server.py, whose
FAKE_TRACE_502=n answers the first n trace POSTs 502 with Retry-After: 0 (the SDK then retries at once).
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine_harness as E

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
UTILS = PLUGIN / "shared-hooks" / "utils"
sys.path.insert(0, str(UTILS))
CLI_JS = PLUGIN / "node_modules" / "@ace-sdk" / "cli" / "dist" / "cli.js"
NODE = shutil.which("node")
KEY = "0b7e6c1a-2f3d-4e5f-8a9b-0c1d2e3f4a5b"
TRACE = {"task": "t", "session_id": "tsid-1", "conversation_id": "cc-1"}


def _line(n, reason="502", key=KEY):
    return "[ace] trace retry attempt=%d/4 reason=%s idempotency_key=%s at=2026-11-03T10:00:0%dZ" % (n, reason, key, n)


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.setenv("ACE_ENGINE", "cli")
    import ace_cli
    mod = importlib.reload(ace_cli)
    import ace_relevance_logger
    ace_relevance_logger._logger = None
    return mod


def _rows(cwd, event="learn_retry"):
    p = Path(cwd) / ".claude" / "data" / "logs" / "ace-relevance.jsonl"
    return [r for r in E.read_jsonl(p) if r.get("event") == event]


def test_parse_retry_lines_plain_and_cli_json_wrapped(cli):
    text = "\n".join([_line(2), json.dumps({"level": "warn", "message": _line(3, "fetch failed")}), "noise"])
    got = cli.learn_retries(text, "cli")
    assert got == [
        {"attempt": 2, "max_attempts": 4, "reason": "502", "idempotency_key": KEY, "at": "2026-11-03T10:00:02Z", "engine": "cli"},
        {"attempt": 3, "max_attempts": 4, "reason": "fetch failed", "idempotency_key": KEY, "at": "2026-11-03T10:00:03Z", "engine": "cli"},
    ]
    assert cli.learn_retries(None, "lib") == [] and cli.learn_retries(MagicMock(), "lib") == []


def test_run_learn_writes_one_row_per_retry_and_counts_a_late_success_as_sent(cli, tmp_path):
    err = _line(2) + "\n" + _line(3) + "\n"
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout='{"success": true}', stderr=err)):
        res, _ = cli.run_learn(dict(TRACE), hook_event_name="SubagentStop")
    assert res == {"success": True}, "a learn that succeeded after retries is still sent"
    rows = _rows(tmp_path)
    assert [r["attempt"] for r in rows] == [2, 3]
    for r in rows:
        assert r["hook"] == "SubagentStop"
        assert r["session_id"] == "cc-1" and r["conversation_id"] == "cc-1" and r["task_session_id"] == "tsid-1"
        assert r["max_attempts"] == 4 and r["reason"] == "502" and r["idempotency_key"] == KEY
        assert r["engine"] == "cli" and r["learning_sent"] is True and r["at"].startswith("2026-11-03T10:00:0")


def test_run_learn_dead_letter_rows_say_not_sent(cli, tmp_path):
    err = "\n".join(_line(n) for n in (2, 3, 4)) + '\n{"event":"ace_trace_dead_letter","attempts":4,"status":502}\n'
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr=err)):
        res, _ = cli.run_learn(dict(TRACE), hook_event_name="Stop")
    assert res is None
    rows = _rows(tmp_path)
    assert [r["attempt"] for r in rows] == [2, 3, 4] and all(r["learning_sent"] is False for r in rows)


def test_run_learn_without_retries_writes_no_retry_row(cli, tmp_path):
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="{}", stderr="")):
        cli.run_learn(dict(TRACE), hook_event_name="Stop")
    assert _rows(tmp_path) == []


def test_run_learn_retry_rows_refuse_a_symlinked_log_dir(cli, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".claude" / "data").mkdir(parents=True)
    (tmp_path / ".claude" / "data" / "logs").symlink_to(outside)
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="{}", stderr=_line(2))):
        cli.run_learn(dict(TRACE), hook_event_name="Stop")
    assert list(outside.iterdir()) == []


# ---------------------------------------------------------------- pinned deps vs the fake server

pinned = pytest.mark.skipif(not (CLI_JS.is_file() and NODE), reason="pinned deps not installed: npm ci in plugins/ace")


def _trace_file(tmp_path):
    p = tmp_path / "trace.json"
    p.write_text(json.dumps({"task": "fix the hook", "trajectory": [], "result": {"success": True},
                             "playbook_used": [], "timestamp": "2026-11-03T00:00:00Z"}))
    return p


@pytest.fixture
def server(tmp_path, request):
    srv = E.FakeServer(tmp_path, FAKE_TRACE_502=str(request.param))
    yield srv, E.sdk_env(tmp_path, srv)
    srv.stop()


def _learn(head, tmp_path, env):
    return subprocess.run(head + ["--transcript", str(_trace_file(tmp_path)), "--json", "--no-stream"],
                          capture_output=True, text=True, env=env, timeout=120)


HEADS = {"lib": lambda: [NODE, str(PLUGIN / "engine" / "learn.js")], "cli": lambda: [NODE, str(CLI_JS), "learn"]}


def _check_wire(srv, r, n_posts):
    import ace_cli
    lines = ace_cli.learn_retries(r.stderr, "x")
    posts = [q for q in srv.requests() if q["path"] == "/traces"]
    assert len(posts) == n_posts, r.stderr[-800:]
    keys = {q["headers"].get("Idempotency-Key") for q in posts}
    assert len(keys) == 1 and None not in keys, "same Idempotency-Key on every attempt"
    assert [x["attempt"] for x in lines] == list(range(2, n_posts + 1)), r.stderr[-800:]
    assert {x["idempotency_key"] for x in lines} == keys and {x["reason"] for x in lines} == {"502"}
    assert all(x["max_attempts"] == 4 for x in lines)


@pinned
@pytest.mark.parametrize("server", [2], indirect=True)
@pytest.mark.parametrize("engine", ["lib", "cli"])
def test_pinned_learn_retries_twice_then_succeeds(server, tmp_path, engine):
    srv, env = server
    r = _learn(HEADS[engine](), tmp_path, env)
    assert r.returncode == 0, r.stderr[-800:]
    assert json.loads(r.stdout)["success"] is True, "stdout stays the parsed result object"
    _check_wire(srv, r, 3)


@pinned
@pytest.mark.parametrize("server", [4], indirect=True)
@pytest.mark.parametrize("engine", ["lib", "cli"])
def test_pinned_learn_dead_letters_after_four_502(server, tmp_path, engine):
    srv, env = server
    r = _learn(HEADS[engine](), tmp_path, env)
    assert r.returncode != 0
    assert "ace_trace_dead_letter" in r.stderr
    _check_wire(srv, r, 4)


@pinned
@pytest.mark.parametrize("server", [2], indirect=True)
@pytest.mark.parametrize("engine", ["lib", "cli"])
def test_python_chain_run_learn_rows_from_the_real_pinned_learn(server, tmp_path, monkeypatch, engine):
    srv, env = server
    for k in [k for k in os.environ if k.startswith("ACE_")]:
        monkeypatch.delenv(k)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))  # the repo plugin: its pinned node_modules
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    if engine == "cli":
        monkeypatch.setenv("ACE_ENGINE", "cli")
    monkeypatch.chdir(tmp_path)
    import ace_engine
    import ace_relevance_logger
    importlib.reload(ace_engine)
    ace_cli = importlib.reload(importlib.import_module("ace_cli"))
    ace_relevance_logger._logger = None
    res, _ = ace_cli.run_learn(dict(TRACE, trajectory=[], result={"success": True}, playbook_used=[]),
                               org="org_fake", project="prj_fake", hook_event_name="Stop")
    assert res is not None and res.get("success") is True
    rows = _rows(tmp_path)
    keys = {q["headers"].get("Idempotency-Key") for q in srv.requests() if q["path"] == "/traces"}
    assert [r["attempt"] for r in rows] == [2, 3]
    assert all(r["engine"] == engine and r["learning_sent"] is True and r["idempotency_key"] in keys for r in rows)
    assert all(r["task_session_id"] == "tsid-1" and r["session_id"] == "cc-1" for r in rows)
