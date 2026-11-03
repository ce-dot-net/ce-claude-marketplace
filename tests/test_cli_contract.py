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

ORG, PROJECT, TOKEN = "org_contract", "prj_contract", "ace_user_contract_token"  # 4.4.0: only ace_user_* tokens

# What the plugin passes (ace_cli.py/ace_engine.py: run_search/run_learn/check_auth_status; ace_graph_builder; commands).
FLAGS = {
    "search": ["--stdin", "--pin-session", "--session-id", "--top-k"],
    "learn": ["--transcript", "--stdin", "--no-stream", "--timeout", "--verbosity", "--retrieval-id", "--applied-log-ids"],
    "whoami": [],
    "projects": [],
    "init": ["--fix-gitignore"],  # bind/configure/auto-adopt (ace_project_context.cli_init, mod context/index.ts cliInit)
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
    """If the plugin starts passing a new flag, it must land in FLAGS (and so in the contract).
    ace_engine.py builds the ace-cli argv (search_command/learn_command); its own `--status` is not an ace-cli flag."""
    used = set()
    for name in ("ace_cli.py", "ace_engine.py"):
        src = (PLUGIN / "shared-hooks" / "utils" / name).read_text()
        used |= set(re.findall(r"""['"](--[a-z][a-z-]+)['"]""", src))
    known = {f for fs in FLAGS.values() for f in fs} | set(GLOBAL_FLAGS)
    assert used - known - {"--status"} == set()


def test_search_session_id_reaches_the_server_without_pinning(run, server, tmp_path):
    """cli >= 4.3.1: --session-id puts session_id into the search request and never opens sessions.db."""
    server.requests.clear()
    _check_search(run("search", "--stdin", "--json", "--session-id", "tsid-contract", "--top-k", "8",
                      stdin="contract query"))
    bodies = [json.loads(b) for m, path, b in server.requests if m == "POST" and "search" in path and b]
    assert bodies and bodies[-1].get("session_id") == "tsid-contract", server.requests
    assert not (tmp_path / "home" / ".ace-cache" / "sessions.db").exists()


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
    """4.4.0: not logged in = exit 3, stderr {"error":{"code":"not_logged_in",...}} (the verify classifier's input)."""
    (tmp_path / "xdg" / "ace" / "config.json").write_text("{}")
    p = run("whoami", "--json")
    assert p.returncode == 3 and json.loads(p.stderr.strip().splitlines()[-1])["error"]["code"] == "not_logged_in"


def test_context_json_is_the_seam_shape(run, tmp_path):
    """4.4.0: `context --json` (offline) gives the resolver result the mod's seam parses; unbound = exit 5."""
    p = run("context", "--json")
    j = json.loads(p.stdout)
    assert isinstance(j.get("bound"), bool)
    assert p.returncode == (0 if j["bound"] else 5)


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


# ---- 4.4.1: `ace-cli init --json` write target (spec §9, fixture init-target.json), the same as our fallback ----

def _init(cwd, home, *extra):
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg"), "PATH": os.pathsep.join([os.path.dirname(NODE), "/usr/bin", "/bin"]),
           "NO_COLOR": "1"}
    return subprocess.run([NODE, str(CLI_JS), "init", "--json", "--org", "org_a", "--project", "prj_a", *extra],
                          capture_output=True, text=True, timeout=60, cwd=str(cwd), env=env)


def _init_cases():
    return json.loads((PLUGIN / "tests-fixtures/project-context/init-target.json").read_text())["cases"]


@pytest.mark.parametrize("case", _init_cases(), ids=[c["name"] for c in _init_cases()])
def test_cli_init_target_matches_the_spec_and_our_fallback(tmp_path, case):
    from test_init_target import build, check
    base = build(tmp_path / "a", case["layout"])
    p = _init(base / case["cwd"], tmp_path / "home")
    assert p.returncode == 0, p.stderr[-500:]
    check(base, case, json.loads(p.stdout))


