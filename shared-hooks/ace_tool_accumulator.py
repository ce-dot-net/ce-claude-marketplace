#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ACE Tool Accumulator - SQLite storage for PostToolUse hook data.

v5.3.0: PostToolUse Accumulation Architecture

This module provides GROUND TRUTH tool execution data by:
1. PostToolUse hook calls `append_tool()` after EVERY tool call
2. Stop hook calls `get_session_tools()` to build trajectory
3. Stop hook calls `clear_session()` to cleanup after processing

Per ACE Research Paper (arXiv:2510.04618v1):
- Page 5: "Generator produces reasoning trajectories"
- Page 7: "leveraging natural execution feedback"
- Page 19: "FULL AGENT-ENVIRONMENT TRAJECTORY"

This replaces unreliable transcript parsing with direct tool data from Claude Code.
"""

import sqlite3
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime


def get_db_path(working_dir: str = None) -> Path:
    """Get database path in project's .claude/data/logs/ directory."""
    if working_dir:
        return Path(working_dir) / '.claude/data/logs/ace-tools.db'
    return Path('.claude/data/logs/ace-tools.db')


def init_db(db_path: Path = None) -> sqlite3.Connection:
    """Initialize SQLite database for tool accumulation."""
    if db_path is None:
        db_path = get_db_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))

    conn.execute('''
        CREATE TABLE IF NOT EXISTS tool_uses (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            tool_input TEXT,
            tool_response TEXT,
            tool_use_id TEXT,
            timestamp TEXT,
            UNIQUE(tool_use_id)
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_session ON tool_uses(session_id)')
    conn.commit()
    return conn


def append_tool(session_id: str, tool_name: str, tool_input: dict,
                tool_response: dict, tool_use_id: str, working_dir: str = None) -> bool:
    """
    Append tool use to accumulator (called by PostToolUse hook).

    Args:
        session_id: Claude Code session ID
        tool_name: Name of the tool (Edit, Write, Bash, etc.)
        tool_input: Tool input parameters (dict)
        tool_response: Tool response/result (dict)
        tool_use_id: Unique tool use ID from Claude Code
        working_dir: Project working directory (optional)

    Returns:
        True if appended successfully, False otherwise
    """
    try:
        db_path = get_db_path(working_dir)
        conn = init_db(db_path)

        conn.execute('''
            INSERT OR IGNORE INTO tool_uses
            (session_id, tool_name, tool_input, tool_response, tool_use_id, timestamp)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        ''', (
            session_id,
            tool_name,
            json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input),
            json.dumps(tool_response) if isinstance(tool_response, dict) else str(tool_response),
            tool_use_id
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"append_tool error: {e}\n")
        return False


def get_session_tools(session_id: str, working_dir: str = None) -> list:
    """
    Get all tools for session (called by Stop hook).

    Args:
        session_id: Claude Code session ID
        working_dir: Project working directory (optional)

    Returns:
        List of tuples: (tool_name, tool_input_json, tool_response_json, tool_use_id)
    """
    try:
        db_path = get_db_path(working_dir)
        if not db_path.exists():
            return []

        conn = init_db(db_path)
        cursor = conn.execute('''
            SELECT tool_name, tool_input, tool_response, tool_use_id
            FROM tool_uses
            WHERE session_id = ?
            ORDER BY id
        ''', (session_id,))
        tools = cursor.fetchall()
        conn.close()
        return tools
    except Exception as e:
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"get_session_tools error: {e}\n")
        return []


def clear_session(session_id: str, working_dir: str = None) -> bool:
    """
    Clear tools after Stop hook processes them.

    Args:
        session_id: Claude Code session ID
        working_dir: Project working directory (optional)

    Returns:
        True if cleared successfully, False otherwise
    """
    try:
        db_path = get_db_path(working_dir)
        if not db_path.exists():
            return True

        conn = init_db(db_path)
        conn.execute('DELETE FROM tool_uses WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"clear_session error: {e}\n")
        return False


def get_session_stats(session_id: str, working_dir: str = None) -> dict:
    """
    Get statistics for a session (for debugging).

    Args:
        session_id: Claude Code session ID
        working_dir: Project working directory (optional)

    Returns:
        Dict with total_tools, state_changing_tools, tool_names
    """
    tools = get_session_tools(session_id, working_dir)
    state_changing = ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit']

    tool_names = [t[0] for t in tools]
    state_changing_count = sum(
        1 for name in tool_names
        if any(sc in name for sc in state_changing)
    )

    return {
        'total_tools': len(tools),
        'state_changing_tools': state_changing_count,
        'tool_names': tool_names
    }


def main():
    """CLI interface for ace_tool_accumulator."""
    parser = argparse.ArgumentParser(description='ACE Tool Accumulator')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # append command
    append_parser = subparsers.add_parser('append', help='Append tool to accumulator')
    append_parser.add_argument('--session-id', required=True, help='Session ID')
    append_parser.add_argument('--tool-name', required=True, help='Tool name')
    append_parser.add_argument('--tool-input', required=True, help='Tool input (JSON)')
    append_parser.add_argument('--tool-response', required=True, help='Tool response (JSON)')
    append_parser.add_argument('--tool-use-id', required=True, help='Tool use ID')
    append_parser.add_argument('--working-dir', help='Working directory')

    # get command
    get_parser = subparsers.add_parser('get', help='Get session tools')
    get_parser.add_argument('--session-id', required=True, help='Session ID')
    get_parser.add_argument('--working-dir', help='Working directory')

    # clear command
    clear_parser = subparsers.add_parser('clear', help='Clear session tools')
    clear_parser.add_argument('--session-id', required=True, help='Session ID')
    clear_parser.add_argument('--working-dir', help='Working directory')

    # stats command
    stats_parser = subparsers.add_parser('stats', help='Get session statistics')
    stats_parser.add_argument('--session-id', required=True, help='Session ID')
    stats_parser.add_argument('--working-dir', help='Working directory')

    args = parser.parse_args()

    if args.command == 'append':
        try:
            tool_input = json.loads(args.tool_input)
        except json.JSONDecodeError:
            tool_input = args.tool_input
        try:
            tool_response = json.loads(args.tool_response)
        except json.JSONDecodeError:
            tool_response = args.tool_response

        success = append_tool(
            session_id=args.session_id,
            tool_name=args.tool_name,
            tool_input=tool_input,
            tool_response=tool_response,
            tool_use_id=args.tool_use_id,
            working_dir=args.working_dir
        )
        print(json.dumps({'success': success}))
        sys.exit(0 if success else 1)

    elif args.command == 'get':
        tools = get_session_tools(args.session_id, args.working_dir)
        result = []
        for tool_name, tool_input, tool_response, tool_use_id in tools:
            result.append({
                'tool_name': tool_name,
                'tool_input': json.loads(tool_input) if tool_input else {},
                'tool_response': json.loads(tool_response) if tool_response else {},
                'tool_use_id': tool_use_id
            })
        print(json.dumps(result, indent=2))

    elif args.command == 'clear':
        success = clear_session(args.session_id, args.working_dir)
        print(json.dumps({'success': success}))
        sys.exit(0 if success else 1)

    elif args.command == 'stats':
        stats = get_session_stats(args.session_id, args.working_dir)
        print(json.dumps(stats, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
