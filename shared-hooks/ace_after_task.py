#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE After Task Hook - PreCompact Event Handler

Two critical functions:
1. Recalls pinned session patterns BEFORE compaction (pattern persistence)
2. Captures learning from completed work (with rich context)

Ensures patterns survive compaction and learning is detailed/unique.
"""

import json
import sys
import subprocess
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_context import get_context
from ace_cli import recall_session


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
    from datetime import datetime

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
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')

        # Only process assistant messages (Claude's responses)
        if role != 'assistant':
            continue

        content_lower = content.lower()

        # Extract decisions (architectural choices, technology selections)
        if any(word in content_lower for word in ['decided', 'chose', 'using', 'will use', 'approach', 'strategy']):
            for sentence in content.split('.'):
                if any(word in sentence.lower() for word in ['decided', 'chose', 'using', 'will use', 'approach']):
                    clean = sentence.strip()
                    if len(clean) > 20:  # Meaningful content
                        decisions.append(clean)

        # Extract gotchas (errors fixed, pitfalls discovered)
        if any(word in content_lower for word in ['error', 'issue', 'problem', 'failed', 'fixed', 'solved', 'gotcha']):
            for sentence in content.split('.'):
                if any(word in sentence.lower() for word in ['error', 'fixed', 'solved', 'issue', 'problem']):
                    clean = sentence.strip()
                    if len(clean) > 20:
                        gotchas.append(clean)

        # Extract accomplishments (what was successfully completed)
        if any(word in content_lower for word in ['completed', 'working', 'successfully', 'implemented', 'created', 'built']):
            for sentence in content.split('.'):
                if any(word in sentence.lower() for word in ['completed', 'working', 'successfully', 'implemented']):
                    clean = sentence.strip()
                    if len(clean) > 20:
                        accomplishments.append(clean)

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

    # Extract playbook patterns used (from ACE retrieval context)
    playbook_used = event.get('playbook_patterns_used', [])

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


def main():
    try:
        # Read hook event from stdin
        event = json.load(sys.stdin)

        # Extract hook event name (PreCompact or Stop)
        hook_event_name = event.get('hook_event_name', 'PreCompact')

        # Get project context
        context = get_context()
        if not context:
            output = {
                "systemMessage": "⚠️ [ACE] No project context found - skipping automatic learning"
            }
            print(json.dumps(output))
            sys.exit(0)

        # STEP 1: Recall pinned session patterns BEFORE learning capture
        # This ensures patterns survive context compaction
        recalled_patterns = None
        if context['project']:
            session_file = Path(f"/tmp/ace-session-{context['project']}.txt")
            if session_file.exists():
                try:
                    session_id = session_file.read_text().strip()
                    recalled_patterns = recall_session(
                        session_id=session_id,
                        org=context['org'],
                        project=context['project']
                    )
                except Exception:
                    # Non-fatal: continue without recalled patterns
                    pass

        # STEP 2: Build ExecutionTrace from event with rich context
        trace = extract_execution_trace(event)

        # STEP 3: Check if there's substantial work to capture
        # Paper-aligned: Focus on trajectory completeness and execution feedback (arXiv:2510.04618v1)
        # Skip only if: no trajectory OR auto-learning session work
        has_substantial_work = (
            trace['trajectory'] and len(trace['trajectory']) > 0 and
            not trace['task'].startswith("Session work")
        )

        if not has_substantial_work:
            # No substantial work - skip learning capture
            output = {
                "systemMessage": ""  # Silent skip - no need to notify user
            }
            print(json.dumps(output))
            sys.exit(0)

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

                    # NEW: v1.0.13+ enhanced learning statistics
                    stats = response.get('learning_statistics')
                    if stats:
                        # Display enhanced feedback (CLI team recommended format)
                        message_lines.append("")
                        message_lines.append("📚 ACE Learning:")

                        # Show what was created/updated
                        created = stats.get('patterns_created', 0)
                        updated = stats.get('patterns_updated', 0)
                        pruned = stats.get('patterns_pruned', 0)

                        if created > 0:
                            message_lines.append(f"   • {created} new pattern{'s' if created != 1 else ''}")
                        if updated > 0:
                            message_lines.append(f"   • {updated} pattern{'s' if updated != 1 else ''} updated")
                        if pruned > 0:
                            message_lines.append(f"   • {pruned} low-quality pattern{'s' if pruned != 1 else ''} pruned")

                        # Show quality metric
                        conf = stats.get('average_confidence', 0)
                        if conf > 0:
                            message_lines.append(f"   • Quality: {int(conf * 100)}%")

                    else:
                        # FALLBACK: Old server (v3.9.x and earlier) or analysis skipped
                        # Try legacy fields for backward compatibility
                        if response.get('analysis_triggered'):
                            message_lines.append("   🧠 Server analysis in progress...")

                        # Old format pattern count
                        patterns_count = response.get('patterns_extracted')
                        if patterns_count:
                            message_lines.append(f"   📝 {patterns_count} patterns extracted for review")

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
                "hookEventName": hook_event_name,  # Dynamic: "PreCompact" or "Stop"
                "additionalContext": ace_context
            }

        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        # Log error but don't block compaction
        print(f"[ERROR] ACE after-task hook failed: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
