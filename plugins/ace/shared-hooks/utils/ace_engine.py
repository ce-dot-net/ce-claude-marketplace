#!/usr/bin/env python3
"""Which process runs a search/learn: the in-process @ace-sdk/core engine or ace-cli (DESIGN §14).

argv builders only; ace_cli.py owns spawning and fallback. `python3 ace_engine.py --status`
prints select() as JSON (used by /ace:ace-doctor).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _plugin_root():
    """Same rule as ace_cli._plugin_root: an ACE CLAUDE_PLUGIN_ROOT wins (a copy, a symlinked checkout), else this
    file's plugin. The engine and its plugin-local core must come from the root the CLI resolution uses."""
    env = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if env and (Path(env) / 'shared-hooks' / 'utils' / 'ace_cli.py').is_file():
        return Path(env)
    return Path(__file__).resolve().parents[2]


ENGINE_DIR = _plugin_root() / 'engine'
CLI_BIN = 'ace-cli'  # default argv head; ace_cli owns which CLI really runs (cli=)
_SCOPE = ENGINE_DIR.parent / 'node_modules' / '@ace-sdk'
PLUGIN_LOCAL_CORES = (_SCOPE / 'cli' / 'node_modules' / '@ace-sdk' / 'core', _SCOPE / 'core')  # as resolve.js


def preflight():
    """(node_or_None, reason) without spawning anything; search.js/learn.js run the full gate (exit 3)."""
    if (os.environ.get('ACE_ENGINE') or '').lower() == 'cli':
        return None, 'ACE_ENGINE=cli'
    node = shutil.which('node')
    if not node:
        return None, 'no node on PATH'
    missing = [f for f in ('search.js', 'learn.js', 'resolve.js') if not (ENGINE_DIR / f).is_file()]
    if missing:  # node would exit 1 on these, which learn must read as "may have sent"
        return None, 'engine file missing: %s' % ','.join(missing)
    if any(d.is_dir() for d in PLUGIN_LOCAL_CORES):  # DESIGN §23: no ace-cli needed
        return node, 'ok'
    cli = shutil.which(CLI_BIN)
    if not cli:
        return None, 'no_cli'
    if '@ace-sdk/cli' not in os.path.realpath(cli).replace(os.sep, '/'):
        return None, 'core_missing: ace-cli is not an @ace-sdk/cli install'
    return node, 'ok'


def select():
    """Full gate for reporting: {"engine", "reason", "node", "core_dir", "core_version"}."""
    node, reason = preflight()
    out = {'engine': 'cli', 'reason': reason, 'node': node, 'core_dir': None, 'core_version': None}
    if not node:
        return out
    try:
        r = subprocess.run([node, str(ENGINE_DIR / 'resolve.js')], capture_output=True, text=True, timeout=20)
        gate = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        out['reason'] = 'resolve failed: %s' % str(e)[:200]
        return out
    out.update(reason=gate.get('reason'), core_dir=gate.get('core_dir'), core_version=gate.get('core_version'))
    if gate.get('ok'):
        out['engine'] = 'lib'
    return out


def search_command(query, *, org=None, project=None, session_id=None, top_k=None, node=None, cli=None, pin=True, ids=()):
    """(argv, stdin_bytes). node=None -> the CLI head `cli`, else the engine.

    CLI: session_id (the TASK session) is always sent as --session-id (cli >= 4.3.1: request field, no
    sessions.db; capped at the CLI's 512) and, with pin, also as --pin-session."""
    if node:
        payload = {'query': query, 'org': org, 'project': project, 'session_id': session_id, 'top_k': top_k}
        payload = {k: v for k, v in payload.items() if v}
        return [node, str(ENGINE_DIR / 'search.js')], json.dumps(payload).encode('utf-8')
    argv = list(cli or (CLI_BIN,)) + ['search', '--stdin', '--json']
    if session_id and pin:
        argv += ['--pin-session', session_id]
    if session_id:
        argv += ['--session-id', str(session_id)[:512]]
    if top_k:
        argv += ['--top-k', str(top_k)]
    return argv + list(ids), query.encode('utf-8', errors='replace')  # ids: --org/--project after the subcommand


def learn_command(trace_path, *, retrieval_id=None, applied_log_ids=None, verbosity='detailed',
                  timeout=300, node=None, cli=None, ids=()):
    """argv for the same flags on either engine (org/project travel via ACE_ORG_ID/ACE_PROJECT_ID, and as
    --org/--project for the CLI)."""
    head = [node, str(ENGINE_DIR / 'learn.js')] if node else list(cli or (CLI_BIN,)) + ['learn']
    # --no-stream: stream mode exits 0 on server 401/500 (m3)
    argv = head + ['--transcript', trace_path, '--json', '--timeout', str(int(timeout * 1000)),
                   '--verbosity', verbosity, '--no-stream']
    if retrieval_id:
        argv += ['--retrieval-id', retrieval_id]
    if applied_log_ids:
        argv += ['--applied-log-ids', ','.join(str(x) for x in applied_log_ids)]
    return argv + ([] if node else list(ids))


if __name__ == '__main__':
    if '--status' not in sys.argv[1:]:
        sys.exit('usage: ace_engine.py --status')
    print(json.dumps(select()))
