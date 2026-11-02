"""R3c RED (e2e) — DESIGN §14: the real hooks run search/learn through the in-process engine.

Gated: ACE_E2E=1. A fake npm prefix (tests/engine_harness.py) supplies ace-cli + @ace-sdk/core;
the hooks see it on PATH exactly like a real nvm/npm global install.
- UPS injects the engine's patterns (no ace-cli search spawn) and logs engine "lib".
- An engine crash falls back to ace-cli inside the same hook (patterns still injected).
- Stop learns through engine/learn.js (no ace-cli learn spawn).
- Informational (§14): engine spawn CPU < 0.6 s vs the ace-cli spawn, real core vs localhost fake server.
"""
import json
import os
import resource
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine_harness as E  # noqa: E402
import ace_e2e_harness as H  # noqa: E402

pytestmark = [
    pytest.mark.skipif(os.environ.get("ACE_E2E") != "1", reason="e2e target tests: set ACE_E2E=1"),
    pytest.mark.skipif(E.node_bin() is None, reason="node not installed"),
]


@pytest.fixture
def prefix_env(tmp_path, monkeypatch):
    bin_dir = E.make_prefix(tmp_path)
    monkeypatch.setenv("PATH", E.path_with(bin_dir))
    monkeypatch.setenv("ACE_FAKE_CORE_LOG", str(tmp_path / "core.log"))
    monkeypatch.delenv("ACE_ENGINE", raising=False)
    made = []
    yield tmp_path, made
    for r in made:
        shutil.rmtree(str(r["sandbox"]), ignore_errors=True)


def _run(name, made):
    r = H.run_fixture(name)
    made.append(r)
    return r


def _engine_rows(r):
    return [x for x in E.read_jsonl(r["sandbox"] / "proj" / ".claude" / "data" / "logs" / "ace-relevance.jsonl")
            if "engine" in x]


def test_ups_searches_via_lib_engine(prefix_env):
    tmp, made = prefix_env
    r = _run("UserPromptSubmit_human", made)
    out = "".join(run["stdout"] for run in r["runs"])
    assert "engine pattern" in out, out[:500]  # CORE_RESPONSE content (ids may be stripped by render)
    assert not [c for c in r["cli_calls"] if c["argv"][:1] == ["search"]]
    assert [x for x in E.read_jsonl(tmp / "core.log") if x.get("op") == "search"]
    assert any(x["engine"] == "lib" for x in _engine_rows(r)), _engine_rows(r)


def test_ups_engine_crash_falls_back_to_cli(prefix_env, monkeypatch):
    tmp, made = prefix_env
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "crash")
    r = _run("UserPromptSubmit_human", made)
    out = "".join(run["stdout"] for run in r["runs"])
    assert "cli pattern" in out and "engine pattern" not in out, out[:500]
    assert any(x["engine"] == "cli" and x.get("reason") for x in _engine_rows(r)), _engine_rows(r)


def test_ups_env_cli_never_runs_engine(prefix_env, monkeypatch):
    tmp, made = prefix_env
    monkeypatch.setenv("ACE_ENGINE", "cli")
    r = _run("UserPromptSubmit_human", made)
    assert [c for c in r["cli_calls"] if c["argv"][:1] == ["search"]]
    assert not E.read_jsonl(tmp / "core.log")


def test_stop_learns_via_lib_engine(prefix_env):
    tmp, made = prefix_env
    r = _run("Stop", made)
    assert all(run["stdout"] == "" for run in r["runs"]), "Stop prints nothing (G3)"
    assert [x for x in E.read_jsonl(tmp / "core.log") if x.get("op") == "learn"], "learn went through the engine"
    assert not [c for c in r["cli_calls"] if c["argv"][:1] == ["learn"]]


def _cpu(argv, **kw):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    p = subprocess.run(argv, capture_output=True, text=True, timeout=90, **kw)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return p, (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)


@pytest.mark.skipif(E.real_core_dir() is None, reason="real ace-cli/@ace-sdk/core not installed")
def test_engine_search_cpu_vs_cli(tmp_path):
    srv = E.FakeServer(tmp_path)
    try:
        (tmp_path / "pfx").mkdir()
        bin_dir = E.make_prefix(tmp_path / "pfx", core="real")
        env = E.sdk_env(tmp_path, srv)
        cli, cli_cpu = _cpu([E.real_cli_path(), "search", "--stdin", "--json"], input="hook json", env=env)
        lib, lib_cpu = _cpu([E.node_bin(), str(E.ENGINE / "search.js")],
                            input=json.dumps({"query": "hook json", "org": "org_fake", "project": "prj_fake"}),
                            env=dict(env, PATH=E.path_with(bin_dir)))
        print("engine CPU %.3fs vs ace-cli CPU %.3fs" % (lib_cpu, cli_cpu))
        assert cli.returncode == 0 and lib.returncode == 0, lib.stderr
        assert lib_cpu < 0.6, "engine spawn CPU %.3fs" % lib_cpu
    finally:
        srv.stop()
