#!/usr/bin/env python3
"""R3c RED — DESIGN §14 Python consumer: shared-hooks/utils/ace_engine.py + ace_cli wiring.

Pinned interface of ace_engine (stdlib, Python 3.9):
  select() -> {"engine": "lib"|"cli", "reason": str, "node": str|None,
               "core_dir": str|None, "core_version": str|None}
      ACE_ENGINE=cli -> cli; no node -> cli; resolve.js gate failure -> cli (reason from the gate);
      otherwise lib.
  search_command(query, *, org=None, project=None, session_id=None, top_k=None, node=None)
      -> (argv, stdin_bytes). node=None -> the unchanged ace-cli argv
      [ace-cli, search, --stdin, --json, (--pin-session X), (--top-k N)] + query bytes;
      node=<path> -> [node, <engine>/search.js] + JSON {query, org, project, session_id?, top_k?}.
  learn_command(trace_path, *, retrieval_id=None, applied_log_ids=None, verbosity="detailed",
                timeout=300, node=None) -> argv  (ace-cli learn ... | [node, <engine>/learn.js, ...])
  `python3 ace_engine.py --status` prints select() as JSON (used by /ace:ace-doctor).
ace_cli.run_search / run_learn get their argv from ace_engine (module attribute lookup at call
time) and fall back to the ace-cli path on: gate failure, missing node, ACE_ENGINE=cli, engine
crash / non-JSON output (search). learn falls back only when the engine failed BEFORE sending
(exit 3 / spawn error): a server error is never re-POSTed through the CLI (double F-080 credit).
Every spawn writes a relevance row carrying `engine` ("lib"|"cli") and `reason`.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest
from pathlib import Path

import engine_harness as E

sys.path.insert(0, str(E.UTILS))

needs_node = pytest.mark.skipif(E.node_bin() is None, reason="node not installed")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh ace_engine/ace_cli, cwd = tmp_path (relevance log lands under it), logs wired."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ACE_FAKE_CLI_LOG", str(tmp_path / "cli.log"))
    monkeypatch.setenv("ACE_FAKE_CORE_LOG", str(tmp_path / "core.log"))
    monkeypatch.delenv("ACE_ENGINE", raising=False)
    monkeypatch.delenv("ACE_FAKE_CORE_MODE", raising=False)

    class Env:
        root = tmp_path

        def use(self, bin_dir):
            monkeypatch.setenv("PATH", E.path_with(bin_dir))
            import plugin_data_dir
            importlib.reload(plugin_data_dir)
            import ace_relevance_logger
            ace_relevance_logger._logger = None
            import ace_engine
            self.engine = importlib.reload(ace_engine)
            import ace_cli
            self.cli = importlib.reload(ace_cli)
            return self

        def cli_calls(self, op=None):
            rows = E.read_jsonl(tmp_path / "cli.log")
            return [r for r in rows if op is None or r["argv"][:1] == [op]]

        def core_ops(self, op):
            return [r for r in E.read_jsonl(tmp_path / "core.log") if r.get("op") == op]

        def engine_rows(self):
            return [r for r in E.read_jsonl(tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl")
                    if "engine" in r]

    return Env()


# ---------------------------------------------------------------- argv builders

def test_search_command_cli_argv_unchanged(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path))
    argv, stdin = e.engine.search_command("fix it", session_id="tsid-1", top_k=8)
    assert argv == ["ace-cli", "search", "--stdin", "--json", "--pin-session", "tsid-1", "--top-k", "8"]
    assert stdin == b"fix it"
    argv, _ = e.engine.search_command("fix it")
    assert argv == ["ace-cli", "search", "--stdin", "--json"]


def test_search_command_lib_argv_and_stdin_json(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path))
    argv, stdin = e.engine.search_command("fix it", org="org_a", project="prj_b", session_id="tsid-1",
                                          top_k=8, node="/x/node")
    assert argv == ["/x/node", str(E.ENGINE / "search.js")]
    assert json.loads(stdin) == {"query": "fix it", "org": "org_a", "project": "prj_b",
                                 "session_id": "tsid-1", "top_k": 8}
    _, stdin = e.engine.search_command("q", org="o", project="p", node="/x/node")
    assert json.loads(stdin) == {"query": "q", "org": "o", "project": "p"}


def test_learn_command_cli_and_lib(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path))
    cli = e.engine.learn_command("/t.json", retrieval_id="r1", applied_log_ids=[1, 2], verbosity="compact")
    assert cli[:4] == ["ace-cli", "learn", "--transcript", "/t.json"]
    assert "--json" in cli and cli[cli.index("--verbosity") + 1] == "compact"
    assert cli[cli.index("--retrieval-id") + 1] == "r1"
    assert cli[cli.index("--applied-log-ids") + 1] == "1,2"
    lib = e.engine.learn_command("/t.json", retrieval_id="r1", applied_log_ids=[1, 2], node="/x/node")
    assert lib[:2] == ["/x/node", str(E.ENGINE / "learn.js")]
    assert lib[lib.index("--transcript") + 1] == "/t.json"
    assert lib[lib.index("--retrieval-id") + 1] == "r1"
    assert lib[lib.index("--applied-log-ids") + 1] == "1,2"


def test_ace_cli_builds_argv_via_ace_engine(env, tmp_path, monkeypatch):
    """§14: ace_cli keeps its logic; only the argv comes from ace_engine (looked up at call time)."""
    e = env.use(E.make_prefix(tmp_path))
    monkeypatch.setenv("ACE_ENGINE", "cli")
    script = "import sys; sys.stdin.read(); print('{\"count\": 0, \"similar_patterns\": [], \"sentinel\": true}')"
    monkeypatch.setattr(e.engine, "search_command",
                        lambda *a, **k: ([sys.executable, "-c", script], b"q"))
    result, _ = e.cli.run_search("q", org="o", project="p")
    assert result and result.get("sentinel") is True


# ---------------------------------------------------------------- select(): gate + every fallback reason

@needs_node
def test_select_lib_when_gate_passes(env, tmp_path):
    sel = env.use(E.make_prefix(tmp_path)).engine.select()
    assert sel["engine"] == "lib", sel
    assert sel["node"] and os.path.basename(sel["node"]).startswith("node")
    assert sel["core_version"] == "3.3.2"


@needs_node
def test_select_env_override_cli(env, tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_ENGINE", "cli")
    sel = env.use(E.make_prefix(tmp_path)).engine.select()
    assert sel["engine"] == "cli" and "ACE_ENGINE" in sel["reason"]


def test_select_no_node(env, tmp_path):
    bin_dir = E.make_prefix(tmp_path, with_node=False)
    if any(os.path.exists(os.path.join(d, "node")) for d in ("/usr/bin", "/bin")):
        pytest.skip("system node in /usr/bin")
    sel = env.use(bin_dir).engine.select()
    assert sel["engine"] == "cli" and "node" in sel["reason"].lower()


@needs_node
@pytest.mark.parametrize("kw,reason", [
    ({"with_cli": False}, "no_cli"),
    ({"core": None}, "core_missing"),
    ({"version": "3.2.1"}, "core_too_old"),
    ({"missing": "config/context.js"}, "file_missing"),
    ({"no_export": True}, "export_missing"),
])
def test_select_gate_failures_fall_back_to_cli(env, tmp_path, kw, reason):
    sel = env.use(E.make_prefix(tmp_path, **kw)).engine.select()
    assert sel["engine"] == "cli"
    assert reason in sel["reason"]


@needs_node
def test_status_cli_prints_selection_json(tmp_path):
    bin_dir = E.make_prefix(tmp_path)
    r = subprocess.run([sys.executable, str(E.UTILS / "ace_engine.py"), "--status"], capture_output=True,
                       text=True, timeout=30, env=dict(os.environ, PATH=E.path_with(bin_dir)))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["engine"] == "lib" and out["core_version"] == "3.3.2"
    r = subprocess.run([sys.executable, str(E.UTILS / "ace_engine.py"), "--status"], capture_output=True,
                       text=True, timeout=30, env=dict(os.environ, PATH=E.path_with(bin_dir), ACE_ENGINE="cli"))
    assert json.loads(r.stdout)["engine"] == "cli"


# ---------------------------------------------------------------- §23 plugin-local + preflight

def _run_in_copy(plugin, code, path, cwd):
    """Run `code` against the plugin copy's ace_engine/ace_cli (ENGINE_DIR follows __file__)."""
    env = dict(os.environ, PATH=path, CLAUDE_PLUGIN_ROOT=str(plugin))  # as Claude Code runs it: its own root
    env.pop("ACE_ENGINE", None)
    r = subprocess.run([sys.executable, "-c", "import json,sys; sys.path.insert(0, %r)\n%s"
                        % (str(plugin / "shared-hooks" / "utils"), code)],
                       capture_output=True, text=True, env=env, cwd=str(cwd), timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_plugin_local_core_runs_the_engine_without_any_ace_cli(tmp_path):
    """§18 clean machine, §23: node + plugin-local core, no ace-cli on PATH."""
    plugin = E.make_plugin_local(tmp_path)
    path = E.path_with(E.make_prefix(tmp_path, core=None, with_cli=False))
    sel = _run_in_copy(plugin, "import ace_engine; print(json.dumps(ace_engine.select()))", path, tmp_path)
    assert sel["engine"] == "lib" and sel["core_version"] == "3.3.2", sel
    res = _run_in_copy(plugin, "import ace_cli; print(json.dumps(ace_cli.run_search('q', org='o', project='p')[0]))",
                       path, tmp_path)
    assert res == E.CORE_RESPONSE


@needs_node
def test_plugin_local_core_ignores_an_unusable_ace_cli_shim(tmp_path):
    """volta/asdf: ace-cli on PATH is a shim whose realpath is not @ace-sdk/cli. PATH must not matter."""
    plugin = E.make_plugin_local(tmp_path)
    bin_dir = E.make_prefix(tmp_path, core=None, with_cli=False)
    shim = bin_dir / "ace-cli"
    shim.write_text("#!/bin/sh\nexit 1\n")
    shim.chmod(0o755)
    sel = _run_in_copy(plugin, "import ace_engine; print(json.dumps(ace_engine.select()))", E.path_with(bin_dir), tmp_path)
    assert sel["engine"] == "lib", sel


def test_cli_head_comes_from_the_caller(env, tmp_path):
    """r3d: cli_argv() may return [node, cli.js]; the builders must not hard-code the head."""
    e = env.use(E.make_prefix(tmp_path))
    argv, stdin = e.engine.search_command("q", session_id="t", top_k=8, cli=["/n", "/cli.js"])
    assert argv == ["/n", "/cli.js", "search", "--stdin", "--json", "--pin-session", "t", "--top-k", "8"]
    assert stdin == b"q"
    assert e.engine.learn_command("/t.json", cli=["/n", "/cli.js"])[:3] == ["/n", "/cli.js", "learn"]


def test_ace_engine_does_not_own_the_cli_spawn_head():
    """r3d's lint: only ace_cli may locate the CLI; ace_engine gets the head from its caller."""
    src = (E.UTILS / "ace_engine.py").read_text(encoding="utf-8")
    assert "CLI_CMD" not in src and "['ace-cli'" not in src and 'which(\'ace-cli' not in src


@needs_node
@pytest.mark.parametrize("script", ["search.js", "learn.js", "resolve.js"])
def test_preflight_rejects_a_partial_engine_dir(env, tmp_path, monkeypatch, script):
    """Node exits 1 on an unloadable script, which learn reads as 'may have sent': never get there."""
    e = env.use(E.make_prefix(tmp_path))
    partial = tmp_path / "engine"
    partial.mkdir()
    for f in {"search.js", "learn.js", "resolve.js"} - {script}:
        (partial / f).write_text("")
    monkeypatch.setattr(e.engine, "ENGINE_DIR", partial)
    node, reason = e.engine.preflight()
    assert node is None and "engine" in reason and script in reason


# ---------------------------------------------------------------- run_search through the engine

@needs_node
def test_run_search_uses_lib_engine(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path))
    result, ms = e.cli.run_search("fix hook", org="org_a", project="prj_b", session_id="tsid-9", top_k=8,
                                  hook_event_name="UserPromptSubmit")
    assert result == E.CORE_RESPONSE
    assert isinstance(ms, int)
    assert e.cli_calls("search") == [], "lib engine must not spawn ace-cli"
    s = e.core_ops("search")[0]["params"]
    assert s["session_id"] == "tsid-9" and s["top_k"] == 8 and s["query"] == "fix hook"
    rows = e.engine_rows()
    assert any(r["engine"] == "lib" and r.get("hook") == "UserPromptSubmit" for r in rows), rows


