#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
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
import shutil
from pathlib import Path
from datetime import datetime

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_context import get_context
from ace_cli import recall_session
from utils.git_utils import get_git_context, detect_commits_in_session
from ace_relevance_logger import log_execution_metrics

# Add plugin utils to path for validation
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))
from validation import is_valid_pattern_id

# Import re at module level for quality filters
import re as regex_module
import time

# CLI command detection (ace-cli preferred, ace-cli fallback)
CLI_CMD = 'ace-cli' if shutil.which('ace-cli') else 'ce-ace'


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

    for tool_name, _, _, _ in tools:
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


def build_trajectory_from_accumulated_tools(session_id: str, working_dir: str = None) -> tuple:
    """
    Build REAL trajectory from PostToolUse accumulated data.

    This is GROUND TRUTH - actual tool execution data.
    No transcript parsing required!

    Per ACE Research Paper (arXiv:2510.04618v1):
    - Page 5: Generator produces trajectories
    - Page 19: Trajectory contains tool calls with inputs and outputs

    Args:
        session_id: Claude Code session ID
        working_dir: Project working directory (optional)

    Returns:
        Tuple of (trajectory_list, tools_list)
    """
    # Import accumulator functions
    sys.path.insert(0, str(Path(__file__).parent))
    from ace_tool_accumulator import get_session_tools, clear_session

    tools = get_session_tools(session_id, working_dir)
    trajectory = []

    for i, (tool_name, tool_input_json, tool_response_json, tool_use_id) in enumerate(tools, 1):
        try:
            tool_input = json.loads(tool_input_json) if tool_input_json else {}
        except json.JSONDecodeError:
            tool_input = {}

        try:
            tool_response = json.loads(tool_response_json) if tool_response_json else {}
        except json.JSONDecodeError:
            tool_response = {}

        # Build trajectory step with REAL data
        trajectory.append({
            "step": i,
            "tool": tool_name,
            "action": summarize_tool_action(tool_name, tool_input),
            "result": summarize_tool_response(tool_name, tool_response)
        })

    return trajectory, tools


def skip_learning(reason, event=None):
    """
    Skip learning with user feedback.

    Per ACE Research Paper: Users should understand when learning is skipped.
    """
    if os.environ.get('ACE_DEBUG_HOOKS') == '1':
        with open('/tmp/ace_hook_debug.log', 'a') as f:
            f.write(f"ACE: Skipping learning - {reason}\n")
            if event:
                f.write(f"  Event: {json.dumps(event, default=str)[:500]}\n")

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

        # STEP 1: Build trajectory from accumulated tools (GROUND TRUTH)
        trajectory, tools = build_trajectory_from_accumulated_tools(session_id, working_dir)

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
        for _, _, tool_response_json, _ in tools:
            try:
                resp = json.loads(tool_response_json) if tool_response_json else {}
                if resp.get('error') or resp.get('stderr'):
                    has_errors = True
                    break
            except Exception:
                pass

        # Load pattern IDs for reinforcement learning
        playbook_used = []
        if session_id:
            try:
                state_file = Path(f'.claude/data/logs/ace-patterns-used-{session_id}.json')
                if state_file.exists():
                    playbook_used_raw = json.loads(state_file.read_text())
                    playbook_used = [pid for pid in playbook_used_raw if isinstance(pid, str) and is_valid_pattern_id(pid)]
                    state_file.unlink()  # One-time use
            except Exception:
                pass

        # v5.4.11: Read agent_type set by SessionStart hook (Claude Code 2.1.2+)
        # agent_type identifies subagent type: "main", "refactorer", "coder", etc.
        # Server can use this to attribute learning to specific agent types
        agent_type = "main"
        try:
            agent_type_file = Path(f"/tmp/ace-agent-type-{session_id}.txt")
            if agent_type_file.exists():
                agent_type = agent_type_file.read_text().strip() or "main"
        except Exception:
            pass  # Default to "main" if file not found

        # Build the trace
        trace = {
            "task": f"User request: {user_prompt[:2000]}",
            "trajectory": trajectory,
            "result": {
                "success": not has_errors,
                "output": f"Executed {len(tools)} tool calls"
            },
            "playbook_used": playbook_used,
            "timestamp": datetime.now().isoformat(),
            "agent_type": agent_type  # v5.4.11: Attribute learning to agent type
        }

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

        # STEP 8: Send to ace-cli learn --stdin
        try:
            env = os.environ.copy()
            if context['org']:
                env['ACE_ORG_ID'] = context['org']
            if context['project']:
                env['ACE_PROJECT_ID'] = context['project']

            # Get verbosity from env, default to 'detailed' for meaningful feedback
            verbosity = os.environ.get('ACE_VERBOSITY', 'detailed')

            result = subprocess.run(
                [CLI_CMD, 'learn', '--stdin', '--json', '--timeout', '300000', '--verbosity', verbosity],
                input=json.dumps(trace),
                text=True,
                capture_output=True,
                timeout=300,  # 5 min safety margin for SSE streaming
                env=env
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
                        merged = stats.get('patterns_merged', 0)
                        pruned = stats.get('patterns_pruned', 0)
                        conf = stats.get('average_confidence', 0)
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

                                # Line 2: quality & helpful
                                line2_parts = []
                                if conf > 0:
                                    line2_parts.append(f"⭐ {int(conf * 100)}% quality")
                                if helpful_delta != 0:
                                    sign = '+' if helpful_delta > 0 else ''
                                    line2_parts.append(f"👍 {sign}{helpful_delta} helpful")
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
                1 for tool_name, _, _, _ in tools
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
