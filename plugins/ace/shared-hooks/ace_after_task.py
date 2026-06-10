#!/usr/bin/env python3
"""
ACE After Task Hook - PostToolUse Accumulation Architecture (v5.3.0)

CRITICAL CHANGE: We NO LONGER parse transcripts!

Per ACE Research Paper (arXiv:2510.04618v1):
- Page 5: "Generator produces reasoning trajectories"
- Page 7: "leveraging natural execution feedback"
- Page 19: "FULL AGENT-ENVIRONMENT TRAJECTORY"

Old approach (broken):
  - Stop/PreCompact only provide transcript_path (no tool data)
  - Transcript parsing is lossy and unreliable
  - tool_result messages confuse task boundaries

New approach (v5.3.0):
  - PostToolUse hook appends EVERY tool call to SQLite (ground truth)
  - Stop hook queries SQLite to build trajectory
  - Trajectory contains REAL tool calls with inputs/outputs
  - No transcript parsing required!

Architecture:
  PostToolUse → append to SQLite
  Stop → query SQLite → build trajectory → send to server → clear SQLite
"""

import json
import sys
import subprocess
import os
from pathlib import Path
from datetime import datetime

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_context import get_context
from ace_cli import recall_session
from utils.git_utils import get_git_context, detect_commits_in_session
from ace_relevance_logger import log_execution_metrics, log_hook_error
from patterns_used_state import (load_playbook_used, reap_patterns_used,
                                 load_retrieval_ids, load_task_session_id)

# Add plugin utils to path for validation
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))
from validation import is_valid_pattern_id

# Import re at module level for quality filters
import re as regex_module
import time

# CLI command detection
CLI_CMD = 'ace-cli'


def is_trivial_task(task_description: str) -> bool:
    """
    Filter out trivial tasks that shouldn't trigger learning.

    Per ACE Research Paper: Learning should only occur with "meaningful execution feedback"
    Trivial tasks like status checks, simple queries, or ACE commands don't qualify.

    Returns True if task is trivial (should be SKIPPED).
    """
    trivial_patterns = [
        # ACE commands - CRITICAL: These were being learned as garbage!
        r'<command-message>ace[:\-]',
        r'ace:ace-',
        r'/ace-',
        r'ace-status',
        r'ace-patterns',
        r'ace-search',
        r'ace-learn',
        r'ace-configure',
        r'ace-bootstrap',
        r'ace-clear',
        r'ace-doctor',
        r'ace-export',
        r'ace-import',
        r'ace-top',

        # Simple queries (not implementation work)
        r'^(what|how|why|where|when|can you|could you|would you)\s.*\?$',
        r'^(list|show|display|print|view|see)\s',
        r'^(check|status|version|help|info)\s*$',

        # Git status checks (read-only, no learning value)
        r'git\s+(status|log|diff|branch|show)\s*$',

        # File listing (read-only)
        r'^ls\s',
        r'^cat\s',
        r'^head\s',
        r'^tail\s',

        # Greetings
        r'^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure)\s*$',

        # System messages
        r'caveat:.*messages below were generated',
        r'^plugin\s*$',
        r'/plugin',
    ]

    task_lower = task_description.lower()
    for pattern in trivial_patterns:
        if regex_module.search(pattern, task_lower, regex_module.IGNORECASE):
            return True
    return False


def has_substantial_work_from_accumulated(tools: list) -> bool:
    """
    Check for substantial work using accumulated tool data.

    GROUND TRUTH - no semantic analysis needed!

    Per ACE Research Paper: Requires "meaningful execution feedback"
    State-changing tools (Edit, Write, Bash, etc.) = meaningful work.

    Args:
        tools: List of tuples (tool_name, tool_input, tool_response, tool_use_id)

    Returns:
        True if ANY state-changing tool was used
    """
    state_changing = ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit']

    for tool_name, _, _, _, *_ in tools:
        if any(t in tool_name for t in state_changing):
            return True

    return False


