#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE After Task Hook - PreCompact Event Handler

Automatically captures learning from completed work before compaction.
Calls ce-ace learn --stdin with conversation summary.
"""

import json
import sys
import subprocess
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_context import get_context


def extract_execution_trace(event):
    """Build proper ExecutionTrace from PreCompact event."""
    from datetime import datetime

    messages = event.get('messages', [])
    tool_uses = event.get('tool_uses', [])

    # Extract task description from first user message or summary
    task_description = event.get('summary', 'Session work')
    if messages and len(messages) > 0:
        first_user_msg = next((m for m in messages if m.get('role') == 'user'), None)
        if first_user_msg:
            content = first_user_msg.get('content', '')
            task_description = content[:200] if content else task_description

    # Build trajectory from tool uses
    trajectory = []
    for idx, tool in enumerate(tool_uses, 1):
        trajectory.append({
            "step": idx,
            "action": f"{tool.get('tool_name', 'unknown')} - {tool.get('description', '')[:100]}",
            "result": tool.get('result', {}).get('summary', 'completed')[:200] if isinstance(tool.get('result'), dict) else 'completed'
        })

    # If no tool uses, create generic trajectory from message flow
    if not trajectory and messages:
        trajectory = [{
            "step": 1,
            "action": "Conversation interaction",
            "result": f"Exchanged {len(messages)} messages"
        }]

    # Extract lessons learned from last assistant message
    lessons = "Auto-captured session learning"
    if messages:
        last_assistant = next((m for m in reversed(messages) if m.get('role') == 'assistant'), None)
        if last_assistant:
            content = last_assistant.get('content', '')
            if content:
                lessons = content[:500]  # Last assistant response as lessons

    # Check for errors in tool results
    has_errors = any(
        tool.get('result', {}).get('error') or tool.get('result', {}).get('stderr')
        for tool in tool_uses
        if isinstance(tool.get('result'), dict)
    )

    # Extract playbook patterns used (from ACE retrieval context)
    playbook_used = event.get('playbook_patterns_used', [])

    return {
        "task": task_description,
        "trajectory": trajectory,
        "result": {
            "success": not has_errors,
            "output": lessons
        },
        "playbook_used": playbook_used,
        "timestamp": datetime.now().isoformat()
    }


def main():
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)

        # Get project context
        context = get_context()
        if not context:
            output = {
                "systemMessage": "⚠️ [ACE] No project context found - skipping automatic learning"
            }
            print(json.dumps(output))
            sys.exit(0)

        # Build ExecutionTrace from event
        trace = extract_execution_trace(event)

        # Build user-visible message lines with details
        message_lines = [
            "",
            "📚 [ACE] Automatically capturing learning from this session...",
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
                message_lines.append("✅ [ACE] Learning captured and sent to server!")
                # Parse JSON response to show what was learned
                try:
                    response = json.loads(result.stdout)
                    if response.get('analysis_triggered'):
                        message_lines.append("   🧠 Server analysis in progress...")

                    # Show pattern count if available
                    patterns_count = response.get('patterns_extracted')
                    if patterns_count:
                        message_lines.append(f"   📝 {patterns_count} patterns extracted for review")

                    # Show sections affected
                    sections = response.get('sections_affected', [])
                    if sections:
                        sections_str = ', '.join(sections)
                        message_lines.append(f"   📚 Sections: {sections_str}")

                    # Show summary if available
                    summary = response.get('summary')
                    if summary:
                        message_lines.append(f"   💡 {summary[:100]}")
                except json.JSONDecodeError:
                    pass  # CLI response wasn't JSON, that's okay
                except Exception:
                    pass  # Don't fail on response parsing
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

        # Output JSON with systemMessage for user visibility
        output = {
            "systemMessage": "\n".join(message_lines)
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block compaction
        print(f"[ERROR] ACE after-task hook failed: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
