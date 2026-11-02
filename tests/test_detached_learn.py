#!/usr/bin/env python3
"""WP-H (v8.0.0 round 2) — detached learn (DESIGN §11 A3) + state-read window (§10 S9).

A3: the async Stop/SubagentStop hook does the cheap part, hands the learn to a DETACHED child
(start_new_session, DEVNULL stdio, job file under the plugin-data session dir, no /tmp) and
exits 0 with NO stdout; `claude -p` teardown kills async hooks (cc_hooks_reference.md:4084-4087)
but not the detached child. Test: fake learn sleeps 2 s -> hook returns < 0.5 s; learn present
after ~3 s; lock removed.
S9: async learners read everything at start; SessionEnd keeps the session dir while a
learn-inflight lock < 10 min exists. The lock must therefore be held BEFORE the hook reads the
session state (else a SessionEnd in between deletes it - the gap noted in ace_session_end.py).
"""
import io
import json
import os
import subprocess
import sys
import time

import pytest

from test_stop_v8 import Box, WORK, PROJECT_ID, ORG_ID, FAKE_CLI, SCRIPTS  # noqa: F401

SLEEPY = FAKE_CLI.replace(
    "argv = sys.argv[1:]",
    "argv = sys.argv[1:]\nimport time\n"
    "if argv[:1] == ['learn']:\n    time.sleep(float(os.environ.get('FAKE_LEARN_SLEEP', '0')))", 1)


@pytest.fixture
def box(tmp_path):
    b = Box(tmp_path)
    cli = b.bin / "ace-cli"
    cli.write_text(SLEEPY.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
    cli.chmod(0o755)
    return b


def _env(**kw):
    base = dict(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID, ACE_LEARN_INLINE="")
    base.update(kw)
    return base


def _wait(pred, secs=8.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def test_hook_returns_fast_while_detached_learn_runs(box):
    """A3: learn sleeps 2 s; hook returns < 0.5 s with empty stdout; lock exists while the
    child learns, learn + execution row land afterwards, lock and job file are gone."""
    sid = "s-a3"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the detached learn hardening")
    t0 = time.monotonic()
    p = box.run_after_task(box.stop_event(sid, last_assistant_message="Applied ctx-1."), **_env(FAKE_LEARN_SLEEP="2"))  # §31: used
    took = time.monotonic() - t0
    assert p.returncode == 0 and json.loads(p.stdout) == {"systemMessage": "ACE · learning sent"}, p.stderr  # item 2: the one learn line
    assert took < 1.2, "hook must not wait for the learn (took %.2fs)" % took
    lock = box.session_dir(sid) / "learn-inflight-main.lock"
    assert lock.exists(), "lock must be held while the detached learn runs"
    assert _wait(lambda: box.cli_calls("learn"), 6), "detached learn never ran"
    assert _wait(lambda: not lock.exists(), 3), "lock must be removed after the learn"
    assert box.relevance_rows("execution"), "execution metrics row must be written by the child"
    assert not list(box.session_dir(sid).glob("learn-job-*.json"))


def test_dispatch_spawns_detached_child_with_job_in_session_dir(box, monkeypatch):
    """A3 contract, in process: Popen(start_new_session=True, stdio DEVNULL), the job file is
    under <plugin-data>/projects/<pid>/sessions/<sid>/ (never /tmp), lock taken before spawn."""
    import ace_after_task as at
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(box.pd))
    monkeypatch.delenv("ACE_LEARN_INLINE", raising=False)
    calls = []

    class FakePopen:
        def __init__(self, argv, **kw):
            calls.append((argv, kw, os.path.exists(lock)))

    lock = str(box.session_dir("s-disp") / "learn-inflight-main.lock")
    box.session_dir("s-disp").mkdir(parents=True)
    monkeypatch.setattr(at.subprocess, "Popen", FakePopen)
    job = {"trace": {"task": "x"}, "org": ORG_ID, "project": PROJECT_ID,
           "hook_event_name": "Stop", "lock": lock, "metrics": {}}
    at.dispatch_learn(job, "s-disp")
    assert len(calls) == 1
    argv, kw, lock_existed = calls[0]
    assert kw.get("start_new_session") is True
    for k in ("stdin", "stdout", "stderr"):
        assert kw.get(k) == subprocess.DEVNULL, k
    job_file = argv[-1]
    assert job_file.startswith(str(box.session_dir("s-disp")) + os.sep)
    assert json.loads(open(job_file).read())["trace"] == {"task": "x"}
    assert lock_existed, "lock must exist before the child is spawned"


def test_learn_child_needs_nothing_but_the_job_file(box, monkeypatch):
    """S9: the child gets everything from the job (trace with F-080 ids); the session state
    may already be gone when it runs."""
    import ace_after_task as at
    sent = []
    monkeypatch.setattr(at, "run_learn", lambda trace, **kw: (sent.append((trace, kw)), ({}, 1))[1])
    monkeypatch.setattr(at, "log_execution_metrics", lambda **kw: None)
    d = box.session_dir("s-child")
    d.mkdir(parents=True)
    job = d / "learn-job-abc.json"
    job.write_text(json.dumps({"trace": {"task": "t", "session_id": "tsid-1"}, "retrieval_id": "r-1",
                               "applied_log_ids": [7], "org": ORG_ID, "project": PROJECT_ID,
                               "hook_event_name": "Stop", "lock": str(d / "learn-inflight-main.lock"),
                               "metrics": {}}))
    at.learn_child(str(job))
    assert sent and sent[0][0]["session_id"] == "tsid-1"
    assert sent[0][1]["retrieval_id"] == "r-1" and sent[0][1]["applied_log_ids"] == [7]
    assert not job.exists()


def test_learn_lock_held_before_session_state_is_read(box, monkeypatch, capsys):
    """S9: a SessionEnd between 'Stop starts' and 'Stop dispatches' must not delete the state
    the Stop is about to read -> the learn-inflight lock exists whenever the hook reads state.
    RED today: the lock is first touched in dispatch_learn, after every state read."""
    import ace_after_task as at
    sid = "s-lockfirst"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement lock-first ordering for the stop hook")
    lock = box.session_dir(sid) / "learn-inflight-main.lock"
    for k, v in box.env(ACE_PROJECT_ID=PROJECT_ID, ACE_ORG_ID=ORG_ID).items():
        monkeypatch.setenv(k, v)
    seen = []
    real = at.load_state

    def spy(*a, **kw):
        seen.append(lock.exists())
        return real(*a, **kw)

    monkeypatch.setattr(at, "load_state", spy)
    monkeypatch.setattr(at, "run_learn", lambda *a, **kw: ({}, 1))
    monkeypatch.chdir(box.project)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(box.stop_event(sid))))
    with pytest.raises(SystemExit):
        at.main()
    assert seen, "Stop must read the session state"
    assert all(seen), "learn-inflight lock must be held before the session state is read"
    assert not lock.exists(), "inline learn must release the lock"
    assert json.loads(capsys.readouterr().out) == {"systemMessage": "ACE · learning sent"}  # item 2


