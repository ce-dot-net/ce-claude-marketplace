#!/usr/bin/env python3
"""WP-H (v8.0.0 round 2) — orphan session sweep (DESIGN §10 P-13) + statusline copy sync (§10).

P-13: SessionEnd may not run (crash, 1.5 s budget, fresh learn lock) -> the ASYNC SessionStart
`--update-check` row sweeps <root>/projects/*/sessions/* whose mtime is older than 7 days.
Bounded, best-effort, local only (runs even when CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC skips
the npm lookup), prints nothing (§9 G3), never touches project-level files or the sync row.
Statusline: the sync SessionStart row keeps ~/.claude/ace_statusline.sh in sync with
scripts/ace_statusline.sh when the installed copy differs (regression; implemented).
"""
import os
import time

from wpa_harness import Env, PROJECT_ID, SCRIPTS

SCRIPT = "ace_install_cli.sh"
DAY = 86400


def _ev(env, sid):
    return {"session_id": sid, "hook_event_name": "SessionStart", "source": "startup",
            "cwd": str(env.project), "transcript_path": ""}


def _session(env, sid, age_days, project=PROJECT_ID):
    d = env.data / "projects" / project / "sessions" / sid
    d.mkdir(parents=True)
    (d / "patterns-used-main.json").write_text("{}")
    t = time.time() - age_days * DAY
    os.utime(str(d / "patterns-used-main.json"), (t, t))
    os.utime(str(d), (t, t))
    return d


def test_update_check_sweeps_sessions_older_than_7_days(tmp_path):
    env = Env(tmp_path)
    old = _session(env, "s-old", 8)
    old_other = _session(env, "s-old-2", 30, project="prj_other")
    fresh = _session(env, "s-fresh", 2)
    domains = env.data / "projects" / PROJECT_ID / "domains.json"
    domains.write_text("[]")
    r = env.run(SCRIPT, _ev(env, "s-now"), args=("--update-check",))
    assert r.returncode == 0, r.stderr
    assert r.stdout == "", "async update-check prints nothing (§9 G3)"
    assert not old.exists() and not old_other.exists(), "orphans > 7 days must be swept"
    assert fresh.exists(), "sessions younger than 7 days stay"
    assert domains.exists(), "project-level files are never swept"


def test_sweep_runs_without_network(tmp_path):
    """The sweep is local: CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC only skips npm."""
    env = Env(tmp_path)
    old = _session(env, "s-old", 9)
    env.run(SCRIPT, _ev(env, "s-now"), args=("--update-check",),
            CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    assert env.npm_calls() == []
    assert not old.exists()


def test_sweep_never_deletes_the_current_session(tmp_path):
    """A resumed session can have an old dir mtime; its own dir must survive."""
    env = Env(tmp_path)
    mine = _session(env, "s-resumed", 10)
    env.run(SCRIPT, _ev(env, "s-resumed"), args=("--update-check",))
    assert mine.exists()


def test_sync_startup_does_not_sweep(tmp_path):
    """The sync row blocks the first response (doc :1248): no sweep there."""
    env = Env(tmp_path)
    old = _session(env, "s-old", 8)
    env.run(SCRIPT, _ev(env, "s-now"))
    assert old.exists()


def test_sweep_ignores_non_dirs_and_foreign_paths(tmp_path):
    env = Env(tmp_path)
    stray = env.data / "projects" / PROJECT_ID / "sessions" / "stray.txt"
    stray.parent.mkdir(parents=True)
    stray.write_text("x")
    t = time.time() - 20 * DAY
    os.utime(str(stray), (t, t))
    logs = env.data / "logs"
    logs.mkdir()
    (logs / "ace-hook-errors.log").write_text("x")
    os.utime(str(logs), (t, t))
    r = env.run(SCRIPT, _ev(env, "s-now"), args=("--update-check",))
    assert r.returncode == 0
    assert logs.exists() and (logs / "ace-hook-errors.log").exists()


# --- statusline copy sync (regression for the implemented behavior) -------------------------

def _statusline_home(env):
    return env.home / ".claude" / "ace_statusline.sh"


def test_statusline_copy_resynced_when_installed_copy_differs(tmp_path):
    env = Env(tmp_path)
    dst = _statusline_home(env)
    dst.parent.mkdir(parents=True)
    dst.write_text("#!/bin/sh\necho old\n")
    r = env.run(SCRIPT, _ev(env, "s-sl"))
    assert r.returncode == 0, r.stderr
    assert dst.read_bytes() == (SCRIPTS / "ace_statusline.sh").read_bytes()
    assert os.access(str(dst), os.X_OK)


def test_statusline_not_installed_is_not_created(tmp_path):
    """Install is /ace-statusline-setup's job; SessionStart only keeps an existing copy current."""
    env = Env(tmp_path)
    env.run(SCRIPT, _ev(env, "s-sl2"))
    assert not _statusline_home(env).exists()


def test_statusline_identical_copy_untouched(tmp_path):
    env = Env(tmp_path)
    dst = _statusline_home(env)
    dst.parent.mkdir(parents=True)
    dst.write_bytes((SCRIPTS / "ace_statusline.sh").read_bytes())
    t = time.time() - 3 * DAY
    os.utime(str(dst), (t, t))
    env.run(SCRIPT, _ev(env, "s-sl3"))
    assert abs(dst.stat().st_mtime - t) < 1
