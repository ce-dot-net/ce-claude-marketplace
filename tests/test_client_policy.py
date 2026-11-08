"""8.1.4 client_policy (DORMANT until the server sends it; DESIGN "Trace delivery" / "client_policy").

A search response MAY carry a top-level object `client_policy` {min_plugin_version, recommended_plugin_version, message,
url} (all optional strings; versions x.y.z; url https only; bounded, no control characters). It is stored like
render_full_pct (7 days, atomic, private); an invalid one is dropped and logged. Below recommended: one doctor line.
Below min: one line (band / SessionStart message) "ACE <version> ist zu alt, bitte /plugin update ausführen". ACE never
turns itself off and keeps learning. Cases: tests-fixtures/client-policy/cases.json (shared with the mod suite).
"""
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "ace"
FIX = PLUGIN / "tests-fixtures" / "client-policy" / "cases.json"
TS = PLUGIN / "mod" / "tests" / "fixtures" / "client_policy_cases.ts"
sys.path.insert(0, str(PLUGIN / "shared-hooks" / "utils"))
CASES = json.loads(FIX.read_text())
import engine_harness as E  # noqa: E402


@pytest.fixture
def pdd(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "ace-pd"))
    monkeypatch.chdir(tmp_path)
    import plugin_data_dir
    importlib.reload(plugin_data_dir)
    import ace_relevance_logger
    ace_relevance_logger._logger = None
    return plugin_data_dir


def test_ts_wrapper_matches_the_shared_fixture():
    text = TS.read_text()
    assert json.loads(text[text.index("= ") + 2:].strip()) == CASES


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_cases(pdd, case, tmp_path):
    now = time.time()
    resp = {"similar_patterns": []}
    if "policy" in case:
        resp["client_policy"] = case["policy"]
    pdd.store_server_switches(resp)
    f = pdd.client_policy_file()
    if case["expect_valid"] is None or case["expect_valid"] is False:
        assert not f.exists()
    else:
        d = json.loads(f.read_text())
        assert d["policy"] == {k: v for k, v in case["policy"].items() if k in pdd.CLIENT_POLICY_KEYS}
        d["at"] = now - case["age_days"] * 86400
        f.write_text(json.dumps(d))
    assert pdd.client_policy_state(case["version"], now=now) == case["expect_state"]
    rows = E.read_jsonl(tmp_path / ".claude" / "data" / "logs" / "ace-relevance.jsonl")
    bad = [r for r in rows if r.get("event") == "client_policy_invalid"]
    assert len(bad) == (1 if case["expect_valid"] is False else 0)
    if bad:
        assert len(json.dumps(bad[0])) < 400, "the row names the reason, never the value"


def test_an_invalid_policy_keeps_the_stored_one(pdd):
    pdd.store_server_switches({"client_policy": {"min_plugin_version": "9.0.0"}})
    pdd.store_server_switches({"client_policy": {"url": "javascript:x"}})
    assert pdd.client_policy_state("8.1.4") == "min"


def test_doctor_and_band_lines(pdd):
    pdd.store_server_switches({"client_policy": {"recommended_plugin_version": "8.2.0", "message": "fixes trace loss",
                                                 "url": "https://example.com/r"}})
    assert pdd.client_policy_line("8.1.4") == "update   ACE 8.1.4 · empfohlen 8.2.0: fixes trace loss · https://example.com/r"
    assert pdd.client_policy_band("8.1.4") is None
    pdd.store_server_switches({"client_policy": {"min_plugin_version": "8.1.5"}})
    assert pdd.client_policy_band("8.1.4") == "ACE 8.1.4 ist zu alt, bitte /plugin update ausführen"
    assert pdd.client_policy_line("8.1.4") == "update   ACE 8.1.4 ist zu alt (min 8.1.5), bitte /plugin update ausführen"
    pdd.store_server_switches({"client_policy": {}})
    assert pdd.client_policy_line("8.1.4") is None and pdd.client_policy_band("8.1.4") is None


def test_session_start_says_it_once_and_ace_stays_on(tmp_path):
    """Python chain (no band): the sync SessionStart row prints the min line; no disabled flag, no install, no reload."""
    pd = tmp_path / "ace-pd"
    pd.mkdir()
    (pd / "client-policy.json").write_text(json.dumps({"policy": {"min_plugin_version": "99.0.0"}, "at": time.time()}))
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text(json.dumps({"env": {"ACE_PROJECT_ID": "prj_p", "ACE_ORG_ID": "org_o"}}))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ACE_", "CLAUDE_"))}
    env.update(HOME=str(tmp_path), CLAUDE_PLUGIN_DATA=str(pd), ACE_AUTO_INSTALL="0", ACE_PROJECT_ID="prj_p")
    ev = {"session_id": "s1", "cwd": str(proj), "hook_event_name": "SessionStart", "source": "startup"}
    p = subprocess.run([sys.executable, str(PLUGIN / "shared-hooks" / "ace_install_cli.py")], input=json.dumps(ev),
                       capture_output=True, text=True, timeout=60, cwd=str(proj), env=env)
    assert p.returncode == 0, p.stderr
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
    assert "ACE %s ist zu alt, bitte /plugin update ausführen" % version in json.loads(p.stdout)["systemMessage"]
    assert not list(pd.rglob("disabled.flag"))


@pytest.mark.skipif(E.node_bin() is None, reason="node not installed")
def test_engine_search_passes_client_policy_through(tmp_path, monkeypatch):
    """engine/search.js captures client_policy from the raw /patterns/search body (like render_full_pct)."""
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "raw_old")
    monkeypatch.setenv("ACE_FAKE_CORE_LOG", str(tmp_path / "core.log"))
    bin_dir = E.make_prefix(tmp_path)
    p = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input=json.dumps({"query": "q", "org": "o", "project": "p"}),
                       capture_output=True, text=True, timeout=60, env=dict(os.environ, PATH=E.path_with(bin_dir)))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.strip().splitlines()[-1])["client_policy"] == {"min_plugin_version": "8.1.0"}
