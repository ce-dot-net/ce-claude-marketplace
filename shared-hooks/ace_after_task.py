#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE After Task Hook - Dual Strategy (PreCompact + Stop)

CRITICAL: We need BOTH hooks for complete learning capture!

PreCompact Hook (Safety Net):
- Fires BEFORE context compaction
- Captures learning before knowledge is lost
- Receives pre-parsed messages/tool_uses from Claude Code

Stop Hook (True End):
- Fires at TRUE end of task/session
- Captures learning from work done AFTER last PreCompact
- Handles short tasks that never trigger PreCompact (e.g., 12 steps)
- Parses transcript manually since Stop doesn't provide messages/tool_uses

Two critical functions:
1. Recalls pinned session patterns (pattern persistence)
2. Captures learning from completed work (with rich trajectory context)

Examples:
- Long task (100 steps): PreCompact@50 + Stop@100 (captures steps 51-100!)
- Short task (12 steps): No PreCompact + Stop@12 (captures all learning!)
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_context import get_context
from ace_cli import recall_session

# Import re at module level for quality filters
import re as regex_module


def is_trivial_task(task_description: str) -> bool:
    """
    Filter out trivial tasks that shouldn't trigger learning.

    Per ACE Research Paper: Learning should only occur with "meaningful execution feedback"
    Trivial tasks like status checks, simple queries, or ACE commands don't qualify.

    Returns True if task is trivial (should be SKIPPED).
    """
    trivial_patterns = [
        # ACE commands - CRITICAL: These were being learned as garbage!
        r'<command-message>ace[:\-]',  # /ace:ace-status, /ace-learn, etc.
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
        r'^(what|how|why|where|when|can you|could you|would you)\s.*\?$',  # Questions ending with ?
        r'^(list|show|display|print|view|see)\s',  # Display commands
        r'^(check|status|version|help|info)\s*$',  # Status checks

        # Git status checks (read-only, no learning value)
        r'git\s+(status|log|diff|branch|show)\s*$',

        # File listing (read-only)
        r'^ls\s',
        r'^cat\s',
        r'^head\s',
        r'^tail\s',

        # Other trivial patterns
        r'^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure)\s*$',  # Greetings

        # Claude Code system messages (not user work)
        r'caveat:.*messages below were generated',  # System caveat wrapper
        r'^plugin\s*$',  # /plugin command
        r'/plugin',  # Plugin management
    ]

    task_lower = task_description.lower()
    for pattern in trivial_patterns:
        if regex_module.search(pattern, task_lower, regex_module.IGNORECASE):
            return True
    return False


def has_substantial_work(trace: dict, min_steps: int = 2) -> bool:
    """
    Determine if trace contains substantial work worth learning.

    Per ACE Research Paper: Requires "meaningful execution feedback"

    v5.2.0: Added min_steps parameter for delta captures.
    Delta captures (from Stop after PreCompact) can have fewer steps
    but still be valuable - we use min_steps=1 for those.

    Args:
        trace: ExecutionTrace dict with 'task', 'trajectory', 'result' keys
        min_steps: Minimum trajectory steps required (default: 2, use 1 for delta)

    Returns True if ALL of these conditions are met:
    - Task is not a generic fallback ("Session work")
    - Trajectory has min_steps+ meaningful steps
    - Trajectory is not generic conversation-only
    - Has state-changing tools OR substantial output (200+ chars)
    """
    trajectory = trace.get('trajectory', [])
    task = trace.get('task', '')
    result_output = trace.get('result', {}).get('output', '')

    # Reject generic fallback tasks
    if task.startswith("Session work"):
        return False

    # Reject trajectories below minimum steps threshold
    # v5.2.0: Use min_steps=1 for delta captures
    if len(trajectory) < min_steps:
        return False

    # Reject generic conversation-only trajectories
    # These were being captured as garbage patterns!
    generic_actions = [
        "Conversation with",
        "Discussion and analysis",
        "Message exchanges",
        "Single-step conversation",
        "completed",  # Generic fallback
    ]
    for step in trajectory:
        action = step.get('action', '')
        result = step.get('result', '')

        # Check if action is generic
        if any(g.lower() in action.lower() for g in generic_actions):
            # Check if result is also generic (double-check)
            if 'completed' in result.lower() or 'discussion' in result.lower():
                return False  # Generic conversation is not substantial

    # Check for state-changing tools (positive signal per ACE paper)
    # Reading files is NOT substantial - need actual modifications
    state_changing_tools = ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit']
    read_only_tools = ['Read', 'Glob', 'Grep', 'WebFetch', 'WebSearch']

    has_state_change = False
    tool_count = 0
    state_change_count = 0

    for step in trajectory:
        action = step.get('action', '')
        tool = step.get('tool', '')
        result = step.get('result', '')

        # Count state-changing operations
        if any(t in tool or t in action for t in state_changing_tools):
            has_state_change = True
            state_change_count += 1

        tool_count += 1

    # Require either:
    # 1. State-changing tools present, OR
    # 2. Substantial output (200+ chars) indicating meaningful analysis
    if not has_state_change and len(result_output) < 200:
        return False

    return True


