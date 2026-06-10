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

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

# ── path bootstrap (same pattern as ace_before_task.py) ─────────────────────
sys.path.insert(0, str(Path(__file__).parent / 'utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

from ace_cli import run_search, check_session_pinning_available  # noqa: E402
from ace_context import get_context                              # noqa: E402
from patterns_used_state import append_patterns_used             # noqa: E402
from validation import is_valid_pattern_id                       # noqa: E402

# ── constants ────────────────────────────────────────────────────────────────
# Fields to keep in patterns before injection (mirrors ace_before_task.py USEFUL_FIELDS)
_USEFUL_FIELDS = {
    'id', 'domain', 'content', 'confidence', 'helpful', 'harmful',
    'section', 'evidence', 'root_cause', 'error_context',
    'cumulative_v15_reward', 'n_hot_pos', 'n_hot_neg', 'isAtRisk',
}

# Maximum query length passed to ACE search (leading semantically-dense portion)
_QUERY_MAX_CHARS = 500

# Tool names that spawn subagents
_SPAWN_TOOL_NAMES = {'Task', 'Agent'}


def _strip_patterns(patterns_response: Dict[str, Any]) -> Dict[str, Any]:
    """Strip server-internal metadata from patterns before injection."""
    if 'similar_patterns' not in patterns_response:
        return patterns_response
    stripped = dict(patterns_response)
    stripped['similar_patterns'] = [
        {k: v for k, v in p.items()
         if k in _USEFUL_FIELDS and (v or k not in ('root_cause', 'error_context'))}
        for p in patterns_response['similar_patterns']
    ]
    return stripped


def _extract_retrieval_ids(patterns_response: Dict[str, Any]):
    """Extract retrieval_id and per-pattern retrieval_log_ids (F-080 compat)."""
    retrieval_id = patterns_response.get('retrieval_id') or None
    retrieval_log_map = {}
    for p in patterns_response.get('similar_patterns', []):
        pid = p.get('id')
        mf = p.get('match_factors') or {}
        rlid = mf.get('retrieval_log_id') if isinstance(mf, dict) else None
        if pid and not isinstance(rlid, bool) and isinstance(rlid, int):
            retrieval_log_map[pid] = rlid
    return retrieval_id, retrieval_log_map


def _read_lines_reversed(path: str):
    """Yield raw lines of a text file in reverse order.

    Reads in chunks from the end so large files are not fully loaded into memory.
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
            while pos > 0:
                read_size = min(chunk_size, pos)
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
            # Yield the final remainder (beginning of file)
            if remainder.strip():
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


def main(event: Optional[Dict[str, Any]] = None) -> None:
    """Process a SubagentStart event.

    Args:
        event: Hook event dict (for testing).  When None, reads from stdin.
    """
    try:
        # Read event
        if event is None:
            event = json.load(sys.stdin)

        # Guard: agent_id must be present and non-null.
        # state_file_path(session, None) resolves to the 'main' suffix, which
        # would corrupt the main-agent state file.
        agent_id = event.get('agent_id')
        if not agent_id:
            sys.exit(0)

        session_id = event.get('session_id', '')
        agent_type = event.get('agent_type', 'subagent')
        transcript_path = event.get('transcript_path', '')

        # Generate a fresh per-task session_id for this subagent.
        # Passed to run_search as the --pin-session value and stored in the state
        # file so SubagentStop's ace_after_task can set trace["session_id"] to this
        # value (correlates search↔learn per-subagent-task, not per conversation).
        task_session_id = str(uuid.uuid4())

        # Derive query from the main session transcript (tail-scan algorithm)
        query = _extract_query_from_transcript(transcript_path, agent_type)
        if not query:
            # No usable query — degrade gracefully, do not search with garbage
            sys.exit(0)

        # Resolve org/project via the same path as ace_before_task (Candidate 1 safe)
        context = get_context()
        if not context:
            sys.exit(0)

        # ── ACE search keyed to subagent's query ──────────────────────────────
        # task_intent is INTENTIONALLY OMITTED — server-authoritative (v7.0.1)
        use_session_pinning = check_session_pinning_available()

        patterns_response = run_search(
            query=query,
            org=context['org'],
            project=context['project'],
            session_id=task_session_id if use_session_pinning else None,
            # task_intent deliberately NOT passed
        )

        if not patterns_response:
            # Search failed or returned nothing — degrade gracefully
            sys.exit(0)

        # Skip error-response dicts
        if isinstance(patterns_response, dict) and patterns_response.get('error'):
            sys.exit(0)

        pattern_list = patterns_response.get('similar_patterns', [])
        if not pattern_list:
            sys.exit(0)

        # ── Persist per-agent patterns_used state ─────────────────────────
        # This is what SubagentStop's load_playbook_used(agent_id=...) will read.
        retrieval_id, retrieval_log_map = _extract_retrieval_ids(patterns_response)
        pattern_ids = [
            p.get('id') for p in pattern_list
            if p.get('id') and is_valid_pattern_id(p.get('id'))
        ]
        if pattern_ids:
            try:
                append_patterns_used(
                    session_id, agent_id, pattern_ids,
                    retrieval_id=retrieval_id,
                    retrieval_log_ids=retrieval_log_map,
                    task_session_id=task_session_id,
                )
            except Exception:
                pass  # non-fatal

        # ── Build additionalContext for the subagent ─────────────────────
        stripped = _strip_patterns(patterns_response)
        pattern_count = len(pattern_list)
        agent_id_attr = f' agent-id="{agent_id}"' if agent_id else ''
        ace_context = (
            f'<ace-patterns-subagent agent-type="{agent_type}"{agent_id_attr}>\n'
            f'{json.dumps(stripped)}\n'
            f'</ace-patterns-subagent>'
        )

        output = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": ace_context,
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
    except Exception:
        # Never block the subagent — swallow all exceptions
        sys.exit(0)


if __name__ == '__main__':
    main()
