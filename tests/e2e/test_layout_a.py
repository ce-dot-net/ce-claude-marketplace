"""Layout (a) render arm: assignment, round trip, budget, TS == Python parity, mutants, goldens.

Layout (a): same envelope as today, body = ONE compact JSON header {"retrieval_id","count","fields"} + ONE line per
pattern (compact JSON array of the values in the fixed field order, missing -> null). Synthetic data only.
"""
import hashlib
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

import mod_reference as R
import ace_pattern_render as A
from ace_pattern_render import render_patterns_dict

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")


def _node_ok():
    try:
        return bool(NODE) and subprocess.run([NODE, "--experimental-strip-types", "-e", "0"], capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False


needs_node = pytest.mark.skipif(not _node_ok(), reason="node >= 22.6 with --experimental-strip-types required")
TAG, ATTRS = "ace-patterns", 'agent-type="main"'
BUDGETS = [700, 1200, 4000, 9500]
CAPS = [2500, 95000]


def _top(resp):  # the pattern that renders first (bandit_rank 1)
    return min((p for p in resp["similar_patterns"] if p["match_factors"].get("bandit_rank") is not None), key=lambda p: p["match_factors"]["bandit_rank"])


# ---------- synthetic corpus: >= 30 lists of different length / field occupancy ----------
def corpus():
    out = []
    sizes = [0, 1, 1, 2, 3, 5, 8, 8, 13, 21, 34, 50, 100, 7, 4, 9, 16, 25]
    for i, n in enumerate(sizes):
        out.append(json.loads(json.dumps(R.load_response(R.make_search_response(n, 100 + i, content_len=40 + 37 * i % 400)))))
    rng = random.Random(7)
    optional = ["root_cause", "error_context", "evidence", "domain", "section", "confidence", "helpful", "harmful",
                "cumulative_v15_reward", "n_hot_pos", "n_hot_neg", "isAtRisk", "content"]
    for j in range(14):  # missing / empty / None fields
        r = R.load_response(R.make_search_response(6 + j, 200 + j, content_len=120))
        for p in r["similar_patterns"]:
            for k in rng.sample(optional, rng.randint(1, 6)):
                if rng.random() < .5:
                    p.pop(k, None)
                else:
                    p[k] = rng.choice([None, "", [], 0])
            if rng.random() < .3:
                p["match_factors"].pop("semantic_score", None)
        if j % 4 == 0:
            r.pop("retrieval_id", None)
        out.append(r)
    big = R.load_response(R.make_search_response(4, 300, content_len=30))  # top-1 alone exceeds any small budget
    _top(big)["content"] = ("é\"\\\n☃ x" * 3000)
    out.append(big)
    uni = R.load_response(R.make_search_response(3, 301, content_len=30))
    _top(uni)["content"] = "emoji \U0001F600 and quote \" and nl\n " * 500
    out.append(uni)
    nest = R.load_response(R.make_search_response(3, 302, content_len=30))  # I1: integer-like nested keys (JS puts them first)
    _top(nest)["evidence"] = [{"10": 1, "2": 2, "a": 3, "b": {"7": 1, "11": 2, "x": 3}}, "plain"]
    out.append(nest)
    return out


LISTS = corpus()
assert len(LISTS) >= 30


def decode(ctx):
    """Layout (a) -> {"head": dict, "patterns": [pattern dict without null fields]}; every line must be valid JSON."""
    lines = ctx.split("\n")
    assert lines[0].startswith("<") and lines[-1].startswith("</")
    body = [ln for ln in lines[1:-1] if ln != A.LAYOUT_A_HINT]
    head = json.loads(body[0])
    assert head["fields"] == A.LAYOUT_A_FIELDS
    pats = []
    for ln in body[1:]:
        vals = json.loads(ln)
        assert isinstance(vals, list) and len(vals) == len(head["fields"])
        pats.append({f: v for f, v in zip(head["fields"], vals) if v is not None})
    return head, pats


def _expected(p):
    return {k: v for k, v in p.items() if v is not None}


# ---------- round trip ----------
@pytest.mark.parametrize("i", range(len(LISTS)))
def test_round_trip_is_lossless(i):
    resp = LISTS[i]
    processed = render_patterns_dict(resp)[0]["similar_patterns"]
    ctx, ids, _, _ = A.render_layout_a_full(resp, tag=TAG, attrs=ATTRS, hint=False)
    head, pats = decode(ctx)
    assert pats == [_expected(p) for p in processed]
    assert head["count"] == len(processed)
    if "retrieval_id" in resp:
        assert head["retrieval_id"] == resp["retrieval_id"]
    else:
        assert "retrieval_id" not in head
    assert list(head)[-2:] == ["count", "fields"]


def test_special_characters_survive():
    ctx = A.render_layout_a(LISTS[-1], tag=TAG, attrs=ATTRS, budget=95000, hint=False)[0]
    _, pats = decode(ctx)
    assert pats[0]["content"] == render_patterns_dict(LISTS[-1])[0]["similar_patterns"][0]["content"]
    assert len(ctx.split("\n")) == 2 + 1 + len(pats)  # newlines inside strings are escaped: one pattern = one line


def test_empty_evidence_and_missing_fields_are_null():
    resp = {"retrieval_id": "r", "similar_patterns": [{"id": "ctx-1-a", "content": "c", "evidence": [], "match_factors": {"bandit_rank": 1}}]}
    ctx = A.render_layout_a(resp, tag=TAG, attrs=ATTRS, hint=False)[0]
    row = json.loads(ctx.split("\n")[2])
    f = A.LAYOUT_A_FIELDS
    assert row[f.index("evidence")] is None and row[f.index("harmful")] is None and row[f.index("content")] == "c"
    assert ",null," in ctx.split("\n")[2]


def test_field_list_is_sorted_and_sixteen():
    assert A.LAYOUT_A_FIELDS == sorted(A.LAYOUT_A_FIELDS) and len(A.LAYOUT_A_FIELDS) == 16
    assert {"bandit_rank", "semantic_score"} <= set(A.LAYOUT_A_FIELDS)


# ---------- budget ----------
def check_budget(render, resp, budget):
    """never over budget, whole patterns, valid JSON per line, shown matches rows, greedy-optimal."""
    ctx = render(resp, budget)
    assert len(ctx) <= budget, (len(ctx), budget)
    head, pats = decode(ctx) if A.LAYOUT_A_FIELDS and ctx.count("\n") >= 2 else (None, [])
    if head is None:
        return ctx, 0
    import re
    shown = int(re.match(r'<[^>]*shown="(\d+)" of="(\d+)"', ctx).group(1))
    assert shown == len(pats)
    allp = render_patterns_dict(resp)[0]["similar_patterns"]
    assert head["count"] == len(allp)
    if shown < len(allp) and shown >= 1 and pats[-1].get("content") == _expected(allp[shown - 1]).get("content"):
        nxt = len(A._la_row(allp[shown])) + 1
        # -2: shown="N" may be shorter than of="M"
        assert len(ctx) + nxt > budget - 2, "not greedy-optimal: the next pattern would still have fit"
    return ctx, shown


def real(resp, budget):
    return A.render_layout_a(resp, tag=TAG, attrs=ATTRS, budget=budget, hint=False)[0]


@pytest.mark.parametrize("budget", [700, 900, 2000, 5000, 9500, 12000])
def test_budget_never_over_and_valid(budget):
    for resp in LISTS:
        if resp["similar_patterns"]:
            check_budget(real, resp, budget)


def test_budget_oversize_top1_is_cut_not_dropped_and_stays_valid():
    ctx = real(LISTS[-2], 2000)
    head, pats = decode(ctx)
    assert len(pats) == 1 and len(ctx) <= 2000 and "evidence" not in pats[0]


def test_hint_costs_budget_and_is_off_by_default(monkeypatch):
    monkeypatch.delenv("ACE_RENDER_LAYOUT_A_HINT", raising=False)
    resp = LISTS[10]
    assert A.LAYOUT_A_HINT not in A.render_layout_a(resp, tag=TAG, attrs=ATTRS)[0]
    monkeypatch.setenv("ACE_RENDER_LAYOUT_A_HINT", "1")
    on = A.render_layout_a(resp, tag=TAG, attrs=ATTRS)[0]
    assert A.LAYOUT_A_HINT in on and len(on) <= 9500
    decode(on)  # the hint line is skipped by the decoder, everything else still valid


def test_budget_more_patterns_than_today_on_the_synthetic_corpus():
    n_today, n_new = [], []
    for resp in LISTS:
        if len(resp["similar_patterns"]) < 6:
            continue
        n_today.append(int(__import__("re").match(r'<[^>]*shown="(\d+)"', A.render_patterns(resp, tag=TAG, attrs=ATTRS)[0]).group(1)))
        n_new.append(int(__import__("re").match(r'<[^>]*shown="(\d+)"', real(resp, 9500)).group(1)))
    assert all(b >= a for a, b in zip(n_today, n_new))
    assert sum(n_new) > sum(n_today)


# ---------- mutants: the checks above must fail on a wrong implementation ----------
def _mutant_budget(sep_cost, valve):
    def f(resp, budget):
        out, _i, _r = render_patterns_dict(resp)
        base = {k: v for k, v in out.items() if k not in ("similar_patterns", "count")}
        total, close = out["count"], "</%s>" % TAG
        avail = budget - len(A._la_assemble(A._la_open(TAG, total, total, ATTRS), A._la_head(base, total), [], close, False))
        picked, chars = [], 0
        for p in out["similar_patterns"]:
            c = len(A._la_row(p)) + sep_cost
            if chars + c > avail:
                break
            picked.append(p)
            chars += c
        while True:
            ctx = A._la_assemble(A._la_open(TAG, len(picked), total, ATTRS), A._la_head(base, total), [A._la_row(p) for p in picked], close, False)
            if not valid_or_fits(ctx, budget, valve) or not picked:
                return ctx
            picked.pop()
    return f


def valid_or_fits(ctx, budget, valve):
    return valve and len(ctx) > budget


def test_budget_mutants_are_red():
    ok = _mutant_budget(1, True)  # the real accounting (sanity: the harness accepts it)
    for resp in LISTS[:20]:
        if resp["similar_patterns"]:
            check_budget(ok, resp, 4000)
    for name, mut in (("separator ', ' assumed (cost+2): under-fills", _mutant_budget(2, True)),
                      ("no newline cost and no valve: overshoots", _mutant_budget(0, False))):
        with pytest.raises(AssertionError):
            for resp in LISTS:
                if resp["similar_patterns"]:
                    for b in BUDGETS:
                        check_budget(mut, resp, b)


def _roundtrip_ok(row_fn, head_fn):
    resp = LISTS[8]
    processed = render_patterns_dict(resp)[0]["similar_patterns"]
    lines = [head_fn()] + [row_fn(p) for p in processed]
    head = json.loads(lines[0])
    got = []
    for ln in lines[1:]:
        vals = json.loads(ln)
        assert len(vals) == len(head["fields"])
        got.append({f: v for f, v in zip(head["fields"], vals) if v is not None})
    assert got == [_expected(p) for p in processed]


def test_mutants_field_order_and_null_are_red(monkeypatch):
    f = A.LAYOUT_A_FIELDS
    head = lambda: A._la_head({}, 8)  # noqa: E731
    _roundtrip_ok(A._la_row, head)  # the real one passes
    with pytest.raises(AssertionError):  # row order swapped against the header
        _roundtrip_ok(lambda p: json.dumps([p.get(k) for k in reversed(f)], separators=(",", ":")), head)
    with pytest.raises(AssertionError):  # null -> omitted: ragged rows
        _roundtrip_ok(lambda p: json.dumps([p.get(k) for k in f if p.get(k) is not None], separators=(",", ":")), head)


# ---------- assignment ----------
def _ids(n, seed=1):
    r = random.Random(seed)
    return [str(__import__("uuid").UUID(int=r.getrandbits(128), version=4)) for _ in range(n)]


def check_assignment(member, full_arm):
    ids = _ids(6000)
    m = [member(s) for s in ids]
    assert member(ids[0]) == member(ids[0])
    assert 0.45 < sum(m) / len(m) < 0.55
    cross = {}
    for s, a in zip(ids, m):
        cross[(full_arm(s) == "full", a)] = cross.get((full_arm(s) == "full", a), 0) + 1
    for k in [(True, True), (True, False), (False, True), (False, False)]:
        assert 0.22 < cross.get(k, 0) / len(ids) < 0.28, (k, cross)


def test_assignment_deterministic_fifty_fifty_and_orthogonal(monkeypatch):
    monkeypatch.setenv("ACE_RENDER_LAYOUT_A_PCT", "50")
    monkeypatch.setenv("ACE_RENDER_FULL_PCT", "50")
    check_assignment(A.layout_a_member, A.render_arm)


def test_assignment_mutant_same_salt_as_render_is_red(monkeypatch):
    monkeypatch.setenv("ACE_RENDER_LAYOUT_A_PCT", "50")
    monkeypatch.setenv("ACE_RENDER_FULL_PCT", "50")
    same_salt = lambda s: int(hashlib.sha256(("render:" + s).encode()).hexdigest()[:8], 16) % 100 < 50  # noqa: E731
    with pytest.raises(AssertionError):
        check_assignment(same_salt, A.render_arm)


def test_assignment_zero_is_off_and_bad_values_are_zero():
    ids = _ids(500)
    assert not any(A.layout_a_member(s, {"ACE_RENDER_LAYOUT_A_PCT": "0"}) for s in ids)
    for bad in ("abc", "-5", "", "1.5"):
        assert not any(A.layout_a_member(s, {"ACE_RENDER_LAYOUT_A_PCT": bad}) for s in ids), bad
    assert all(A.layout_a_member(s, {"ACE_RENDER_LAYOUT_A_PCT": "100"}) for s in ids)
    assert all(A.layout_a_member(s, {"ACE_RENDER_LAYOUT_A_PCT": "250"}) for s in ids)
    assert not A.layout_a_member("", {"ACE_RENDER_LAYOUT_A_PCT": "100"}) and not A.layout_a_member(None, {})


def test_default_is_off_and_the_single_constant(monkeypatch):
    assert A.LAYOUT_A_DEFAULT_PCT == 0
    ids = _ids(3000)
    assert not any(A.layout_a_member(s, {}) for s in ids)
    monkeypatch.setattr(A, "LAYOUT_A_DEFAULT_PCT", 40)  # the one constant drives the default
    share = sum(A.layout_a_member(s, {}) for s in ids) / len(ids)
    assert abs(share - 0.40) < 0.04


# I2: both chains read ACE_RENDER_LAYOUT_A_PCT with the same strict parser (ASCII digits, optional sign, outer whitespace)
PCT_VALUES = ["5_0", " 50 ", "+50", "50.0", "0x10", "", "1e1", "-5", "\uff15\uff10", "50\n", "007", "100", "101", "-0", "5 0"]
PCT_WANT = [0, 50, 50, 0, 0, 0, 0, 0, 0, 50, 7, 100, 100, 0, 0]
PCT_ENVS = [{"ACE_RENDER_LAYOUT_A_PCT": v} for v in PCT_VALUES]


def test_pct_parser_python():
    assert [A.layout_a_pct({"ACE_RENDER_LAYOUT_A_PCT": v}) for v in PCT_VALUES] == PCT_WANT


def test_nested_integer_like_keys_are_sorted_in_rows():
    ctx = A.render_layout_a(LISTS[-1], tag=TAG, attrs=ATTRS, budget=95000, hint=False)[0]
    assert '[{"10":1,"2":2,"a":3,"b":{"11":2,"7":1,"x":3}},"plain"]' in ctx


# ---------- TS == Python ----------
@pytest.fixture(scope="module")
def node_out():
    sids = [""] + _ids(400, 5)
    envs = [{}, *PCT_ENVS, {"ACE_RENDER_LAYOUT_A_PCT": "0"}, {"ACE_RENDER_LAYOUT_A_PCT": "30"}, {"ACE_RENDER_LAYOUT_A_PCT": "100"},
            {"ACE_RENDER_LAYOUT_A_PCT": "bad"}, {"ACE_RENDER_LAYOUT_A_PCT": "-1"}, {"ACE_RENDER_LAYOUT_A_PCT": "999"}]
    job = {"lists": [json.dumps(r) for r in LISTS], "budgets": BUDGETS, "caps": CAPS, "sids": sids, "envs": envs, "vectors": VECTORS, "pcts": PCT_VALUES}
    p = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "--import", str(HERE / "ts_resolve.mjs"), str(HERE / "layout_a_node.mjs")],
                       input=json.dumps(job), capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout), sids, envs


