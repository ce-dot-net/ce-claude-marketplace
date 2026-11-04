"""Shared hook bootstrap (WP-A): plugin version / ACE_CLIENT_ID and event -> (session_id, project_id).

Replaces scripts/_ace_env.sh for Python hooks (DESIGN §3.1: shims do no env work) and
the shell `cd` + jq .claude/settings.json lookup: the project comes from ace_project_context (the one core) for the
hook JSON `cwd` (cc_hooks_reference.md:402), stdlib only.
"""
import json
import os
from pathlib import Path

from plugin_data_dir import resolve_session_id


def plugin_root():
    return Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])


def plugin_version():
    try:
        return json.loads((plugin_root() / ".claude-plugin" / "plugin.json").read_text()).get("version") or "0.0.0"
    except Exception:
        return "0.0.0"


def client_id():
    return "claude-code-plugin/%s" % plugin_version()


def read_event():
    """Hook JSON from stdin; {} on anything unparsable. Never raises."""
    import sys
    try:
        ev = json.loads(sys.stdin.read() or "{}")
        return ev if isinstance(ev, dict) else {}
    except Exception:
        return {}


def resolve_ids(event):
    """(session_id, project_id). chdir to the event cwd; the binding comes from ace_project_context."""
    cwd = event.get("cwd")
    if cwd and os.path.isdir(cwd):
        try:
            os.chdir(cwd)
        except OSError:
            pass
    pid = None
    try:
        from ace_project_context import get_context
        pid = (get_context() or {}).get("project")
    except Exception:
        pass
    return resolve_session_id(event), pid
