#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE Task Complete Hook - PostToolUse Event Handler

Automatically captures learning after substantial task completion.
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


def extract_task_trace(event):
    """
    Build ExecutionTrace from PostToolUse event with RICH context.

    Extracts:
    - What was done (detailed task description)
    - How it was done (steps and approach)
    - What changed (file paths, code snippets)
    - What was learned (outcomes, errors resolved)

    This prevents generic "Edit: " messages and ensures unique, valuable learning.
    """
    from datetime import datetime

    tool_name = event.get('tool_name', 'unknown')
    tool_description = event.get('description', '')
    tool_result = event.get('result', {})

    # Build RICH task description with context
    # Include file paths, specific changes, and intent
    if tool_name == 'Edit' and tool_description:
        # Extract file path from description (usually first part)
        task_description = f"Modified code: {tool_description}"
    elif tool_name == 'Write' and tool_description:
        task_description = f"Created/wrote file: {tool_description}"
    elif tool_name == 'Task' and tool_description:
        task_description = f"Completed subagent task: {tool_description}"
    elif tool_name == 'Bash' and 'git commit' in tool_description.lower():
        task_description = f"Committed changes: {tool_description}"
    else:
        # Fallback with tool name and description
        task_description = f"{tool_name}: {tool_description}" if tool_description else tool_name

    # Build detailed trajectory (capture FULL descriptions - server will filter)
    trajectory = [{
        "step": 1,
        "action": f"{tool_name} - {tool_description}",  # NO TRUNCATION - send all
        "result": str(tool_result.get('summary', 'completed')) if isinstance(tool_result, dict) else 'completed'
    }]

    # Detect success/failure from result
    has_error = False
    error_details = None
    if isinstance(tool_result, dict):
        has_error = bool(tool_result.get('error') or tool_result.get('stderr'))
        if has_error:
            error_details = tool_result.get('error') or tool_result.get('stderr', '')

    # Extract output/lessons with FULL CONTEXT (no truncation)
    # Server Reflector/Curator will handle deduplication and filtering
    output = ""
    if isinstance(tool_result, dict):
        # Include ALL fields for maximum context
        if tool_result.get('output'):
            output += f"Output: {tool_result['output']}\n"
        if tool_result.get('summary'):
            output += f"Summary: {tool_result['summary']}\n"
        if tool_result.get('details'):
            output += f"Details: {tool_result['details']}\n"
        if error_details:
            output += f"Error resolved: {error_details}\n"

    # Generous limit (5000 chars) - capture comprehensive context
    lessons = output[:5000] if output.strip() else f"Successfully completed {tool_name} operation: {tool_description}"

    return {
        "task": task_description[:2000],  # Increased: 300 → 2000 chars for full context
        "trajectory": trajectory,
        "result": {
            "success": not has_error,
            "output": lessons  # Up to 5000 chars of lessons
        },
        "timestamp": datetime.now().isoformat(),
        "trigger": "PostToolUse"
    }


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

        # Build ExecutionTrace from event
        trace = extract_task_trace(event)

        # Call ce-ace learn --stdin with ExecutionTrace JSON
        # Context passed via environment variables
        try:
            # Build environment with context
            import os
            env = os.environ.copy()
            if context['org']:
                env['ACE_ORG_ID'] = context['org']
            if context['project']:
                env['ACE_PROJECT_ID'] = context['project']

            result = subprocess.run(
                ['ce-ace', 'learn', '--stdin', '--json'],
                input=json.dumps(trace),
                text=True,
                capture_output=True,
                timeout=30,
                env=env
            )

            if result.returncode == 0:
                # Learning captured successfully - show details
                message_lines = [
                    f"✅ [ACE] Learned from: {trace['task'][:60]}..."
                ]

                # Parse response to show what was learned
                try:
                    response = json.loads(result.stdout)

                    # Show pattern count if available
                    patterns_count = response.get('patterns_extracted')
                    if patterns_count:
                        message_lines.append(f"   📝 {patterns_count} new patterns")

                    # Show sections affected
                    sections = response.get('sections_affected', [])
                    if sections:
                        sections_str = ', '.join(sections[:2])
                        if len(sections) > 2:
                            sections_str += f' +{len(sections)-2} more'
                        message_lines.append(f"   📚 {sections_str}")

                except (json.JSONDecodeError, Exception):
                    pass  # No extra details available

                output = {
                    "systemMessage": "\n".join(message_lines)
                }
            else:
                # Failed silently - don't interrupt user
                output = {}

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # Fail silently - don't interrupt workflow
            output = {}

        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block tool execution
        print(json.dumps({}))
        sys.exit(0)


if __name__ == '__main__':
    main()