def _pack(t):
    return t[0], t[1], t[3]


@needs_node
def test_ts_python_parity_every_path_byte_identical(node_out):
    out, _, _ = node_out
    assert out["fields"] == A.LAYOUT_A_FIELDS and out["hint"] == A.LAYOUT_A_HINT
    checked = 0
    for resp, row in zip(LISTS, out["lists"]):
        for b, ts in zip(BUDGETS, row["budget"]):
            ctx, ids, _, rl = A.render_layout_a(resp, tag=TAG, attrs=ATTRS, budget=b, hint=False)
            assert (ts["ctx"], ts["ids"], ts["rlog"]) == (ctx, ids, rl); checked += 1
        ctx, ids, _, rl = A.render_layout_a(resp, tag="ace-patterns-subagent", attrs='agent-type="general-purpose"', hint=False)
        ts = row["sub"][0]
        assert (ts["ctx"], ts["ids"], ts["rlog"]) == (ctx, ids, rl); checked += 1
        for c, ts in zip(CAPS, row["full"]):
            ctx, ids, _, rl = A.render_layout_a_full(resp, tag=TAG, attrs=ATTRS, cap=c, hint=False)
            assert (ts["ctx"], ts["ids"], ts["rlog"]) == (ctx, ids, rl); checked += 1
        d = render_patterns_dict(resp)[0]
        ctx = A.render_layout_a_domain_shift(d, 'ace-"cli"&<x>', hint=False)
        assert row["ds"][0]["ctx"] == ctx and row["ds"][0]["ids"] == [p["id"] for p in d["similar_patterns"] if p.get("id") and A.is_valid_pattern_id(p["id"])]; checked += 1
        hb, hf, hd = row["hint"]
        assert hb["ctx"] == A.render_layout_a(resp, tag=TAG, attrs=ATTRS, hint=True)[0]
        assert hf["ctx"] == A.render_layout_a_full(resp, tag=TAG, attrs=ATTRS, hint=True)[0]
        assert hd["ctx"] == A.render_layout_a_domain_shift(render_patterns_dict(resp)[0], "ace-cli", hint=True); checked += 3
    assert checked >= 30 * 8


