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
    shutil.rmtree(str(session_dir(pid, sid, create=False)), ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
