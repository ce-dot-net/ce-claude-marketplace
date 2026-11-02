#!/usr/bin/env python3
"""R3c RED — DESIGN §14 parity harness vs the REAL server (p6/m3 compare.py as a pytest).

engine search JSON vs `ace-cli search --json` on 3 real queries: same top-level keys, same
per-pattern key sets, same counts, retrieval_id present on both. SEARCH ONLY (never learn), no
--pin-session/session_id (no pin rows), project/org from a copy of the repo's
.claude/settings.json, credentials from the developer's real ~/.config/ace/config.json.
Skips without network, without the real ace-cli/core, or without a real login.
"""
import json
import os
import pwd
import shutil
import socket
import subprocess

import pytest

import engine_harness as E

QUERIES = ["hook JSON emission with jq", "plugin release version bump manifests",
           "pytest hermetic fake ace-cli on PATH"]


def _online():
    try:
        socket.create_connection(("ace-api.code-engine.app", 443), timeout=3).close()
        return True
    except OSError:
        return False


REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir
REAL_CFG = os.path.join(REAL_HOME, ".config", "ace", "config.json")

pytestmark = [
    pytest.mark.skipif(E.node_bin() is None, reason="node not installed"),
    pytest.mark.skipif(E.real_core_dir() is None, reason="real ace-cli/@ace-sdk/core not installed"),
    pytest.mark.skipif(not os.path.exists(REAL_CFG), reason="no real ACE login"),
    pytest.mark.skipif(not _online(), reason="no network"),
]


@pytest.fixture(scope="module")
def live_env(tmp_path_factory):
    d = tmp_path_factory.mktemp("live")
    shutil.copy(str(E.REPO / ".claude" / "settings.json"), str(d / "settings.json"))
    ids = json.loads((d / "settings.json").read_text())["env"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("ACE_") and k != "XDG_CONFIG_HOME"}
    env.update(HOME=REAL_HOME, ACE_ORG_ID=ids["ACE_ORG_ID"], ACE_PROJECT_ID=ids["ACE_PROJECT_ID"],
               PATH=E.path_with(E.make_prefix(d, core="real")))  # conftest's fake ace-cli would fail the gate
    return env, ids


def _key_sets(result):
    # order-insensitive: two live calls may rank ties differently
    return sorted(tuple(sorted(p)) for p in result["similar_patterns"])


@pytest.mark.parametrize("query", QUERIES)
def test_engine_search_parity_with_ace_cli(live_env, query):
    """Two live ace-cli calls can differ from EACH OTHER too (100 vs 101 patterns, per-pattern keys), so a
    pair may be retried. An engine that really drops keys or patterns fails every attempt."""
    env, ids = live_env
    payload = json.dumps({"query": query, "org": ids["ACE_ORG_ID"], "project": ids["ACE_PROJECT_ID"]})
    for _ in range(5):
        cli = subprocess.run([E.real_cli_path(), "search", "--stdin", "--json"], input=query,
                             capture_output=True, text=True, env=env, timeout=90)
        if cli.returncode != 0:
            pytest.skip("ace-cli search failed (auth/server): " + cli.stderr[:200])
        lib = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input=payload,
                             capture_output=True, text=True, env=env, timeout=90)
        assert lib.returncode == 0, lib.stderr[:500]
        a, b = json.loads(cli.stdout), json.loads(lib.stdout)
        assert sorted(a) == sorted(b), "top-level keys"
        assert a.get("retrieval_id") and b.get("retrieval_id"), "retrieval_id on both (F-080)"
        if _key_sets(a) == _key_sets(b) and a.get("count") == b.get("count"):
            return
    assert len(a["similar_patterns"]) == len(b["similar_patterns"]), "pattern count"
    assert a.get("count") == b.get("count")
    assert _key_sets(a) == _key_sets(b), "per-pattern key sets"
