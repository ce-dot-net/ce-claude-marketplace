"""8.2.3: engine/search.js puts `interactive` (bool) and `human_prompt_count` (int >= 0) into the POST /patterns/search
body, each only when the stdin payload carries a valid value (wrong type / negative / non-integer -> dropped, never
defaulted). The core builds the body itself (searchPatterns -> this.request(url, 'POST', body)); the engine's
client.request wrapper adds the fields to that plain object. The Python chain (ace_engine.search_command) never sends them.
"""
import json
import os
import subprocess
import sys

import pytest

import engine_harness as E

sys.path.insert(0, str(E.UTILS))

needs_node = pytest.mark.skipif(E.node_bin() is None, reason="node not installed")


def _search_body(tmp_path, monkeypatch, extra):
    monkeypatch.setenv("ACE_FAKE_CORE_MODE", "raw_old")  # the fake core sends its body through client.request
    log = tmp_path / "core.log"
    monkeypatch.setenv("ACE_FAKE_CORE_LOG", str(log))
    bin_dir = E.make_prefix(tmp_path)
    payload = {"query": "q", "org": "o", "project": "p", **extra}
    p = subprocess.run([E.node_bin(), str(E.ENGINE / "search.js")], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=60, env=dict(os.environ, PATH=E.path_with(bin_dir)))
    assert p.returncode == 0, p.stderr
    raws = [r for r in E.read_jsonl(log) if r.get("op") == "raw" and r["endpoint"].startswith("/patterns/search")]
    assert len(raws) == 1
    return raws[0]["body"]


@needs_node
@pytest.mark.parametrize("extra,want", [
    ({"interactive": False, "human_prompt_count": 0}, {"interactive": False, "human_prompt_count": 0}),  # headless -p
    ({"interactive": True, "human_prompt_count": 3}, {"interactive": True, "human_prompt_count": 3}),
    ({"interactive": False}, {"interactive": False}),
    ({"human_prompt_count": 2}, {"human_prompt_count": 2}),
])
def test_valid_fields_reach_the_request_body(tmp_path, monkeypatch, extra, want):
    body = _search_body(tmp_path, monkeypatch, extra)
    assert {k: body[k] for k in ("interactive", "human_prompt_count") if k in body} == want
    assert body["query"] == "q"  # the core's own fields stay


@needs_node
@pytest.mark.parametrize("extra", [
    {},
    {"interactive": None, "human_prompt_count": None},
    {"interactive": "false", "human_prompt_count": "0"},
    {"interactive": 0, "human_prompt_count": -1},
    {"interactive": 1, "human_prompt_count": 1.5},
    {"human_prompt_count": True},
    {"interactive": [], "human_prompt_count": {}},
])
def test_unknown_or_invalid_fields_are_omitted(tmp_path, monkeypatch, extra):
    body = _search_body(tmp_path, monkeypatch, extra)
    assert "interactive" not in body
    assert "human_prompt_count" not in body


def test_python_chain_never_sends_them():
    import ace_engine
    _, stdin = ace_engine.search_command("q", org="o", project="p", session_id="t", top_k=8, node="/x/node")
    payload = json.loads(stdin)
    assert "interactive" not in payload and "human_prompt_count" not in payload
    with pytest.raises(TypeError):
        ace_engine.search_command("q", node="/x/node", interactive=False)
