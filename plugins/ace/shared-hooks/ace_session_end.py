#!/usr/bin/env python3
"""ACE SessionEnd (v8): delete THIS session's dir under plugin data, nothing else (DESIGN §4).

Plugin SessionEnd hooks have a hard 1.5 s budget (cc_hooks_reference.md:3578-3586); output is discarded.
No session_id -> no-op (never fall back to 'default': that dir is shared).
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))


def main():
    from ace_env import read_event, resolve_ids
    from plugin_data_dir import session_dir
    ev = read_event()
    if not ev.get("session_id"):
        return 0
    sid, pid = resolve_ids(ev)
    d = session_dir(pid, sid, create=False)
    if os.path.exists(os.path.join(str(d), "learn-deferred")):  # the deferred Stop's notification never came
        try:
            from ace_relevance_logger import log_event
            log_event("learn_deferred_lost", reason="session_end", session_id=sid)
            os.unlink(os.path.join(str(d), "learn-deferred"))
        except Exception:
            pass
    # Async Stop/SubagentStop may still be learning: keep the dir while a fresh learn lock exists.
    import glob
    import time
    for lk in glob.glob(os.path.join(str(d), "learn-inflight-*.lock")):
        try:
            if time.time() - os.path.getmtime(lk) < 600:  # learn timeout 300 s + margin (S9/A3)
                return 0
        except OSError:
            pass
    # Stop may be starting right now (async; takes its lock only after python startup) and has not
    # consumed state yet: keep the dir if anything in it is fresh; the P-13 sweep cleans up later.
    try:
        for e in os.scandir(str(d)):
            if time.time() - e.stat().st_mtime < 60:
                return 0
    except OSError:
        pass
    shutil.rmtree(str(d), ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            from ace_relevance_logger import log_error
            log_error('SessionEnd', 'ace_session_end.main', error=e)
        except Exception:
            pass
    sys.exit(0)
