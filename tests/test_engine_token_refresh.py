#!/usr/bin/env python3
"""DESIGN §26 token-refresh edges, real @ace-sdk/core engine vs the localhost fake server (never the real one).

An expired access token makes every spawn refresh. When the refresh endpoint rate-limits (429, 30/min per IP) or
answers invalid_grant reason=reuse (family revoked): no logout (config auth untouched), a bounded number of refresh
POSTs per spawn (no loop), and the hook still gets patterns: from the engine (core keeps the old token) or, when the
server also rejects the search, from the ace-cli fallback. Fan-out of 30 parallel expired spawns included.
"""
import importlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

import engine_harness as E

sys.path.insert(0, str(E.UTILS))

pytestmark = [pytest.mark.real_engine, pytest.mark.skipif(E.node_bin() is None, reason="node not installed"),
              pytest.mark.skipif(E.real_core_dir() is None, reason="real ace-cli/@ace-sdk/core not installed")]


@pytest.fixture
def world(tmp_path, monkeypatch, request):
    refresh, search = request.param
    monkeypatch.setenv("FAKE_REFRESH", refresh)
    if search:
        monkeypatch.setenv("FAKE_SEARCH", search)
    srv = E.FakeServer(tmp_path)
    (tmp_path / "pfx").mkdir()
    bin_dir = E.make_prefix(tmp_path / "pfx", core="real")
    env = E.sdk_env(tmp_path, srv, PATH=E.path_with(bin_dir), ACE_FAKE_CLI_LOG=str(tmp_path / "cli.log"))
    cfg = tmp_path / "xdg" / "ace" / "config.json"
    c = json.loads(cfg.read_text())
    c["auth"]["expires_at"] = "2020-01-01T00:00:00Z"  # expired: every spawn tries to refresh
    cfg.write_text(json.dumps(c))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("ACE_ENGINE", raising=False)
    monkeypatch.chdir(tmp_path)
    import plugin_data_dir
    importlib.reload(plugin_data_dir)
    import ace_engine
    importlib.reload(ace_engine)
    import ace_cli
    cli = importlib.reload(ace_cli)
    yield cli, srv, cfg, c["auth"], tmp_path
    srv.stop()


CASES = [("429", None), ("reuse", None), ("429", "401"), ("reuse", "401")]


def _check(world, results):
    cli, srv, cfg, auth_before, root = world
    for res, _ms in results:
        assert res and res.get("similar_patterns"), res  # patterns not lost
    auth = json.loads(cfg.read_text())["auth"]
    assert auth.get("token") == auth_before["token"] and auth.get("refresh_token") == auth_before["refresh_token"], \
        "no logout: a failed refresh must leave the stored auth alone"
    refreshes = [q for q in srv.requests() if q["path"].startswith("/api/v1/auth/refresh")]
    assert len(refreshes) <= 2 * len(results), "refresh loop: %d POSTs for %d spawns" % (len(refreshes), len(results))
    return root


@pytest.mark.parametrize("world", CASES, indirect=True, ids=["429", "reuse", "429+search401", "reuse+search401"])
def test_failed_refresh_keeps_login_and_patterns(world):
    cli = world[0]
    root = _check(world, [cli.run_search("hook json", org="org_fake", project="prj_fake", timeout=25)])
    via_cli = E.read_jsonl(root / "cli.log")
    if world[1].requests() and any(q["path"].startswith("/patterns/search") for q in world[1].requests()):
        rejected = __import__("os").environ.get("FAKE_SEARCH") == "401"
        assert bool(via_cli) == rejected, "the ace-cli fallback runs exactly when the server rejects the engine's search"


@pytest.mark.parametrize("world", [("429", None), ("reuse", "401")], indirect=True, ids=["429", "reuse+search401"])
def test_fan_out_of_30_expired_spawns(world):
    cli = world[0]
    with ThreadPoolExecutor(30) as pool:
        results = list(pool.map(lambda i: cli.run_search("hook json %d" % i, org="org_fake", project="prj_fake",
                                                         timeout=25), range(30)))
    _check(world, results)