def summarize_tool_action(tool_name: str, tool_input: dict) -> str:
    """
    Create human-readable action summary for tool call.

    Per ACE Research Paper Page 19: Trajectory should show what tool did.
    """
    if tool_name == 'Edit':
        file_path = tool_input.get('file_path', 'unknown file')
        return f"Edited {Path(file_path).name}"

    elif tool_name == 'Write':
        file_path = tool_input.get('file_path', 'unknown file')
        return f"Wrote {Path(file_path).name}"

    elif tool_name == 'Read':
        file_path = tool_input.get('file_path', 'unknown file')
        return f"Read {Path(file_path).name}"

    elif tool_name == 'Bash':
        command = tool_input.get('command', tool_input.get('description', ''))
        if len(command) > 60:
            command = command[:60] + '...'
        return f"Ran: {command}"

    elif tool_name == 'Grep':
        pattern = tool_input.get('pattern', '')
        return f"Searched for: {pattern}"

    elif tool_name == 'Glob':
        pattern = tool_input.get('pattern', '')
        return f"Found files matching: {pattern}"

    elif tool_name == 'Task':
        description = tool_input.get('description', tool_input.get('prompt', ''))
        if len(description) > 60:
            description = description[:60] + '...'
        return f"Spawned task: {description}"

    elif tool_name == 'TodoWrite':
        return "Updated todo list"

    elif tool_name.startswith('mcp__'):
        # MCP tool call
        return f"Called MCP: {tool_name}"

    else:
        return f"{tool_name}"


def summarize_tool_response(tool_name: str, tool_response: dict) -> str:
    """
    Create human-readable result summary for tool response.

    Per ACE Research Paper Page 19: Trajectory should show execution feedback.
    """
    if isinstance(tool_response, str):
        if len(tool_response) > 100:
            return tool_response[:100] + '...'
        return tool_response

    # Handle error responses
    if tool_response.get('error'):
        return f"Error: {tool_response.get('error', 'Unknown error')[:100]}"

    if tool_response.get('stderr'):
        return f"Stderr: {tool_response.get('stderr', '')[:100]}"

    # Handle success responses
    if tool_name in ['Edit', 'Write']:
        success = tool_response.get('success', False)
        return "Success" if success else "Failed"

    elif tool_name == 'Read':
        content = tool_response.get('content', '')
        lines = content.count('\n') + 1 if content else 0
        return f"Read {lines} lines"

    elif tool_name == 'Bash':
        stdout = tool_response.get('stdout', '')
        exit_code = tool_response.get('exit_code', tool_response.get('exitCode', 0))
        if exit_code != 0:
            return f"Exit code {exit_code}"
        if stdout:
            first_line = stdout.split('\n')[0]
            if len(first_line) > 60:
                first_line = first_line[:60] + '...'
            return first_line or "Success"
        return "Success"

    elif tool_name in ['Grep', 'Glob']:
        # Files found
        files = tool_response.get('files', [])
        if isinstance(files, list):
            return f"Found {len(files)} files"
        return str(tool_response)[:100]

    elif tool_name == 'Task':
        return "Task completed"

    else:
        # Generic response summary
        response_str = str(tool_response)
        if len(response_str) > 100:
            return response_str[:100] + '...'
        return response_str


