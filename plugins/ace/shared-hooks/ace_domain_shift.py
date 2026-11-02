#!/usr/bin/env python3
"""ACE domain-shift hook (v8): PostToolUse Read|Glob|Grep, the ONE domain-shift path.

Replaces the PreToolUse bash wrapper and the old PostToolUse bash inject (DESIGN §3, §6 WP-D).
When the tool's path enters a domain (from the last UPS search, domains.json, C3) that this
agent has not been in, search `--top-k 8` (server-side bound for the per-tool hot path) with
the file basename as query, strip-and-gate, record the injected ids (C1/F-080) and emit
PostToolUse additionalContext (cc_hooks_reference.md:2220-2245), capped at 10,000 chars.
No domain filter and no intent hint (server owns both; domain_match anti-predicts relevance).
"""
import html
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

import plugin_data_dir                                    # noqa: E402
from ace_cli import run_search                            # noqa: E402
from ace_context import get_context                       # noqa: E402
from ace_relevance_logger import log_domain_shift, log_error  # noqa: E402
from patterns_used_state import (append_patterns_used, load_task_session_id,  # noqa: E402
                                 strip_and_gate, task_session_id_for)

_TOOLS = ('Read', 'Glob', 'Grep')
_CAP = 10000


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def match_domain_to_path(domain: str, path: str) -> bool:
    """Port of the v7.1.14 bash matcher: path segments (split on / . _ - whitespace)
    vs domain words (split on - whitespace); both >= 3 chars; exact word or common
    prefix >= 4. Case-insensitive."""
    words = [w for w in re.split(r'[-\s]+', domain.lower()) if len(w) >= 3]
    for seg in re.split(r'[/._\-\s]+', path.lower()):
        if len(seg) < 3:
            continue
        for w in words:
            if seg == w or _common_prefix_len(w, seg) >= 4:
                return True
    return False


