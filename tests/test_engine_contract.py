#!/usr/bin/env python3
"""R3c RED — DESIGN §14 engine contract: search.js / learn.js stdin-stdout + wire behavior.

search.js: stdin JSON {query, project, org, session_id?, top_k?} -> stdout EXACTLY the
  `ace-cli search --json` object (the core searchPatterns result), exit 0. Uses the core's
  createContext + AceClient (getConfig -> threshold/top_k/section like the CLI ->
  searchPatterns with session_id for the server-side stamp, include_metadata, expandNeighbors).
  Never opens sessions.db. X-ACE-Client: claude-code-plugin/<plugin.json version>.
  Gate failure -> exit 3 (no stdout JSON); runtime/server failure -> exit 1, error on stderr.
learn.js: `node learn.js --transcript F --json [--retrieval-id R] [--applied-log-ids a,b]
  [--verbosity V] [--timeout MS] [--no-stream]` performs the same requests as
  `ace-cli learn --no-stream` (GET /api/v1/config, POST /traces; storeExecutionTrace, never the
  stream), prints the CLI's --json success object, exits non-zero on 401/500 with the error on stderr.

Fake-core tests run anywhere with node; real-core tests use the installed @ace-sdk/core against a
localhost fake server (tests/engine_fake_server.py) with a fake config + localhost fetch guard.
"""
import json
import os
import subprocess

import pytest

import engine_harness as E

pytestmark = pytest.mark.skipif(E.node_bin() is None, reason="node not installed")
needs_real = pytest.mark.skipif(E.real_core_dir() is None, reason="real ace-cli/@ace-sdk/core not installed")


def _search_js(bin_dir, payload, **env):
    e = dict(os.environ, PATH=E.path_with(bin_dir))
    e.pop("ACE_CLIENT_ID", None)
    e.update(env)
    return subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input=json.dumps(payload),
                          capture_output=True, text=True, env=e, timeout=30)


# ---------------------------------------------------------------- fake core (contract)

@pytest.fixture
def fake_core(tmp_path):
    bin_dir = E.make_prefix(tmp_path)
    return bin_dir, tmp_path / "core.log"


def test_search_stdout_is_exactly_the_core_result(fake_core):
    bin_dir, log = fake_core
    r = _search_js(bin_dir, {"query": "fix hook json", "org": "org_a", "project": "prj_b"},
                   ACE_FAKE_CORE_LOG=str(log))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == E.CORE_RESPONSE


def test_search_passes_query_session_topk_and_context(fake_core):
    bin_dir, log = fake_core
    r = _search_js(bin_dir, {"query": "fix hook json", "org": "org_a", "project": "prj_b",
                             "session_id": "tsid-42", "top_k": 8}, ACE_FAKE_CORE_LOG=str(log))
    assert r.returncode == 0, r.stderr
    rows = E.read_jsonl(log)
    ctx = [x for x in rows if x["op"] == "context"]
    assert ctx and ctx[0]["org"] == "org_a" and ctx[0]["project"] == "prj_b"
    s = [x for x in rows if x["op"] == "search"][0]["params"]
    assert s["query"] == "fix hook json"
    assert s["session_id"] == "tsid-42"
    assert s["top_k"] == 8
    assert s["threshold"] == 0.5  # server config search_threshold, like ace-cli
    assert s.get("include_metadata") is True


def test_search_without_topk_uses_server_search_top_k(fake_core):
    bin_dir, log = fake_core
    r = _search_js(bin_dir, {"query": "q", "org": "o", "project": "p"}, ACE_FAKE_CORE_LOG=str(log))
    assert r.returncode == 0, r.stderr
    s = [x for x in E.read_jsonl(log) if x["op"] == "search"][0]["params"]
    assert s["top_k"] == 100
    assert not s.get("session_id")


def test_search_sets_x_ace_client_plugin_version(fake_core):
    """§14: X-ACE-Client = claude-code-plugin/<version> (ace-cli hard-codes `cli`, m3 V1)."""
    bin_dir, log = fake_core
    r = _search_js(bin_dir, {"query": "q", "org": "o", "project": "p"}, ACE_FAKE_CORE_LOG=str(log))
    assert r.returncode == 0, r.stderr
    ctor = [x for x in E.read_jsonl(log) if x["op"] == "ctor"][0]
    assert ctor["customHeaders"]["X-ACE-Client"] == "claude-code-plugin/" + E.plugin_version()


def test_search_runtime_failure_exits_1_with_stderr(fake_core):
    bin_dir, log = fake_core
    r = _search_js(bin_dir, {"query": "q", "org": "o", "project": "p"}, ACE_FAKE_CORE_LOG=str(log),
                   ACE_FAKE_CORE_MODE="throw")
    assert r.returncode == 1
    assert "500" in r.stderr
    assert not r.stdout.strip()