@needs_node
def test_ts_pct_parser_parity(node_out):
    out, _, _ = node_out
    assert out["pcts"] == PCT_WANT


@needs_node
def test_ts_python_assignment_parity(node_out):
    out, sids, envs = node_out
    for env, ts in zip(envs, out["members"]):
        assert ts == [A.layout_a_member(s, env) for s in sids], env


# ---------- goldens (Python chain) ----------
def test_new_goldens_exist_and_old_ones_are_untouched():
    g = json.loads((R.FIX_JSON / "golden.json").read_text())
    for k in ("layout_a_main_8", "layout_a_full_8", "layout_a_sub_8", "layout_a_domain_shift_8"):
        assert k in g and g[k].startswith("<ace-patterns")
    for k in ("budget_main_8", "full_main_8", "full_sub_8", "domain_shift_8", "full_main_edge"):
        assert g[k].startswith("<ace-patterns") and '"similar_patterns": [{' in g[k]  # today's byte form


# ---------- the server's cohort vectors (tests-fixtures/layout-a/cohort_vectors.json), read by both chains ----------
VECTORS = json.loads((R.PLUGIN / "tests-fixtures" / "layout-a" / "cohort_vectors.json").read_text())


def _arm_env(monkeypatch, cfg):
    monkeypatch.setenv("ACE_AB_CONTROL_PCT", str(cfg["C"]))
    monkeypatch.setenv("ACE_AB_COMPACT_PCT", str(cfg["K"]))
    monkeypatch.setenv("ACE_RENDER_FULL_PCT", str(cfg["F"]))


