"""8.4.0: a rejected token must not go unseen. dead/ entries with last_error "auth" younger than 30 min raise ONE
notice per session (Python UPS; `ace_trace_queue.py --auth-held` is the same check for the mod); independent of the search.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_stop_v8 import Box, PROJECT_ID, box  # noqa: F401  (puts shared-hooks/utils on sys.path)
import ace_trace_queue as Q

REPO = Path(__file__).resolve().parent.parent
BEFORE = REPO / "plugins" / "ace" / "shared-hooks" / "ace_before_task.py"
QUEUE = REPO / "plugins" / "ace" / "shared-hooks" / "utils" / "ace_trace_queue.py"
NOW = 1_800_000_000.0
MIN = 60


def put_dead(qdir, n, err="auth", age=5 * MIN, now=NOW):
    d = Path(qdir) / "dead"
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%032x.json" % n)
    p.write_text(json.dumps({"v": 1, "created_at": now - age, "attempts": 1, "last_error": err, "meta": {}, "trace": {}}))
    os.utime(p, (now - age, now - age))
    return p


# ---------- the queue check ----------

def test_recent_auth_entries_count(tmp_path):
    for i in range(3):
        put_dead(tmp_path, i, age=(i + 1) * MIN)
    assert Q.auth_held_count(tmp_path, NOW) == 3
    assert Q.auth_held_line(tmp_path, NOW) == (
        "ACE: nicht angemeldet, Traces werden NICHT gesendet (3 Traces wartend/abgelegt). Bitte `ace-cli login` ausführen.")


def test_count_includes_the_older_hours_when_one_is_recent(tmp_path):
    put_dead(tmp_path, 1, age=2 * MIN)
    put_dead(tmp_path, 2, age=5 * 3600)
    put_dead(tmp_path, 3, age=30 * 3600)  # outside the 24 h counting window
    assert Q.auth_held_count(tmp_path, NOW) == 2


def test_only_old_auth_entries_is_silent(tmp_path):
    put_dead(tmp_path, 1, age=31 * MIN)
    put_dead(tmp_path, 2, age=3 * 3600)
    assert Q.auth_held_count(tmp_path, NOW) == 0 and Q.auth_held_line(tmp_path, NOW) is None


def test_window_boundary_is_30_minutes(tmp_path):
    assert Q.AUTH_HELD_WINDOW_S == 1800
    put_dead(tmp_path, 1, age=30 * MIN)
    assert Q.auth_held_count(tmp_path, NOW) == 1
    put_dead(tmp_path, 1, age=30 * MIN + 1)
    assert Q.auth_held_count(tmp_path, NOW) == 0


@pytest.mark.parametrize("err", ["invalid", "4xx", "network", "gave_up", None])
def test_other_dead_reasons_are_silent(tmp_path, err):
    put_dead(tmp_path, 1, err=err)
    assert Q.auth_held_count(tmp_path, NOW) == 0


def test_other_reasons_are_not_counted(tmp_path):
    put_dead(tmp_path, 1)
    put_dead(tmp_path, 2, err="4xx")
    assert Q.auth_held_count(tmp_path, NOW) == 1


def test_empty_or_missing_dead_is_silent(tmp_path):
    assert Q.auth_held_count(tmp_path, NOW) == 0
    (tmp_path / "dead").mkdir()
    assert Q.auth_held_count(tmp_path, NOW) == 0


def test_broken_and_hostile_dead_files_are_ignored(tmp_path):
    put_dead(tmp_path, 1)
    d = tmp_path / "dead"
    (d / "junk.json").write_text("{not json")
    (d / "list.json").write_text("[1]")
    (d / ("%032x.json" % 9)).symlink_to(d / "junk.json")
    assert Q.auth_held_count(tmp_path, NOW) == 1


def test_a_successful_login_clears_it_when_the_dead_entries_age_out(tmp_path):
    put_dead(tmp_path, 1, age=10 * MIN)
    assert Q.auth_held_count(tmp_path, NOW) == 1
    assert Q.auth_held_count(tmp_path, NOW + 25 * MIN) == 0  # no new dead/auth: after the window nothing is shown


def test_cheap_path_parses_nothing_when_no_recent_file(tmp_path, monkeypatch):
    put_dead(tmp_path, 1, age=2 * 3600)
    monkeypatch.setattr(Q, "_read_raw", lambda *a, **k: pytest.fail("parsed a file although none is recent"))
    assert Q.auth_held_count(tmp_path, NOW) == 0


def test_cli_prints_the_line_or_nothing(tmp_path):
    def run():
        return subprocess.run([sys.executable, "-I", str(QUEUE), "--auth-held", "--data-root", str(tmp_path)],
                              capture_output=True, text=True, timeout=30)
    assert run().stdout == ""
    put_dead(tmp_path / "trace-queue", 1, now=time.time())
    r = run()
    assert r.returncode == 0
    assert r.stdout.strip() == Q.AUTH_HELD_LINE % 1


# ---------- the Python UserPromptSubmit ----------

PROMPT = "please refactor the parser module so that it streams its input instead of reading it all"


def ups(box, sid, prompt=PROMPT, **env):
    ev = {"prompt": prompt, "cwd": str(box.project), "session_id": sid, "hook_event_name": "UserPromptSubmit"}
    p = subprocess.run([sys.executable, str(BEFORE)], input=json.dumps(ev), capture_output=True, text=True, timeout=60,
                       cwd=str(box.project), env=box.env(ACE_PROJECT_ID=PROJECT_ID, **env))
    assert p.returncode == 0, p.stderr
    try:
        return json.loads(p.stdout).get("systemMessage", "") if p.stdout.strip() else ""
    except ValueError:
        return p.stdout


ups_env = ups


def held(box, n=2):
    for i in range(n):
        put_dead(box.pd / "trace-queue", i, now=time.time())


def test_ups_shows_the_notice_once_per_session(box):
    held(box, 2)
    assert (Q.AUTH_HELD_LINE % 2) in ups(box, "s-a")
    assert "nicht angemeldet, Traces werden NICHT" not in ups(box, "s-a")
    assert (box.session_dir("s-a") / "auth_held_notified").exists()


def test_ups_new_session_shows_it_again(box):
    held(box, 1)
    assert "NICHT gesendet" in ups(box, "s-a")
    assert "NICHT gesendet" in ups(box, "s-b")


def test_ups_silent_without_auth_dead(box):
    put_dead(box.pd / "trace-queue", 1, err="4xx", now=time.time())
    put_dead(box.pd / "trace-queue", 2, age=2 * 3600, now=time.time())
    assert "NICHT gesendet" not in ups(box, "s-a")
    assert not (box.session_dir("s-a") / "auth_held_notified").exists()


def test_ups_after_login_the_notice_is_gone(box):
    held(box, 1)
    for f in (box.pd / "trace-queue" / "dead").glob("*.json"):  # entries aged out (or pruned): nothing left in the window
        os.utime(f, (time.time() - 3 * 3600,) * 2)
        e = json.loads(f.read_text()); e["created_at"] = time.time() - 3 * 3600; f.write_text(json.dumps(e))
    assert "NICHT gesendet" not in ups(box, "s-a")


# ---------- 8.4.0: the local-sink notice (ACE_TRACE_SINK set: nothing is sent) ----------

SINK_LINE = "ACE: Traces gehen in die lokale Senke (ACE_TRACE_SINK), es wird NICHTS gesendet."


def test_sink_line_text_and_mod_parity():
    assert Q.SINK_LINE == SINK_LINE
    ts = (REPO / "plugins" / "ace" / "mod" / "handlers" / "prompt.ts").read_text()
    assert "export const SINK_LINE = %r" % SINK_LINE in ts or 'export const SINK_LINE = "%s"' % SINK_LINE in ts


def test_sink_line_function(monkeypatch):
    monkeypatch.delenv("ACE_TRACE_SINK", raising=False)
    assert Q.sink_line() is None
    for v in ("", "   ", "\t"):
        monkeypatch.setenv("ACE_TRACE_SINK", v)
        assert Q.sink_line() is None
    monkeypatch.setenv("ACE_TRACE_SINK", "file:/tmp/x")
    assert Q.sink_line() == SINK_LINE


def test_ups_sink_once_per_session_and_again_in_a_new_one(box):
    assert SINK_LINE in ups_env(box, "s-a", ACE_TRACE_SINK="file:" + str(box.root / "sink"))
    assert SINK_LINE not in ups_env(box, "s-a", ACE_TRACE_SINK="file:" + str(box.root / "sink"))
    assert SINK_LINE in ups_env(box, "s-b", ACE_TRACE_SINK="file:" + str(box.root / "sink"))


@pytest.mark.parametrize("v", [None, "", "   "])
def test_ups_no_sink_never(box, v):
    kw = {} if v is None else {"ACE_TRACE_SINK": v}
    assert SINK_LINE not in ups_env(box, "s-a", **kw)
    assert SINK_LINE not in ups_env(box, "s-a", **kw)
    assert not (box.session_dir("s-a") / "sink_notified").exists()


def test_ups_sink_and_auth_held_together(box):
    held(box, 1)
    msg = ups_env(box, "s-a", ACE_TRACE_SINK="file:" + str(box.root / "sink"))
    assert SINK_LINE in msg and "nicht angemeldet, Traces werden NICHT gesendet" in msg
    msg2 = ups_env(box, "s-a", ACE_TRACE_SINK="file:" + str(box.root / "sink"))
    assert SINK_LINE not in msg2 and "nicht angemeldet" not in msg2