def test_search_gate_failure_exits_3(tmp_path):
    bin_dir = E.make_prefix(tmp_path, version="3.1.0")
    r = _search_js(bin_dir, {"query": "q", "org": "o", "project": "p"})
    assert r.returncode == 3
    assert not r.stdout.strip()


def test_search_rejects_bad_stdin(fake_core):
    bin_dir, _ = fake_core
    assert (E.ENGINE / "search.js").is_file()
    e = dict(os.environ, PATH=E.path_with(bin_dir))
    r = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input="not json",
                       capture_output=True, text=True, env=e, timeout=30)
    assert r.returncode != 0 and not r.stdout.strip()


def _learn_js(bin_dir, args, **env):
    e = dict(os.environ, PATH=E.path_with(bin_dir), ACE_ORG_ID="o", ACE_PROJECT_ID="p")
    e.update(env)
    return subprocess.run([E.node_bin(), str(E.ENGINE / "learn.js")] + args, capture_output=True,
                          text=True, env=e, timeout=30)


def _trace(tmp_path):
    p = tmp_path / "trace.json"
    p.write_text(json.dumps({"task": "fix the hook", "trajectory": [], "result": {"success": True},
                             "playbook_used": [], "timestamp": "2026-11-02T00:00:00Z"}))
    return p


def test_learn_uses_sync_post_and_f080_fields(fake_core, tmp_path):
    bin_dir, log = fake_core
    r = _learn_js(bin_dir, ["--transcript", str(_trace(tmp_path)), "--json", "--verbosity", "detailed",
                            "--retrieval-id", "ret-9", "--applied-log-ids", "101,102"],
                  ACE_FAKE_CORE_LOG=str(log))
    assert r.returncode == 0, r.stderr
    rows = E.read_jsonl(log)
    assert not [x for x in rows if x["op"] == "learn_stream"], "learn must be --no-stream (sync POST)"
    t = [x for x in rows if x["op"] == "learn"][0]["trace"]
    assert t["task"] == "fix the hook"
    assert t["retrieval_id"] == "ret-9"
    assert t["applied_log_ids"] == [101, 102]
    out = json.loads(r.stdout)
    assert out["success"] is True and out["task"] == "fix the hook"
    assert out["message"] == "Execution trace stored successfully"


def test_learn_server_error_exits_nonzero(fake_core, tmp_path):
    bin_dir, log = fake_core
    r = _learn_js(bin_dir, ["--transcript", str(_trace(tmp_path)), "--json"], ACE_FAKE_CORE_LOG=str(log),
                  ACE_FAKE_CORE_MODE="throw")
    assert r.returncode not in (0, 3)
    assert "500" in r.stderr
    assert '"success": true' not in r.stdout and '"success":true' not in r.stdout


def test_learn_gate_failure_exits_3_before_any_request(tmp_path):
    bin_dir = E.make_prefix(tmp_path, no_export=True)
    log = tmp_path / "core.log"
    r = _learn_js(bin_dir, ["--transcript", str(_trace(tmp_path)), "--json"], ACE_FAKE_CORE_LOG=str(log))
    assert r.returncode == 3
    assert not [x for x in E.read_jsonl(log) if x["op"] == "learn"]


# ---------------------------------------------------------------- real core vs localhost fake server

@pytest.fixture
def real(tmp_path):
    srv = E.FakeServer(tmp_path)
    (tmp_path / "pfx").mkdir()
    bin_dir = E.make_prefix(tmp_path / "pfx", core="real")
    yield bin_dir, srv, E.sdk_env(tmp_path, srv)
    srv.stop()


@needs_real
def test_real_core_search_headers_and_session_stamp(real, tmp_path):
    bin_dir, srv, env = real
    env["PATH"] = E.path_with(bin_dir)
    r = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")],
                       input=json.dumps({"query": "hook json", "org": "org_fake", "project": "prj_fake",
                                         "session_id": "tsid-real", "top_k": 5}),
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["retrieval_id"] == "ret-fake-1"
    reqs = srv.requests()
    post = [q for q in reqs if q["path"].startswith("/patterns/search")]
    assert len(post) == 1
    assert post[0]["body"]["session_id"] == "tsid-real"
    assert post[0]["body"]["top_k"] == 5
    for q in reqs:
        if q["path"].startswith(("/patterns/search", "/api/v1/config")):
            assert q["headers"].get("X-ACE-Client") == "claude-code-plugin/" + E.plugin_version(), q
            assert q["headers"].get("User-Agent", "").startswith("ace-sdk/"), q
    assert not (tmp_path / "home" / ".ace-cache" / "sessions.db").exists(), "engine must never open sessions.db"