def test_vectors_python_chain(monkeypatch):
    v = VECTORS
    assert len(v["cases"]) >= 14
    layout_env = {"ACE_RENDER_LAYOUT_A_PCT": str(v["L"])}
    for c in v["cases"]:
        if c["id"]:
            assert int(hashlib.sha256(("render:" + c["id"]).encode()).hexdigest()[:8], 16) % 100 == c["render_bucket"]
            assert int(hashlib.sha256(("layout:" + c["id"]).encode()).hexdigest()[:8], 16) % 100 == c["layout_bucket"]
        _arm_env(monkeypatch, v["configs"]["c0"])
        assert A.render_arm(c["id"]) == c["arm_c0"], c
        _arm_env(monkeypatch, v["configs"]["c10"])
        assert A.render_arm(c["id"]) == c["arm_c10"], c
        assert A.layout_a_applies(c["id"], layout_env) == c["layout_a"], c
    by = {c["id"]: c for c in v["cases"]}
    for cid in ("tv-02", "tv-05"):  # compact / control: the layout bucket says yes, the arm gate says no
        assert A.layout_a_member(cid, {"ACE_RENDER_LAYOUT_A_PCT": "100"}) and not A.layout_a_applies(cid, {"ACE_RENDER_LAYOUT_A_PCT": "100"})
    assert by["tv-02"]["arm_c10"] == "compact" and by["tv-05"]["arm_c10"] == "control"


