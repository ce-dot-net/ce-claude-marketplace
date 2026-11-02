#!/usr/bin/env python3
"""WP-H (v8.0.0 round 2) — C7 self-eval loop contract (DESIGN §10 C7), behavioral.

Stop writes .claude/data/logs/ace-eval-request.json (patterns were injected) -> the next UPS
injects the ACE_REVIEW request into additionalContext and consumes the request file -> Stop
parses `ACE_REVIEW: N` from last_assistant_message into ace-review-result.json (read by the
statusline). Locations stay in <project>/.claude/data/logs. Behavior byte-identical to 7.1.x;
these are regression tests through the real hook entry points (the existing
test_ace_self_eval.py only greps source text).
"""
import json
import subprocess
import sys

import pytest

from test_stop_v8 import Box, WORK, PROJECT_ID, ORG_ID, FAKE_CLI, HOOKS  # noqa: F401

PATTERNS = {"count": 2, "retrieval_id": "ret-c7", "similar_patterns": [
    {"id": "ctx-c7-%d" % i, "domain": "python-hooks", "section": "strategies",
     "content": "pattern %d: keep hooks thin" % i, "confidence": 0.8, "helpful": 3, "harmful": 0,
     "cumulative_v15_reward": 1.0, "isAtRisk": False,
     "match_factors": {"bandit_rank": i + 1, "retrieval_log_id": 500 + i}} for i in range(2)]}

PATTERN_CLI = FAKE_CLI.replace(
    'print(json.dumps({"count": 0, "similar_patterns": []}))',
    "print(json.dumps(%r))" % (PATTERNS,), 1)


@pytest.fixture
def box(tmp_path):
    b = Box(tmp_path)
    cli = b.bin / "ace-cli"
    cli.write_text(PATTERN_CLI.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
    cli.chmod(0o755)
    return b


def _logs(box):
    return box.project / ".claude" / "data" / "logs"


def _ups(box, sid, prompt="refactor the uploader retry policy to use exponential backoff"):
    ev = {"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": prompt,
          "cwd": str(box.project), "transcript_path": str(box.root / "t.jsonl"),
          "permission_mode": "default"}
    p = subprocess.run([sys.executable, str(HOOKS / "ace_before_task.py")], input=json.dumps(ev),
                       capture_output=True, text=True, timeout=60, cwd=str(box.project),
                       env=box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID))
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}


def _stop(box, sid, msg="Done."):
    p = box.run_after_task(box.stop_event(sid, last_assistant_message=msg),
                           ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID)
    assert p.returncode == 0 and p.stdout == "", p.stderr
    return p


def test_stop_writes_eval_request_when_patterns_were_used(box):
    sid = "s-c7-req"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the uploader retry policy", pattern_ids=["ctx-c7-0"])
    _stop(box, sid)
    req = json.loads((_logs(box) / "ace-eval-request.json").read_text())
    assert req["patterns_injected"] == 1 and req["tools_executed"] == 1
    assert req["timestamp"].endswith("Z")


def test_stop_without_patterns_writes_no_eval_request(box):
    sid = "s-c7-none"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the uploader retry policy")
    _stop(box, sid)
    assert not (_logs(box) / "ace-eval-request.json").exists()


def test_ups_injects_ace_review_request_and_consumes_it(box):
    req = _logs(box) / "ace-eval-request.json"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(json.dumps({"patterns_injected": 3, "avg_relevance": 0, "domains": 0,
                               "tools_executed": 5, "success": True,
                               "timestamp": "2026-11-02T00:00:00Z"}))
    out = _ups(box, "s-c7-ups")
    ctx = (out.get("hookSpecificOutput") or {}).get("additionalContext") or ""
    assert "ACE_REVIEW" in ctx and "3 patterns" in ctx, out
    assert len(ctx) <= 10000
    assert not req.exists(), "UPS must consume the eval request"


def test_stop_parses_ace_review_into_result_file(box):
    sid = "s-c7-review"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the uploader retry policy")
    _stop(box, sid, msg="All green.\nACE_REVIEW: 85% | 12m saved | patterns pointed at the retry helper")
    res = json.loads((_logs(box) / "ace-review-result.json").read_text())
    assert res == {"quality_pct": 85, "time_saved": "12m"}


def test_stop_without_ace_review_leaves_result_file_alone(box):
    sid = "s-c7-noreview"
    res = _logs(box) / "ace-review-result.json"
    res.parent.mkdir(parents=True, exist_ok=True)
    res.write_text(json.dumps({"quality_pct": 70, "time_saved": "5m"}))
    box.write_state(sid, user_prompt="implement the uploader retry policy")
    _stop(box, sid, msg="Nothing to review here.")
    assert json.loads(res.read_text())["quality_pct"] == 70


def test_full_round_trip_request_review_result(box):
    """Stop(1) -> request file -> UPS -> ACE_REVIEW ask -> Stop(2) with the answer -> result."""
    sid = "s-c7-rt"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the uploader retry policy", pattern_ids=["ctx-c7-0", "ctx-c7-1"])
    _stop(box, sid)
    assert (_logs(box) / "ace-eval-request.json").exists()
    ctx = (_ups(box, sid).get("hookSpecificOutput") or {}).get("additionalContext") or ""
    assert "ACE_REVIEW" in ctx
    assert not (_logs(box) / "ace-eval-request.json").exists()
    box.seed_tools(sid, WORK)
    _stop(box, sid, msg="Implemented.\nACE_REVIEW: 60% | 4m saved | retry pattern helped")
    assert json.loads((_logs(box) / "ace-review-result.json").read_text())["quality_pct"] == 60