def _context(domain: str, stripped: dict) -> str:
    """Wrap in the domain-shift tag, dropping trailing patterns until <= 10,000 chars.
    Mutates `stripped`: afterwards it holds exactly the injected patterns."""
    attr = html.escape(domain, quote=True)  # domains.json is server-provided
    while True:
        ctx = '<ace-patterns-domain-shift domain="%s">%s</ace-patterns-domain-shift>' % (
            attr, json.dumps(stripped))
        if len(ctx) <= _CAP:
            return ctx
        if not stripped.get('similar_patterns'):
            return None  # never raw-truncate JSON (v7.1.11): inject nothing
        stripped['similar_patterns'] = stripped['similar_patterns'][:-1]
        stripped['count'] = len(stripped['similar_patterns'])


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get('tool_name') not in _TOOLS:
            return
        ti = event.get('tool_input') or {}
        file_path = ti.get('file_path') or ti.get('path')
        if not file_path and event.get('tool_name') == 'Glob':
            g = ti.get('pattern')  # a Grep `pattern` is a regex, never a path
            file_path = g if isinstance(g, str) and '/' in g and '*' not in os.path.basename(g) else None
        if not file_path or not isinstance(file_path, str):
            return
        cwd = event.get('cwd')
        if cwd and os.path.isdir(cwd):
            os.chdir(cwd)  # v8 shims never cd (DESIGN §3.1); logger/context resolve from cwd
        ctx = get_context()
        if not ctx:
            return
        project, org = ctx['project'], ctx['org']
        t0 = time.monotonic()
        sid = plugin_data_dir.resolve_session_id(event)
        if plugin_data_dir.is_disabled(project, sid) or plugin_data_dir.is_mod_active(project, sid):
            return
        try:
            domains = json.loads(plugin_data_dir.domains_file(project).read_text())
        except (OSError, ValueError):
            return  # first UPS search has not happened yet
        names = sorted({k.split(':')[0].lower() for k in domains})
        path_lower = file_path.lower()
        matched = next((d for d in names if match_domain_to_path(d, path_lower)), None)
        if not matched:
            return

        agent_id = event.get('agent_id') or ''
        last_file = (plugin_data_dir.session_dir(project, sid)
                     / ('domain-last-%s.txt' % plugin_data_dir._safe(agent_id or 'main')))
        try:
            last = last_file.read_text().strip().lower()
        except OSError:
            last = ''
        if matched == last:
            return
        # Claim the domain BEFORE searching: PostToolUse hooks of parallel tool calls run
        # concurrently, so an O_EXCL claim file lets exactly one of them search (v7.1.14 wrote the
        # marker first too). A stale claim (crashed hook) is taken over after 60 s.
        claim = last_file.with_name('domain-claim-%s.lock' % plugin_data_dir._safe(agent_id or 'main'))
        try:
            os.close(os.open(str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            try:
                if time.time() - claim.stat().st_mtime < 60:
                    return
                claim.touch()
            except OSError:
                return
        except OSError:
            return
        try:
            _search_and_inject(event, ctx, project, org, sid, agent_id, last_file, last, matched,
                               file_path, t0)
        finally:
            try:
                claim.unlink()
            except OSError:
                pass
    except Exception as e:
        log_error('PostToolUse', 'ace_domain_shift.main', error=e)  # DESIGN §3.1; exit 0, no stdout


def _search_and_inject(event, ctx, project, org, sid, agent_id, last_file, last, matched,
                       file_path, t0) -> None:
    try:  # re-read under the claim: a concurrent hook may have finished since our first read
        if last_file.read_text().strip().lower() == matched:
            return
    except OSError:
        pass

    query = re.sub(r'\.[^.]*$', '', os.path.basename(file_path.rstrip('/')))
    if not query:
        return  # no usable query

    # G2/§12: main agent anchors on the event prompt_id; a subagent is its own session and
    # uses ITS id from SubagentStart (uuid4 if missing), never the parent's prompt_id.
    if agent_id:
        tsid = (load_task_session_id(sid, agent_id, 'SubagentStop', project_id=project)
                or task_session_id_for(None))
    else:
        tsid = event.get('prompt_id') or load_task_session_id(sid, None, 'Stop', project_id=project) \
            or task_session_id_for(None)
    result, _ms = run_search(query, org=org, project=project, session_id=tsid, top_k=8,
                             timeout=17, hook_event_name='PostToolUse')
    ok = isinstance(result, dict) and not result.get('error')
    if ok:  # a failed/timed-out search must stay retryable (domain not marked visited)
        try:
            last_file.write_text(matched)
        except OSError:
            pass
    patterns = result.get('similar_patterns') if ok else None
    stripped = strip_and_gate(result) if patterns else None
    returned = len((stripped or {}).get('similar_patterns') or [])
    additional = _context(matched, stripped) if returned else None  # trims `stripped` to the injected set
    kept = (stripped or {}).get('similar_patterns') or []
    kept_ids = [p.get('id') for p in kept if isinstance(p, dict) and p.get('id')]
    # search_succeeded = the search itself worked (0 patterns is still a success); hook=PostToolUse (C5)
    log_domain_shift(session_id=sid, from_domain=last, to_domain=matched, file_path=file_path,
                     patterns_found=returned, search_succeeded=ok, project_id=project,
                     hook='PostToolUse', patterns_injected=len(kept_ids),
                     hook_ms=int((time.monotonic() - t0) * 1000), agent_id=agent_id or None)
    if not additional:
        return

    # F-080 credit only what was actually injected (v7.1.11): match by id after the 10k trim.
    keep = set(kept_ids)
    rlog = {}
    for p in patterns:
        rlid = (p.get('match_factors') or {}).get('retrieval_log_id') if isinstance(p, dict) else None
        if p.get('id') in keep and isinstance(rlid, int) and not isinstance(rlid, bool):
            rlog[p['id']] = rlid
    # Keep the task's FIRST retrieval_id (main UPS search): rlog ids merge, but overwriting
    # the rid would attribute main-search log ids to the domain-shift retrieval.
    try:
        from patterns_used_state import _read_state_file, state_file_path
        _sf = state_file_path(sid, agent_id or None, None, project)
        has_rid = _sf.exists() and bool(_read_state_file(_sf)[1])
    except Exception:
        has_rid = False
    append_patterns_used(sid, agent_id or None, kept_ids,
                         retrieval_id=None if has_rid else (result.get('retrieval_id') or None),
                         retrieval_log_ids=rlog, task_session_id=tsid, project_id=project)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": additional}}))


if __name__ == '__main__':
    main()
