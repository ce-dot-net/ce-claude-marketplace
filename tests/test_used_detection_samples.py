"""8.2.7 "used" label noise, Python chain: the token check (used_pattern_ids) against a SYNTHETIC fixture (12 invented
projects, fixed seed, no transcript text). Same fixture and same numbers as plugins/ace/mod/tests/used_detection.test.ts."""
import json
from pathlib import Path

from test_stop_v8 import box  # noqa: F401  (puts shared-hooks on sys.path)
from patterns_used_state import tool_haystack, used_pattern_ids  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "mod" / "tests" / "fixtures" / "used_samples.ts"
D = json.loads(FIX.read_text()[len("export default "):])


def _run(s, message, inputs):
    ids = [p[0] for p in s["patterns"]]
    return used_pattern_ids(ids, dict(s["patterns"]), message, tool_haystack(inputs))


def test_negative_cross_project_pairs():
    hits = [(i, j) for i, j in D["pairs"] if _run(D["samples"][i], D["samples"][j]["answer"], D["samples"][j]["inputs"])]
    assert len(D["pairs"]) >= 60
    assert len(hits) <= int(0.02 * len(D["pairs"])), hits


def test_control_own_spans_found():
    ok = [pid for k, pid, spans in D["control"] if pid in _run(D["samples"][k], "Done.", [{"command": " ; ".join(spans)}])]
    assert len(D["control"]) == 12
    assert len(ok) >= 11


def test_real_samples_counts_mod_parity():
    assert [len(_run(s, s["answer"], s["inputs"])) for s in D["samples"]] == [10, 3, 0, 5, 16, 0, 8, 3, 1, 1, 16, 4]


def test_fixtures_stay_synthetic():
    """The fixtures ship to every user (public repo): no home paths, user names, ticket ids, temp dirs; the 8.2.7
    fixture has no mail address at all."""
    banned = ["/Us" + "ers/", "ptsa" + "faridis", "AO" + "P-", "/priv" + "ate/tmp"]  # split: this file must not match a grep for them
    for f in sorted(FIX.parent.iterdir()):
        assert not [b for b in banned if b in f.read_text()], f.name
    assert "@" not in FIX.read_text().replace("noreply@anthropic.com", "")


def test_length_same_overlap_same_result():
    short = "Run `ace-cli doctor --fix` and keep plugins/ace/state.json"
    long = short + " Also mind src/other_module.py, `zz-tool rebuild`, lib/unrelated_util.ts, fooBarBaz, --long-flag and docs/guide_x.md." * 4
    filler = {f"ctx-f{k}": f"Note {k} on topic_{k}/x.md" for k in range(8)}
    ids = ["ctx-1-short", "ctx-2-long", *filler]
    for h in ["", "ace-cli doctor --fix", "cat plugins/ace/state.json", "ace-cli doctor --fix && cat plugins/ace/state.json", "npm test; git status"]:
        r = used_pattern_ids(ids, {"ctx-1-short": short, "ctx-2-long": long, **filler}, "Done.", h)
        assert ("ctx-1-short" in r) == ("ctx-2-long" in r), h


def test_id_literal_is_a_sure_hit():
    ids = ["ctx-1000000001-aaaa", "ctx-1000000002-bbbb"]
    c = {"ctx-1000000001-aaaa": "Run `git status` first", "ctx-1000000002-bbbb": "plain words"}
    assert used_pattern_ids(ids, c, "Applied ctx-1000000002-bbbb.", "") == ["ctx-1000000002-bbbb"]
    assert used_pattern_ids(ids, c, "Done.", tool_haystack([{"command": "echo ctx-1000000001-aaaa"}])) == ["ctx-1000000001-aaaa"]


def test_universal_vocabulary_and_whole_words():
    ids = ["ctx-1", "ctx-2", "ctx-3"]
    c = {"ctx-1": "Check `git diff --stat`, `git status` and `grep -n` before you push",
         "ctx-2": "Call `render_dict` from utils/render_mod.py",
         "ctx-3": "Use `ace-cli search --pin-session` with sessions/pins.json"}
    h = lambda cmd: tool_haystack([{"command": cmd}])  # noqa: E731
    assert used_pattern_ids(ids, c, "Done.", h("git diff --stat; git status; grep -n x y")) == []
    assert used_pattern_ids(ids, c, "Done.", h("render_dictx utils/render_mod.pyc")) == []
    assert used_pattern_ids(ids, c, "Done.", h('python3 -c "render_dict()" utils/render_mod.py')) == ["ctx-2"]
    assert used_pattern_ids(ids, c, "Done.", h("ace-cli search --pin-session abc")) == ["ctx-3"]


# 8.2.7 trace lists (mod parity: used_ids_model_list / used_ids_tokens_list, ids only, <= 50, injected order)
def test_trace_carries_per_source_id_lists(box):
    from test_stop_v8 import ORG_ID, PROJECT_ID, WORK
    a, b = "ctx-1111111111-aaaa", "ctx-2222222222-bbbb"
    sid = "s827-lists"
    box.write_state(sid, user_prompt="refactor the parser module", pattern_ids=[a, b], retrieval_id="ret-1",
                    retrieval_log_ids={a: 7, b: 8}, pattern_contents={a: "x", b: "y"}, render_variant="full")
    box.seed_tools(sid, WORK)
    p = box.run_after_task(box.stop_event(sid, last_assistant_message="applied %s and %s" % (b, a)),
                           ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0, p.stderr
    (learn,) = box.cli_calls("learn")
    t = learn["trace"]
    assert t["used_ids_tokens_list"] == [a, b] and t["used_ids_model_list"] == []  # injected order; no Haiku source
    assert t["applied_log_ids"] == [7, 8]


def test_trace_lists_empty_when_nothing_used(box):
    from test_stop_v8 import ORG_ID, PROJECT_ID, WORK
    a = "ctx-1111111111-aaaa"
    sid = "s827-empty"
    box.write_state(sid, user_prompt="refactor the parser module", pattern_ids=[a], retrieval_id="ret-1",
                    retrieval_log_ids={a: 7}, pattern_contents={a: "x"}, render_variant="full")
    box.seed_tools(sid, WORK)
    assert box.run_after_task(box.stop_event(sid), ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID).returncode == 0
    (learn,) = box.cli_calls("learn")
    assert (learn["trace"]["used_ids_model_list"], learn["trace"]["used_ids_tokens_list"]) == ([], [])