@needs_node
def test_vectors_ts_chain_equals_the_table(node_out):
    out, _, _ = node_out
    for c, ts in zip(VECTORS["cases"], out["vectors"]):
        assert (ts["arm_c0"], ts["arm_c10"], ts["layout_a"]) == (c["arm_c0"], c["arm_c10"], c["layout_a"]), c


# ---------- source order env > server file (< 7 days) > constant, files, expiry ----------
@pytest.fixture
def pdd(monkeypatch, tmp_path):
    import plugin_data_dir as P
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    monkeypatch.delenv("ACE_RENDER_LAYOUT_A_PCT", raising=False)
    monkeypatch.delenv("ACE_RENDER_FULL_PCT", raising=False)
    return P


def test_server_share_is_stored_in_its_own_file_only(pdd):
    pdd.store_server_switches({"render_layout_a_pct": 40})
    assert json.loads(pdd.render_layout_a_pct_file().read_text())["pct"] == 40
    assert pdd.render_layout_a_pct_file().name == "render-layout-a-pct.json"
    assert not pdd.render_full_pct_file().exists()  # render-full-pct.json is never touched
    pdd.store_server_switches({"render_full_pct": 70})
    assert json.loads(pdd.render_layout_a_pct_file().read_text())["pct"] == 40
    assert json.loads(pdd.render_full_pct_file().read_text())["pct"] == 70


