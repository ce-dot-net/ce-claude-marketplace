#!/usr/bin/env python3
"""
ACE SubagentStart Hook - Per-Subagent Search at Agent Spawn

Fires when Claude Code spawns a subagent/workflow-agent.  Runs an ACE search
keyed to the subagent's own agent_id using a query derived from the main session
transcript, then writes patterns_used_state so the SubagentStop learn's
playbook_used overlaps those retrieval rows (enables per-agent crediting —
server candidate 3).

CC 2.1.170+ event shape (NO 'task' field):
  {
    "hook_event_name": "SubagentStart",
    "session_id": "...",
    "agent_id": "subagent-xyz",
    "agent_type": "coder|Explore|Plan|general-purpose|...",
    "cwd": "/absolute/path",
    "transcript_path": "/path/to/main/session.jsonl"
  }

Query derivation — TAIL-SCAN ALGORITHM:
  1. Open transcript_path (main session JSONL). Read lines in reverse — do NOT
     load the whole file into memory.
  2. Parse each line as JSON. On parse failure, skip.
  3. Find blocks with type='tool_use' and name in ('Task', 'Agent').
  4. TYPE-MATCH: return the first (most-recent) block whose
     block.input.subagent_type == event.agent_type and prompt is non-empty.
  5. GLOBAL FALLBACK: if no type-matched block exists, return the most-recent
     Task/Agent block with a non-empty prompt regardless of subagent_type.
  6. If still nothing: sys.exit(0) silently — no garbage query.
  7. Truncate prompt to ~500 chars for the query.

Design constraints:
  - task_intent is NEVER passed (server-authoritative, consistent with v7.0.1).
  - org/project resolved via get_context() — same path as ace_before_task.
  - Never blocks the subagent: all failures are caught and swallowed.
  - Fires unconditionally for every subagent (no tool-type or domain-file gates).
  - Writes per-agent patterns_used state keyed by agent_id so SubagentStop's
    load_playbook_used(agent_id=...) can find it.

Output JSON shape (CC SubagentStart additionalContext):
  {
    "hookSpecificOutput": {
      "hookEventName": "SubagentStart",
      "additionalContext": "<ace-patterns-subagent agent-id=...>...</ace-patterns-subagent>"
    }
  }
"""

import glob
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

# ── path bootstrap (same pattern as ace_before_task.py) ─────────────────────
sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

from ace_cli import run_search  # noqa: E402
import ace_search_cache  # noqa: E402
from ace_context import get_context                              # noqa: E402
from patterns_used_state import append_patterns_used, injected_contents, load_state  # noqa: E402
import plugin_data_dir                                           # noqa: E402
from ace_relevance_logger import log_search, log_error, log_search_skipped           # noqa: E402
from ace_pattern_render import render_patterns, render_cohort, render_compact_all  # noqa: E402

# ── constants ────────────────────────────────────────────────────────────────
# Maximum query length passed to ACE search (leading semantically-dense portion)
_QUERY_MAX_CHARS = 500

# Tool names that spawn subagents
_SPAWN_TOOL_NAMES = {'Task', 'Agent'}

# Parent-transcript reverse scan reads at most this many trailing bytes (critic T7/T12).
_SCAN_MAX_BYTES = 2 * 1024 * 1024

# Workflow agents get a fixed harness preamble ending in this marker; with the
# 500-char cap it would make every Workflow query identical, so drop it.
_WORKFLOW_MARKER = 'The computed task text follows:'


