#!/usr/bin/env python3
"""DESIGN §23 (a): the plugin <-> pinned ace-cli contract.

Runs the REAL pinned CLI (plugins/ace/node_modules, `npm ci --ignore-scripts`) against a local fake
server in a sandboxed HOME: every flag the plugin passes exists in `--help`, every JSON field the
plugin reads survives the CLI. Skips without node_modules, runs in CI and in the ace-cli-watch PR,
where a failure names the exact flags/fields to adapt. Never touches the network or the real config.
"""
import json
import os
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
CLI_JS = PLUGIN / "node_modules" / "@ace-sdk" / "cli" / "dist" / "cli.js"
NODE = shutil.which("node")
SQLITE_BINARY = PLUGIN / "node_modules" / "better-sqlite3" / "build" / "Release" / "better_sqlite3.node"

pytestmark = pytest.mark.skipif(not (CLI_JS.is_file() and NODE),
                                reason="pinned CLI not installed: npm ci --ignore-scripts in plugins/ace")

ORG, PROJECT, TOKEN = "org_contract", "prj_contract", "ace_contract_token"

# What the plugin passes (ace_cli.py: run_search/run_learn/check_auth_status; ace_graph_builder; commands).
FLAGS = {
    "search": ["--stdin", "--pin-session", "--top-k"],
    "learn": ["--transcript", "--stdin", "--no-stream", "--timeout", "--verbosity", "--retrieval-id", "--applied-log-ids"],
    "whoami": [],
    "projects": [],
}
GLOBAL_FLAGS = ["--json", "--version", "--org", "--project"]

PATTERN = {"id": "11111111-2222-4333-8444-555555555555", "content": "tip", "domain": "auth",
           "section": "strategies_and_hard_rules", "confidence": 0.9, "helpful": 1, "harmful": 0,
           "cumulative_v15_reward": 1.0, "isAtRisk": False, "semantic_score": 0.8, "bandit_rank": 1,
           "retrieval_log_id": 7, "match_factors": {"bandit_rank": 1, "retrieval_log_id": 7, "ucb_score": 0.5}}
SEARCH_RESPONSE = {"similar_patterns": [PATTERN], "count": 1, "retrieval_id": "22222222-3333-4444-8555-666666666666"}
SEARCH_FIELDS = ["similar_patterns", "count", "retrieval_id"]
LEARN_RESPONSE = {"status": "accepted", "analysis_performed": False, "deferred": True,
                  "learning_statistics": {"patterns_created": 0}}
LEARN_FIELDS = ["learning_statistics"]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self.server.requests.append((self.command, self.path, body.decode("utf-8", "replace")))
        path = self.path.split("?")[0]
        if "search" in path:
            return self._reply(200, SEARCH_RESPONSE)
        if path.endswith("/traces") or "traces" in path:
            return self._reply(202, LEARN_RESPONSE)
        if "projects" in path or "accessible" in path:
            return self._reply(200, {"projects": [{"project_id": PROJECT, "project_name": "contract"}],
                                     "organizations": [{"org_id": ORG, "name": "x"}]})
        if "config" in path:
            return self._reply(200, {"search_threshold": 0.4, "constitution_threshold": 0.4, "search_top_k": 10,
                                     "runtime_settings": {"learningEnabled": True}})
        return self._reply(200, {})

    do_GET = do_POST = do_PUT = _route


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    srv.requests = []
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


@pytest.fixture
def run(server, tmp_path):
    xdg = tmp_path / "xdg"
    (xdg / "ace").mkdir(parents=True)
    (tmp_path / "home" / ".ace-cache").mkdir(parents=True)
    # Up-to-date 24 h stamp: the CLI's own npm check stays offline.
    (tmp_path / "home" / ".ace-cache" / "cli-version-check.json").write_text(json.dumps(
        {"lastCheck": 32503680000000, "latestVersion": "0.0.0", "timestamp": 32503680000000}))
    (xdg / "ace" / "config.json").write_text(json.dumps({
        "serverUrl": "http://127.0.0.1:%d" % server.server_port, "projectId": PROJECT, "defaultOrgId": ORG,
        "auth": {"token": TOKEN, "user_id": "u", "email": "c@example.invalid",
                 "organizations": [{"org_id": ORG, "name": "x", "role": "admin", "projects": [PROJECT]}],
                 "authenticated_at": "2026-01-01T00:00:00Z", "refresh_token": "r",
                 "expires_at": "2099-01-01T00:00:00Z", "refresh_expires_at": "2099-01-01T00:00:00Z",
                 "absolute_expires_at": "2099-01-01T00:00:00Z"}}))

    def _run(*argv, stdin=None):
        env = {"HOME": str(tmp_path / "home"), "XDG_CONFIG_HOME": str(xdg), "PATH": os.pathsep.join([os.path.dirname(NODE), "/usr/bin", "/bin"]),  # git context
               "ACE_ORG_ID": ORG, "ACE_PROJECT_ID": PROJECT, "NO_COLOR": "1"}
        return subprocess.run([NODE, str(CLI_JS)] + list(argv), input=stdin, capture_output=True, text=True,
                              timeout=60, cwd=str(tmp_path), env=env)
    return _run


def _pin():
    return json.loads((PLUGIN / "package.json").read_text())["dependencies"]["@ace-sdk/cli"]


