#!/usr/bin/env python3
"""
Single source of truth for the ACE patterns-used state file.

v8 layout (DESIGN §4): <plugin-data>/projects/<project_id>/sessions/<session_id>/
patterns-used-<agent>.json where agent = agent_id (subagents) or 'main'.
Paths come ONLY from plugin_data_dir; an explicit state_dir stands for the
session dir. Optional keys user_prompt / rendered_context / hook_event_name
(contract C1) carry data from UPS/SubagentStart to Stop and SessionStart(compact).

This module centralizes the read/write/cleanup logic that was previously
duplicated inline in ace_before_task.py (writer) and ace_after_task.py (reader).
"""
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

# ace_pattern_render is in the same utils directory
_UTILS_DIR = Path(__file__).resolve().parent
if str(_UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(_UTILS_DIR))

# is_valid_pattern_id is already used by ace_before_task.py and ace_after_task.py.
# Import it from the SAME module they use: plugins/ace/utils/validation.py.
# This file lives at plugins/ace/shared-hooks/utils/ -> ../../utils is plugins/ace/utils.
_PLUGIN_UTILS = Path(__file__).resolve().parent.parent.parent / "utils"
if str(_PLUGIN_UTILS) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_UTILS))
from validation import is_valid_pattern_id  # noqa: E402

import plugin_data_dir  # noqa: E402

USER_PROMPT_MAX = 4000
RENDERED_CONTEXT_MAX = 10000


def _project_id(project_id=None):
    """kwarg, else ace_context.get_context()['project'], else 'default'."""
    if project_id:
        return project_id
    try:
        from ace_context import get_context
        # Anchor to $CLAUDE_PROJECT_DIR (cwd-independent, v6.6.6 lesson): the
        # session cwd can move to a subdir; the cwd-relative lookup would then
        # resolve a different project id for writer vs reader.
        ctx = get_context(os.environ.get('CLAUDE_PROJECT_DIR') or None)
        if (not ctx or not ctx.get('project')) and os.environ.get('CLAUDE_PROJECT_DIR'):
            ctx = get_context()
        if ctx and ctx.get('project'):
            return ctx['project']
    except Exception:
        pass
    return 'default'


def _state_dir(state_dir=None, session_id=None, project_id=None, create=False):
    if state_dir is not None:
        return Path(state_dir)
    return plugin_data_dir.session_dir(_project_id(project_id), session_id, create=create)


def state_file_path(session_id, agent_id, state_dir=None, project_id=None):
    agent_suffix = agent_id if agent_id else 'main'
    return _state_dir(state_dir, session_id, project_id) / f'patterns-used-{agent_suffix}.json'


def _filter_retrieval_log_ids(retrieval_log_ids):
    """Filter retrieval_log_ids dict: keep only entries whose value is int but NOT bool."""
    if not retrieval_log_ids:
        return {}
    return {
        pid: v
        for pid, v in retrieval_log_ids.items()
        if not isinstance(v, bool) and isinstance(v, int)
    }


@contextmanager
def _locked(sf):
    """Exclusive flock on a sibling .lock so concurrent appends don't lose data.
    Best-effort: without fcntl/flock the atomic replace still prevents torn files."""
    fh = None
    try:
        import fcntl
        fh = open(str(sf) + '.lock', 'a')
        fcntl.flock(fh, fcntl.LOCK_EX)
    except Exception:
        pass
    try:
        yield
    finally:
        if fh is not None:
            try:
                fh.close()  # releases the lock
            except Exception:
                pass


