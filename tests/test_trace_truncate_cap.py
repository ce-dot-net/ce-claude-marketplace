"""Full steps (Python chain): trace_truncate keeps everything under ONE hard byte cap, as the mod's capTrace (mod/lib/trace.ts).

No 10 KB per tool_response, no 'last 50 steps', no 2 MiB cut. Over ACE_TRACE_HARD_CAP_BYTES (default 4 MiB, json.dumps bytes =
mod pyDumps): longest payloads (tool_response / tool_input) -> '<truncated: N bytes>', then the oldest steps that did not fail;
a _truncation_marker with counters and metadata.trace_truncated ONLY when the cap bites.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins", "ace", "shared-hooks"))
from utils import trace_truncate as tt  # noqa: E402


def _trace(steps, task="User request: fix it", summary="done"):
    return {"task": task, "trajectory": steps, "result": {"success": True, "summary": summary}, "playbook_used": []}


def _step(i, result="Success", **kw):
    return dict({"step": i + 1, "tool": "Bash", "action": "echo :: echo %d" % i, "result": result}, **kw)


def test_defaults_match_the_mod():
    assert tt.TRACE_HARD_CAP_BYTES == 4 * 1024 * 1024
    assert tt.TEXT_HARD_CAP_CHARS == 200_000


def test_under_the_cap_nothing_changes_80_steps_no_marker_no_metadata():
    t = _trace([_step(i) for i in range(80)])
    before = json.dumps(t)
    out, hit = tt.cap_trace(t)
    assert hit is None and json.dumps(out) == before
    assert "metadata" not in out and not any(s.get("_truncation_marker") for s in out["trajectory"])


def test_under_the_cap_a_50kb_tool_response_and_a_base64_blob_stay_whole():
    blob = "QUJD" * 5000
    t = _trace([_step(0, tool_response="x" * 50_000), _step(1, tool_response=blob), _step(2, tool_response={"stdout": "y" * 20_000})])
    out, hit = tt.cap_trace(t)
    assert hit is None
    assert [s["tool_response"] for s in out["trajectory"]][:2] == ["x" * 50_000, blob]
    assert out["trajectory"][2]["tool_response"]["stdout"] == "y" * 20_000


def test_over_the_cap_longest_payloads_first_marker_counters_size_under_cap(monkeypatch):
    monkeypatch.setenv("ACE_TRACE_HARD_CAP_BYTES", "25000")
    sizes = [1000, 50_000, 9000, 30_000]
    t = _trace([_step(i, tool_response="z" * n) for i, n in enumerate(sizes)])
    out, hit = tt.cap_trace(t)
    st = [s for s in out["trajectory"] if not s.get("_truncation_marker")]
    assert [s["tool_response"] if s["tool_response"].startswith("<") else "full" for s in st] == \
        ["full", "<truncated: 50002 bytes>", "full", "<truncated: 30002 bytes>"]
    m = out["trajectory"][0]
    assert (m["_truncation_marker"], m["original_length"], m["kept"], m["outputs_truncated"], m["steps_dropped"]) == (True, 4, 4, 2, 0)
    assert out["metadata"]["trace_truncated"] is True
    assert len(json.dumps(out)) <= 25000
    assert hit["steps"] == 4 and hit["bytes_after"] == len(json.dumps(out)) and hit["bytes_before"] > 90_000


def test_then_oldest_non_failed_steps_go_failed_steps_always_stay(monkeypatch):
    monkeypatch.setenv("ACE_TRACE_HARD_CAP_BYTES", "8000")
    steps = [_step(0, result="Error: build failed")] + [_step(i, action="echo :: " + "p" * 400) for i in range(1, 41)]
    out, hit = tt.cap_trace(_trace(steps))
    m = out["trajectory"][0]
    assert m["steps_dropped"] > 0 and m["kept"] == 41 - m["steps_dropped"]
    assert m["kept_indices"][0] == 0
    assert out["trajectory"][1]["result"] == "Error: build failed"
    assert out["trajectory"][-1]["step"] == 41
    assert len(json.dumps(out)) <= 8000 and hit is not None


@pytest.mark.parametrize("raw,want", [(None, 4 * 1024 * 1024), ("junk", 4 * 1024 * 1024), ("-1", 4 * 1024 * 1024), ("8388608", 5 * 1024 * 1024 - 256 * 1024), ("1000000", 1000000)])  # round 8 I3: clamped below MAX_FILE
def test_hard_cap_env_parsing(monkeypatch, raw, want):
    if raw is None:
        monkeypatch.delenv("ACE_TRACE_HARD_CAP_BYTES", raising=False)
    else:
        monkeypatch.setenv("ACE_TRACE_HARD_CAP_BYTES", raw)
    assert tt.hard_cap_bytes() == want


def test_text_cap_marks_task_and_summary_like_the_mod(monkeypatch):
    monkeypatch.setenv("ACE_TEXT_HARD_CAP_CHARS", "5000")
    out, hit = tt.cap_trace(_trace([_step(0)], task="User request: " + "w" * 7000, summary="s" * 8000))
    assert out["task"] == "User request: " + "w" * 5000 + "<truncated: 7000 chars>"
    assert out["result"]["summary"] == "s" * 5000 + "<truncated: 8000 chars>"
    assert hit is None  # the byte cap did not bite: no marker, no metadata
    assert "metadata" not in out


def test_truncate_trace_wrapper_returns_the_trace():
    t = _trace([_step(i) for i in range(60)])
    assert tt.truncate_trace(t) is t and len(t["trajectory"]) == 60


def test_text_cap_is_idempotent_on_an_already_capped_text(monkeypatch):
    monkeypatch.setenv("ACE_TEXT_HARD_CAP_CHARS", "5000")
    capped = "s" * 5000 + "<truncated: 8000 chars>"
    out, _ = tt.cap_trace(_trace([_step(0)], summary=capped))
    assert out["result"]["summary"] == capped