def filter_garbage_trajectory(trajectory):
    """
    Filter empty/garbage tool descriptions BEFORE sending to server.

    v5.2.0: Client-side garbage filtering (CRITICAL)

    Per ACE Research Paper: Reflector expects CONCRETE code patterns.
    Empty or minimal descriptions create trash patterns on the server.

    Examples of garbage to filter:
    - "Edit - " (empty description)
    - "Write - " (empty description)
    - "Bash - ls" (trivial command)

    Args:
        trajectory: List of trajectory step dicts with 'action', 'result' keys

    Returns:
        Filtered trajectory with only meaningful steps
    """
    filtered = []

    for step in trajectory:
        action = step.get('action', '')
        result = step.get('result', '')

        # Skip empty tool descriptions: "Edit - " or "Write - "
        if ' - ' in action:
            parts = action.split(' - ', 1)
            if len(parts) == 2:
                tool_name, description = parts
                # Require non-empty description with at least 5 chars
                if description.strip() and len(description.strip()) >= 5:
                    filtered.append(step)
                else:
                    # Log filtered garbage in debug mode
                    import os
                    if os.environ.get('ACE_DEBUG_HOOKS') == '1':
                        with open('/tmp/ace_hook_debug.log', 'a') as f:
                            f.write(f"Filtered garbage action: '{action}'\n")
                    continue
            else:
                filtered.append(step)
        else:
            # Keep non-tool actions (decisions, accomplishments, etc.)
            # But filter very short/empty ones
            if action.strip() and len(action.strip()) >= 10:
                filtered.append(step)

    return filtered


def skip_learning(reason, event=None):
    """
    Never skip silently - always provide feedback to user.

    v5.2.0: User feedback on skip

    Per ACE Research Paper: Users should understand when learning
    is skipped and why, to help them improve their workflow.

    Args:
        reason: Human-readable reason for skipping
        event: Optional event dict for additional context

    Returns:
        JSON-serializable dict with continue=True and systemMessage
    """
    import os
    if os.environ.get('ACE_DEBUG_HOOKS') == '1':
        with open('/tmp/ace_hook_debug.log', 'a') as f:
            f.write(f"ACE: Skipping learning - {reason}\n")
            if event:
                f.write(f"  Event: {json.dumps(event, default=str)[:500]}\n")

    return {
        "continue": True,
        "systemMessage": f"[ACE] Learning skipped: {reason}"
    }


# Position tracking state files for delta learning (v5.2.0)
POSITION_STATE_FILE = Path('.claude/data/logs/ace-position-state.json')


def record_captured_position(session_id, position, hook_type='precompact'):
    """
    Record the position (message count) at which learning was captured.

    v5.2.0: Position-based delta tracking

    This enables Stop hook to capture ONLY NEW work since PreCompact,
    instead of skipping entirely (which loses delta learning).

    Args:
        session_id: Claude Code session ID
        position: Number of task messages captured
        hook_type: Which hook recorded this ('precompact', 'posttooluse')
    """
    try:
        POSITION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Load existing state
        state = {}
        if POSITION_STATE_FILE.exists():
            with open(POSITION_STATE_FILE, 'r') as f:
                state = json.load(f)

        # Record position for this session
        state[session_id] = {
            'position': position,
            'hook_type': hook_type,
            'timestamp': datetime.now().isoformat()
        }

        # Save state
        with open(POSITION_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    except Exception as e:
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"record_captured_position error: {e}\n")