def _read_lines_reversed(path: str):
    """Yield raw lines of a text file in reverse order.

    Reads in chunks from the end, at most the last _SCAN_MAX_BYTES (2 MB).
    Yields stripped non-empty strings.
    """
    chunk_size = 8192
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)  # seek to end
            file_size = f.tell()
            if file_size == 0:
                return

            remainder = b''
            pos = file_size
            lowest = max(0, file_size - _SCAN_MAX_BYTES)
            while pos > lowest:
                read_size = min(chunk_size, pos - lowest)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)
                # Prepend remainder from previous iteration
                chunk = chunk + remainder
                # Split on newlines
                lines = chunk.split(b'\n')
                # The first fragment may be incomplete — save it as remainder
                remainder = lines[0]
                # Yield complete lines in reverse order (last first)
                for line in reversed(lines[1:]):
                    stripped = line.strip()
                    if stripped:
                        yield stripped.decode('utf-8', errors='replace')
            # Yield the final remainder only when we reached the file start
            # (otherwise it is a partial line cut by the 2 MB bound).
            if lowest == 0 and remainder.strip():
                yield remainder.strip().decode('utf-8', errors='replace')
    except (OSError, IOError):
        return


def _extract_query_from_transcript(transcript_path: str, agent_type: str) -> Optional[str]:
    """Tail-scan the main session JSONL to find the best query for this subagent.

    Returns a non-empty string (possibly truncated) or None if nothing usable found.

    Algorithm:
      1. Scan lines in reverse (most-recent first).
      2. For each JSON line, look for content blocks with type='tool_use' and
         name in ('Task', 'Agent').
      3. TYPE-MATCH PASS: return the first hit where block.input.subagent_type
         matches agent_type (case-insensitive) and prompt/description is non-empty.
      4. GLOBAL PASS: if no type match after full scan, return the first hit with
         any non-empty prompt/description regardless of subagent_type.
      5. Truncate to _QUERY_MAX_CHARS.
    """
    if not transcript_path:
        return None

    best_global: Optional[str] = None  # best from global pass (most-recent any-type)

    for raw_line in _read_lines_reversed(transcript_path):
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if not isinstance(entry, dict):
            continue

        # Extract content list from message
        message = entry.get('message') or {}
        if not isinstance(message, dict):
            continue
        content = message.get('content')
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get('type') != 'tool_use':
                continue
            if block.get('name') not in _SPAWN_TOOL_NAMES:
                continue

            tool_input = block.get('input') or {}
            if not isinstance(tool_input, dict):
                continue

            # Extract prompt (prefer 'prompt', fall back to 'description')
            prompt = tool_input.get('prompt') or tool_input.get('description') or ''
            if not prompt:
                continue

            prompt = str(prompt).strip()
            if not prompt:
                continue

            # TYPE-MATCH check (case-insensitive)
            block_type = str(tool_input.get('subagent_type') or '').strip()
            if block_type.lower() == agent_type.lower():
                # Best match: type matches — return immediately (most-recent wins)
                return prompt[:_QUERY_MAX_CHARS]

            # Track global fallback (most-recent any-type, first encountered in reverse scan)
            if best_global is None:
                best_global = prompt

    # No type-matched block found — use global fallback if available
    if best_global:
        return best_global[:_QUERY_MAX_CHARS]

    return None


_SYSREM = re.compile(r'<system-reminder>.*?</system-reminder>', re.S)


def _query_from_own_transcript(transcript_path: str, session_id: str, agent_id: str) -> Optional[str]:
    """First user message of this agent's own transcript, if it exists yet.

    Layout (observed): <dir of main transcript>/<session_id>/subagents/**/agent-<agent_id>.jsonl
    (Workflow agents live under subagents/workflows/<wf_id>/). Workflow agent
    prompts are NOT Agent/Task tool_use blocks in the main transcript.
    """
    if not (transcript_path and session_id and agent_id):
        return None
    # direct path first, then workflows/<wf_id>/ (no recursive walk: O(n) per spawn in fan-out)
    base = os.path.join(glob.escape(os.path.dirname(transcript_path)), glob.escape(session_id), 'subagents')
    name = 'agent-%s.jsonl' % glob.escape(agent_id)
    for path in (glob.glob(os.path.join(base, name)) or glob.glob(os.path.join(base, '*', name))
                 or glob.glob(os.path.join(base, '*', '*', name))):
        try:
            with open(path, 'rb') as f:
                head = f.read(65536).decode('utf-8', errors='replace')
        except OSError:
            continue
        for line in head.splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            msg = entry.get('message') if isinstance(entry, dict) else None
            if not isinstance(msg, dict) or msg.get('role') != 'user':
                continue
            content = msg.get('content')
            if isinstance(content, list):
                content = ' '.join(b.get('text', '') for b in content
                                   if isinstance(b, dict) and b.get('type') == 'text')
            if not isinstance(content, str):
                continue
            content = _SYSREM.sub('', content)
            if _WORKFLOW_MARKER in content:
                content = content.split(_WORKFLOW_MARKER, 1)[1]
            content = content.strip()
            if content:
                return content[:_QUERY_MAX_CHARS]
            continue  # empty after stripping (reminder-only entry): try the next user entry
    return None