def parse_agent_transcript(path: str) -> list:
    """
    Parse a per-agent transcript JSONL file (CC's agent_transcript_path).

    CC writes a dedicated transcript per subagent at agent_transcript_path.
    Each line is a JSON message; tool_use / tool_result blocks live inside
    message.content[].

    Returns:
        List of 8-tuples compatible with get_session_tools (timing fields are
        not available from the transcript, so they are padded with None):
        (tool_name, tool_input_json, tool_response_json, tool_use_id, agent_id,
         start_ms, end_ms, duration_ms)

    Raises:
        Exceptions are propagated to caller so it can fall back.
    """
    tool_uses = {}   # tool_use_id -> (tool_name, tool_input_json)
    tool_results = {}  # tool_use_id -> tool_response_json
    order = []  # preserve encounter order by tool_use_id

    transcript_file = Path(path).expanduser()
    with open(transcript_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = entry.get('message') or {}
            content = message.get('content')
            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get('type')
                if btype == 'tool_use':
                    tu_id = block.get('id') or ''
                    tname = block.get('name', '')
                    tinput = block.get('input', {})
                    try:
                        tinput_json = json.dumps(tinput)
                    except (TypeError, ValueError):
                        tinput_json = '{}'
                    if tu_id and tu_id not in tool_uses:
                        tool_uses[tu_id] = (tname, tinput_json)
                        order.append(tu_id)
                elif btype == 'tool_result':
                    tu_id = block.get('tool_use_id') or ''
                    tcontent = block.get('content', '')
                    if isinstance(tcontent, list):
                        parts = []
                        for c in tcontent:
                            if isinstance(c, dict) and c.get('type') == 'text':
                                parts.append(c.get('text', ''))
                            elif isinstance(c, str):
                                parts.append(c)
                        tresp = {'content': '\n'.join(parts)}
                        if block.get('is_error'):
                            tresp['error'] = tresp.get('content', '')
                        try:
                            tresp_json = json.dumps(tresp)
                        except (TypeError, ValueError):
                            tresp_json = '{}'
                    elif isinstance(tcontent, str):
                        payload = {'content': tcontent}
                        if block.get('is_error'):
                            payload['error'] = tcontent
                        tresp_json = json.dumps(payload)
                    else:
                        try:
                            tresp_json = json.dumps(tcontent)
                        except (TypeError, ValueError):
                            tresp_json = '{}'
                    if tu_id:
                        tool_results[tu_id] = tresp_json

    # Derive agent_id from filename: agent-{uuid}.jsonl
    agent_id = None
    try:
        stem = Path(path).stem
        if stem.startswith('agent-'):
            agent_id = stem[len('agent-'):] or None
    except Exception:
        agent_id = None

    results = []
    for tu_id in order:
        tname, tinput_json = tool_uses[tu_id]
        tresp_json = tool_results.get(tu_id, '{}')
        # 8-tuple to match get_session_tools(); transcript has no timing data,
        # so start_ms/end_ms/duration_ms are None (build_trajectory skips None).
        results.append((tname, tinput_json, tresp_json, tu_id, agent_id, None, None, None))
    return results


def build_trajectory_from_accumulated_tools(session_id: str, working_dir: str = None, agent_transcript_path: str = None) -> tuple:
    """
    Build REAL trajectory from PostToolUse accumulated data or per-agent transcript.

    Per-agent transcript (CC's agent_transcript_path) is preferred when present
    because the session-wide SQLite accumulator cross-contaminates subagents.

    Args:
        session_id: Claude Code session ID
        working_dir: Project working directory (optional)
        agent_transcript_path: CC per-agent transcript path (optional)

    Returns:
        Tuple of (trajectory_list, tools_list)
    """
    # Import accumulator functions
    sys.path.insert(0, str(Path(__file__).parent))
    from ace_tool_accumulator import get_session_tools, clear_session

    tools = None
    if agent_transcript_path:
        try:
            p = Path(agent_transcript_path).expanduser()
            if p.exists():
                tools = parse_agent_transcript(agent_transcript_path)
        except Exception as _e:
            try:
                log_hook_error(
                    location="agent_transcript_parse_failed",
                    session_id=session_id,
                    project_id=None,
                    hook="Stop",
                    error=_e,
                    extra={"agent_transcript_path": agent_transcript_path},
                )
            except Exception:
                pass
            tools = None

    if tools is None:
        tools = get_session_tools(session_id, working_dir)
    trajectory = []

    for i, (tool_name, tool_input_json, tool_response_json, tool_use_id, agent_id, start_ms, end_ms, duration_ms) in enumerate(tools, 1):
        try:
            tool_input = json.loads(tool_input_json) if tool_input_json else {}
        except json.JSONDecodeError:
            tool_input = {}

        try:
            tool_response = json.loads(tool_response_json) if tool_response_json else {}
        except json.JSONDecodeError:
            tool_response = {}

        # Build trajectory step with REAL data
        step = {
            "step": i,
            "tool": tool_name,
            "action": summarize_tool_action(tool_name, tool_input),
            "result": summarize_tool_response(tool_name, tool_response),
        }
        # v6.5.0 Item #1: include timing fields when available (SDK confirmed all 3 additive)
        if start_ms is not None:
            step["start_ms"] = start_ms
        if end_ms is not None:
            step["end_ms"] = end_ms
        if duration_ms is not None:
            step["duration_ms"] = duration_ms
        trajectory.append(step)

    return trajectory, tools


def skip_learning(reason, event=None):
    """
    Skip learning with user feedback.

    Per ACE Research Paper: Users should understand when learning is skipped.

    v6.6.7: also reaps this agent's patterns-used state file (per-agent-pure)
    so a skipped (sub)agent doesn't leave an orphan until the SessionEnd GC.
    This path fires NO learn, so reaping here can never strip IDs from a trace
    that is sent to the server. Best-effort: a reap failure never breaks the
    skip. The suffix is derived from `event` because agent_id is not yet in
    scope at the skip sites (they run before it is computed).
    """
    if os.environ.get('ACE_DEBUG_HOOKS') == '1':
        with open('/tmp/ace_hook_debug.log', 'a') as f:
            f.write(f"ACE: Skipping learning - {reason}\n")
            if event:
                f.write(f"  Event: {json.dumps(event, default=str)[:500]}\n")

    if event:
        try:
            reap_patterns_used(
                event.get('session_id', ''),
                event.get('agent_id') or None,
                event.get('hook_event_name', 'Stop'),
            )
        except Exception:
            pass  # reaping is best-effort; never break the skip path

    return {
        "continue": True,
        "systemMessage": f"[ACE] Learning skipped: {reason}"
    }


def get_user_prompt_from_transcript(transcript_path: str) -> str:
    """
    Extract the user's prompt from transcript for task description.

    This is the ONLY transcript parsing we do - just to get the user's request.
    All tool execution data comes from accumulated tools.
    """
    try:
        transcript_file = Path(transcript_path).expanduser()
        if not transcript_file.exists():
            return "No user prompt found"

        all_entries = []
        with open(transcript_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    all_entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Find LAST user message (task start) - search backwards
        # Skip tool_result messages - they have role=user but are not user prompts
        for i in range(len(all_entries) - 1, -1, -1):
            message = all_entries[i].get('message', {})
            if message.get('role') == 'user':
                content = message.get('content', '')

                if isinstance(content, list):
                    # Skip tool_result messages
                    has_tool_result = any(
                        isinstance(b, dict) and b.get('type') == 'tool_result'
                        for b in content
                    )
                    if has_tool_result:
                        continue

                    # Extract text content
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    user_prompt = '\n'.join(text_parts)
                    if user_prompt.strip():
                        return user_prompt[:2000]

                elif isinstance(content, str) and len(content.strip()) > 10:
                    return content[:2000]

        return "No user prompt found"

    except Exception as e:
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"get_user_prompt_from_transcript error: {e}\n")
        return "No user prompt found"


def _resolve_effort_level(event):
    """Resolve the effort signal to a hashable STRING for the weight lookup.

    CC 2.1.133+ delivers effort as a dict {"level": "high"} in the hook event;
    older versions and the CLAUDE_EFFORT env give a bare string. Using the raw
    dict as a dict key raised `TypeError: unhashable type: 'dict'` and killed
    after_task BEFORE the trace was sent. Always returns a non-empty string.
    """
    raw = event.get("effort") if isinstance(event, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("level")
    if raw is None:
        raw = os.environ.get("CLAUDE_EFFORT", "normal")
    return raw if isinstance(raw, str) and raw else "normal"


def _learn_via_transcript(trace, env=None, verbosity='detailed', timeout=300, cli_cmd=CLI_CMD,
                          retrieval_id=None, applied_log_ids=None):
    """Submit an ExecutionTrace to `ace-cli learn` via a temp file + --transcript.

    ace-cli `learn --stdin` cannot read payloads larger than the ~64KB OS pipe
    buffer — it errors {"message":"Failed to read from stdin"} and the producer
    side gets a BrokenPipe, so ANY trace over ~64KB silently fails to learn
    (empirically: 64KB ok, 80KB fails; a 3.25MB --transcript file succeeds).
    A transcript file has no such limit, so traces of any size (up to the 2MB
    truncate cap) submit reliably. Returns the subprocess.CompletedProcess; the
    temp file is always removed.

    F-080: retrieval_id and applied_log_ids are passed as --retrieval-id and
    --applied-log-ids flags to ace-cli learn when present/non-empty.
    """
    import tempfile
    fd, path = tempfile.mkstemp(prefix='ace-trace-', suffix='.json')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(trace, f)
        cmd = [cli_cmd, 'learn', '--transcript', path, '--json',
               '--timeout', '300000', '--verbosity', verbosity]
        if retrieval_id:
            cmd += ['--retrieval-id', retrieval_id]
        if applied_log_ids:
            cmd += ['--applied-log-ids', ','.join(str(x) for x in applied_log_ids)]
        return subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def main():
    """
    ACE After Task Hook - PostToolUse Accumulation Architecture (v5.3.0)

    Stop hook processes accumulated tool data:
    1. Query SQLite for session's tools (ground truth from PostToolUse)
    2. Build trajectory with real tool calls
    3. Send to ace-cli learn --stdin
    4. Clear accumulated tools (cleanup)
    """
    try:
        # Track execution start time for metrics
        execution_start_time = time.time()

        # Read hook event from stdin
        event = json.load(sys.stdin)

        # DEBUG: Log raw event
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            debug_log = Path('/tmp/ace_hook_debug.log')
            with open(debug_log, 'a') as f:
                f.write(f"\n\n{'='*80}\n")
                f.write(f"Hook fired at: {datetime.now().isoformat()}\n")
                f.write(f"Event data:\n{json.dumps(event, indent=2)}\n")
                f.write(f"{'='*80}\n")

        # Extract event metadata
        hook_event_name = event.get('hook_event_name', 'Stop')
        session_id = event.get('session_id', 'unknown')
        transcript_path = event.get('transcript_path', '')
        last_assistant_message = event.get('last_assistant_message', '')  # v5.5.0: CC 2.1.51+

        # Handle SubagentStop: use agent's transcript
        if hook_event_name == 'SubagentStop' and 'agent_transcript_path' in event:
            transcript_path = event['agent_transcript_path']

        # Get project context
        context = get_context()
        if not context:
            output = skip_learning("No project context found", event)
            print(json.dumps(output))
            sys.exit(0)

        # Determine working directory
        working_dir = event.get('cwd') or event.get('working_directory')
        if not working_dir and transcript_path:
            try:
                working_dir = str(Path(transcript_path).parent.parent.parent)
            except Exception:
                working_dir = None

        # =======================================================================
        # v5.3.0: POSTTOOLUSE ACCUMULATION ARCHITECTURE
        # =======================================================================

        # v6.4.0: Prefer CC's per-agent transcript (agent_transcript_path) to avoid
        # cross-agent contamination from the session-wide SQLite accumulator.
        agent_transcript_path = event.get('agent_transcript_path') or None

        # STEP 1: Build trajectory from accumulated tools (GROUND TRUTH)
        trajectory, tools = build_trajectory_from_accumulated_tools(
            session_id, working_dir, agent_transcript_path=agent_transcript_path
        )

        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"Accumulated tools: {len(tools)} total\n")
                for t in tools[:5]:
                    f.write(f"  - {t[0]}\n")
                if len(tools) > 5:
                    f.write(f"  ... and {len(tools) - 5} more\n")

        # STEP 2: Get user prompt for task description
        user_prompt = "No user prompt found"
        if transcript_path:
            user_prompt = get_user_prompt_from_transcript(transcript_path)

        # STEP 3: QUALITY GATE - Check for trivial task
        if is_trivial_task(user_prompt):
            output = skip_learning("Trivial task (ACE command or simple query)", event)
            print(json.dumps(output))
            sys.exit(0)

        # STEP 4: QUALITY GATE - Check for substantial work
        if not has_substantial_work_from_accumulated(tools):
            output = skip_learning("No substantial work (no Edit/Write/Bash tools)", event)
            print(json.dumps(output))
            sys.exit(0)

        # STEP 5: Build ExecutionTrace (ACE Paper compliant format)
        # Check for errors in tool responses
        has_errors = False
        for _, _, tool_response_json, _, *_ in tools:
            try:
                resp = json.loads(tool_response_json) if tool_response_json else {}
                if resp.get('error') or resp.get('stderr'):
                    has_errors = True
                    break
            except Exception:
                pass

        # v6.0.0: Read agent_type natively from hook event (CC 2.1.69+)
        # agent_type identifies subagent type: "main", "refactorer", "coder", etc.
        agent_type = event.get('agent_type', 'main')
        # v6.4.0: Per-agent scope — None for main agent, UUID for subagents
        agent_id = event.get('agent_id') or None

        # v6.4.0: Resolve parent_agent_id from spawn log (best-effort).
        # SubagentStop wrapper writes {event: "subagent_done", child_agent_id, parent_agent_id}
        # BEFORE invoking ace_after_task.py, so the entry is present at read time.
        parent_agent_id = None
        if agent_id:
            try:
                spawn_log_path = Path('.claude/data/logs/ace-spawn-log.jsonl')
                if spawn_log_path.exists():
                    with open(spawn_log_path) as _sl:
                        for _line in reversed(list(_sl)):
                            try:
                                _sp = json.loads(_line)
                                if (_sp.get('event') == 'subagent_done'
                                        and _sp.get('child_agent_id') == agent_id):
                                    parent_agent_id = _sp.get('parent_agent_id')
                                    break
                            except Exception:
                                continue
            except Exception:
                pass  # non-fatal

        # F-080: Read retrieval metadata BEFORE load_playbook_used unlinks the file.
        # load_retrieval_ids is read-only (does NOT unlink). Must call it first so
        # the state file is still present when load_playbook_used later unlinks it.
        retrieval_log_map = load_retrieval_ids(session_id, agent_id, hook_event_name)
        # Also read retrieval_id and task_session_id from the state file (before unlink).
        # Both load_retrieval_ids and load_task_session_id are read-only.
        _retrieval_id_from_state = None
        try:
            from patterns_used_state import _read_state_file, state_file_path
            _sf = state_file_path(session_id, agent_id if hook_event_name == 'SubagentStop' else None)
            if _sf.exists():
                _, _retrieval_id_from_state, _, _ = _read_state_file(_sf)
        except Exception:
            pass  # non-fatal
        # Read task_session_id before load_playbook_used unlinks the state file.
        task_session_id = load_task_session_id(session_id, agent_id, hook_event_name)

        # Load pattern IDs for reinforcement learning (per-agent scope in v6.4.0).
        # Delegated to patterns_used_state.load_playbook_used (single source of
        # truth). PER-AGENT-PURE — each agent owns its own trace, never merged:
        # the terminal main Stop reads ONLY -{session}-main.json (forces the 'main'
        # suffix, ignoring any agent_id CC stamps on Stop, which fixes the agent_id
        # asymmetry); a SubagentStop reads ONLY its own -{agent_id} file. Neither
        # consumes another agent's file (no state steal, no cross-agent merge);
        # orphans are reaped by the SessionEnd GC. GAP3 self-heal: a per-file error
        # routes to log_hook_error via on_error.
        playbook_used = load_playbook_used(
            session_id,
            agent_id,
            hook_event_name,
            on_error=lambda f, e: log_hook_error(
                location="load_playbook_used",
                session_id=session_id,
                project_id=None,
                hook=hook_event_name,
                error=e,
                extra={"state_file": str(f)},
            ),
        )

        # F-080: Compute applied_log_ids = intersection of playbook_used with retrieval_log_map.
        # Order follows playbook_used (not the map). Only ints (no bools).
        applied_log_ids = [
            retrieval_log_map[pid] for pid in playbook_used if pid in retrieval_log_map
        ]
        # Use retrieval_id read from state file (before load_playbook_used unlinked it).
        retrieval_id = _retrieval_id_from_state

        # agent_id-contract proof: record which agent_id the READ side used and how
        # many IDs it recovered. Diffing this against the wrapper's write-side
        # 'agent_id' on ace-relevance.jsonl proves per-agent attribution end-to-end
        # on a live subagent session. Guarded + non-fatal — never fail the learn pipeline.
        try:
            _rel = Path('.claude/data/logs')
            _rel.mkdir(parents=True, exist_ok=True)
            with open(_rel / 'ace-relevance.jsonl', 'a') as _rf:
                _rf.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "event": "playbook_load",
                    "hook": hook_event_name,
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "count": len(playbook_used),
                }) + "\n")
        except Exception:
            pass  # non-fatal

        # Build the trace
        trace = {
            "task": f"User request: {user_prompt[:2000]}",
            "trajectory": trajectory,
            "result": {
                "success": not has_errors,
                "output": f"Executed {len(tools)} tool calls",
                "summary": last_assistant_message[:2000] if last_assistant_message else None,  # v5.5.0: CC 2.1.51+
            },
            "playbook_used": playbook_used,
            "timestamp": datetime.now().isoformat(),
            "agent_type": agent_type  # v5.4.11: Attribute learning to agent type
        }
        # per-task session_id: use task_session_id if stored; else OMIT session_id entirely.
        # Do NOT fall back to CC conversation session_id — that creates false correlation
        # across tasks (the exact bug this fixes). NULL on the server is better than wrong.
        if task_session_id:
            trace["session_id"] = task_session_id
        # else: omit — server leaves session_id NULL, no false cross-task correlation
        if agent_id:
            trace["agent_id"] = agent_id
        if parent_agent_id:
            trace["parent_agent_id"] = parent_agent_id
        # F-080: Enrich trace with retrieval provenance (omit keys when absent/empty).
        if retrieval_id:
            trace["retrieval_id"] = retrieval_id
        if applied_log_ids:
            trace["applied_log_ids"] = applied_log_ids

        # v6.5.0 Item #9: effort level signal (CC 2.1.133+ provides this in hook input).
        # Plugin-side weight mapping per SDK-team guidance (Q4):
        # auto/low/normal → 1.0 (baseline), high → 1.5, xhigh/max → 2.0
        # Initially logged-only; Curator scoring planned for later release.
        _EFFORT_WEIGHT = {
            "auto": 1.0, "low": 1.0, "normal": 1.0,
            "high": 1.5,
            "xhigh": 2.0, "max": 2.0,
        }
        # v6.6.5: CC 2.1.133+ sends effort as a dict {"level": ...}; resolve to a
        # hashable string (using the raw dict as a key crashed after_task before
        # the trace was ever sent — for main and subagent stops alike).
        effort_level = _resolve_effort_level(event)
        trace["effort_level"] = effort_level
        trace["effort_weight"] = _EFFORT_WEIGHT.get(effort_level, 1.0)

        # STEP 5.5: Git context capture (Issue #6)
        # Extract git context for AI-Trail correlation
        git_context = None
        try:
            git_context = get_git_context(working_dir)
            session_commits = detect_commits_in_session(tools)
            if session_commits and git_context:
                git_context['session_commits'] = session_commits
        except Exception as e:
            if os.environ.get('ACE_DEBUG_HOOKS') == '1':
                with open('/tmp/ace_hook_debug.log', 'a') as f:
                    f.write(f"Git context extraction failed: {e}\n")

        if git_context:
            trace["git"] = git_context

        # STEP 6: Recall pinned session patterns
        recalled_patterns = None
        if context['project']:
            session_file = Path(f"/tmp/ace-session-{context['project']}.txt")
            if session_file.exists():
                try:
                    session_id_from_file = session_file.read_text().strip()
                    recalled_patterns = recall_session(
                        session_id=session_id_from_file,
                        org=context['org'],
                        project=context['project']
                    )
                except Exception:
                    pass

        # STEP 7: Build user-visible message (output depends on verbosity setting)
        message_lines = []

        # v6.5.0 Item #16 (PR-review I2): truncate large traces before wire-send.
        # Target <2MB; preserves all failed steps + last 50 trajectory steps;
        # drops base64 blobs and oversized tool_response payloads.
        try:
            import sys as _sys
            _self_dir = os.path.dirname(os.path.abspath(__file__))
            if _self_dir not in _sys.path:
                _sys.path.insert(0, _self_dir)
            from utils.trace_truncate import truncate_trace
            trace = truncate_trace(trace)
        except Exception:
            pass  # never fail the learn pipeline on truncation issues

        # STEP 8: Send to ace-cli learn via --transcript (temp file)
        try:
            env = os.environ.copy()
            if context['org']:
                env['ACE_ORG_ID'] = context['org']
            if context['project']:
                env['ACE_PROJECT_ID'] = context['project']

            # Get verbosity from env, default to 'detailed' for meaningful feedback
            verbosity = os.environ.get('ACE_VERBOSITY', 'detailed')

            # v6.6.3: --transcript (temp file), NOT --stdin. ace-cli learn --stdin
            # cannot read payloads > ~64KB (OS pipe buffer) -> "Failed to read from
            # stdin" + BrokenPipe -> any trace over ~64KB silently failed to learn.
            # F-080: pass retrieval_id + applied_log_ids flags when present.
            result = _learn_via_transcript(
                trace, env=env, verbosity=verbosity,
                retrieval_id=retrieval_id,
                applied_log_ids=applied_log_ids,
            )

            if result.returncode == 0:
                try:
                    response = json.loads(result.stdout)
                    stats = response.get('learning_statistics', {})

                    # Handle nested learning_statistics structure from CLI v3.0.0+
                    # Response can be: {learning_statistics: {patterns_created: ...}}
                    # Or nested: {learning_statistics: {learning_statistics: {patterns_created: ...}}}
                    if 'learning_statistics' in stats:
                        stats = stats.get('learning_statistics', {})

                    if stats:
                        created = stats.get('patterns_created', 0)
                        updated = stats.get('patterns_updated', 0)
                        # F-080: ace-cli 4.0.1 uses patterns_deduplicated; 4.0.0 used patterns_merged
                        merged = stats.get('patterns_deduplicated', stats.get('patterns_merged', 0))
                        pruned = stats.get('patterns_pruned', 0)
                        conf = stats.get('average_confidence', 0)
                        # F-080: cumulative_v15_reward_delta is PRIMARY; helpful_delta is fallback
                        _v15 = stats.get('cumulative_v15_reward_delta')
                        helpful_delta = stats.get('helpful_delta', 0)
                        by_section = stats.get('by_section', {})
                        analysis_time = stats.get('analysis_time_seconds', 0)

                        if verbosity == 'compact':
                            # Single line: ✅ [ACE] 📚 +2 patterns 🔄 1 merged ⭐ 85% quality
                            parts = []
                            if created > 0:
                                parts.append(f"📚 +{created} patterns")
                            if merged > 0 or updated > 0:
                                parts.append(f"🔄 {merged + updated} merged")
                            if conf > 0:
                                parts.append(f"⭐ {int(conf * 100)}% quality")
                            if parts:
                                message_lines.append(f"✅ [ACE] {' '.join(parts)}")
                            else:
                                message_lines.append("✅ [ACE] Learning captured!")
                        else:
                            # Detailed mode with full breakdown
                            message_lines.append("✅ [ACE] Learning captured!")

                            # Only show stats if there's something to report
                            if created > 0 or updated > 0 or pruned > 0 or conf > 0 or analysis_time > 0:
                                message_lines.append("")
                                message_lines.append("📚 ACE Learning:")

                                # Line 1: patterns
                                line1_parts = []
                                if created > 0:
                                    line1_parts.append(f"📝 +{created} new")
                                if updated > 0:
                                    line1_parts.append(f"🔄 {updated} updated")
                                if pruned > 0:
                                    line1_parts.append(f"🧹 {pruned} pruned")
                                if line1_parts:
                                    message_lines.append(f"   {'  '.join(line1_parts)}")

                                # Line 2: quality & reward/helpful delta
                                line2_parts = []
                                if conf > 0:
                                    line2_parts.append(f"⭐ {int(conf * 100)}% quality")
                                # F-080: cumulative_v15_reward_delta is PRIMARY display metric
                                if _v15 is not None:
                                    line2_parts.append(f"📈 {_v15:+.1f} reward delta")
                                elif helpful_delta != 0:
                                    line2_parts.append(f"📈 {helpful_delta:+d} reward delta")
                                if line2_parts:
                                    message_lines.append(f"   {'  '.join(line2_parts)}")

                                # Line 3: sections
                                if by_section:
                                    sections = [k.split('_')[0].title() for k, v in by_section.items() if v > 0]
                                    if sections:
                                        message_lines.append(f"   📂 {', '.join(sections)}")

                                # Line 4: timing
                                if analysis_time > 0:
                                    message_lines.append(f"   ⏱️ {analysis_time:.1f}s analysis")
                    else:
                        # No stats returned (compact mode from CLI or old CLI version)
                        message_lines.append("✅ [ACE] Learning captured!")
                except json.JSONDecodeError:
                    message_lines.append("✅ [ACE] Learning captured!")
            else:
                message_lines.append(f"⚠️ [ACE] Learning capture failed: {result.stderr}")
                message_lines.append("   You can manually capture with: /ace-learn")

        except subprocess.TimeoutExpired:
            message_lines.append("⚠️ [ACE] Learning capture timed out")
            message_lines.append("   You can manually capture with: /ace-learn")
        except FileNotFoundError:
            message_lines.append("⚠️ [ACE] ace-cli not found - install with: npm install -g @ace-sdk/cli")
        except Exception as e:
            message_lines.append(f"⚠️ [ACE] Learning capture error: {e}")
            message_lines.append("   You can manually capture with: /ace-learn")

        message_lines.append("")

        # STEP 8.5: Log execution metrics for relevance analysis (v5.4.2)
        try:
            # Count state-changing tools for metrics
            state_changing_tools = ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit']
            state_changing_count = sum(
                1 for tool_name, _, _, _, *_ in tools
                if any(t in tool_name for t in state_changing_tools)
            )

            execution_time = time.time() - execution_start_time

            log_execution_metrics(
                session_id=session_id,
                patterns_used=playbook_used,
                tools_executed=len(tools),
                state_changing_tools=state_changing_count,
                success=not has_errors,
                execution_time_seconds=execution_time,
                learning_sent='✅' in message_lines[0] if message_lines else False,
                project_id=context.get('project'),
                agent_type=agent_type
            )
        except Exception:
            pass  # Non-fatal: continue without metrics logging

        # STEP 9: Clear accumulated tools (cleanup)
        sys.path.insert(0, str(Path(__file__).parent))
        from ace_tool_accumulator import clear_session
        clear_session(session_id, working_dir)

        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"Cleared accumulated tools for session {session_id}\n")

        # Add recalled patterns message
        if recalled_patterns and recalled_patterns.get('count', 0) > 0:
            pattern_count = recalled_patterns['count']
            message_lines.insert(1, f"🔄 [ACE] Recalled {pattern_count} patterns from session")

        # Output JSON with systemMessage + recalled patterns
        output = {
            "systemMessage": "\n".join(message_lines)
        }

        if recalled_patterns and recalled_patterns.get('count', 0) > 0:
            ace_context = f"<ace-patterns>\n{json.dumps(recalled_patterns, indent=2)}\n</ace-patterns>"
            output["hookSpecificOutput"] = {
                "hookEventName": hook_event_name,
                "additionalContext": ace_context
            }

        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"FATAL ERROR: {e}\n")
                import traceback
                f.write(traceback.format_exc())
        print(f"[ERROR] ACE after-task hook failed: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
