"""8.4.3: trace.followup (server-side follow-up judging, locked contract v1) survives the trace queue (settle -> requeue -> replay)
byte for byte; the queue never inspects or rewrites it."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "ace" / "shared-hooks" / "utils"))
import ace_trace_queue as Q  # noqa: E402

T0 = 1_800_000_000.0
DEAD_502 = '{"event":"ace_trace_dead_letter","attempts":4,"status":502,"error":"Server error (502)","timestamp":"x"}'
META = {"org": "org_t", "project": "prj_t", "retrieval_id": None, "applied_log_ids": [], "hook": "Stop", "agent_type": "main"}
FOLLOWUP = {"text": "das ist falsch, mach das anders … \U0001F600", "target_retrieval_id": "00000000-0000-4000-8000-000000000001",
            "applied_log_ids": [7, 8], "ts": "2027-01-15T08:00:00.000Z"}


def test_followup_round_trips_through_the_queue(tmp_path, monkeypatch):
    monkeypatch.delenv("ACE_TRACE_QUEUE", raising=False)
    qdir = tmp_path / "data" / "trace-queue"
    trace = {"task": "t", "trajectory": [], "result": {"success": True}, "playbook_used": [], "timestamp": "x",
             "applied_log_ids": [], "followup": dict(FOLLOWUP)}
    qid = "%032x" % 1
    assert Q.settle(qdir, qid, trace, META, 1, DEAD_502, now=T0)[0]["event"] == "learn_requeued"
    got = []
    Q.replay(qdir, lambda e: (got.append(e), (0, "{}"))[1], now=T0 + 61)
    assert json.dumps(got[0]["trace"]["followup"]) == json.dumps(FOLLOWUP)
