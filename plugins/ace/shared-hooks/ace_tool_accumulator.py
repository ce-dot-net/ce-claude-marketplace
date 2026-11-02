#!/usr/bin/env python3
"""
ACE Tool Accumulator - SQLite storage for PostToolUse / PostToolUseFailure data.

v8 (DESIGN §4, §5 C4):
  PostToolUse        -> `ace_tool_accumulator.py --log`      (event on stdin) -> record_tool(success=True)
  PostToolUseFailure -> `ace_tool_accumulator.py --failure`  (event on stdin) -> record_tool(success=False)
  Stop               -> get_session_tools()  (ace_after_task builds the trajectory)

The db lives in the per-session plugin-data dir
(<root>/projects/<project_id>/sessions/<session_id>/tools.db), so SessionEnd
removes rows left behind by skipped turns. WAL + busy_timeout (concurrent
async PostToolUse writers + the Stop reader), one versioned migration.
The hook mode prints nothing and never spawns ace-cli.
"""

import argparse
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, 'utils')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import plugin_data_dir  # noqa: E402
from ace_context import get_context  # noqa: E402

SCHEMA_VERSION = 1
_COLUMNS = [("agent_id", "TEXT"), ("start_ms", "INTEGER"), ("end_ms", "INTEGER"),
            ("duration_ms", "INTEGER"), ("success", "INTEGER"), ("error_first_line", "TEXT")]
ERROR_LOG_MAX = 5 * 1024 * 1024


def log_hook_exception(hook, err):
    """Append one line to <plugin-data>/logs/ace-hook-errors.log (max 5 MB, 1 backup). Never raises."""
    try:
        p = plugin_data_dir.errors_log()
        if p.exists() and p.stat().st_size > ERROR_LOG_MAX:
            os.replace(str(p), str(p) + '.1')
        ts = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with open(str(p), 'a') as f:
            f.write("%s %s %s: %s\n" % (ts, hook, type(err).__name__, str(err)[:500]))
    except Exception:
        pass


def read_event():
    """Hook JSON from stdin; invalid UTF-8 is replaced instead of failing the parse."""
    try:
        sys.stdin.reconfigure(errors='replace')
    except Exception:
        pass
    return json.load(sys.stdin)


@contextmanager
def _in_dir(working_dir):
    prev = None
    try:
        if working_dir and os.path.isdir(working_dir):
            prev = os.getcwd()
            os.chdir(working_dir)
    except OSError:
        prev = None
    try:
        yield
    finally:
        if prev:
            try:
                os.chdir(prev)
            except OSError:
                pass


def get_db_path(session_id: str, working_dir: str = None) -> Path:
    """<plugin-data>/projects/<project>/sessions/<session>/tools.db (project from .claude/settings.json)."""
    with _in_dir(working_dir):
        ctx = get_context()
    return plugin_data_dir.session_dir((ctx or {}).get('project') or 'default', session_id) / 'tools.db'


