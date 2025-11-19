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

        # Substantial work detected - tracking for future learning
        # NOTE: Actual learning happens via PreCompact/Stop hooks to avoid duplicates
        # This hook just monitors for substantial work completion

        # Silent exit - no learning capture here
        print(json.dumps({}))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block tool execution
        print(json.dumps({}))
        sys.exit(0)


if __name__ == '__main__':
    main()
