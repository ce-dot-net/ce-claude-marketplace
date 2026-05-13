#!/usr/bin/env python3
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
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime


def get_db_path(working_dir: str = None) -> Path:
    return _resolve_db_path(working_dir)


def _resolve_db_path(working_dir: str = None) -> Path:
    """Resolve ace-tools.db path with backward-compat.

    v6.5.0 Item #2: prefer ${CLAUDE_PLUGIN_DATA}/projects/<id>/ace-tools.db when set
    (plugin-persistent, survives plugin updates). Falls back to project-local
    .claude/data/logs/ace-tools.db when env not set OR when an existing DB lives
    at the old path (in-place compatibility for users with existing data).
    """
    import os as _os

    # v6.5.0: Project-isolated plugin data dir
    if _os.environ.get("CLAUDE_PLUGIN_DATA"):
        try:
            # Ensure shared-hooks dir is on sys.path even when this module is loaded
            # by absolute path (e.g. `python3 /full/path/ace_tool_accumulator.py`)
            import sys as _sys
            _self_dir = _os.path.dirname(_os.path.abspath(__file__))
            if _self_dir not in _sys.path:
                _sys.path.insert(0, _self_dir)
            from utils.plugin_data_dir import get_project_data_dir
            new_path = get_project_data_dir(cwd=working_dir, create=False) / "ace-tools.db"
            old_path = (Path(working_dir) if working_dir else Path()) / ".claude/data/logs/ace-tools.db"
            # If user has existing data in the old path AND no new path yet, keep
            # reading from old until an explicit migration step is run.
            if old_path.exists() and not new_path.exists():
                return old_path
            return new_path
        except Exception:
            pass  # Fall through to legacy path on any error
    # Legacy / fallback
    if working_dir:
        return Path(working_dir) / '.claude/data/logs/ace-tools.db'
    return Path('.claude/data/logs/ace-tools.db')


def init_db(db_path=None) -> sqlite3.Connection:
    """Initialize SQLite database for tool accumulation.

    Accepts either a pathlib.Path or a string for db_path.

    v6.5.0 PR-review I3: triggers a one-shot lazy migration of legacy
    `.claude/data/logs/ace-tools.db` to `${CLAUDE_PLUGIN_DATA}/projects/<id>/`
    when the env var is set, the legacy path has data, and the new path
    doesn't exist yet. Behind an `ACE_MIGRATE_DATA=1` env opt-in for safety.
    """
    if db_path is None:
        db_path = get_db_path()
    # Accept str or Path
    db_path = Path(db_path)

    # PR-review I3: opt-in lazy migration of existing DB.
    if os.environ.get("ACE_MIGRATE_DATA") == "1" and os.environ.get("CLAUDE_PLUGIN_DATA"):
        try:
            import sys as _sys
            _self_dir = os.path.dirname(os.path.abspath(__file__))
            if _self_dir not in _sys.path:
                _sys.path.insert(0, _self_dir)
            from utils.plugin_data_dir import get_project_data_dir, lazy_migrate
            new_db = get_project_data_dir(create=True) / "ace-tools.db"
            old_db = Path(".claude/data/logs/ace-tools.db")
            if old_db.exists() and not new_db.exists():
                lazy_migrate(old_db, new_db)
                # After successful migration, write subsequent appends to new path
                db_path = new_db
        except Exception:
            pass  # migration is best-effort; keep using current db_path

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
            agent_id TEXT,
            start_ms INTEGER,
            end_ms INTEGER,
            duration_ms INTEGER,
            timestamp TEXT,
            UNIQUE(tool_use_id)
        )
    ''')
    # v6.0.0: Add agent_id column if upgrading from older schema
    try:
        conn.execute('ALTER TABLE tool_uses ADD COLUMN agent_id TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    # v6.5.0: Add timing columns if upgrading from older schema (Item #1)
    for col, ddl in [("start_ms", "INTEGER"), ("end_ms", "INTEGER"), ("duration_ms", "INTEGER")]:
        try:
            conn.execute(f'ALTER TABLE tool_uses ADD COLUMN {col} {ddl}')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.execute('CREATE INDEX IF NOT EXISTS idx_session ON tool_uses(session_id)')
    conn.commit()
    return conn


def append_tool(session_id: str, tool_name: str, tool_input: dict,
                tool_response: dict, tool_use_id: str, agent_id: str = None,
                working_dir: str = None,
                start_ms: int = None, end_ms: int = None, duration_ms: int = None,
                db_path=None) -> bool:
    """
    Append tool use to accumulator (called by PostToolUse hook).

    Args:
        session_id: Claude Code session ID
        tool_name: Name of the tool (Edit, Write, Bash, etc.)
        tool_input: Tool input parameters (dict)
        tool_response: Tool response/result (dict)
        tool_use_id: Unique tool use ID from Claude Code
        agent_id: Agent ID for per-agent trajectory (CC 2.1.69+, optional)
        working_dir: Project working directory (optional)
        start_ms: Tool call start timestamp (epoch ms, optional) — v6.5.0
        end_ms: Tool call end timestamp (epoch ms, optional) — v6.5.0
        duration_ms: Tool call duration (ms, optional) — v6.5.0
        db_path: Explicit DB path (overrides working_dir-derived path, optional)

    Returns:
        True if appended successfully, False otherwise
    """
    try:
        if db_path is None:
            db_path = get_db_path(working_dir)
        conn = init_db(db_path)

        try:
            conn.execute('''
                INSERT INTO tool_uses
                (session_id, tool_name, tool_input, tool_response, tool_use_id, agent_id,
                 start_ms, end_ms, duration_ms, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (
                session_id,
                tool_name,
                json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input),
                json.dumps(tool_response) if isinstance(tool_response, dict) else str(tool_response),
                tool_use_id,
                agent_id or None,
                start_ms,
                end_ms,
                duration_ms,
            ))
        except sqlite3.IntegrityError:
            pass  # Duplicate tool_use_id — normal for hook retries
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        import os
        if os.environ.get('ACE_DEBUG_HOOKS') == '1':
            with open('/tmp/ace_hook_debug.log', 'a') as f:
                f.write(f"append_tool error: {e}\n")
        return False


