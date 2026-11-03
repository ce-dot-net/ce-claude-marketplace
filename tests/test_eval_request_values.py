"""Item 1: the self-eval request carries the real relevance and domain count of the task's search
(v7.1.14 ace_stop_wrapper.sh: avg confidence of the injected patterns x 100, distinct domains of the
returned ones), never a hardcoded 0, and the request text never claims 0% when patterns were injected."""
import importlib.util
import json
import sys
from pathlib import Path

from test_ups_machine_prompt_guard import (  # noqa: F401  (fixtures)
    HUMAN_PROMPT, SHARED, _main_state, _run, fake_cli, project)

import patterns_used_state as pus


def test_eval_stats_avg_relevance_of_injected_and_distinct_returned_domains():
    injected = [{"confidence": 0.8}, {"confidence": 0.5}]
    returned = injected + [{"domain": "a"}, {"domain": "b"}, {"domain": "a"}, {"domain": ""}, {}]
    assert pus.eval_stats(injected, returned) == {"avg_relevance": 65, "domains": 2}


def test_eval_stats_non_numbers_are_zero_and_the_percentage_is_clamped():
    assert pus.eval_stats([{"confidence": "x"}, {"confidence": True}, {}], []) == {"avg_relevance": 0, "domains": 0}
    assert pus.eval_stats([{"confidence": 1.5e300}], [{"domain": 7}]) == {"avg_relevance": 100, "domains": 1}
    assert pus.eval_stats([], []) == {"avg_relevance": 0, "domains": 0}


def test_ups_stores_the_eval_stats_in_the_main_state(project, fake_cli, monkeypatch, capsys):
    _run(monkeypatch, capsys, HUMAN_PROMPT, project)  # 3 patterns, confidence 0.8, two domains
    assert _main_state()["eval_stats"] == {"avg_relevance": 80, "domains": 2}


def test_append_keeps_prior_eval_stats_when_none_supplied(tmp_path):
    pus.append_patterns_used("s", None, [], state_dir=tmp_path, task_session_id="t",
                             eval_stats={"avg_relevance": 50, "domains": 3}, reset=True)
    pus.append_patterns_used("s", None, [], state_dir=tmp_path, hook_event_name="PostToolUse")
    st = json.loads((tmp_path / "patterns-used-main.json").read_text())
    assert st["eval_stats"] == {"avg_relevance": 50, "domains": 3}


def _ctx(proj, req):
    (proj / ".claude/data/logs/ace-eval-request.json").write_text(json.dumps(req))
    spec = importlib.util.spec_from_file_location("ace_before_task_evalv", SHARED / "ace_before_task.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check_eval_request_and_review()


def test_eval_text_never_claims_zero_relevance(project):
    ctx = _ctx(project, {"patterns_injected": 5, "avg_relevance": 0, "domains": 0, "tools_executed": 3})
    assert "0% relevance" not in ctx and "0 domains" not in ctx
    assert "used 5 patterns (3 tools)" in ctx


def test_eval_text_with_real_values(project):
    ctx = _ctx(project, {"patterns_injected": 5, "avg_relevance": 80, "domains": 2, "tools_executed": 3})
    assert "used 5 patterns (80% relevance, 2 domains, 3 tools)" in ctx
