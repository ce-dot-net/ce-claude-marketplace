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
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_context import get_context


def is_substantial_task(event):
    """
    Determine if this tool use represents substantial work worth learning from.

    Triggers on:
    - Task tool completion (subagent work)
    - Multiple file edits in sequence
    - Implementation/debugging work (Write, Edit after Read)
    - Git commits

    Skips:
    - Single file reads
    - Simple Grep/Glob searches
    - Trivial Bash commands
    - Basic Q&A interactions
    """
    tool_name = event.get('tool_name', '')
    tool_description = event.get('description', '').lower()

    # Task tool completion is always substantial
    if tool_name == 'Task':
        return True

    # Git commits indicate completed work
    if tool_name == 'Bash' and 'git commit' in tool_description:
        return True

    # Multiple Write/Edit operations indicate implementation work
    if tool_name in ['Write', 'Edit']:
        # Check if this is part of a sequence (we'll track state)
        return True

    # Skip trivial operations
    trivial_tools = ['Read', 'Grep', 'Glob', 'Bash']
    if tool_name in trivial_tools:
        return False

    return False


def extract_task_trace(event):
    """Build ExecutionTrace from PostToolUse event."""
    from datetime import datetime

    tool_name = event.get('tool_name', 'unknown')
    tool_description = event.get('description', '')
    tool_result = event.get('result', {})

    # Build task description
    task_description = f"{tool_name}: {tool_description}"

    # Build trajectory from this tool use
    trajectory = [{
        "step": 1,
        "action": f"{tool_name} - {tool_description[:100]}",
        "result": str(tool_result.get('summary', 'completed'))[:200] if isinstance(tool_result, dict) else 'completed'
    }]

    # Detect success/failure from result
    has_error = False
    if isinstance(tool_result, dict):
        has_error = bool(tool_result.get('error') or tool_result.get('stderr'))

    # Extract output/lessons
    output = tool_result.get('output', '') if isinstance(tool_result, dict) else str(tool_result)
    lessons = output[:500] if output else "Completed task successfully"

    return {
        "task": task_description[:200],
        "trajectory": trajectory,
        "result": {
            "success": not has_error,
            "output": lessons
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