@needs_node
def test_run_search_lib_never_touches_pin_store_or_backoff(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path))
    e.cli.run_search("q", session_id="tsid-1", hook_event_name="SubagentStart")
    import plugin_data_dir
    assert not plugin_data_dir.pin_backoff_file().exists()
    assert not any(r.get("pin_failed") for r in E.read_jsonl(tmp_path / ".claude/data/logs/ace-relevance.jsonl"))


def _assert_cli_fallback(e, reason_substr=None):
    calls = e.cli_calls("search")
    assert calls, "fallback must spawn ace-cli search"
    rows = e.engine_rows()
    cli_rows = [r for r in rows if r["engine"] == "cli"]
    assert cli_rows, rows
    assert all(r.get("reason") for r in cli_rows), rows
    if reason_substr:
        assert any(reason_substr in r["reason"] for r in cli_rows), rows


@needs_node
def test_run_search_env_cli(env, tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_ENGINE", "cli")
    e = env.use(E.make_prefix(tmp_path))
    result, _ = e.cli.run_search("q", session_id="tsid-1")
    assert result == E.CLI_RESPONSE
    _assert_cli_fallback(e, "ACE_ENGINE")
    assert e.core_ops("search") == []
    assert "--pin-session" in e.cli_calls("search")[0]["argv"], "CLI path keeps the pin (A1 unchanged)"


def test_run_search_no_node(env, tmp_path):
    if any(os.path.exists(os.path.join(d, "node")) for d in ("/usr/bin", "/bin")):
        pytest.skip("system node in /usr/bin")
    e = env.use(E.make_prefix(tmp_path, with_node=False))
    result, _ = e.cli.run_search("q")
    assert result == E.CLI_RESPONSE
    _assert_cli_fallback(e, "node")


@needs_node
@pytest.mark.parametrize("kw", [{"core": None}, {"version": "3.2.1"}, {"no_export": True},
                                {"missing": "client/ace-client.js"}])
def test_run_search_gate_failure_falls_back(env, tmp_path, kw):
    e = env.use(E.make_prefix(tmp_path, **kw))
    result, _ = e.cli.run_search("q", session_id="tsid-1")
    assert result == E.CLI_RESPONSE
    _assert_cli_fallback(e)


@needs_node
def test_run_search_no_ace_cli_at_all(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path, with_cli=False))
    result, _ = e.cli.run_search("q")
    assert isinstance(result, dict) and result.get("error") == "cli_not_found"