def test_skipped_stop_leaves_no_lock(box):
    """Taking the lock early must not leak it: a trivial/machine prompt skip removes it,
    else SessionEnd would keep the dir for 10 min for nothing."""
    sid = "s-lockskip"
    box.write_state(sid, user_prompt="<task-notification>done</task-notification>")
    p = box.run_after_task(box.stop_event(sid), **_env())
    assert p.returncode == 0 and p.stdout == ""
    assert not (box.session_dir(sid) / "learn-inflight-main.lock").exists()
    assert box.cli_calls("learn") == []


def test_sessionend_during_detached_learn_keeps_dir_then_learn_completes(box):
    """S9 end to end: Stop (detached, learn sleeps 2 s) -> SessionEnd fires at once -> the session
    dir survives (fresh lock), the learn still carries the F-080 ids from the state."""
    sid = "s-race"
    box.seed_tools(sid, WORK)
    box.write_state(sid, user_prompt="implement the race-safe session end",
                    pattern_ids=["ctx-1"], retrieval_id="ret-9", retrieval_log_ids={"ctx-1": 41})
    p = box.run_after_task(box.stop_event(sid, last_assistant_message="Applied ctx-1."), **_env(FAKE_LEARN_SLEEP="2"))  # §31: used
    assert p.returncode == 0
    end = box.run_shim("ace_sessionend_wrapper.sh",
                       {"session_id": sid, "hook_event_name": "SessionEnd", "reason": "other",
                        "cwd": str(box.project), "transcript_path": ""})
    assert end.returncode == 0
    assert box.session_dir(sid).exists(), "SessionEnd must not delete the dir while learn is in flight"
    assert _wait(lambda: box.cli_calls("learn"), 6)
    trace = box.cli_calls("learn")[0]["trace"]
    assert trace.get("retrieval_id") == "ret-9" and trace.get("applied_log_ids") == [41]
