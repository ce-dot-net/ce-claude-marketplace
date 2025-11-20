#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE Task Complete Hook - PostToolUse Event Handler

Monitors for substantial task completion.
Actual learning capture happens via PreCompact/Stop hooks to avoid duplicates.

Triggers on meaningful work: Task tool completion, multiple edits, implementations.
Skips trivial operations: single reads, basic Q&A.
"""

import json
import sys
import subprocess
import time
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_context import get_context

# State tracking for edit sequences
STATE_FILE = Path('/tmp/ace_edit_sequence_state.json')


def load_sequence_state():
    """Load edit sequence tracking state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {'edit_count': 0, 'last_timestamp': 0, 'last_tool': None}


def save_sequence_state(state):
    """Save edit sequence tracking state."""
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass  # Fail silently if can't write state


def check_sequence_completion(tool_name):
    """
    Detect when an edit sequence has COMPLETED (all steps done).

    Key insight: We want learning AT THE END, not during work!

    Logic:
    - During Edit/Write sequence → Track but DON'T trigger
    - Different tool AFTER sequence → Sequence complete, TRIGGER!
    - This captures the complete task after all edits are done

    Example:
      Edit #1 (hero.tsx)   → Track, don't trigger
      Edit #2 (styles.css) → Track, don't trigger
      Edit #3 (utils.ts)   → Track, don't trigger
      Read (review.tsx)    → Sequence ended, TRIGGER! ✓

    This prevents losing knowledge while avoiding mid-task triggers.
    """
    state = load_sequence_state()
    current_time = time.time()

    # Check if we're continuing or ending a sequence
    was_in_sequence = state.get('in_sequence', False)
    sequence_count = state.get('edit_count', 0)

    if tool_name in ['Edit', 'Write']:
        # Continue/start sequence - track but don't trigger
        if current_time - state['last_timestamp'] > 60:
            # New sequence starting
            state['edit_count'] = 1
        else:
            # Continuing sequence
            state['edit_count'] += 1

        state['in_sequence'] = True
        state['last_timestamp'] = current_time
        state['last_tool'] = tool_name
        save_sequence_state(state)

        # Don't trigger during sequence
        return False

    else:
        # Different tool - check if sequence just ended
        if was_in_sequence and sequence_count >= 2:
            # Sequence completed! Trigger learning for completed work
            state['in_sequence'] = False
            state['edit_count'] = 0
            state['last_timestamp'] = current_time
            state['last_tool'] = tool_name
            save_sequence_state(state)
            return True  # TRIGGER! Task complete
        else:
            # No sequence to complete
            state['in_sequence'] = False
            state['edit_count'] = 0
            state['last_timestamp'] = current_time
            state['last_tool'] = tool_name
            save_sequence_state(state)
            return False


def is_substantial_task(event):
    """
    Determine if this tool use represents substantial work worth learning from.

    Triggers AT THE END of work (critical to avoid losing knowledge):
    - Task tool completion (subagent explicitly finished)
    - Git commits (user explicitly checkpointed)
    - Edit sequence completion (2+ edits done, now switching to different tool)

    Does NOT trigger:
    - During edit sequences (mid-work)
    - Single isolated edits
    - Trivial operations (Read, Grep, etc. with no prior work)

    Key: Captures complete knowledge after all steps are done!
    """
    tool_name = event.get('tool_name', '')
    tool_description = event.get('description', '').lower()

    # Task tool completion is always substantial
    if tool_name == 'Task':
        return True

    # Git commits indicate completed work
    if tool_name == 'Bash' and 'git commit' in tool_description:
        return True

    # Check if edit sequence just completed (regardless of current tool)
    # This captures work AT THE END when switching from edits to other tools
    if check_sequence_completion(tool_name):
        return True

    # All other cases - no trigger
    return False


def build_execution_trace_from_posttooluse(event):
    """
    Build ExecutionTrace from PostToolUse event.

    Note: PostToolUse has limited context (just recent tool use),
    but we capture what's available for immediate learning.
    """
    from datetime import datetime

    tool_name = event.get('tool_name', 'unknown')
    tool_description = event.get('description', '')

    # Build task description from recent context
    task_description = f"Task completed: {tool_description[:200]}" if tool_description else "Task completed"

    # Build trajectory from accumulated edit sequence
    trajectory = []
    state = load_sequence_state()

    if state.get('edit_count', 0) >= 2:
        # We have an edit sequence - this is what we're learning from
        task_description = f"Code modifications: {state['edit_count']} files edited"
        for i in range(1, state['edit_count'] + 1):
            trajectory.append({
                "step": i,
                "action": "Edit - File modification",
                "result": "completed"
            })

    # Add current tool as final step
    trajectory.append({
        "step": len(trajectory) + 1,
        "action": f"{tool_name} - {tool_description}",
        "result": "completed"
    })

    return {
        "task": task_description,
        "trajectory": trajectory,
        "result": {
            "success": True,
            "output": f"Completed: {tool_description}"
        },
        "playbook_used": [],
        "timestamp": datetime.now().isoformat()
    }


def capture_learning(trace, context):
    """
    Capture learning by calling ce-ace learn --stdin.
    Returns learning statistics if available.
    """
    import os

    # Build environment with context
    env = os.environ.copy()
    if context.get('org'):
        env['ACE_ORG_ID'] = context['org']
    if context.get('project'):
        env['ACE_PROJECT_ID'] = context['project']

    try:
        result = subprocess.run(
            ['ce-ace', 'learn', '--stdin', '--json'],
            input=json.dumps(trace),
            text=True,
            capture_output=True,
            timeout=30,
            env=env
        )

        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                return response.get('learning_statistics')
            except json.JSONDecodeError:
                return None
        return None

    except Exception:
        return None


def main():
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)

        # Check if this is substantial work
        if not is_substantial_task(event):
            # Skip trivial operations silently
            print(json.dumps({}))
            sys.exit(0)

        # Get project context
        context = get_context()
        if not context:
            # No context, skip silently
            print(json.dumps({}))
            sys.exit(0)

        # Substantial work detected - capture learning immediately!
        trace = build_execution_trace_from_posttooluse(event)

        # Capture learning
        stats = capture_learning(trace, context)

        # Build user feedback
        message_lines = ["✅ [ACE] Task complete - Learning captured!"]

        if stats:
            # Display enhanced feedback (v1.0.13+)
            created = stats.get('patterns_created', 0)
            updated = stats.get('patterns_updated', 0)

            if created > 0 or updated > 0:
                message_lines.append("")
                message_lines.append("📚 ACE Learning:")
                if created > 0:
                    message_lines.append(f"   • {created} new pattern{'s' if created != 1 else ''}")
                if updated > 0:
                    message_lines.append(f"   • {updated} pattern{'s' if updated != 1 else ''} updated")

                conf = stats.get('average_confidence', 0)
                if conf > 0:
                    message_lines.append(f"   • Quality: {int(conf * 100)}%")

        # Return feedback to user
        output = {
            "systemMessage": "\n".join(message_lines)
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block tool execution
        print(json.dumps({}))
        sys.exit(0)


if __name__ == '__main__':
    main()