def get_session_tools(session_id: str = None, working_dir: str = None, db_path=None) -> list:
    """
    Get all tools for session (called by Stop hook).

    Args:
        session_id: Claude Code session ID
        working_dir: Project working directory (optional)
        db_path: Explicit DB path override (optional) — v6.5.0

    Returns:
        List of 8-tuples (v6.5.0):
          (tool_name, tool_input_json, tool_response_json, tool_use_id, agent_id,
           start_ms, end_ms, duration_ms)
    """
    try:
        if db_path is None:
            db_path = get_db_path(working_dir)
        else:
            db_path = Path(db_path)
        if not db_path.exists():
            return []

        conn = init_db(db_path)
        cursor = conn.execute('''
            SELECT tool_name, tool_input, tool_response, tool_use_id, agent_id,
                   start_ms, end_ms, duration_ms
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
    append_parser.add_argument('--agent-id', default='', help='Agent ID (CC 2.1.69+)')
    append_parser.add_argument('--working-dir', help='Working directory')
    append_parser.add_argument('--start-ms', type=int, default=None, help='Tool start epoch ms (v6.5.0)')
    append_parser.add_argument('--end-ms', type=int, default=None, help='Tool end epoch ms (v6.5.0)')
    append_parser.add_argument('--duration-ms', type=int, default=None, help='Tool duration ms (v6.5.0)')

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
            agent_id=args.agent_id or None,
            working_dir=args.working_dir,
            start_ms=args.start_ms,
            end_ms=args.end_ms,
            duration_ms=args.duration_ms,
        )
        print(json.dumps({'success': success}))
        sys.exit(0 if success else 1)

    elif args.command == 'get':
        tools = get_session_tools(args.session_id, args.working_dir)
        result = []
        for tool_name, tool_input, tool_response, tool_use_id, agent_id, start_ms, end_ms, duration_ms in tools:
            entry = {
                'tool_name': tool_name,
                'tool_input': json.loads(tool_input) if tool_input else {},
                'tool_response': json.loads(tool_response) if tool_response else {},
                'tool_use_id': tool_use_id,
                'agent_id': agent_id,
            }
            if start_ms is not None:
                entry['start_ms'] = start_ms
            if end_ms is not None:
                entry['end_ms'] = end_ms
            if duration_ms is not None:
                entry['duration_ms'] = duration_ms
            result.append(entry)
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