@needs_real
def test_real_core_search_parity_with_ace_cli_on_fake_server(real, tmp_path):
    """Same server answer -> engine JSON == `ace-cli search --json` JSON (hermetic parity)."""
    bin_dir, srv, env = real
    cli = subprocess.run([E.real_cli_path(), "search", "--stdin", "--json"], input="hook json",
                         capture_output=True, text=True, env=env, timeout=60)
    assert cli.returncode == 0, cli.stderr
    env["PATH"] = E.path_with(bin_dir)
    lib = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")],
                         input=json.dumps({"query": "hook json", "org": "org_fake", "project": "prj_fake"}),
                         capture_output=True, text=True, env=env, timeout=60)
    assert lib.returncode == 0, lib.stderr
    assert json.loads(lib.stdout) == json.loads(cli.stdout)
    bodies = [q["body"] for q in srv.requests() if q["path"].startswith("/patterns/search")]
    for body in bodies:  # searchPatterns generates these two per call (temp_search_<Date.now()>)
        del body["pattern"]["id"], body["pattern"]["created_at"]
    assert len(bodies) == 2 and bodies[0] == bodies[1], "same search request body as the CLI"


def _learn_pair(real, tmp_path, mode_env=None):
    bin_dir, srv, env = real
    tr = _trace(tmp_path)
    flags = ["--transcript", str(tr), "--json", "--retrieval-id", "ret-77", "--applied-log-ids", "5,6"]
    cli = subprocess.run([E.real_cli_path(), "learn"] + flags + ["--no-stream"], capture_output=True,
                         text=True, env=env, timeout=60)
    n_cli = len(srv.requests())
    env = dict(env, PATH=E.path_with(bin_dir))
    lib = subprocess.run([E.node_bin(), str(E.ENGINE / "learn.js")] + flags, capture_output=True,
                         text=True, env=env, timeout=60)
    reqs = srv.requests()
    return cli, lib, reqs[:n_cli], reqs[n_cli:]


@needs_real
def test_real_core_learn_equals_ace_cli_no_stream(real, tmp_path):
    cli, lib, rc, rl = _learn_pair(real, tmp_path)
    assert cli.returncode == 0, cli.stderr
    assert lib.returncode == 0, lib.stderr
    # only the trace POSTs are compared: the CLI's cached GET /api/v1/config makes the full list order-dependent
    rl, rc = [q for q in rl if q["path"] == "/traces"], [q for q in rc if q["path"] == "/traces"]
    assert [(q["method"], q["path"]) for q in rl] == [(q["method"], q["path"]) for q in rc]
    assert ("POST", "/traces") in [(q["method"], q["path"]) for q in rl]
    bc = [q["body"] for q in rc if q["path"] == "/traces"][0]
    bl = [q["body"] for q in rl if q["path"] == "/traces"][0]
    assert bl == bc, "trace body byte-equal to ace-cli learn --no-stream"
    assert bl["retrieval_id"] == "ret-77" and bl["applied_log_ids"] == [5, 6]
    assert json.loads(lib.stdout) == json.loads(cli.stdout)
    hdr = [q for q in rl if q["path"] == "/traces"][0]["headers"]
    assert hdr.get("X-ACE-Client") == "claude-code-plugin/" + E.plugin_version()


@needs_real
@pytest.mark.parametrize("mode", ["401", "500"])
def test_real_core_learn_nonzero_on_server_error(tmp_path, mode):
    srv = E.FakeServer(tmp_path, mode=mode)
    try:
        (tmp_path / "pfx").mkdir()
        bin_dir = E.make_prefix(tmp_path / "pfx", core="real")
        env = E.sdk_env(tmp_path, srv, PATH=E.path_with(bin_dir))
        r = subprocess.run([E.node_bin(), str(E.ENGINE / "learn.js"), "--transcript", str(_trace(tmp_path)),
                            "--json"], capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode != 0
        assert "Cannot find module" not in r.stderr, r.stderr[:300]
        assert any(x in r.stderr for x in ("401", "expired", "500")), r.stderr[:300]
        assert '"success"' not in r.stdout
        assert [q for q in srv.requests() if q["path"] == "/traces"], "the trace POST was attempted"
    finally:
        srv.stop()


@needs_real
def test_stalled_graph_refresh_does_not_hold_the_search_result(tmp_path, monkeypatch):
    """The result is on stdout before the core's background edge refresh; a stalled refresh must not
    outlive the hook budget (subprocess.run would time out and discard the printed patterns)."""
    monkeypatch.setenv("FAKE_GRAPH_DELAY", "40")
    srv = E.FakeServer(tmp_path)
    try:
        (tmp_path / "pfx").mkdir()
        env = E.sdk_env(tmp_path, srv, PATH=E.path_with(E.make_prefix(tmp_path / "pfx", core="real")))
        r = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")],
                           input=json.dumps({"query": "hook json", "org": "org_fake", "project": "prj_fake"}),
                           capture_output=True, text=True, env=env, timeout=25)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["retrieval_id"] == "ret-fake-1"
        assert any("graph" in q["path"] for q in srv.requests()), "the refresh must really have started"
    finally:
        srv.stop()
