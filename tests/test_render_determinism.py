#!/usr/bin/env python3
"""The Python render chain must emit the same bytes in every process (PYTHONHASHSEED must not matter).

_KEEP_FIELDS was a frozenset iterated to build each pattern dict, so key order followed the hash seed.
Per-pattern keys are now SORTED: the byte form of the mod (pyDumps(p, true)) and of the committed goldens.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "plugins" / "ace" / "shared-hooks"

CHILD = r"""
import json, sys
sys.path[:0] = [%(utils)r, %(shared)r, %(pu)r]
from ace_pattern_render import render_patterns, render_compact_all, render_patterns_dict
import ace_domain_shift as ds
pats = []
for i in range(8):
    pats.append({
        "id": "a799d7ed-b5d0-5287-8c19-33645cc1%%04d" %% i, "domain": "d%%d" %% (i %% 3), "content": "c %%d é" %% i,
        "section": "apis_to_use", "evidence": [{"b": 1, "10": 2, "2": 3, "a": {"z": 1, "y": [{"q": 1, "p": 2}]}}, {"\u00fc": 1, "\U0001F600": 2, "a": 3, "Z": 4}], "root_cause": "rc", "error_context": "ec",
        "cumulative_v15_reward": -0.5 * i, "n_hot_pos": i, "n_hot_neg": 0, "isAtRisk": i %% 2 == 0,
        "confidence": 0.5, "helpful": 1.5, "harmful": 0.0, "junk": 1, "tier": "x",
        "match_factors": {"bandit_rank": 8 - i, "semantic_score": 0.5 + i / 100.0, "retrieval_log_id": 100 + i}})
resp = {"retrieval_id": "r", "similar_patterns": pats, "count": 8, "domains_summary": {"a": 1}}
out = []
for tag, attrs in (("ace-patterns", 'agent-type="main"'), ("ace-patterns-subagent", 'agent-type="general-purpose"')):
    out.append(render_patterns(resp, tag=tag, attrs=attrs))
out.append(render_compact_all(resp, tag="ace-patterns", attrs='agent-type="main"'))
d, ids, rlog = render_patterns_dict(resp)
out.append([json.dumps(d), ids, rlog])
d2 = render_patterns_dict(resp)[0]
out.append(ds._context("ace-cli", d2))
print(json.dumps(out))
""" % {"utils": str(SHARED / "utils"), "shared": str(SHARED), "pu": str(REPO / "plugins" / "ace" / "utils")}


def _run(seed):
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    r = subprocess.run([sys.executable, "-c", CHILD], env=env, capture_output=True, text=True, check=True)
    return r.stdout


def test_all_render_paths_are_byte_identical_across_hash_seeds():
    outs = {s: _run(s) for s in (0, 1, 12345)}
    assert len(set(outs.values())) == 1, "render output depends on PYTHONHASHSEED"


def test_pattern_keys_are_sorted():
    out = json.loads(_run(1))
    first = json.loads(out[3][0])["similar_patterns"][0]
    assert list(first) == sorted(first)


def test_nested_dicts_are_sorted_deep_lists_keep_order():
    out = json.loads(_run(1))
    ev = json.loads(out[3][0])["similar_patterns"][0]["evidence"]
    assert list(ev[0]) == ["10", "2", "a", "b"]
    assert list(ev[0]["a"]) == ["y", "z"] and list(ev[0]["a"]["y"][0]) == ["p", "q"]
    assert list(ev[1]) == sorted(ev[1]) and len(ev) == 2  # umlaut + emoji keys; list order kept (cap 2)