def get_captured_position(session_id):
    """
    Get the last captured position for delta learning.

    v5.2.0: Position-based delta tracking

    Returns:
        Position (int) if found, 0 otherwise
    """
    try:
        if not POSITION_STATE_FILE.exists():
            return 0

        with open(POSITION_STATE_FILE, 'r') as f:
            state = json.load(f)

        session_state = state.get(session_id, {})
        return session_state.get('position', 0)

    except Exception:
        return 0


def clear_captured_position(session_id):
    """
    Clear position state after Stop hook completes (cleanup).

    v5.2.0: Position-based delta tracking

    Called at end of Stop hook to clean up state for next task.
    """
    try:
        if not POSITION_STATE_FILE.exists():
            return

        with open(POSITION_STATE_FILE, 'r') as f:
            state = json.load(f)

        if session_id in state:
            del state[session_id]

            with open(POSITION_STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)

    except Exception:
        pass


def extract_execution_trace(event):
    """
    Build ExecutionTrace from PreCompact event with RICH context.

    Extracts comprehensive session summary:
    - User's original request/question (what they asked for)
    - Tools used and files modified (what was done)
    - Outcomes and learnings (what worked/failed)
    - Assistant's approach and decisions (how it was done)

    Prevents generic "Session work" messages and ensures unique, valuable learning.
    """
    messages = event.get('messages', [])
    tool_uses = event.get('tool_uses', [])

    # Extract RICH task description from conversation
    task_description = "Session work"  # Fallback

    if messages and len(messages) > 0:
        # Get user's first substantial message (skip system messages)
        user_messages = [m for m in messages if m.get('role') == 'user']
        if user_messages:
            first_user = user_messages[0]
            content = first_user.get('content', '')
            if content:
                # Use first user message as task description (captures intent)
                task_description = f"User request: {content[:250]}"

    # Build trajectory from CONVERSATION MESSAGES (high-level insights)
    # Server team guidance: Extract decisions/gotchas/accomplishments, NOT tool operations
    trajectory = []
    decisions = []
    gotchas = []
    accomplishments = []
    files_modified = set()

    # Track files from tool uses (for context only, not trajectory)
    for tool in tool_uses:
        tool_name = tool.get('tool_name', 'unknown')
        tool_desc = tool.get('description', '')
        if tool_name in ['Edit', 'Write'] and tool_desc:
            files_modified.add(tool_desc.split()[0] if tool_desc else 'unknown')

    # Extract high-level insights from conversation messages
    # Server team guidance: Pattern-based extraction, not keyword matching
    import re

    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')

        # Only process assistant messages (Claude's responses)
        if role != 'assistant':
            continue

        # Normalize content to string (handle both string and list formats)
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    text_parts.append(block.get('text', ''))
            content = '\n'.join(text_parts)
        elif not isinstance(content, str):
            content = str(content)

        # 1. Extract structured headings (most reliable)
        # Look for: "Decision:", "Key decision:", "Strategy:", "Approach:"
        decision_patterns = [
            r'(?:^|\n)\*\*Decision \d+[:\-]\s*(.+?)(?:\*\*|\n|$)',  # **Decision 1: ...**
            r'(?:decision|chose|strategy|approach):\s*(.+?)(?:\n|$)',  # decision: text
            r'(?:I\'ve|I\'ll|I)\s+(decided|chosen)\s+to\s+(.+?)(?:\.|,|\n)',  # I've decided to...
            r'using\s+(.+?)\s+(?:to|for|because)',  # using X to/for/because
        ]

        for pattern in decision_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                text = match.group(1) if match.lastindex >= 1 else match.group(0)
                clean = text.strip()
                if len(clean) > 20 and clean not in decisions:
                    decisions.append(clean[:200])  # Cap at 200 chars

        # 2. Extract comparisons and trade-offs (reveal architectural thinking)
        # Look for: "instead of", "rather than", "prevents", "avoids"
        comparison_patterns = [
            r'(.+?)\s+(?:instead of|rather than)\s+(.+?)(?:\.|,|\n)',
            r'(?:this|that|which)\s+prevents\s+(.+?)(?:\.|,|\n)',
            r'(?:avoids?|prevent(?:s|ing)?|stop(?:s|ping)?)\s+(.+?)(?:\.|,|\n)',
        ]

        for pattern in comparison_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                full_match = match.group(0).strip()
                if len(full_match) > 20 and full_match not in decisions:
                    decisions.append(full_match[:200])

        # 3. Extract from code comments (contain WHY, gotchas, edge cases)
        # Look for: # comments, // comments, /* comments */
        comment_patterns = [
            r'//\s*(.+?)(?:\n|$)',  # // single line
            r'#\s*(.+?)(?:\n|$)',   # # Python style
            r'/\*\s*(.+?)\s*\*/',   # /* multi-line */
        ]

        for pattern in comment_patterns:
            matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
            for match in matches:
                comment = match.group(1).strip()
                # Comments often explain gotchas or decisions
                if len(comment) > 20:
                    if any(word in comment.lower() for word in ['prevent', 'avoid', 'gotcha', 'important', 'note']):
                        if comment not in gotchas:
                            gotchas.append(comment[:200])
                    elif any(word in comment.lower() for word in ['because', 'reason', 'why', 'to']):
                        if comment not in decisions:
                            decisions.append(comment[:200])

        # 4. Extract error handling context (not just "error" but explanation)
        # Look for patterns like: "This prevents X", "Without this, Y happens"
        error_patterns = [
            r'(?:this|that)\s+(?:prevents?|fixes?|solves?)\s+(.+?)(?:\.|,|\n)',
            r'without\s+(?:this|that),?\s+(.+?)(?:\.|,|\n)',
            r'(?:if we don\'t|must|should|need to)\s+(.+?)\s+(?:to avoid|to prevent|or|otherwise)\s+(.+?)(?:\.|,|\n)',
        ]

        for pattern in error_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                text = ' '.join([g for g in match.groups() if g]).strip()
                if len(text) > 20 and text not in gotchas:
                    gotchas.append(text[:200])

        # 5. Extract accomplishments (completed work with context)
        # More flexible than keyword matching
        accomplishment_patterns = [
            r'(?:I\'ve|I\s+have)\s+(implemented|created|built|added|fixed)\s+(.+?)(?:\.|,|\n)',
            r'(?:successfully|completed|working)\s+(.+?)(?:\.|,|\n)',
            r'(?:now|finally)\s+(?:works?|functioning|operational|ready)\s*[:\-]?\s*(.+?)(?:\.|,|\n)',
        ]

        for pattern in accomplishment_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                text = ' '.join([g for g in match.groups() if g]).strip()
                if len(text) > 20 and text not in accomplishments:
                    accomplishments.append(text[:200])

    # Build meaningful trajectory from extracted insights
    if decisions:
        trajectory.append({
            "step": 1,
            "action": "Made architectural decisions",
            "result": " | ".join(decisions[:3])  # Top 3 decisions
        })

    if gotchas:
        trajectory.append({
            "step": len(trajectory) + 1,
            "action": "Encountered and resolved issues",
            "result": " | ".join(gotchas[:3])  # Top 3 gotchas
        })

    if accomplishments:
        trajectory.append({
            "step": len(trajectory) + 1,
            "action": "Completed work items",
            "result": " | ".join(accomplishments[:3])  # Top 3 completions
        })

    # Fallback: If no meaningful insights extracted, create minimal trajectory
    # This ensures we don't skip valuable conversational learning
    if not trajectory and messages:
        trajectory = [{
            "step": 1,
            "action": f"Conversation with {len(messages)} message exchanges",
            "result": "Discussion and analysis completed"
        }]

    # Extract lessons learned from assistant's responses (FULL context)
    # Capture MORE messages for comprehensive learning
    lessons = []

    if messages:
        # Get last 5-10 assistant messages (instead of 2-3) for comprehensive context
        assistant_messages = [m for m in messages if m.get('role') == 'assistant']
        if assistant_messages:
            # Take last 10 messages to capture full arc of work
            for msg in assistant_messages[-10:]:
                content = msg.get('content', '')

                # Normalize content to string (handle both string and list formats)
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    content = '\n'.join(text_parts)
                elif not isinstance(content, str):
                    content = str(content)

                if content:
                    # Increased from 200 → 500 chars per message
                    lessons.append(content[:500])

    # Build comprehensive output
    lessons_str = " | ".join(lessons) if lessons else "Auto-captured session learning"

    # Add files modified context (ALL files, not just first 5)
    if files_modified:
        lessons_str += f" | Files modified: {', '.join(sorted(files_modified))}"

    # Check for errors in tool results
    has_errors = any(
        tool.get('result', {}).get('error') or tool.get('result', {}).get('stderr')
        for tool in tool_uses
        if isinstance(tool.get('result'), dict)
    )

    # CRITICAL: Load pattern IDs for reinforcement learning (ACE paper feedback loop)
    # ace_before_task.py saved which patterns were retrieved at task start
    # We load those IDs and send to server so it can update 'helpful' scores
    playbook_used = []
    session_id = event.get('session_id')
    if session_id:
        try:
            state_file = Path(f'.claude/data/logs/ace-patterns-used-{session_id}.json')
            if state_file.exists():
                playbook_used = json.loads(state_file.read_text())
                # Clean up state file after loading (one-time use)
                state_file.unlink()
        except Exception:
            # Non-fatal: continue without pattern tracking
            playbook_used = []

    return {
        "task": task_description[:2000],  # Increased: 400 → 2000 chars
        "trajectory": trajectory,
        "result": {
            "success": not has_errors,
            "output": lessons_str[:10000]  # Increased: 1000 → 10000 chars for FULL session context
        },
        "playbook_used": playbook_used,
        "timestamp": datetime.now().isoformat()
    }