def _consume_stash(project, sid, prompt_id, agent_type) -> Optional[str]:
    """G1: prompt written by the PreToolUse Agent stash for this prompt_id + agent_type;
    deleted once read. None when absent (caller falls back to the transcript scan)."""
    if not prompt_id:
        return None
    try:
        f = plugin_data_dir.agent_prompt_file(project, sid, prompt_id, agent_type)
        data = json.loads(f.read_text())
        if (data or {}).get('ambiguous'):
            return None  # tombstone stays: later same-type spawns of this prompt also fall back
        f.unlink()
        q = str((data or {}).get('prompt') or (data or {}).get('description') or '').strip()
        return q[:_QUERY_MAX_CHARS] or None
    except (OSError, ValueError, AttributeError):
        return None


def _parent_task_prompt(session_id, project, prompt_id) -> Optional[str]:
    """P10: the human prompt of the task that spawned this workflow, from the parent's MAIN state - only when
    that state belongs to the same prompt_id (a stale state of an earlier prompt must not become the query)."""
    if not prompt_id:
        return None
    st = load_state(session_id, None, 'Stop', project_id=project)
    q = str(st.get('user_prompt') or '').strip()
    return q[:_QUERY_MAX_CHARS] if q and st.get('task_session_id') == prompt_id else None