def _atomic_write(sf, text):
    fd, tmp = tempfile.mkstemp(dir=str(sf.parent), prefix='.pus-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        os.replace(tmp, sf)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_state_file(sf):
    """Read state file; return (pattern_ids_list, retrieval_id, retrieval_log_ids, task_session_id).

    Handles both legacy bare-list format and new dict format.
    Legacy: ["id1", "id2"]  → retrieval_id=None, retrieval_log_ids={}, task_session_id=None
    New:    {"pattern_ids": [...], "retrieval_id": ..., "retrieval_log_ids": {...},
             "task_session_id": "uuid4-string-or-None"}

    Raises ValueError/json.JSONDecodeError if the file exists but is not valid JSON,
    so callers (load_playbook_used) can handle corruption via their own except + on_error.
    Returns ([], None, {}, None) ONLY for missing files or wrong-type content (not JSON errors).
    """
    if not sf.exists():
        return [], None, {}, None
    return _parse_state(json.loads(sf.read_text()))  # intentionally raises on bad JSON


def _parse_state(raw):
    """(ids, retrieval_id, retrieval_log_ids, task_session_id) from parsed JSON."""
    if isinstance(raw, list):
        # Legacy bare-list format
        return raw, None, {}, None
    if isinstance(raw, dict):
        ids = raw.get('pattern_ids') or []
        rid = raw.get('retrieval_id') or None
        rlog = raw.get('retrieval_log_ids') or {}
        tsid = raw.get('task_session_id') or None
        return ids, rid, rlog, tsid
    return [], None, {}, None


def append_patterns_used(session_id, agent_id, pattern_ids, state_dir=None,
                         retrieval_id=None, retrieval_log_ids=None,
                         task_session_id=None, project_id=None,
                         user_prompt=None, rendered_context=None,
                         hook_event_name=None):
    """Append+dedupe valid pattern IDs to the per-agent file; return the full list.

    F-080: optional params retrieval_id (str|None) and retrieval_log_ids (dict|None).
    task_session_id: optional per-task uuid4 (str|None) stored for ace_after_task to read
    before the state file is reaped — so the server can correlate search↔learn per task.
    State file is now written as dict schema:
      {"pattern_ids": [...], "retrieval_id": ..., "retrieval_log_ids": {...},
       "task_session_id": "uuid4-or-None"}
    Backward compat: existing bare-list files are read transparently.
    bool guard: retrieval_log_ids values that are bool are excluded even though
    bool is a subclass of int.
    """
    if not session_id:
        return []
    ids = [p for p in (pattern_ids or []) if isinstance(p, str) and is_valid_pattern_id(p)]
    has_retrieval = retrieval_id is not None or bool(retrieval_log_ids)
    has_task_session = task_session_id is not None
    has_extra = bool(user_prompt or rendered_context or hook_event_name)
    if not ids and not has_retrieval and not has_task_session and not has_extra:
        return []
    sf = state_file_path(session_id, agent_id, state_dir, project_id)
    sf.parent.mkdir(parents=True, exist_ok=True)
    with _locked(sf):
        try:
            prior_raw = json.loads(sf.read_text()) if sf.exists() else {}
        except Exception:
            prior_raw = {}
        existing_ids, existing_rid, existing_rlog, existing_tsid = _parse_state(prior_raw)
        seen = set(existing_ids)
        for pid in ids:
            if pid not in seen:
                existing_ids.append(pid)
                seen.add(pid)
        # Merge retrieval_log_ids (new entries win over existing for same key)
        merged_rlog = dict(existing_rlog)
        merged_rlog.update(_filter_retrieval_log_ids(retrieval_log_ids or {}))
        # retrieval_id: use new value if provided, else keep existing
        merged_rid = retrieval_id if retrieval_id is not None else existing_rid
        # task_session_id: use new value if provided, else keep existing
        merged_tsid = task_session_id if task_session_id is not None else existing_tsid
        state = {
            'pattern_ids': existing_ids,
            'retrieval_id': merged_rid,
            'retrieval_log_ids': merged_rlog,
            'task_session_id': merged_tsid,
        }
        # C1 optional keys: keep earlier values unless a new one is supplied.
        prior = prior_raw if isinstance(prior_raw, dict) else {}
        for key, val, cap in (('user_prompt', user_prompt, USER_PROMPT_MAX),
                              ('rendered_context', rendered_context, RENDERED_CONTEXT_MAX),
                              ('hook_event_name', hook_event_name, None)):
            # None = not supplied (keep prior); '' is an explicit "set" (control arm clears
            # a stale rendered_context so WP-D never re-injects it).
            val = val if val is not None else prior.get(key)
            if val is not None and (val or key == 'rendered_context'):
                state[key] = val[:cap] if cap else val
        _atomic_write(sf, json.dumps(state))
    return existing_ids


def load_playbook_used(session_id, agent_id, hook_event_name='Stop', state_dir=None, on_error=None, project_id=None):
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
        files = [state_file_path(session_id, agent_id, state_dir, project_id)]
    else:
        files = [state_file_path(session_id, None, state_dir, project_id)]
    seen = set()
    result = []
    for f in files:
        try:
            if f.exists():
                ids, _rid, _rlog, _tsid = _read_state_file(f)
                for pid in ids:
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


def reap_patterns_used(session_id, agent_id, hook_event_name='Stop', state_dir=None, on_error=None, project_id=None):
    """Unlink (reap) the per-agent patterns-used state file WITHOUT reading it.

    v6.6.7: the learning-skip path in ace_after_task (no project context /
    trivial task / no substantial work) returns BEFORE load_playbook_used(),
    the consumer that normally unlinks the file. So a skipped (sub)agent used to
    leave its per-agent file orphaned until the SessionEnd GC. This reaps it
    eagerly, honoring the SAME PER-AGENT-PURE rule as load_playbook_used:
      • SubagentStop          -> reap ONLY this subagent's -{agent_id} file
      • terminal Stop (else)   -> reap ONLY the -main file (force 'main' suffix,
                                  ignoring any agent_id CC stamps on Stop), and
                                  LEAVE sibling -{uuid} files for their own
                                  SubagentStop.

    SAFETY (user invariant): this only ever runs on a path that fires NO learn,
    so it can never strip pattern IDs from a trace that is sent to the server.
    Pure unlink (never reads), uses missing_ok, and never raises; on_error(file,
    exc) is invoked only if the unlink itself fails (e.g. permissions).
    """
    if not session_id:
        return
    if hook_event_name == 'SubagentStop':
        f = state_file_path(session_id, agent_id, state_dir, project_id)
    else:
        f = state_file_path(session_id, None, state_dir, project_id)
    try:
        f.unlink(missing_ok=True)
    except Exception as e:
        if on_error:
            try:
                on_error(f, e)
            except Exception:
                pass


def load_retrieval_ids(session_id, agent_id, hook_event_name='Stop', state_dir=None, project_id=None):
    """Read the retrieval_log_ids map from the per-agent state file WITHOUT unlinking it.

    F-080: read-only companion to load_playbook_used.  Returns
    {pattern_id: retrieval_log_id (int)} from the new dict schema.
    Legacy bare-list files (or missing files) return {} without crash.
    Honors the same per-agent-pure routing as load_playbook_used:
      SubagentStop → this subagent's -{agent_id} file
      other        → -main file
    """
    if not session_id:
        return {}
    if hook_event_name == 'SubagentStop':
        sf = state_file_path(session_id, agent_id, state_dir, project_id)
    else:
        sf = state_file_path(session_id, None, state_dir, project_id)
    try:
        _ids, _rid, rlog, _tsid = _read_state_file(sf)
        return dict(rlog) if rlog else {}
    except Exception:
        return {}


def load_task_session_id(session_id, agent_id, hook_event_name='Stop', state_dir=None, project_id=None):
    """Read the task_session_id from the per-agent state file WITHOUT unlinking it.

    per-task session_id: read-only companion to load_retrieval_ids.
    Returns the task_session_id (str uuid4) written by ace_before_task or
    ace_subagent_start at search time, so ace_after_task can set
    trace["session_id"] = task_session_id (correlates search↔learn per task
    rather than per CC conversation).

    Honors the same per-agent-pure routing as load_playbook_used:
      SubagentStop → this subagent's -{agent_id} file
      other        → -main file
    Returns None for missing files, legacy bare-list files, or any error.
    """
    if not session_id:
        return None
    if hook_event_name == 'SubagentStop':
        sf = state_file_path(session_id, agent_id, state_dir, project_id)
    else:
        sf = state_file_path(session_id, None, state_dir, project_id)
    try:
        _ids, _rid, _rlog, tsid = _read_state_file(sf)
        return tsid or None
    except Exception:
        return None


def load_state(session_id, agent_id, hook_event_name='Stop', state_dir=None, project_id=None):
    """Read the whole state dict WITHOUT unlinking it ({} if missing/corrupt).

    Readers of the C1 optional keys (user_prompt, rendered_context,
    hook_event_name): Stop/SubagentStop, SessionStart(compact).
    """
    if not session_id:
        return {}
    aid = agent_id if hook_event_name == 'SubagentStop' else None
    try:
        raw = json.loads(state_file_path(session_id, aid, state_dir, project_id).read_text())
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Render + strip helper (shared by bash domain-shift inject paths).
# Uses ace_pattern_render.render_patterns — NO quality gate, bandit_rank sort,
# bandit_rank/semantic_score hoisted, expanded dropped.
# ---------------------------------------------------------------------------

# NOTE: The domain-shift count bound is server-side (v7.1.1+).
# Both domain-shift scripts pass --top-k 8 to ace-cli search so the SERVER
# selects the top-8 patterns.  strip_and_gate renders all returned patterns
# (no client-side cap, no gate, no ucb_score sort).


def _quality_gate(patterns):
    """Dual-format quality gate — RETAINED for backward compat with existing tests
    and for any callers outside the injection path.  The INJECTION path now uses
    render_patterns (no gate).  This function is no longer called from strip_and_gate.

    v15 path  (cumulative_v15_reward present):
        keep if NOT isAtRisk AND reward >= 0
    Legacy path (no cumulative_v15_reward):
        keep if confidence >= 0.5 OR helpful >= 2
    """
    result = []
    for p in patterns:
        reward = p.get('cumulative_v15_reward')
        if reward is not None:
            if not p.get('isAtRisk', False) and reward >= 0:
                result.append(p)
        else:
            if p.get('confidence', 0) >= 0.5 or p.get('helpful', 0) >= 2:
                result.append(p)
    return result


def strip_and_gate(data):
    """Render search-result dict via ace_pattern_render (NO quality gate).

    Returns a new dict with:
      - similar_patterns: sorted by bandit_rank ASC (None→tail), all patterns
        retained (no gate), server-internal fields stripped, bandit_rank and
        semantic_score hoisted from match_factors, evidence capped to 2.
      - expanded dropped
      - count updated to reflect the full rendered pattern count
      - top-level fields (retrieval_id, etc.) preserved

    Used by both domain-shift bash scripts via --strip-and-gate CLI mode.
    Domain-shift sets are small (≤8 via --top-k 8 server-side), so all
    patterns are rendered verbatim (tier_k parameter is a no-op in render_patterns_dict
    — budget is not applied here; all patterns are returned).
    The bash scripts wrap this JSON output in their own <ace-patterns-domain-shift> tag.

    Delegates directly to render_patterns_dict (structured return) to avoid
    the fragile string-split / parse-back / silent fallback approach.
    """
    from ace_pattern_render import render_patterns_dict
    output_dict, _ids, _rl_map = render_patterns_dict(data, tier_k=100)
    return output_dict


# CLI entrypoint for the bash PreToolUse/PostToolUse wrappers.
#
# Modes:
#   default (no special flag): reads search JSON on stdin, extracts
#     similar_patterns[].id, appends to per-agent state file.
#
#   --read-task-session-id: read state file for (session, agent-id),
#     print task_session_id to stdout (empty string if absent), exit 0
#     WITHOUT writing.
#
#   --strip-and-gate: read search JSON from stdin, apply USEFUL_FIELDS
#     strip + v15 quality gate, print filtered JSON to stdout, exit 0.
#     Does NOT require --session (stateless transform).
if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument('--session', default=None)
    ap.add_argument('--agent-id', default='')
    ap.add_argument('--state-dir', default=None)
    ap.add_argument('--retrieval-id', default=None)
    # Change A: pass task_session_id through append call
    ap.add_argument('--task-session-id', default=None)
    # Change A: read-only mode — print stored task_session_id and exit
    ap.add_argument('--read-task-session-id', action='store_true', default=False)
    # Change B: strip+gate mode — stateless quality-gate transform
    ap.add_argument('--strip-and-gate', action='store_true', default=False)
    a = ap.parse_args()

    # ── --strip-and-gate mode (stateless, no --session required) ─────────────
    if a.strip_and_gate:
        try:
            data = json.load(sys.stdin)
        except Exception:
            sys.exit(0)
        print(json.dumps(strip_and_gate(data)))
        sys.exit(0)

    # ── --read-task-session-id mode (read-only, no write) ────────────────────
    if a.read_task_session_id:
        if not a.session:
            print('')
            sys.exit(0)
        agent_id = a.agent_id or None
        # Route to the correct file: when agent_id is present, treat as
        # SubagentStop so load_task_session_id reads the agent-specific file.
        hook_event = 'SubagentStop' if agent_id else 'Stop'
        tsid = load_task_session_id(
            a.session,
            agent_id,
            hook_event,
            state_dir=a.state_dir,
        )
        print(tsid if tsid else '')
        sys.exit(0)

    # ── default append mode ───────────────────────────────────────────────────
    if not a.session:
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    pats = data.get('similar_patterns') or data.get('patterns') or []
    ids = [p.get('id') for p in pats if isinstance(p, dict) and p.get('id')]
    # F-080: extract match_factors.retrieval_log_id per pattern (bool guard applied)
    retrieval_log_map = {}
    for p in pats:
        if not isinstance(p, dict):
            continue
        pid = p.get('id')
        mf = p.get('match_factors') or {}
        rlid = mf.get('retrieval_log_id') if isinstance(mf, dict) else None
        if pid and not isinstance(rlid, bool) and isinstance(rlid, int):
            retrieval_log_map[pid] = rlid
    # retrieval_id: use --retrieval-id flag if provided, else fall back to top-level field
    retrieval_id = a.retrieval_id or data.get('retrieval_id') or None
    append_patterns_used(a.session, a.agent_id or None, ids, a.state_dir,
                         retrieval_id=retrieval_id, retrieval_log_ids=retrieval_log_map,
                         task_session_id=a.task_session_id or None)
    sys.exit(0)