def get_task_messages(transcript_path):
    """
    Get all messages since the LAST user prompt = THIS TASK's work.

    v5.2.0: Per-task parsing instead of incremental session parsing.

    Claude Code provides NO per-task identifier, so we define:
    - Task Start = Last `role: "user"` message in transcript
    - Task Work = All messages AFTER that user message
    - Task End = Stop/SubagentStop hook fires

    This ensures we capture the FULL context of the current task,
    not just messages since last PreCompact (which loses context).

    Returns:
        (task_messages, user_prompt, last_user_idx): Tuple of:
            - task_messages: List of message dicts since last user prompt
            - user_prompt: The user's prompt text that started this task
            - last_user_idx: Index of last user message (for position tracking)
    """
    all_entries = []
    task_messages = []
    user_prompt = "No user prompt found"

    try:
        transcript_file = Path(transcript_path).expanduser()
        if not transcript_file.exists():
            return [], user_prompt, -1

        # Read ALL entries from transcript
        with open(transcript_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    all_entries.append(entry)
                except json.JSONDecodeError:
                    continue

        if not all_entries:
            return [], user_prompt, -1

        # Find LAST user message (task start) - search backwards
        last_user_idx = -1
        for i in range(len(all_entries) - 1, -1, -1):
            message = all_entries[i].get('message', {})
            if message.get('role') == 'user':
                last_user_idx = i

                # Extract user prompt text
                content = message.get('content', '')
                if isinstance(content, list):
                    # Handle content blocks format
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))
                    user_prompt = '\n'.join(text_parts)
                elif isinstance(content, str):
                    user_prompt = content
                else:
                    user_prompt = str(content)

                break

        if last_user_idx == -1:
            return [], "No user prompt found", -1

        # Everything AFTER = THIS TASK's work
        task_entries = all_entries[last_user_idx + 1:]

        # Convert entries to messages format (matching parse_transcript output)
        for entry in task_entries:
            message = entry.get('message', {})
            if 'role' in message and 'content' in message:
                task_messages.append({
                    'role': message['role'],
                    'content': message['content']
                })

    except Exception as e:
        # Non-fatal: return empty
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"get_task_messages error: {e}\n")

    return task_messages, user_prompt, last_user_idx