def init_db(db_path) -> sqlite3.Connection:
    """Open the db (WAL, busy_timeout 5 s) and run the one versioned migration."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.execute('PRAGMA busy_timeout=5000')
    if conn.execute('PRAGMA user_version').fetchone()[0] < SCHEMA_VERSION:
        conn.execute('PRAGMA journal_mode=WAL')
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
                success INTEGER,
                error_first_line TEXT,
                timestamp TEXT,
                UNIQUE(tool_use_id)
            )
        ''')
        have = {r[1] for r in conn.execute('PRAGMA table_info(tool_uses)')}
        for col, ddl in _COLUMNS:
            if col not in have:
                conn.execute('ALTER TABLE tool_uses ADD COLUMN %s %s' % (col, ddl))
        conn.execute('CREATE INDEX IF NOT EXISTS idx_session ON tool_uses(session_id)')
        conn.execute('PRAGMA user_version=%d' % SCHEMA_VERSION)
        conn.commit()
    return conn


def record_tool(session_id, agent_id, tool_name, tool_input_summary, tool_response_summary,
                success=True, error_first_line=None, tool_use_id=None,
                start_ms=None, end_ms=None, duration_ms=None, working_dir=None, db_path=None) -> bool:
    """C4: append one tool row. Returns True when stored (duplicate tool_use_id counts as stored)."""
    try:
        conn = init_db(db_path or get_db_path(session_id, working_dir))
        try:
            conn.execute(
                'INSERT INTO tool_uses (session_id, tool_name, tool_input, tool_response, tool_use_id,'
                ' agent_id, start_ms, end_ms, duration_ms, success, error_first_line, timestamp)'
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                (session_id, tool_name, tool_input_summary, tool_response_summary, tool_use_id,
                 agent_id or None, start_ms, end_ms, duration_ms, 1 if success else 0, error_first_line))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # duplicate tool_use_id — normal for hook retries
        finally:
            conn.close()
        return True
    except Exception as e:
        log_hook_exception('accumulator', e)
        return False


def append_tool(session_id, tool_name, tool_input, tool_response, tool_use_id, agent_id=None,
                working_dir=None, start_ms=None, end_ms=None, duration_ms=None, db_path=None) -> bool:
    """Compatibility wrapper (pre-v8 signature, dict payloads, always success)."""
    dump = lambda v: json.dumps(v) if isinstance(v, (dict, list)) else str(v)  # noqa: E731
    return record_tool(session_id, agent_id, tool_name, dump(tool_input), dump(tool_response), True, None,
                       tool_use_id=tool_use_id, start_ms=start_ms, end_ms=end_ms,
                       duration_ms=duration_ms, working_dir=working_dir, db_path=db_path)


_ALL = object()  # sentinel: no agent scoping (legacy behaviour)


def get_session_tools(session_id: str = None, working_dir: str = None, db_path=None, agent_id=_ALL) -> list:
    """8-tuples (tool_name, tool_input_json, tool_response_json, tool_use_id, agent_id,
    start_ms, end_ms, duration_ms). A failed row (PostToolUseFailure) has its
    error_first_line merged into tool_response as {"error": ...}."""
    try:
        db_path = Path(db_path) if db_path else get_db_path(session_id, working_dir)
        if not db_path.exists():
            return []
        conn = init_db(db_path)
        rows = conn.execute('''
            SELECT tool_name, tool_input, tool_response, tool_use_id, agent_id,
                   start_ms, end_ms, duration_ms, success, error_first_line
            FROM tool_uses WHERE session_id = ?''' + ('' if agent_id is _ALL else ' AND agent_id IS ?') + ' ORDER BY id',
            (session_id,) if agent_id is _ALL else (session_id, agent_id or None)).fetchall()
        conn.close()
    except Exception as e:
        log_hook_exception('accumulator', e)
        return []
    tools = []
    for name, tin, tresp, tuid, aid, s, e, d, success, err in rows:
        if success == 0:
            try:
                body = json.loads(tresp) if tresp else {}
            except ValueError:
                body = {}
            body = dict(body) if isinstance(body, dict) else {'content': body}
            body['error'] = err or body.get('error') or 'failed'
            tresp = json.dumps(body)
        tools.append((name, tin, tresp, tuid, aid, s, e, d))
    return tools


def clear_session(session_id: str, working_dir: str = None, agent_id=_ALL) -> bool:
    try:
        db_path = get_db_path(session_id, working_dir)
        if not db_path.exists():
            return True
        conn = init_db(db_path)
        if agent_id is _ALL:
            conn.execute('DELETE FROM tool_uses WHERE session_id = ?', (session_id,))
        else:  # agent_id IS ? matches NULL (= the main agent)
            conn.execute('DELETE FROM tool_uses WHERE session_id = ? AND agent_id IS ?',
                         (session_id, agent_id or None))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log_hook_exception('accumulator', e)
        return False


def get_session_stats(session_id: str, working_dir: str = None) -> dict:
    tools = get_session_tools(session_id, working_dir)
    state_changing = ['Edit', 'Write', 'Bash', 'mcp__', 'NotebookEdit']
    tool_names = [t[0] for t in tools]
    return {
        'total_tools': len(tools),
        'state_changing_tools': sum(1 for n in tool_names if any(sc in n for sc in state_changing)),
        'tool_names': tool_names,
    }


MAX_FIELD_CHARS = 8192


def _dump(value):
    """JSON-dump a tool payload, capped at MAX_FIELD_CHARS (Read/Write/MCP outputs can be huge).
    Dicts keep their shape: oversized string values are cut individually first."""
    if isinstance(value, str):
        return value[:MAX_FIELD_CHARS]
    if isinstance(value, dict):
        value = {k: (v[:2000] + '...[truncated]' if isinstance(v, str) and len(v) > 2000 else v)
                 for k, v in value.items()}
    out = json.dumps(value if value is not None else {})
    if len(out) > MAX_FIELD_CHARS:
        out = json.dumps({'_truncated': out[:MAX_FIELD_CHARS - 64]})
    return out


def hook_main(failure: bool) -> None:
    """PostToolUse / PostToolUseFailure entry: event on stdin, silent, 0 CLI calls."""
    hook = 'PostToolUseFailure' if failure else 'PostToolUse'
    try:
        ev = read_event()
        if not isinstance(ev, dict):
            raise ValueError('hook event is not a JSON object')
        cwd = ev.get('cwd') or ev.get('working_directory')
        if cwd and os.path.isdir(cwd):
            os.chdir(cwd)  # project context (.claude/settings.json) comes from the hook cwd
        sid, tool, tuid = ev.get('session_id'), ev.get('tool_name'), ev.get('tool_use_id')
        if not (sid and tool and tuid):
            return
        ctx = get_context() or {}
        if plugin_data_dir.disabled_flag(ctx.get('project') or 'default', sid).exists():
            return
        if failure:
            # doc cc_hooks_reference.md:2287-2330 — `error` is display text, key on its first line
            err = str(ev.get('error') or '')
            first = (err.splitlines() or [''])[0][:200]
            resp, success = json.dumps({'error': err[:2000]}), False
        else:
            first, resp, success = None, _dump(ev.get('tool_response')), True
        record_tool(sid, ev.get('agent_id'), tool, _dump(ev.get('tool_input')), resp, success, first,
                    tool_use_id=tuid, start_ms=ev.get('tool_start_ms') or ev.get('start_ms'),
                    end_ms=ev.get('tool_end_ms') or ev.get('end_ms'), duration_ms=ev.get('duration_ms'))
    except Exception as e:
        log_hook_exception(hook, e)


def main():
    """Hook mode (`--log`/`--no-log`/`--failure`) or the debug CLI (get/clear/stats)."""
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if sys.argv[1:2] == ['--batch']:
        return  # ponytail: WP-H implements PostToolBatch; until then a silent rc-0 no-op
    if not sys.argv[1:] or sys.argv[1] in ('--log', '--no-log', '--failure'):
        hook_main('--failure' in flags)
        return

    parser = argparse.ArgumentParser(description='ACE Tool Accumulator')
    sub = parser.add_subparsers(dest='command')
    for name in ('get', 'clear', 'stats'):
        p = sub.add_parser(name)
        p.add_argument('--session-id', required=True)
        p.add_argument('--working-dir')
    args = parser.parse_args()

    if args.command == 'get':
        result = []
        for name, tin, tresp, tuid, aid, s, e, d in get_session_tools(args.session_id, args.working_dir):
            entry = {'tool_name': name, 'tool_input': json.loads(tin) if tin else {},
                     'tool_response': json.loads(tresp) if tresp else {},
                     'tool_use_id': tuid, 'agent_id': aid}
            for k, v in (('start_ms', s), ('end_ms', e), ('duration_ms', d)):
                if v is not None:
                    entry[k] = v
            result.append(entry)
        print(json.dumps(result, indent=2))
    elif args.command == 'clear':
        ok = clear_session(args.session_id, args.working_dir)
        print(json.dumps({'success': ok}))
        sys.exit(0 if ok else 1)
    elif args.command == 'stats':
        print(json.dumps(get_session_stats(args.session_id, args.working_dir), indent=2))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