@needs_node
@pytest.mark.parametrize("mode", ["crash", "throw", "garbage", "drift"])
def test_run_search_engine_failure_falls_back_to_cli(env, tmp_path, monkeypatch, mode):
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", mode)
    e = env.use(E.make_prefix(tmp_path))
    result, _ = e.cli.run_search("q", session_id="tsid-1", hook_event_name="SubagentStart")
    assert result == E.CLI_RESPONSE, "engine crash must not lose patterns"
    assert e.core_ops("search"), "engine was tried first"
    _assert_cli_fallback(e)
    assert any(r["engine"] == "lib" and r.get("ok") is False for r in e.engine_rows()), \
        "the failed lib attempt is logged too"


# ---------------------------------------------------------------- run_learn through the engine

TRACE = {"task": "fix the hook", "trajectory": [], "result": {"success": True}, "playbook_used": [],
         "timestamp": "2026-11-02T00:00:00Z"}


@needs_node
def test_run_learn_uses_lib_engine(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path))
    out, _ = e.cli.run_learn(dict(TRACE), retrieval_id="ret-1", applied_log_ids=[3, 4], org="o", project="p",
                             hook_event_name="Stop")
    assert out and out.get("success") is True
    assert e.cli_calls("learn") == []
    t = e.core_ops("learn")[0]["trace"]
    assert t["retrieval_id"] == "ret-1" and t["applied_log_ids"] == [3, 4]
    assert any(r["engine"] == "lib" for r in e.engine_rows())