def parse_transcript(transcript_path, start_line=0):
    """
    Parse Claude Code transcript .jsonl file to extract messages and tool_uses.

    Supports incremental parsing by accepting a start_line parameter.
    This enables parsing only NEW messages since last processing.

    NOTE: v5.2.0 - This function is kept for backward compatibility.
    For per-task parsing, use get_task_messages() instead.

    Args:
        transcript_path: Path to the .jsonl transcript file
        start_line: Line number to start parsing from (0-indexed, default: 0)

    Returns:
        (messages, tool_uses, lines_parsed): Tuple of messages list, tool_uses list, and number of lines parsed
    """
    messages = []
    tool_uses = []
    lines_parsed = 0

    try:
        transcript_file = Path(transcript_path).expanduser()
        if not transcript_file.exists():
            return messages, tool_uses, 0

        with open(transcript_file, 'r') as f:
            for line_num, line in enumerate(f):
                # Skip lines before start_line (incremental parsing)
                if line_num < start_line:
                    continue

                lines_parsed += 1
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)

                    # Claude Code transcript format: {type: "user/assistant", message: {role, content}}
                    # Extract message if present
                    message = entry.get('message', {})
                    if 'role' in message and 'content' in message:
                        messages.append({
                            'role': message['role'],
                            'content': message['content']
                        })

                        # Extract tool uses from assistant messages
                        if message.get('role') == 'assistant':
                            content = message['content']
                            # Look for tool use blocks in content
                            if isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                                        tool_uses.append({
                                            'tool_name': block.get('name'),
                                            'tool_input': block.get('input', {}),
                                            'description': ''  # Not available in transcript
                                        })

                except json.JSONDecodeError:
                    continue

    except Exception as e:
        # Non-fatal: return empty lists
        pass

    return messages, tool_uses, lines_parsed


