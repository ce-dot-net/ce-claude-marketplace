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


def parse_transcript(transcript_path):
    """
    Parse Claude Code transcript .jsonl file to extract messages and tool_uses.

    Stop hooks provide transcript_path instead of parsed messages/tool_uses.
    This function reads the .jsonl file and reconstructs the data structure
    that PreCompact hooks receive natively.
    """
    messages = []
    tool_uses = []

    try:
        transcript_file = Path(transcript_path).expanduser()
        if not transcript_file.exists():
            return messages, tool_uses

        with open(transcript_file, 'r') as f:
            for line in f:
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

    return messages, tool_uses


def main():
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

        # Extract hook event name (PreCompact or Stop)
        hook_event_name = event.get('hook_event_name', 'PreCompact')

        # CRITICAL: Handle Stop and PostToolUse hook data format
        # According to Claude Code docs, Stop/PostToolUse hooks provide transcript_path instead of parsed messages
        # PreCompact hooks provide pre-parsed messages/tool_uses directly
        if hook_event_name in ['Stop', 'PostToolUse']:
            # Check if we already have messages (defensive coding)
            if 'messages' not in event or not event.get('messages'):
                # Need to parse transcript
                if 'transcript_path' in event:
                    messages, tool_uses = parse_transcript(event['transcript_path'])
                    event['messages'] = messages
                    event['tool_uses'] = tool_uses
                else:
                    # Fallback: no transcript path and no messages
                    # This shouldn't happen but handle gracefully
                    event['messages'] = []
                    event['tool_uses'] = []

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
        # Paper-aligned: Focus on trajectory completeness and execution feedback
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
        hook_label = "PreCompact (safety)" if hook_event_name == "PreCompact" else "Stop (end-of-task)"
        message_lines = [
            "",
            f"📚 [ACE] Automatically capturing learning from this session... ({hook_label})",
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
