#!/usr/bin/env python3
"""ACE domain-shift hook (v8): PostToolUse Read|Glob|Grep, the ONE domain-shift path.

Replaces the PreToolUse bash wrapper and the old PostToolUse bash inject (DESIGN §3, §6 WP-D).
When the tool's path enters a domain (from the last UPS search, domains.json, C3) that this
agent has not been in, search `--top-k 8` (server-side bound for the per-tool hot path) with
the file basename as query, strip-and-gate, record the injected ids (C1/F-080) and emit
PostToolUse additionalContext (cc_hooks_reference.md:2220-2245), capped at 10,000 chars.
No domain filter and no intent hint (server owns both; domain_match anti-predicts relevance).
"""
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

import plugin_data_dir                                    # noqa: E402
from ace_cli import run_search                            # noqa: E402
from ace_context import get_context                       # noqa: E402
from ace_relevance_logger import log_domain_shift         # noqa: E402
from patterns_used_state import (append_patterns_used, load_task_session_id,  # noqa: E402
                                 strip_and_gate)

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
    """Wrap in the domain-shift tag, dropping trailing patterns until <= 10,000 chars."""
    while True:
        ctx = '<ace-patterns-domain-shift domain="%s">%s</ace-patterns-domain-shift>' % (
            domain, json.dumps(stripped))
        if len(ctx) <= _CAP or not stripped.get('similar_patterns'):
            return ctx[:_CAP]
        stripped['similar_patterns'] = stripped['similar_patterns'][:-1]
        stripped['count'] = len(stripped['similar_patterns'])


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get('tool_name') not in _TOOLS:
            return
        ti = event.get('tool_input') or {}
        file_path = ti.get('file_path') or ti.get('path') or ti.get('pattern')
        if not file_path or not isinstance(file_path, str):
            return
        cwd = event.get('cwd')
        if cwd and os.path.isdir(cwd):
            os.chdir(cwd)  # v8 shims never cd (DESIGN §3.1); logger/context resolve from cwd
        ctx = get_context()
        if not ctx:
            return
        project, org = ctx['project'], ctx['org']
        sid = plugin_data_dir.resolve_session_id(event)
        if plugin_data_dir.disabled_flag(project, sid).exists():
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
        try:
            last_file.write_text(matched)
        except OSError:
            pass
        if matched == last:
            return

        query = re.sub(r'\.[^.]*$', '', os.path.basename(file_path.rstrip('/')))
        if not query:
            return  # no usable query

        tsid = (load_task_session_id(sid, agent_id or None, 'SubagentStop' if agent_id else 'Stop',
                                     project_id=project) or str(uuid.uuid4()))
        result, _ms = run_search(query, org=org, project=project, session_id=tsid, top_k=8,
                                 timeout=10, hook_event_name='PostToolUse')
        patterns = (result or {}).get('similar_patterns') if isinstance(result, dict) \
            and not result.get('error') else None
        stripped = strip_and_gate(result) if patterns else None
        found = len((stripped or {}).get('similar_patterns') or [])
        log_domain_shift(session_id=sid, from_domain=last, to_domain=matched, file_path=file_path,
                         patterns_found=found, search_succeeded=bool(found), project_id=project)
        if not found:
            return

        rlog = {}
        for p in patterns:
            rlid = (p.get('match_factors') or {}).get('retrieval_log_id') if isinstance(p, dict) else None
            if p.get('id') and isinstance(rlid, int) and not isinstance(rlid, bool):
                rlog[p['id']] = rlid
        append_patterns_used(sid, agent_id or None, [p.get('id') for p in patterns if p.get('id')],
                             retrieval_id=result.get('retrieval_id') or None,
                             retrieval_log_ids=rlog, task_session_id=tsid, project_id=project)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": _context(matched, stripped)}}))
    except Exception:
        pass  # never fail the tool call


if __name__ == '__main__':
    main()
