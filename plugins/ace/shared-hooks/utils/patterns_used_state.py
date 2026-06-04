#!/usr/bin/env python3
"""
Single source of truth for the ACE patterns-used state file.

State file naming: ace-patterns-used-{session_id}-{agent_suffix}.json
where agent_suffix = agent_id (for subagents) or 'main' (for the main agent).

This module centralizes the read/write/cleanup logic that was previously
duplicated inline in ace_before_task.py (writer) and ace_after_task.py (reader).
The path scheme stays RELATIVE (STATE_DIR_DEFAULT = '.claude/data/logs'); hook
wrappers cd to event.cwd so the relative path resolves to the project root.
Do NOT anchor to $CLAUDE_PROJECT_DIR.
"""
import json
import sys
from pathlib import Path

# is_valid_pattern_id is already used by ace_before_task.py and ace_after_task.py.
# Import it from the SAME module they use: plugins/ace/utils/validation.py.
# This file lives at plugins/ace/shared-hooks/utils/ -> ../../utils is plugins/ace/utils.
_PLUGIN_UTILS = Path(__file__).resolve().parent.parent.parent / "utils"
if str(_PLUGIN_UTILS) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_UTILS))
from validation import is_valid_pattern_id  # noqa: E402

STATE_DIR_DEFAULT = '.claude/data/logs'


def _state_dir(state_dir=None):
    return Path(state_dir) if state_dir is not None else Path(STATE_DIR_DEFAULT)


def state_file_path(session_id, agent_id, state_dir=None):
    agent_suffix = agent_id if agent_id else 'main'
    return _state_dir(state_dir) / f'ace-patterns-used-{session_id}-{agent_suffix}.json'


def append_patterns_used(session_id, agent_id, pattern_ids, state_dir=None):
    """Append+dedupe valid pattern IDs to the per-agent file; return the full list.

    Behavior-identical to ace_before_task.py:313-340.
    """
    if not session_id:
        return []
    ids = [p for p in (pattern_ids or []) if isinstance(p, str) and is_valid_pattern_id(p)]
    if not ids:
        return []
    d = _state_dir(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    sf = state_file_path(session_id, agent_id, state_dir)
    existing = []
    if sf.exists():
        try:
            existing = json.loads(sf.read_text())
        except Exception:
            existing = []
    seen = set(existing)
    for pid in ids:
        if pid not in seen:
            existing.append(pid)
            seen.add(pid)
    sf.write_text(json.dumps(existing))
    return existing


def load_playbook_used(session_id, agent_id, hook_event_name='Stop', state_dir=None, on_error=None):
    """Load + reap the patterns-used state for a (sub)agent stop event.

    PER-AGENT-PURE attribution (authoritative): the CLIENT owns
    trajectory/session/agent attribution; EACH agent (main + each subagent)
    manages its OWN trajectory/traces independently. The server only learns
    from the ExecutionTrace the client POSTs. Therefore playbook_used MUST be
    per-agent — NEVER merge one agent's recalls into another agent's trace.

    SubagentStop: read ONLY this subagent's own -{agent_id} file and unlink
    ONLY it. NEVER touch other suffixes -> no state-file-steal.

    Terminal main Stop (hook_event_name != 'SubagentStop'): read ONLY the
    -main file (force the 'main' suffix; the main writer always writes 'main',
    so ignore any agent_id CC stamps on Stop), reap it, and LEAVE sibling
    -{uuid} files on disk. NO glob, NO cross-agent merge.

    Per-file try/except so a corrupt file self-heals (returns [] + unlinks);
    on_error(file, exc) is invoked for each failing file.
    """
    if not session_id:
        return []
    if hook_event_name == 'SubagentStop':
        files = [state_file_path(session_id, agent_id, state_dir)]
    else:
        files = [state_file_path(session_id, None, state_dir)]
    seen = set()
    result = []
    for f in files:
        try:
            if f.exists():
                raw = json.loads(f.read_text())
                for pid in raw:
                    if isinstance(pid, str) and is_valid_pattern_id(pid) and pid not in seen:
                        seen.add(pid)
                        result.append(pid)
                f.unlink()
        except Exception as e:
            if on_error:
                try:
                    on_error(f, e)
                except Exception:
                    pass
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
    return result


# CLI entrypoint for the bash PreToolUse wrapper: reads search JSON on stdin,
# extracts similar_patterns[].id, appends.
if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument('--session', required=True)
    ap.add_argument('--agent-id', default='')
    ap.add_argument('--state-dir', default=None)
    a = ap.parse_args()
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    pats = data.get('similar_patterns') or data.get('patterns') or []
    ids = [p.get('id') for p in pats if isinstance(p, dict) and p.get('id')]
    append_patterns_used(a.session, a.agent_id or None, ids, a.state_dir)
    sys.exit(0)