@needs_node
def test_run_learn_gate_failure_falls_back_to_cli(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path, version="3.0.0"))
    out, _ = e.cli.run_learn(dict(TRACE), retrieval_id="ret-1", org="o", project="p")
    assert out and out.get("via") == "cli"
    assert len(e.cli_calls("learn")) == 1
    assert any(r["engine"] == "cli" and r.get("reason") for r in e.engine_rows())


@needs_node
def test_run_learn_env_cli(env, tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_ENGINE", "cli")
    e = env.use(E.make_prefix(tmp_path))
    out, _ = e.cli.run_learn(dict(TRACE), org="o", project="p")
    assert out and out.get("via") == "cli"
    assert e.core_ops("learn") == []


@needs_node
def test_run_learn_server_error_is_not_reposted_via_cli(env, tmp_path, monkeypatch):
    """A server error after the POST must not be retried through ace-cli (duplicate trace / double credit)."""
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "throw")
    e = env.use(E.make_prefix(tmp_path))
    out, _ = e.cli.run_learn(dict(TRACE), org="o", project="p", hook_event_name="Stop")
    assert out is None
    assert len(e.core_ops("learn")) == 1
    assert e.cli_calls("learn") == []
    rows = E.read_jsonl(tmp_path / ".claude/data/logs/ace-relevance.jsonl")
    assert any(r.get("event") == "error" and r.get("hook") == "Stop" for r in rows), rows