def _real_worktree(tmp_path):
    main = Path(os.path.realpath(tmp_path)) / "main"
    main.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(main), *a], capture_output=True, text=True, check=True)
    g("init", "-q")
    g("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i")
    (main / ".gitignore").write_text(".ace/\n")
    g("worktree", "add", "-q", str(main.parent / "wt"), "-b", "wt")
    return main, main.parent / "wt"


def test_cli_init_in_a_real_worktree_writes_the_main_checkout_and_fixes_gitignore(tmp_path):
    main, wt = _real_worktree(tmp_path)
    j = json.loads(_init(wt, tmp_path / "home", "--fix-gitignore").stdout)
    assert j["path"] == str(main / ".ace/config.json") and j["mainCheckout"] is True and j["gitignore"] == "fixed"
    assert "written_to_main_checkout" in j["warnings"] and not (wt / ".ace").exists()
    assert (main / ".gitignore").read_text().splitlines() == [".ace/*", "!.ace/config.json"]


def test_cli_init_reports_the_shadowing_worktree_file_and_leaves_it(tmp_path):
    main, wt = _real_worktree(tmp_path)
    (wt / ".ace").mkdir()
    (wt / ".ace/config.json").write_text('{"orgId": "org_a", "projectId": "prj_old"}')
    j = json.loads(_init(wt, tmp_path / "home").stdout)
    assert j["shadowedBy"] == str(wt / ".ace/config.json") and "worktree_file_shadows_main" in j["warnings"]
    assert "prj_old" in (wt / ".ace/config.json").read_text()


@pytest.mark.parametrize("what", ["ace_dir", "config", "gitignore"])
def test_cli_init_refuses_symlinks_exit_1_json(tmp_path, what):
    """The refusal the plugin treats as final (no fallback write): exit 1, stderr {"error":{"message"}} naming the path."""
    main, wt = _real_worktree(tmp_path)
    victim = tmp_path / "victim"
    victim.mkdir()
    if what == "ace_dir":
        (main / ".ace").symlink_to(victim)
    elif what == "config":
        (main / ".ace").mkdir()
        (main / ".ace/config.json").symlink_to(victim / "x.json")
    else:
        (victim / "gi").write_text(".ace/\n")
        (main / ".gitignore").unlink()
        (main / ".gitignore").symlink_to(victim / "gi")
    p = _init(wt, tmp_path / "home", "--fix-gitignore")
    if what == "gitignore":  # git does not read a symlinked .gitignore: nothing ignored, the target is never written
        assert p.returncode == 0 and (victim / "gi").read_text() == ".ace/\n"
        return
    assert p.returncode == 1 and "symlink" in json.loads(p.stderr.strip().splitlines()[-1])["error"]["message"]
    assert not (victim / "x.json").exists() and [f.name for f in victim.iterdir()] in ([], ["gi"])


def test_python_chain_binds_through_the_real_cli(tmp_path, monkeypatch):
    """ace_project_context.bind with the real pinned CLI: via cli, the main checkout, the shadow left for [Entfernen]."""
    import sys
    sys.path.insert(0, str(PLUGIN / "shared-hooks/utils"))
    import ace_cli
    import ace_project_context as apc
    monkeypatch.setattr(ace_cli, "_cmd", lambda *a: [NODE, str(CLI_JS), *a])
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    main, wt = _real_worktree(tmp_path)
    (wt / "src").mkdir()
    r = apc.bind(str(wt / "src"), "org_a", "prj_a")
    assert r["via"] == "cli" and r["path"] == str(main / ".ace/config.json") and r["mainCheckout"] is True
    (wt / ".ace").mkdir()
    (wt / ".ace/config.json").write_text("{}")
    r = apc.bind(str(wt / "src"), "org_a", "prj_a")
    assert r["shadowedBy"] == str(wt / ".ace/config.json")
    assert apc.remove_shadow(str(wt / "src"), r["shadowedBy"]) and not (wt / ".ace/config.json").exists()
