#!/usr/bin/env python3
"""
Single source of truth for the ACE patterns-used state file.

State file naming: ace-patterns-used-{session_id}-{agent_suffix}.json
where agent_suffix = agent_id (for subagents) or 'main' (for the main agent).

This module centralizes the read/write/cleanup logic that was previously
duplicated inline in ace_before_task.py (writer) and ace_after_task.py (reader).
The path anchors to $CLAUDE_PROJECT_DIR/.claude/data/logs when CC provides it
(confirmed available to hooks since CC 2.1.141), so the writer (before_task /
PreToolUse) and the reader (after_task) resolve the SAME ABSOLUTE path regardless
of each hook process's cwd — robust to any mid-session cwd change. It falls back
to the relative '.claude/data/logs' (resolved against the wrapper's cd-to-event.cwd)
when CLAUDE_PROJECT_DIR is unset. All consumers go through _state_dir() so writer
and reader stay consistent by construction.
"""
import json
import os
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
    if state_dir is not None:
        return Path(state_dir)
    # v6.6.6: anchor to $CLAUDE_PROJECT_DIR (CC provides it to hooks since 2.1.141)
    # so writer + reader hit the SAME absolute dir even if a hook's cwd differs.
    proj = os.environ.get('CLAUDE_PROJECT_DIR')
    if proj:
        return Path(proj) / STATE_DIR_DEFAULT
    return Path(STATE_DIR_DEFAULT)


def state_file_path(session_id, agent_id, state_dir=None):
    agent_suffix = agent_id if agent_id else 'main'
    return _state_dir(state_dir) / f'ace-patterns-used-{session_id}-{agent_suffix}.json'


def _filter_retrieval_log_ids(retrieval_log_ids):
    """Filter retrieval_log_ids dict: keep only entries whose value is int but NOT bool."""
    if not retrieval_log_ids:
        return {}
    return {
        pid: v
        for pid, v in retrieval_log_ids.items()
        if not isinstance(v, bool) and isinstance(v, int)
    }


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
    raw = json.loads(sf.read_text())  # intentionally raises on bad JSON
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
                         task_session_id=None):
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
    if not ids and not has_retrieval and not has_task_session:
        return []
    d = _state_dir(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    sf = state_file_path(session_id, agent_id, state_dir)
    try:
        existing_ids, existing_rid, existing_rlog, existing_tsid = _read_state_file(sf)
    except Exception:
        existing_ids, existing_rid, existing_rlog, existing_tsid = [], None, {}, None
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
    sf.write_text(json.dumps(state))
    return existing_ids


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


def reap_patterns_used(session_id, agent_id, hook_event_name='Stop', state_dir=None, on_error=None):
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
        f = state_file_path(session_id, agent_id, state_dir)
    else:
        f = state_file_path(session_id, None, state_dir)
    try:
        f.unlink(missing_ok=True)
    except Exception as e:
        if on_error:
            try:
                on_error(f, e)
            except Exception:
                pass


def load_retrieval_ids(session_id, agent_id, hook_event_name='Stop', state_dir=None):
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
        sf = state_file_path(session_id, agent_id, state_dir)
    else:
        sf = state_file_path(session_id, None, state_dir)
    try:
        _ids, _rid, rlog, _tsid = _read_state_file(sf)
        return dict(rlog) if rlog else {}
    except Exception:
        return {}


def load_task_session_id(session_id, agent_id, hook_event_name='Stop', state_dir=None):
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
        sf = state_file_path(session_id, agent_id, state_dir)
    else:
        sf = state_file_path(session_id, None, state_dir)
    try:
        _ids, _rid, _rlog, tsid = _read_state_file(sf)
        return tsid or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Quality-gate + strip helper (shared by bash domain-shift inject paths).
# Mirrors ace_before_task.USEFUL_FIELDS and _apply_quality_gate exactly so
# ALL injection paths (main UserPromptSubmit + both domain-shift hooks) apply
# the SAME v15 gate and field strip.
# ---------------------------------------------------------------------------

_USEFUL_FIELDS = {
    'id', 'domain', 'content', 'confidence', 'helpful', 'harmful',
    'section', 'evidence', 'root_cause', 'error_context',
    # v15 reward-vocab fields (issue #27 / v7.1.2 Change B)
    'cumulative_v15_reward', 'n_hot_pos', 'n_hot_neg', 'isAtRisk',
}

# NOTE: The domain-shift count bound moved server-side (v7.1.1+).
# Both domain-shift scripts now pass --top-k 8 to ace-cli search so the SERVER
# selects the top-8 patterns.  strip_and_gate is gate+strip only — no client-
# side cap, no DOMAIN_SHIFT_TOP_K constant, no ucb_score sort.
# The main UserPromptSubmit search (ace_before_task.py) and the subagent-start
# search (ace_subagent_start.py) remain fully uncapped (server search_top_k).


def _quality_gate(patterns):
    """Dual-format quality gate — mirrors ace_before_task._apply_quality_gate.

    v15 path  (cumulative_v15_reward present):
        keep if NOT isAtRisk AND reward >= 0
        (@ace-sdk/core 3.2.2: isAtRisk means reward<0; reward==0 = neutral/uncredited,
        kept. Only reward<0 / at-risk patterns are dropped. Fix A: also guard reward >= 0
        so stale/mixed server data with reward<0 + isAtRisk=False is still dropped.
        Mirrors ace_before_task _apply_quality_gate — keep both in sync.)
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
    """Apply USEFUL_FIELDS strip + quality gate to a search-result dict.

    Returns a new dict with similar_patterns filtered (quality gate) and
    stripped of server-internal fields.  'count' is updated to reflect the
    post-gate count.  Top-level fields (retrieval_id, etc.) are preserved.

    Count bound: the caller (domain-shift scripts) passes --top-k 8 to
    ace-cli search, so the SERVER selects which patterns to return.  This
    function does NOT impose a client-side cap or sort — it is gate+strip only.
    Both domain-shift paths (ace_pretooluse_wrapper.sh and
    ace_posttooluse_domain_inject.sh) pipe through --strip-and-gate.
    """
    pats = data.get('similar_patterns') or []
    # Apply quality gate
    gated = _quality_gate(pats)
    # Strip server-internal fields (match_factors and all non-useful fields)
    stripped = [{k: v for k, v in p.items() if k in _USEFUL_FIELDS} for p in gated]
    result = dict(data)
    result['similar_patterns'] = stripped
    result['count'] = len(stripped)
    return result


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