def main(event: Optional[Dict[str, Any]] = None) -> None:
    """Process a SubagentStart event.

    Args:
        event: Hook event dict (for testing).  When None, reads from stdin.
    """
    try:
        t_start = time.monotonic()
        # Read event
        if event is None:
            event = json.load(sys.stdin)
            # v8 shims never cd (DESIGN §3.1): resolve the project from the hook cwd.
            _cwd = event.get('cwd')
            if _cwd and os.path.isdir(_cwd):
                os.chdir(_cwd)

        # Guard: agent_id must be present and non-null.
        # state_file_path(session, None) resolves to the 'main' suffix, which
        # would corrupt the main-agent state file.
        agent_id = event.get('agent_id')
        if not agent_id:
            sys.exit(0)

        session_id = event.get('session_id', '')
        agent_type = event.get('agent_type', 'subagent')
        transcript_path = event.get('transcript_path', '')

        context = get_context()
        if not context:
            sys.exit(0)  # no project: nothing to search, and no state may land in 'default/'
        project = context['project']

        # §4: per-session disabled flag under plugin data.
        if plugin_data_dir.is_disabled(project, plugin_data_dir.resolve_session_id(event)) or plugin_data_dir.is_mod_active(project, plugin_data_dir.resolve_session_id(event)):
            sys.exit(0)

        # Resume / teammate re-wake re-fires SubagentStart (cc_hooks_reference.md:2549):
        # this agent already has a task_session_id -> keep it, no new search. CC re-injects
        # a re-run's context only if the earlier copy is gone, e.g. after the subagent
        # auto-compacted (:2582), and dedupes otherwise, so re-emit the stored context.
        # (SubagentStop reaps the state, so an agent resumed after stopping searches afresh.)
        prior = load_state(session_id, agent_id, 'SubagentStop', project_id=project)
        if prior.get('task_session_id'):
            if prior.get('rendered_context'):
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": prior['rendered_context']}}))
            sys.exit(0)

        # Generate a fresh per-task session_id for this subagent.
        # Passed to run_search as the --pin-session value and stored in the state
        # file so SubagentStop's ace_after_task can set trace["session_id"] to this
        # value (correlates search↔learn per-subagent-task, not per conversation).
        # DESIGN §12: every subagent is its own ACE session -> fresh uuid4, never the parent's
        # prompt_id (that stays only as parent_task_id).
        task_session_id = str(uuid.uuid4())
        parent_task_id = event.get('prompt_id') or None

        # §16 P7: a fork (default-on since CC 2.1.302) inherits the parent's context INCLUDING the injected
        # block: own pin + state so SubagentStop learns normally, but no second search / injection.
        if agent_type == 'fork' and os.environ.get('ACE_SUBAGENT_INJECT_FORKS') != '1':
            try:
                append_patterns_used(session_id, agent_id, [], task_session_id=task_session_id,
                                     hook_event_name='SubagentStart', project_id=project,
                                     parent_task_id=parent_task_id)
                log_search_skipped('SubagentStart', 'fork_inherits_context', session_id, project)
            except Exception as e:
                log_error('SubagentStart', 'ace_subagent_start.fork', session_id, project, e)
            sys.exit(0)

        # SubagentStart input has no prompt field (cc_hooks_reference.md:2553-2566):
        # own transcript first (Workflow agents), else bounded parent-transcript tail scan.
        # query_source: only stash/own_transcript are exact; parent_scan can be a sibling's prompt.
        query, query_source = None, None
        sources = [('stash', lambda: _consume_stash(project, plugin_data_dir.resolve_session_id(event),
                                                    event.get('prompt_id'), agent_type)),
                   ('own_transcript', lambda: _query_from_own_transcript(transcript_path, session_id, agent_id)),
                   ('parent_scan', lambda: _extract_query_from_transcript(transcript_path, agent_type))]
        if agent_type == 'workflow-subagent':  # §16 P10: no Agent stash fires; parent_scan would pick a sibling's prompt
            sources = [sources[1], ('parent_task', lambda: _parent_task_prompt(session_id, project, parent_task_id)),
                       sources[2]]
        for src, fn in sources:
            query = fn()
            if query:
                query_source = src
                break

        # Persist the per-task anchor IMMEDIATELY (before search / early-exits) so
        # SubagentStop's load_task_session_id finds it even if the search returns 0
        # patterns, fails, or errors.  The later append_patterns_used call (inside
        # `if pattern_ids:`) will merge pattern_ids + retrieval_id into this same
        # file via the normal merge logic.
        try:
            append_patterns_used(session_id, agent_id, [], task_session_id=task_session_id,
                                 user_prompt=query, hook_event_name='SubagentStart',
                                 project_id=project, parent_task_id=parent_task_id,
                                 query_source=query_source)
        except Exception as e:
            log_error('SubagentStart', 'ace_subagent_start.anchor', session_id, project, e)

        if not query:
            # No usable query — degrade gracefully, do not search with garbage
            sys.exit(0)

        # ── ACE search keyed to subagent's query ──────────────────────────────
        # task_intent is INTENTIONALLY OMITTED — server-authoritative (v7.0.1)
        # §32: a real cached hit (same project, exact query, < 15 min, not yet served to this agent) skips the spawn;
        # it carries the cached retrieval_id, so the trace is credited from that search.
        patterns_response = ace_search_cache.reuse_get(context['project'], 'subagent', query, agent_id)
        cache_hit = patterns_response is not None
        if not cache_hit:
            patterns_response, _search_ms = run_search(
                query=query,
                org=context['org'],
                project=context['project'],
                session_id=task_session_id,
                timeout=25,
                hook_event_name='SubagentStart',
                # task_intent deliberately NOT passed
            )
            ace_search_cache.reuse_put(context['project'], 'subagent', query, agent_id, patterns_response)

        if not patterns_response:
            # Search failed or returned nothing — degrade gracefully
            sys.exit(0)

        # Skip error-response dicts
        if isinstance(patterns_response, dict) and patterns_response.get('error'):
            sys.exit(0)

        pattern_list = patterns_response.get('similar_patterns', [])
        if not pattern_list:
            sys.exit(0)

        # ── A/B cohort (§28): the conversation's arm (CC session_id, shared with the main agent), never the pin.
        _cohort = render_cohort(session_id)

        retrieval_id = patterns_response.get('retrieval_id') or None
        agent_id_attr = f'agent-type="{agent_type}" agent-id="{agent_id}"' if agent_id else f'agent-type="{agent_type}"'
        pattern_count = len(pattern_list)

        # ── Render dispatch by cohort ─────────────────────────────────────────
        if _cohort == 'control':
            # Control arm: search ran (retrieval_id logged), inject ZERO patterns.
            ace_context = None
            pattern_ids = []
            retrieval_log_map = {}
            try:
                append_patterns_used(session_id, agent_id, [],
                                     retrieval_id=retrieval_id,
                                     task_session_id=task_session_id, project_id=project, render_variant=_cohort)
            except Exception as e:
                log_error('SubagentStart', 'ace_subagent_start.control', session_id, project, e)

        elif _cohort == 'compact':
            # Compact arm: all patterns as compact one-liners, total ≤ 9500 chars.
            ace_context, pattern_ids, _, retrieval_log_map = render_compact_all(
                patterns_response,
                tag='ace-patterns-subagent',
                attrs=agent_id_attr,
            )
            if pattern_ids:
                try:
                    append_patterns_used(
                        session_id, agent_id, pattern_ids,
                        retrieval_id=retrieval_id,
                        retrieval_log_ids=retrieval_log_map,
                        task_session_id=task_session_id,
                        project_id=project, rendered_context=ace_context, render_variant=_cohort,
                        pattern_contents=injected_contents(patterns_response.get('similar_patterns'), pattern_ids),
                    )
                except Exception as e:
                    log_error('SubagentStart', 'ace_subagent_start.state', session_id, project, e)

        else:
            # Budget arm (default): existing budget-verbatim render (unchanged).
            ace_context, pattern_ids, _, retrieval_log_map = render_patterns(
                patterns_response,
                tag='ace-patterns-subagent',
                attrs=agent_id_attr,
            )
            if pattern_ids:
                try:
                    append_patterns_used(
                        session_id, agent_id, pattern_ids,
                        retrieval_id=retrieval_id,
                        retrieval_log_ids=retrieval_log_map,
                        task_session_id=task_session_id,
                        project_id=project, rendered_context=ace_context, render_variant=_cohort,
                        pattern_contents=injected_contents(patterns_response.get('similar_patterns'), pattern_ids),
                    )
                except Exception as e:
                    log_error('SubagentStart', 'ace_subagent_start.state', session_id, project, e)

        log_search(hook='SubagentStart', session_id=session_id, user_prompt=query,
                   search_query=query, patterns_returned=pattern_count,
                   patterns_injected=len(pattern_ids),
                   hook_ms=int((time.monotonic() - t_start) * 1000),
                   project_id=context['project'], org_id=context['org'],
                   agent_type=agent_type, render_cohort=_cohort, parent_task_id=parent_task_id,
                   query_source=query_source, cache_hit=cache_hit)

        if ace_context is not None:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": ace_context,
                }
            }
        else:
            # Control arm: no additionalContext
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                }
            }
        # Optionally surface a user-visible message (not required by SubagentStart)
        if pattern_count > 0:
            top_domains = list({p.get('domain', '') for p in pattern_list if p.get('domain')})[:3]
            domains_str = ', '.join(top_domains) if top_domains else 'general'
            output["systemMessage"] = (
                f"[ACE] {pattern_count} patterns loaded for subagent "
                f"({domains_str})"
            )

        print(json.dumps(output))
        sys.exit(0)

    except SystemExit:
        raise
    except Exception as e:
        # Never block the subagent: log (DESIGN §3.1), exit 0, no stdout
        log_error('SubagentStart', 'ace_subagent_start.main', error=e)
        sys.exit(0)


if __name__ == '__main__':
    main()