def main():
    """
    ACE After Task Hook - Per-Task + Delta Learning Architecture (v5.2.0)

    This hook captures learning from completed work using a per-task approach:

    1. PreCompact: Captures FULL task work before context compaction
       - Records position for delta tracking
       - Ensures learning survives compaction

    2. Stop: Captures DELTA work (new steps since PreCompact)
       - If PreCompact ran: capture only NEW steps
       - If PreCompact never ran: capture FULL task

    3. SubagentStop: Captures subagent work (separate transcript)
       - Uses agent_transcript_path for subagent's own work

    Task Boundary: Last `role: "user"` message in transcript
    """
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)

        # DEBUG: Log raw event if ACE_DEBUG_HOOKS is set
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            debug_log = Path('/tmp/ace_hook_debug.log')
            with open(debug_log, 'a') as f:
                f.write(f"\n\n{'='*80}\n")
                f.write(f"Hook fired at: {datetime.now().isoformat()}\n")
                f.write(f"Event data:\n{json.dumps(event, indent=2)}\n")
                f.write(f"{'='*80}\n")

        # Extract hook event name (PreCompact, Stop, PostToolUse, SubagentStop)
        hook_event_name = event.get('hook_event_name', 'PreCompact')
        session_id = event.get('session_id', 'unknown')

        # Get project context EARLY (needed for all paths)
        context = get_context()
        if not context:
            output = skip_learning("No project context found", event)
            print(json.dumps(output))
            sys.exit(0)

        # =======================================================================
        # v5.2.0: PER-TASK + DELTA LEARNING ARCHITECTURE
        # =======================================================================

        # Determine transcript path
        transcript_path = None
        if hook_event_name == 'SubagentStop' and 'agent_transcript_path' in event:
            # SubagentStop: Use subagent's transcript (not parent session)
            transcript_path = event['agent_transcript_path']
        elif 'transcript_path' in event:
            transcript_path = event['transcript_path']

        # STEP 1: Get task messages using per-task parsing (v5.2.0)
        # Parse from LAST user prompt = THIS TASK's work
        task_messages = []
        user_prompt = "No user prompt found"
        task_position = 0
        is_delta_capture = False
        min_steps = 2  # Default: require 2+ steps

        if transcript_path:
            task_messages, user_prompt, _ = get_task_messages(transcript_path)
            task_position = len(task_messages)

            if os.environ.get('ACE_DEBUG_HOOKS') == '1':
                with open('/tmp/ace_hook_debug.log', 'a') as f:
                    f.write(f"Per-task parsing: {task_position} messages since last user prompt\n")
                    f.write(f"User prompt: {user_prompt[:100]}...\n")

        # STEP 2: Delta tracking for Stop hook (v5.2.0)
        # Check if PreCompact already captured some work
        if hook_event_name == 'Stop':
            last_captured_position = get_captured_position(session_id)

            if last_captured_position > 0 and last_captured_position < task_position:
                # PreCompact ran - capture ONLY NEW messages (delta)
                delta_count = task_position - last_captured_position
                task_messages = task_messages[last_captured_position:]
                is_delta_capture = True
                min_steps = 1  # Lower threshold for delta captures

                if os.environ.get('ACE_DEBUG_HOOKS') == '1':
                    with open('/tmp/ace_hook_debug.log', 'a') as f:
                        f.write(f"DELTA capture: {delta_count} new steps since PreCompact (position {last_captured_position})\n")

            elif last_captured_position >= task_position:
                # PreCompact captured everything - no new work
                output = skip_learning("No new work since PreCompact", event)
                print(json.dumps(output))
                # Clean up position state
                clear_captured_position(session_id)
                sys.exit(0)

            # Clean up position state after Stop
            clear_captured_position(session_id)

        # STEP 3: Build event with task messages for extract_execution_trace
        # (Backward compatible with existing extract_execution_trace function)
        event['messages'] = task_messages
        event['tool_uses'] = []  # Will be extracted from messages

        # STEP 4: Recall pinned session patterns BEFORE learning capture
        # This ensures patterns survive context compaction
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
                    # Non-fatal: continue without recalled patterns
                    pass

        # STEP 5: Build ExecutionTrace from task messages with rich context
        trace = extract_execution_trace(event)

        # Override task description with actual user prompt (not generic fallback)
        if user_prompt and user_prompt != "No user prompt found":
            trace['task'] = f"User request: {user_prompt[:2000]}"

        # STEP 6a: QUALITY GATE - Filter trivial tasks
        # Per ACE Research Paper: Only learn from "meaningful execution feedback"
        if is_trivial_task(trace['task']):
            output = skip_learning("Trivial task (ACE command or simple query)", event)
            print(json.dumps(output))
            sys.exit(0)

        # STEP 6b: QUALITY GATE - Check for substantial work
        # v5.2.0: Use min_steps=1 for delta captures
        if not has_substantial_work(trace, min_steps=min_steps):
            reason = "No substantial work" if not is_delta_capture else f"Delta too small ({len(task_messages)} messages)"
            output = skip_learning(reason, event)
            print(json.dumps(output))
            sys.exit(0)

        # STEP 6c: GARBAGE FILTER - Filter empty/trivial trajectory steps
        # v5.2.0: Client-side garbage filtering BEFORE sending to server
        clean_trajectory = filter_garbage_trajectory(trace['trajectory'])
        if len(clean_trajectory) == 0:
            output = skip_learning("No meaningful actions in trajectory", event)
            print(json.dumps(output))
            sys.exit(0)
        trace['trajectory'] = clean_trajectory

        # STEP 7: PreCompact records position for delta tracking
        # Stop will use this to capture only NEW work
        if hook_event_name == 'PreCompact' and task_position > 0:
            record_captured_position(session_id, task_position, 'precompact')
            if os.environ.get('ACE_DEBUG_HOOKS') == '1':
                with open('/tmp/ace_hook_debug.log', 'a') as f:
                    f.write(f"PreCompact: Recorded position {task_position} for delta tracking\n")

        # Build user-visible message lines with details
        if is_delta_capture:
            hook_label = f"Stop (delta: {len(task_messages)} new steps)"
        elif hook_event_name == "PreCompact":
            hook_label = "PreCompact (safety net)"
        elif hook_event_name == "SubagentStop":
            hook_label = "SubagentStop (Task agent)"
        else:
            hook_label = f"{hook_event_name} (end-of-task)"

        message_lines = [
            "",
            f"📚 [ACE] Automatically capturing learning... ({hook_label})",
            f"   Task: {trace['task'][:80]}...",
            f"   Status: {'✅ Success' if trace['result']['success'] else '❌ Failed'}"
        ]

        # Show trajectory details (up to 5 key actions)
        if trace['trajectory']:
            message_lines.append(f"   Actions performed ({len(trace['trajectory'])} total):")
            for step in trace['trajectory'][:5]:
                action_summary = step['action'][:80]
                message_lines.append(f"     {step['step']}. {action_summary}")
            if len(trace['trajectory']) > 5:
                message_lines.append(f"     ... and {len(trace['trajectory']) - 5} more actions")

        if trace['playbook_used']:
            message_lines.append(f"   Patterns used: {len(trace['playbook_used'])}")

        # Call ce-ace learn --stdin with ExecutionTrace JSON
        # Context passed via environment variables
        try:
            env = os.environ.copy()
            if context['org']:
                env['ACE_ORG_ID'] = context['org']
            if context['project']:
                env['ACE_PROJECT_ID'] = context['project']

            # IMPORTANT: Timeout must be less than hook timeout (130s in hooks.json)
            result = subprocess.run(
                ['ce-ace', 'learn', '--stdin', '--json'],
                input=json.dumps(trace),
                text=True,
                capture_output=True,
                timeout=120,
                env=env
            )

            if result.returncode == 0:
                message_lines.append("✅ [ACE] Learning captured and sent to server!")
                # Parse JSON response to show what was learned
                try:
                    response = json.loads(result.stdout)

                    # v1.0.13+ enhanced learning statistics
                    stats = response.get('learning_statistics')
                    if stats:
                        message_lines.append("")
                        message_lines.append("📚 ACE Learning:")

                        created = stats.get('patterns_created', 0)
                        updated = stats.get('patterns_updated', 0)
                        pruned = stats.get('patterns_pruned', 0)

                        if created > 0:
                            message_lines.append(f"   • {created} new pattern{'s' if created != 1 else ''}")
                        if updated > 0:
                            message_lines.append(f"   • {updated} pattern{'s' if updated != 1 else ''} updated")
                        if pruned > 0:
                            message_lines.append(f"   • {pruned} low-quality pattern{'s' if pruned != 1 else ''} pruned")

                        conf = stats.get('average_confidence', 0)
                        if conf > 0:
                            message_lines.append(f"   • Quality: {int(conf * 100)}%")

                    else:
                        # FALLBACK: Old server format
                        if response.get('analysis_triggered'):
                            message_lines.append("   🧠 Server analysis in progress...")
                        patterns_count = response.get('patterns_extracted')
                        if patterns_count:
                            message_lines.append(f"   📝 {patterns_count} patterns extracted for review")

                except json.JSONDecodeError:
                    pass
                except Exception:
                    pass
            else:
                message_lines.append(f"⚠️ [ACE] Learning capture failed: {result.stderr}")
                message_lines.append("   You can manually capture with: /ace-learn")

        except subprocess.TimeoutExpired:
            message_lines.append("⚠️ [ACE] Learning capture timed out")
            message_lines.append("   You can manually capture with: /ace-learn")
        except FileNotFoundError:
            message_lines.append("⚠️ [ACE] ce-ace CLI not found - install with: npm install -g @ce-dot-net/ce-ace-cli")
        except Exception as e:
            message_lines.append(f"⚠️ [ACE] Learning capture error: {e}")
            message_lines.append("   You can manually capture with: /ace-learn")

        message_lines.append("")

        # Add message about recalled patterns (if any)
        if recalled_patterns and recalled_patterns.get('count', 0) > 0:
            pattern_count = recalled_patterns['count']
            message_lines.insert(1, f"🔄 [ACE] Recalled {pattern_count} patterns from session (patterns persist across compaction)")

        # Output JSON with systemMessage + recalled patterns as additionalContext
        output = {
            "systemMessage": "\n".join(message_lines)
        }

        # Inject recalled patterns as additional context (if available)
        if recalled_patterns and recalled_patterns.get('count', 0) > 0:
            ace_context = f"<ace-patterns>\n{json.dumps(recalled_patterns, indent=2)}\n</ace-patterns>"
            output["hookSpecificOutput"] = {
                "hookEventName": hook_event_name,
                "additionalContext": ace_context
            }

        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block compaction
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"FATAL ERROR: {e}\n")
                import traceback
                f.write(traceback.format_exc())
        print(f"[ERROR] ACE after-task hook failed: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
