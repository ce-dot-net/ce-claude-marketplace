"""8.4.0: a 403 / error code no_access is NOT a login problem (the server answers it for a transient project-check timeout):
requeue as 'forbidden' with the normal BACKOFF, at most FORBIDDEN_MAX_ATTEMPTS tries, then dead/ with last_error 'no_access'.
401 / token_expired / not_logged_in stay immediately ('dead','auth'); the 'nicht angemeldet' notice and the re-queue script follow.
"""
import json
import os
import sys
from pathlib import Path

import pytest

U = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "shared-hooks" / "utils"
sys.path.insert(0, str(U))
import ace_trace_queue as Q  # noqa: E402

T0 = 1_800_000_000.0
META = {"org": "o", "project": "p", "retrieval_id": "r", "hook": "Stop", "agent_type": "main"}
RESP403 = 'ace_trace_response {"status":403,"path":"/traces","detail":"Project not accessible with this token and organization"}'
RESP401 = 'ace_trace_response {"status":401,"path":"/traces","detail":"Invalid user token"}'
CLI403 = '{"error":{"code":"no_access","status":403,"message":"x"}}'
QID = "%032x" % 7


@pytest.fixture
def qdir(tmp_path, monkeypatch):
    monkeypatch.delenv("ACE_TRACE_QUEUE", raising=False)
    return tmp_path / "trace-queue"


def dead_entry(qdir):
    d = qdir / "dead"
    fs = list(d.glob("*.json")) if d.is_dir() else []
    return json.loads(fs[0].read_text()) if fs else None


def test_constant():
    assert Q.FORBIDDEN_MAX_ATTEMPTS == 3


@pytest.mark.parametrize("code,out,keyed", [(1, RESP403, True), (1, RESP403, False), (1, CLI403, True), (1, CLI403, False)])
def test_403_and_no_access_requeue_as_forbidden(code, out, keyed):
    assert Q.classify(code, out, keyed=keyed) == ("requeue", "forbidden")


@pytest.mark.parametrize("code,out", [(1, RESP401),
                                      (4, '{"error":{"code":"token_expired","status":401,"message":"e"}}'),
                                      (3, '{"error":{"code":"not_logged_in","status":null,"message":"n"}}')])
def test_401_and_login_codes_stay_dead_auth(code, out):
    assert Q.classify(code, out, keyed=False) == ("dead", "auth")


def test_no_access_is_no_immediate_dead_code():
    assert "no_access" not in Q._AUTH_CODES and "no_access" not in Q._REJECT_CODES


def test_first_send_403_is_queued_with_normal_backoff(qdir):
    rows = Q.settle(qdir, QID, {"task": "t"}, META, 1, RESP403, now=T0)
    assert rows[0]["event"] == "learn_requeued" and rows[0]["error_class"] == "forbidden"
    e = json.loads((qdir / (QID + ".json")).read_text())
    assert e["last_error"] == "forbidden" and e["attempts"] == 1 and e["next_at"] == T0 + Q.BACKOFF[0]
    assert dead_entry(qdir) is None


def test_third_failed_attempt_goes_dead_as_no_access(qdir):
    Q.settle(qdir, QID, {"task": "t"}, META, 1, RESP403, now=T0)  # attempt 1
    now = T0
    for attempt in (2, 3):
        now += 10 * 3600
        rows = Q.replay(qdir, lambda e: (1, RESP403, True), now=now)
        assert len(rows) == 1
        if attempt == 2:
            assert rows[0]["event"] == "learn_requeued"
            assert dead_entry(qdir) is None
    assert rows[0]["event"] == "learn_lost" and rows[0]["error_class"] == "no_access"
    d = dead_entry(qdir)
    assert d["last_error"] == "no_access" and d["attempts"] == 3
    assert not (qdir / (QID + ".json")).exists()


def test_forbidden_then_success_is_sent(qdir):
    Q.settle(qdir, QID, {"task": "t"}, META, 1, RESP403, now=T0)
    rows = Q.replay(qdir, lambda e: (0, "{}", True), now=T0 + 3600)
    assert rows[0]["event"] == "learn_replayed" and dead_entry(qdir) is None


def test_401_on_replay_is_dead_auth(qdir):
    Q.settle(qdir, QID, {"task": "t"}, META, 1, RESP403, now=T0)
    Q.replay(qdir, lambda e: (1, RESP401, True), now=T0 + 3600)
    assert dead_entry(qdir)["last_error"] == "auth"


def test_auth_held_counts_only_auth_not_no_access(tmp_path):
    from test_auth_held_notice import put_dead, NOW
    put_dead(tmp_path, 1, err="no_access")
    put_dead(tmp_path, 2, err="no_access")
    assert Q.auth_held_count(tmp_path, NOW) == 0
    put_dead(tmp_path, 3, err="auth")
    assert Q.auth_held_count(tmp_path, NOW) == 1


@pytest.mark.parametrize("status,want", [(401, ("dead", "auth")), (403, ("requeue", "forbidden"))])
def test_cli_error_status_without_a_known_code(status, want):
    out = '{"error":{"code":"generic","status":%d,"message":"x"}}' % status
    assert Q.classify(1, out, keyed=True) == want