def test_server_share_invalid_values_are_ignored(pdd):
    pdd.store_server_switches({"render_layout_a_pct": 40})
    for bad in (True, False, -1, 101, "5", 5.0, None, [1]):
        pdd.store_server_switches({"render_layout_a_pct": bad})
        assert pdd.stored_render_layout_a_pct() == 40, bad
    pdd.store_server_switches({})  # a missing field keeps it
    assert pdd.stored_render_layout_a_pct() == 40
    pdd.store_server_switches({"render_layout_a_pct": 0})
    assert pdd.stored_render_layout_a_pct() == 0


def test_source_order_env_then_file_then_constant(pdd, monkeypatch):
    assert A.layout_a_pct() == A.LAYOUT_A_DEFAULT_PCT == 0
    pdd.store_server_switches({"render_layout_a_pct": 100})
    assert A.layout_a_pct() == 100
    ids = _ids(200)
    assert all(A.layout_a_member(s) for s in ids)
    monkeypatch.setenv("ACE_RENDER_LAYOUT_A_PCT", "0")
    assert A.layout_a_pct() == 0 and not any(A.layout_a_member(s) for s in ids)
    monkeypatch.setenv("ACE_RENDER_LAYOUT_A_PCT", "bad")
    assert A.layout_a_pct() == 0
    monkeypatch.delenv("ACE_RENDER_LAYOUT_A_PCT")
    pdd.store_server_switches({"render_layout_a_pct": 0})
    monkeypatch.setenv("ACE_RENDER_LAYOUT_A_PCT", "100")
    assert A.layout_a_pct() == 100


def test_stored_share_expires_after_seven_days(pdd):
    import time
    f = pdd.render_layout_a_pct_file()
    f.parent.mkdir(parents=True, exist_ok=True)  # alone, no earlier test has created the data dir
    f.write_text(json.dumps({"pct": 100, "at": int(time.time()) - 6 * 86400}))
    assert pdd.stored_render_layout_a_pct() == 100
    f.write_text(json.dumps({"pct": 100, "at": int(time.time()) - 8 * 86400}))
    assert pdd.stored_render_layout_a_pct() is None and A.layout_a_pct() == 0
    for junk in ("x", "[]", '{"pct": 200, "at": 1}', '{"pct": 5}'):
        f.write_text(junk)
        assert pdd.stored_render_layout_a_pct() is None
