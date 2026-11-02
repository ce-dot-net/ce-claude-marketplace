"""Renderer parity harness: the mod's TypeScript renderer (plugins/ace/mod/core.ts) vs the Python
chain (ace_pattern_render), per-pattern bytes of the sorted-key dump (DESIGN §13.1, §9 G9).

Runs on the committed synthetic fixtures (tests/e2e/fixtures/mod) and, when present, on the m1
prototype's real search captures (/tmp/ace-v8-dry/m1-mod-full-chain/fixtures, override with
ACE_MOD_M1_FIXTURES; never committed: real server data). Skips when node is missing.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import mod_reference as R
from ace_pattern_render import (normalize_render_variant, render_arm, render_cohort, render_compact_all, render_patterns,
                                render_patterns_dict)
from patterns_used_state import used_pattern_ids

NODE = shutil.which("node")
def _strip_types_ok(node):
    """The mod is TypeScript; these tests run it with node --experimental-strip-types (node >= 22.6).
    Users never need this (Claude Code runs the mod itself); only the test harness does."""
    if not node:
        return False
    try:
        return subprocess.run([node, "--experimental-strip-types", "-e", "0"], capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _strip_types_ok(NODE), reason="node >= 22.6 with --experimental-strip-types required")
HERE = Path(__file__).resolve().parent
M1 = Path(os.environ.get("ACE_MOD_M1_FIXTURES", "/tmp/ace-v8-dry/m1-mod-full-chain/fixtures"))
FIXTURES = sorted(str(p) for p in R.FIX_JSON.glob("search_*.json")) + \
    (sorted(str(p) for p in M1.glob("search-*.json")) if M1.is_dir() else [])
SIDS = ["", "sess-1"] + [R._uuid(__import__("random").Random(i)) for i in range(300)]
ENVS = [{}, {"ACE_AB_CONTROL_PCT": "50"}, {"ACE_AB_CONTROL_PCT": "20", "ACE_AB_COMPACT_PCT": "30"},
        {"ACE_AB_CONTROL_PCT": "20", "ACE_AB_COMPACT_PCT": "30", "ACE_RENDER_FULL_PCT": "0"},
        {"ACE_RENDER_FULL_PCT": "40"}, {"ACE_RENDER_FULL_PCT": "bad"}, {"ACE_AB_CONTROL_PCT": "70", "ACE_AB_COMPACT_PCT": "40"},
        {"ACE_AB_CONTROL_PCT": "-1"}, {"ACE_AB_COMPACT_PCT": "100"}]
_C = "Refuse a planted symlink in the rotation chain before moving the relevance log — naïve café ☃ résumé."
_UC = json.loads((R.MOD / "tests" / "fixtures" / "used_cases.ts").read_text()[len("export default "):])
USED = [[c["ids"], c["contents"], c["message"], c["tool_inputs"]] for c in _UC]  # item H2 shared fixture
VARIANTS = ["full", " Budget\n", "FULL", "control", "compact", "", "fullish"]
ROOTS = [["/h", "/h/.claude/plugins/cache/ce-dot-net-marketplace/ace/8.0.0", "ace"],
         ["/h", "/repo/plugins/ace", "ace"]]


@pytest.fixture(scope="module")
def node_out():
    job = {"fixtures": FIXTURES, "sids": SIDS, "envs": ENVS, "roots": ROOTS, "learnJob": None, "used": USED,
           "variants": VARIANTS}
    p = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", str(HERE / "mod_parity_node.mjs")],
                       input=json.dumps(job), capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, "mod renderer did not run (plugins/ace/mod/core.ts):\n" + p.stderr[-2000:]
    return json.loads(p.stdout)


def _resp(path):
    return R.load_response(Path(path).read_text())


def test_fixture_set_is_not_empty():
    assert len(FIXTURES) >= 4


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: Path(p).name)
def test_per_pattern_bytes_match_python_sorted_dump(node_out, path):
    d, ids, rlog = render_patterns_dict(_resp(path))
    got = node_out["fixtures"][path]
    want = [json.dumps(p, sort_keys=True) for p in d["similar_patterns"]]
    assert len(got["patterns_sorted_bytes"]) == len(want)
    for i, (a, b) in enumerate(zip(want, got["patterns_sorted_bytes"])):
        assert a == b, "pattern %d differs:\npy:  %s\nmod: %s" % (i, a[:400], b[:400])
    assert got["top_keys"] == list(d.keys())
    assert got["top_rest_bytes"] == {k: json.dumps(v) for k, v in d.items() if k != "similar_patterns"}
    assert got["ids"] == ids
    assert got["rlog_entries"] == [list(x) for x in rlog.items()]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: Path(p).name)
def test_full_render_and_100k_guard_match_reference(node_out, path):
    resp = _resp(path)
    got = node_out["fixtures"][path]
    ctx, ids, _rl, _n, _t = R.render_full(resp, "ace-patterns", 'agent-type="main"')
    assert len(got["full"]) <= R.FULL_CAP
    assert got["full"] == ctx
    assert got["full_ids"] == ids
    assert got["state_render"] == R.render_full(resp, "ace-patterns", 'agent-type="main"', cap=R.STATE_RENDER_CAP)[0]


def test_oversized_fixture_exercises_the_guard(node_out):
    path = str(R.FIX_JSON / "search_120_big.json")
    ctx = node_out["fixtures"][path]["full"]
    assert 'of="120"' in ctx.split("\n", 1)[0] and 'shown="120"' not in ctx.split("\n", 1)[0]
    assert len(ctx) <= R.FULL_CAP


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: Path(p).name)
def test_budget_arm_matches_render_patterns(node_out, path):
    ctx, ids, _r, rlog = render_patterns(_resp(path), tag="ace-patterns", attrs='agent-type="main"')
    got = node_out["fixtures"][path]["budget"]
    assert got["context"].split("\n", 1)[0] == ctx.split("\n", 1)[0]
    assert len(got["context"]) == len(ctx) <= 9500
    body = lambda s: json.loads(s[s.index("\n") + 1:s.rindex("\n")])  # noqa: E731
    assert body(got["context"]) == body(ctx)
    assert got["ids"] == ids
    assert got["rlog"] == rlog


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: Path(p).name)
def test_compact_arm_matches_render_compact_all(node_out, path):
    ctx, ids, _r, rlog = render_compact_all(_resp(path), tag="ace-patterns", attrs='agent-type="main"')
    got = node_out["fixtures"][path]["compact"]
    assert got["context"] == ctx
    assert got["ids"] == ids
    assert got["rlog"] == rlog


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: Path(p).name)
def test_domain_shift_render_matches_reference(node_out, path):
    assert node_out["fixtures"][path]["domain_shift"] == R.render_domain_shift(_resp(path), "ace-cli")


def test_render_cohort_salted_bucket_and_knobs(node_out, monkeypatch):
    for env, got in zip(ENVS, node_out["cohorts"]):
        assert got == [R.mod_render_cohort(s, env) for s in SIDS], env
        if env.get("ACE_RENDER_FULL_PCT") == "0":  # full arm off -> exactly the Python chain's cohorts
            for k in ("ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT"):
                monkeypatch.setenv(k, env.get(k, "0"))
            assert got[1:] == [render_cohort(s) for s in SIDS[1:]]
    assert set(node_out["cohorts"][0]) <= {"budget", "full"}  # §31 default (8.0.0): 50/50 budget/full, no control/compact


def test_render_arm_python_ts_parity(node_out, monkeypatch):
    """§28: the production Python render_arm and the mod's renderCohort are ONE function (same salt, knobs, order).
    render_cohort is the Python chain's rendered variant: the full arm renders as budget."""
    for env, got in zip(ENVS, node_out["cohorts"]):
        for k in ("ACE_AB_CONTROL_PCT", "ACE_AB_COMPACT_PCT", "ACE_RENDER_FULL_PCT"):
            monkeypatch.delenv(k, raising=False)
            if k in env:
                monkeypatch.setenv(k, env[k])
        assert got == [render_arm(s or None) for s in SIDS], env
        assert [render_cohort(s or None) for s in SIDS] == ["budget" if a == "full" else a for a in got], env


def test_used_pattern_ids_python_ts_parity(node_out):
    from patterns_used_state import tool_haystack
    assert node_out["used"] == [used_pattern_ids(i, c, m, tool_haystack(t)) for i, c, m, t in USED]
    assert node_out["used"] == [c["expected"] for c in _UC]


def test_normalize_variant_python_ts_parity(node_out):
    assert node_out["normalized"] == [normalize_render_variant(v) for v in VARIANTS] == \
        ["full", "budget", "full", None, None, None, None]


def test_data_root_derives_from_plugin_root(node_out):
    assert node_out["roots"] == ["/h/.claude/plugins/data/ace-ce-dot-net-marketplace",
                                 "/h/.claude/plugins/data/ace-inline"]