@needs_node
def test_run_learn_removes_temp_trace_on_lib_path(env, tmp_path):
    e = env.use(E.make_prefix(tmp_path))
    e.cli.run_learn(dict(TRACE), org="o", project="p")
    import plugin_data_dir
    tmp = plugin_data_dir.data_root() / "tmp"
    assert not (tmp.exists() and list(tmp.glob("ace-trace-*.json")))
    assert e.core_ops("learn"), "lib path ran"


@needs_node
def test_run_learn_engine_timeout_is_logged_and_not_retried(env, tmp_path, monkeypatch):
    """§14: every spawn is logged. The POST may have been sent, so no CLI retry either."""
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "hang")
    e = env.use(E.make_prefix(tmp_path))
    out, _ = e.cli.run_learn(dict(TRACE), org="o", project="p", timeout=2, hook_event_name="Stop")
    assert out is None
    assert e.cli_calls("learn") == []
    assert [r for r in e.engine_rows() if r["engine"] == "lib" and r["reason"] == "timeout" and r["ok"] is False]
    rows = E.read_jsonl(tmp_path / ".claude/data/logs/ace-relevance.jsonl")
    assert any("timeout" in str(r.get("error_type", r)) and r.get("event") == "error" for r in rows), rows


# ---------------------------------------------------------------- doctor + ADR (mod-callable interface)

def test_doctor_shows_active_engine():
    doc = (E.PLUGIN / "commands" / "ace-doctor.md").read_text(encoding="utf-8")
    assert "ace_engine.py --status" in doc
    assert "ACE_ENGINE=cli" in doc
    assert "engine" in doc.lower() and "lib" in doc
    engine_line = [l for l in doc.splitlines() if l.startswith("- ℹ️ Engine: cli")][0]
    assert "npm install -g" not in engine_line, "§23: repair is /ace:ace-install-cli, global is the last mention"
    assert "/ace:ace-install-cli" in engine_line


def test_adr_records_engine_decision_and_mod_interface():
    text = (E.PLUGIN / "docs" / "technical" / "ADR-001-language.md").read_text(encoding="utf-8")
    for s in ("engine/search.js", "engine/learn.js", "engine/resolve.js", "ace_engine.py",
              "ACE_ENGINE", "X-ACE-Client", "claude-code-plugin/", "3.2.2", "dist/cjs",
              "$.process.run", "session_id", "top_k", "--no-stream", "exit 3"):
        assert s in text, "ADR-001 must document " + s
    assert "8.0.0" in text
    assert "ace-cli >= 4.3.0" in text and "ACE_CLIENT_ID" in text, "CLI path attribution (4.3.0)"
    for s in ("Windows", "WSL2", "Volta", "asdf", "nvm", "core_too_new", "node_modules/@ace-sdk/core"):
        assert s in text, "ADR-001 must document " + s
    assert "v8.1 plan" not in text, "§14: in-process core is IN 8.0.0, not deferred to 8.1"


def test_engine_root_follows_an_ace_plugin_root_env(tmp_path, monkeypatch):
    """The engine (and its plugin-local core) come from the same root as ace_cli.cli_argv: an ACE
    CLAUDE_PLUGIN_ROOT wins. Otherwise a copy without node_modules would still run the repo's real core."""
    root = tmp_path / "ace"
    (root / "shared-hooks" / "utils").mkdir(parents=True)
    (root / "shared-hooks" / "utils" / "ace_cli.py").write_text("")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
    import ace_engine
    m = importlib.reload(ace_engine)
    assert m.ENGINE_DIR == root / "engine"
    assert all(str(d).startswith(str(root)) for d in m.PLUGIN_LOCAL_CORES)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "foreign-plugin"))
    own = Path(ace_engine.__file__).resolve().parents[2] / "engine"
    assert importlib.reload(ace_engine).ENGINE_DIR == own
    monkeypatch.undo()  # restore the session env, then the module, so later tests see the hermetic root again
    importlib.reload(ace_engine)