def test_installed_cli_is_the_pin(run):
    assert re.search(r"\d+\.\d+\.\d+", run("--version").stdout).group(0) == _pin()


@pytest.mark.parametrize("verb,flag", [(v, f) for v, fs in sorted(FLAGS.items()) for f in fs])
def test_every_flag_the_plugin_passes_exists(run, verb, flag):
    assert re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(flag), run(verb, "--help").stdout), "%s %s" % (verb, flag)


@pytest.mark.parametrize("flag", GLOBAL_FLAGS)
def test_global_flags_exist(run, flag):
    assert re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(flag), run("--help").stdout), flag


def test_flags_table_covers_ace_cli_py():
    """If the plugin starts passing a new flag, it must land in FLAGS (and so in the contract)."""
    src = (PLUGIN / "shared-hooks" / "utils" / "ace_cli.py").read_text()
    used = set(re.findall(r"""['"](--[a-z][a-z-]+)['"]""", src))
    known = {f for fs in FLAGS.values() for f in fs} | set(GLOBAL_FLAGS)
    assert used - known == set()


def _check_search(p):
    assert p.returncode == 0, p.stderr[-800:]
    out = json.loads(p.stdout)
    for k in SEARCH_FIELDS:
        assert k in out, k
    got = out["similar_patterns"][0]
    missing = [k for k in PATTERN if k not in got and k not in got.get("match_factors", {})]
    assert missing == [], "pattern fields the plugin reads are gone: %s" % missing


def test_search_fields_survive(run):
    """Works on what CC installs (`--ignore-scripts`, no better-sqlite3 binary)."""
    _check_search(run("search", "--stdin", "--json", "--top-k", "8", stdin="contract query"))


@pytest.mark.skipif(not SQLITE_BINARY.is_file(), reason="npm rebuild better-sqlite3 not run")
def test_pinned_search_fields_survive(run):
    """Needs the binary: without it ace-cli 4.2.2 exits 1 with empty stdout on --pin-session."""
    _check_search(run("search", "--stdin", "--json", "--pin-session", "11111111-1111-4111-8111-111111111111",
                      "--top-k", "8", stdin="contract query"))


def test_learn_no_stream_posts_the_trace_with_f080_and_stamped_fields(run, server, tmp_path):
    trace = {"task": "contract", "trajectory": [{"step": 1, "tool": "Edit", "action": "x"}],
             "result": {"success": True, "output": "o", "summary": "s"}, "playbook_used": [],
             "timestamp": "2026-11-02T00:00:00Z", "agent_type": "Explore", "agent_id": "a1",
             "session_id": "s1", "parent_agent_id": "parent", "render_variant": "budget"}
    f = tmp_path / "trace.json"
    f.write_text(json.dumps(trace))
    server.requests.clear()
    p = run("learn", "--transcript", str(f), "--json", "--no-stream", "--timeout", "1000", "--verbosity", "detailed",
            "--retrieval-id", "22222222-3333-4444-8555-666666666666", "--applied-log-ids", "7,8")
    assert p.returncode == 0, p.stderr[-800:]
    out = json.loads(p.stdout)
    for k in LEARN_FIELDS:
        assert k in out or k in out.get("result", {}), (k, out)
    posted = [json.loads(b) for m, path, b in server.requests if m == "POST" and "traces" in path]
    assert posted, server.requests
    for k in ("session_id", "agent_id", "agent_type", "parent_agent_id", "render_variant", "retrieval_id", "applied_log_ids"):
        assert k in posted[-1], "%s no longer reaches the server" % k


def test_learn_no_stream_server_error_is_a_real_exit_code(run, server, tmp_path, monkeypatch):
    f = tmp_path / "trace.json"
    f.write_text(json.dumps({"task": "t", "trajectory": [], "result": {"success": True, "output": "o"},
                             "playbook_used": [], "timestamp": "2026-11-02T00:00:00Z"}))
    monkeypatch.setattr(_Handler, "_reply", lambda self, code, obj: _Handler._raw(self, 500))
    assert run("learn", "--transcript", str(f), "--json", "--no-stream").returncode != 0


def _raw(self, code):
    self.send_response(code)
    self.send_header("Content-Length", "0")
    self.end_headers()


_Handler._raw = _raw


def test_whoami_fields(run):
    p = run("whoami", "--json")
    assert p.returncode == 0, p.stderr[-500:]
    assert json.loads(p.stdout).get("authenticated") is True


def test_whoami_unauthenticated_is_rc_zero_json(run, tmp_path):
    (tmp_path / "xdg" / "ace" / "config.json").write_text("{}")
    p = run("whoami", "--json")
    assert p.returncode == 0 and json.loads(p.stdout)["authenticated"] is False


def test_projects_fields(run):
    """ace_graph_builder reads project_id / project_name (v7.1.6)."""
    p = run("projects", "--json")
    assert p.returncode == 0, p.stderr[-500:]
    assert "project_id" in p.stdout and "project_name" in p.stdout


def test_notifier_text_still_matches_our_filter():
    """§23: the wrapper and error rows filter these lines; a reworded notifier must fail here."""
    checker = CLI_JS.parent / "utils" / "version-checker.js"
    t = checker.read_text()
    assert "Update available" in t and "npm install -g" in t
