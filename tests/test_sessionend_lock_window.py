#!/usr/bin/env python3
"""WP-H (v8.0.0 round 2) RED — SessionEnd learn-lock window (DESIGN §10 S9, §11 A3, §11 A2).

SessionEnd deletes the session dir ONLY when no `learn-inflight-*.lock` younger than 10 min
exists (the detached learn may run up to `run_learn(timeout=300)`); otherwise the dir is left
for the P-13 orphan sweep. SessionEnd Python must finish < 0.5 s cold (plugin SessionEnd hooks
have a 1.5 s budget, cc_hooks_reference.md:3578-3586).
"""
import os
import time

import pytest

from wpa_harness import Env

SCRIPT = "ace_sessionend_wrapper.sh"


def _ev(env, sid):
    return {"session_id": sid, "hook_event_name": "SessionEnd", "reason": "other",
            "cwd": str(env.project), "transcript_path": ""}


def _seed(env, sid, lock_age_s=None, agent="main"):
    d = env.session_dir(sid)
    d.mkdir(parents=True)
    (d / "patterns-used-main.json").write_text("{}")
    os.utime(str(d / "patterns-used-main.json"), (time.time() - 300, time.time() - 300))
    if lock_age_s is not None:
        lk = d / ("learn-inflight-%s.lock" % agent)
        lk.touch()
        t = time.time() - lock_age_s
        os.utime(str(lk), (t, t))
    return d


@pytest.mark.parametrize("age", [5, 150, 5 * 60, 9 * 60 + 30])
def test_fresh_lock_under_10_min_keeps_session_dir(tmp_path, age):
    """RED for ages >= 120 s: today's window is 120 s, A3/S9 require 10 min."""
    env = Env(tmp_path)
    d = _seed(env, "s-lock", lock_age_s=age)
    r = env.run(SCRIPT, _ev(env, "s-lock"))
    assert r.returncode == 0, r.stderr
    assert d.exists(), "lock aged %ss (< 10 min) must keep the session dir" % age


def test_subagent_lock_also_protects_dir(tmp_path):
    env = Env(tmp_path)
    d = _seed(env, "s-lock-sa", lock_age_s=4 * 60, agent="agent-123")
    env.run(SCRIPT, _ev(env, "s-lock-sa"))
    assert d.exists()


def test_stale_lock_over_10_min_does_not_block_delete(tmp_path):
    """A crashed learner's lock older than 10 min no longer pins the dir."""
    env = Env(tmp_path)
    d = _seed(env, "s-stale", lock_age_s=11 * 60)
    env.run(SCRIPT, _ev(env, "s-stale"))
    assert not d.exists()


def test_no_lock_deletes(tmp_path):
    env = Env(tmp_path)
    d = _seed(env, "s-nolock")
    env.run(SCRIPT, _ev(env, "s-nolock"))
    assert not d.exists()


def test_sessionend_cold_under_half_second(tmp_path):
    """§9 G6 / §11 A2: SessionEnd < 0.5 s cold with the cached python path (shim reads it)."""
    import sys
    env = Env(tmp_path)
    (env.data / "python_path").write_text(sys.executable + "\n")
    _seed(env, "s-cold", lock_age_s=30)
    t0 = time.monotonic()
    r = env.run(SCRIPT, _ev(env, "s-cold"))
    took = time.monotonic() - t0
    assert r.returncode == 0
    assert took < 0.5, "SessionEnd took %.2fs (budget 0.5 s cold)" % took
