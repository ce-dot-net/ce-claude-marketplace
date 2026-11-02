#!/usr/bin/env python3
"""ACE CLI Subprocess Wrapper - Calls ace-cli with --stdin pattern

v8 (DESIGN §5 C2): run_search / run_learn are exactly ONE ace-cli spawn each.
No --version probe, no whoami pre-check; both return (result_or_None, duration_ms).
The search cache moved to ace_search_cache (disk) and is consulted by the hooks.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


CLI_CMD = 'ace-cli'  # name of the global fallback; spawns go through _cmd()/cli_argv()
_NOT_FOUND = "ace-cli not found. Run /ace:ace-install-cli"
# ace-cli's own update notifier (4.2.2 dist/utils/version-checker.js): a pinned CLI says it whenever npm is ahead.
_NOTIFIER = re.compile(r'Update available: v|Run: npm install -g @ace-sdk')


def _pin():
    """The exact ace-cli version this plugin version was tested with (package.json, DESIGN §23)."""
    root = os.environ.get('CLAUDE_PLUGIN_ROOT') or str(Path(__file__).resolve().parents[2])
    try:
        v = json.loads((Path(root) / 'package.json').read_text())['dependencies']['@ace-sdk/cli']
        return v if re.fullmatch(r'\d+\.\d+\.\d+', v) else None
    except Exception:
        return None


def _tup(v):
    return tuple(int(x) for x in v.split('.'))


def _global_below_pin(path) -> bool:
    """True only when SessionStart's cli_version.json cache says this very binary is older than the pin.
    No cache / unknown version = accepted (never spawn a probe here; never disable on unknown)."""
    try:
        pin, real = _pin(), os.path.realpath(path)
        c = json.loads(_plugin_dir().cli_version_file().read_text())
        return bool(pin and c.get('path') == real and c.get('mtime') == os.stat(real).st_mtime
                    and c.get('version') and _tup(c['version']) < _tup(pin))
    except Exception:
        return False


def global_cli():
    """Path of an `ace-cli` on PATH, or None (the fallback; version floor is applied by _resolve)."""
    return shutil.which('ace-cli')


def _resolve():
    """(argv prefix, source): plugin-local [node, cli.js] -> global [ace-cli] (>= pin) -> (None, None).
    The ONE place that locates ace-cli. No spawn. Plugin-local needs CLAUDE_PLUGIN_ROOT (hooks always have it)."""
    root, node = os.environ.get('CLAUDE_PLUGIN_ROOT'), shutil.which('node')
    if root and node:
        js = Path(root) / 'node_modules' / '@ace-sdk' / 'cli' / 'dist' / 'cli.js'
        if js.is_file():
            return [node, str(js)], 'plugin-local'
    g = global_cli()
    if g and not _global_below_pin(g):
        return ['ace-cli'], 'global'  # by name: the child resolves it on the same PATH
    return None, None


def cli_argv():
    return _resolve()[0]


def cli_source():
    return _resolve()[1]


def _cmd(*args):
    argv = cli_argv()
    if not argv:
        raise FileNotFoundError('ace-cli')
    return argv + list(args)


def clean_stderr(text) -> str:
    """Drop ace-cli's own 'Update available ... npm install -g' notifier lines (DESIGN §20.2)."""
    return '\n'.join(l for l in (text or '').splitlines() if not _NOTIFIER.search(l)).strip()


_AUTH_MSG = {"error": "not_authenticated", "message": "Not logged in. Run /ace-login first."}


def _log_cli_error(location: str, returncode: int, stdout_sample: str, stderr_sample: str,
                    query: str = None, project_id: str = None, extra: dict = None,
                    hook_event_name: str = "UserPromptSubmit") -> None:
    """Log ace-cli failures to the canonical telemetry stream (UTC 'Z' timestamps)."""
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "event": "error",
            "hook": hook_event_name,
            "location": location,
            "project_id": project_id,
            "returncode": returncode,
            "stdout_sample": stdout_sample[:300] if stdout_sample else '',
            "stderr_sample": stderr_sample[:300] if stderr_sample else '',
            "query_sample": query[:100] if query else '',
        }
        if extra:
            entry.update(extra)
        import sys as _sys
        _u = str(Path(__file__).resolve().parent)
        if _u not in _sys.path:
            _sys.path.insert(0, _u)
        from ace_relevance_logger import ACERelevanceLogger
        ACERelevanceLogger()._write_log(entry)  # shares the one rotation scheme
    except Exception:
        pass  # Logging must not fail the caller


def _text(b) -> str:
    if not b:
        return ''
    return b.decode('utf-8', errors='replace') if isinstance(b, bytes) else b


def _env(org, project):
    env = os.environ.copy()
    if org:
        env['ACE_ORG_ID'] = org
    if project:
        env['ACE_PROJECT_ID'] = project
    if not env.get('ACE_CLIENT_ID'):  # X-ACE-Client attribution for every search/learn
        try:
            from ace_env import client_id, plugin_version
            env['ACE_CLIENT_ID'] = client_id()
            env.setdefault('ACE_PLUGIN_VERSION', plugin_version())
        except Exception:
            pass
    return env


def _plugin_dir():
    """Import plugin_data_dir (same utils dir) lazily; None if unavailable."""
    try:
        import sys as _sys
        _u = str(Path(__file__).resolve().parent)
        if _u not in _sys.path:
            _sys.path.insert(0, _u)
        import plugin_data_dir
        return plugin_data_dir
    except Exception:
        return None


def _pin_backoff_active() -> bool:
    """True while <root>/pin-backoff is younger than ACE_PIN_BACKOFF_MIN (default 30) min."""
    try:
        pdd = _plugin_dir()
        mins = float(os.environ.get('ACE_PIN_BACKOFF_MIN') or 30)
        return pdd is not None and (time.time() - pdd.pin_backoff_file().stat().st_mtime) < mins * 60
    except Exception:
        return False


def _touch_backoff() -> None:
    try:
        _plugin_dir().pin_backoff_file().touch()
    except Exception:
        pass


def _log_pin(session_id, hook_event_name, **fields) -> None:
    """Best-effort relevance row for a pin failure/skip (DESIGN §11 A1)."""
    try:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                 "event": "pin", "hook": hook_event_name, "session_id": session_id}
        entry.update(fields)
        import sys as _sys
        _u = str(Path(__file__).resolve().parent)
        if _u not in _sys.path:
            _sys.path.insert(0, _u)
        from ace_relevance_logger import ACERelevanceLogger
        ACERelevanceLogger()._write_log(entry)
    except Exception:
        pass


def _is_auth_failure(stderr: str, stdout: str) -> bool:
    return (any(x in stderr.lower() for x in ['unauthorized', '401', 'not logged in', 'no api token', 'token_expired'])
            or any(x in stdout.lower() for x in ['not logged in', 'no api token']))


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def run_search(query: str, *, org: str = None, project: str = None, session_id: str = None,
               top_k: int = None, timeout: int = 25,
               hook_event_name: str = "UserPromptSubmit") -> Tuple[Optional[Dict[str, Any]], int]:
    """ONE `ace-cli search --stdin --json [--pin-session X] [--top-k N]` spawn.

    Returns (result_dict_or_None, duration_ms). Structured error dicts are kept:
    {"error": "not_authenticated"|"timeout"|"cli_not_found", "message": ...}.
    Context goes via ACE_ORG_ID / ACE_PROJECT_ID env. session_id pins the results
    server-side (always used when given; ace-cli >= 4.1.2 supports it).
    Failures are logged with the CALLER's hook_event_name.
    """
    t0 = time.monotonic()
    pin = session_id
    try:
        if pin and _pin_backoff_active():  # sessions.db lock is sticky (p2): don't even try
            pin = None
            _log_pin(session_id, hook_event_name, pin_skipped="backoff")
        base = _cmd('search', '--stdin', '--json')
        tail = ['--top-k', str(top_k)] if top_k else []
        stdin = query.encode('utf-8', errors='replace')

        def spawn(c, to):
            return subprocess.run(c, input=stdin, capture_output=True, timeout=to, env=_env(org, project))

        result = spawn(base + (['--pin-session', pin] if pin else []) + tail, timeout)
        stderr = clean_stderr(_text(result.stderr))
        stdout = _text(result.stdout)
        # A1: a pinned search that dies on the sessions.db lock (or prints nothing) is
        # re-run ONCE without the pin; the pinned command itself is never re-run.
        locked = 'database is locked' in stderr.lower()
        if pin and (locked or (not stdout.strip() and not _is_auth_failure(stderr, stdout))):
            _log_pin(session_id, hook_event_name, pin_failed=True)
            if locked or 'bindings file' in stderr.lower():  # sticky lock, or `--ignore-scripts` without the
                _touch_backoff()  # better-sqlite3 binary (until the SessionStart rebuild): don't pay 2 spawns per prompt
            remaining = timeout - (time.monotonic() - t0)
            if remaining >= 2:  # A2: never overrun the hook budget with a floored retry
                result = spawn(base + tail, remaining)
                stderr = clean_stderr(_text(result.stderr))
                stdout = _text(result.stdout)
        if result.returncode != 0:
            if _is_auth_failure(stderr, stdout):
                return dict(_AUTH_MSG), _ms(t0)
            _log_cli_error("ace_cli_nonzero_exit", result.returncode, stdout, stderr,
                           query=query, project_id=project, hook_event_name=hook_event_name)
            return None, _ms(t0)

        try:
            return json.loads(stdout), _ms(t0)
        except json.JSONDecodeError as _je:
            _log_cli_error("ace_cli_json_parse_failed", result.returncode, stdout, stderr,
                           query=query, project_id=project, hook_event_name=hook_event_name,
                           extra={"parse_error": str(_je)[:200],
                                  "stdout_bytes": len(result.stdout) if result.stdout else 0})
            return None, _ms(t0)

    except subprocess.TimeoutExpired:
        if pin:  # a pinned spawn stuck on the lock: don't make every later call wait again
            _touch_backoff()
        _log_cli_error("ace_cli_timeout", -1, '', '', query=query, project_id=project,
                       hook_event_name=hook_event_name)
        return {"error": "timeout", "message": "Search timed out. Check your connection."}, _ms(t0)
    except FileNotFoundError:
        return {"error": "cli_not_found",
                "message": _NOT_FOUND}, _ms(t0)


def run_learn(trace: Dict[str, Any], *, retrieval_id: str = None, applied_log_ids=None,
              org: str = None, project: str = None, verbosity: str = 'detailed',
              timeout: int = 300,
              hook_event_name: str = "Stop") -> Tuple[Optional[Dict[str, Any]], int]:
    """ONE `ace-cli learn --transcript <tmpfile>` spawn (F-080 flags kept).

    The trace goes through a temp file (learn --stdin breaks above ~64KB pipe
    buffer); the file is always removed. Returns (parsed_json_or_None, ms).
    """
    t0 = time.monotonic()
    try:  # plugin-data tmp (S10), so a SIGKILLed learn leaves nothing in the system tmp
        import plugin_data_dir
        _tmp = plugin_data_dir.data_root() / 'tmp'
        _tmp.mkdir(parents=True, exist_ok=True)
        _tmp = str(_tmp)
    except Exception:
        _tmp = None
    fd, path = tempfile.mkstemp(prefix='ace-trace-', suffix='.json', dir=_tmp)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(trace, f, default=str)
        cmd = _cmd('learn', '--transcript', path, '--json',
                   '--timeout', str(int(timeout * 1000)), '--verbosity', verbosity, '--no-stream')  # stream mode exits 0 on server 401/500 (m3)
        if retrieval_id:
            cmd += ['--retrieval-id', retrieval_id]
        if applied_log_ids:
            cmd += ['--applied-log-ids', ','.join(str(x) for x in applied_log_ids)]
        # A lock failure may occur after the server POST: retrying learn could
        # duplicate the trace / double F-080 credit, so learn never retries.
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout,
                                env=_env(org, project))
        if result.returncode != 0:
            _log_cli_error("ace_cli_learn_nonzero_exit", result.returncode, _text(result.stdout),
                           clean_stderr(_text(result.stderr)), project_id=project, hook_event_name=hook_event_name)
            return None, _ms(t0)
        try:
            return json.loads(result.stdout), _ms(t0)
        except (json.JSONDecodeError, TypeError) as _je:
            _log_cli_error("ace_cli_learn_json_parse_failed", result.returncode,
                           _text(result.stdout), _text(result.stderr), project_id=project,
                           hook_event_name=hook_event_name, extra={"parse_error": str(_je)[:200]})
            return None, _ms(t0)
    except subprocess.TimeoutExpired:
        _log_cli_error("ace_cli_learn_timeout", -1, '', '', project_id=project,
                       hook_event_name=hook_event_name)
        return None, _ms(t0)
    except FileNotFoundError:
        _log_cli_error("ace_cli_learn_not_found", -1, '', '', project_id=project,
                       hook_event_name=hook_event_name)
        return None, _ms(t0)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def check_auth_status(warn_threshold_hours: float = 2.0) -> Optional[str]:
    """
    Check ACE authentication status - WARNING UX v5.4.21

    IMPORTANT: Don't warn active users! The sliding window TTL automatically
    extends the token by +48h on EVERY API call. SDK Core also auto-refreshes
    tokens when they're about to expire.

    Only warn in these specific cases:
    1. Hard cap approaching (7-day limit) - server provides is_hard_cap_approaching
    2. User has been idle ~47h AND token expiring soon
    3. Refresh token expired (actual session end)
    4. Not authenticated at all

    Args:
        warn_threshold_hours: Only used for idle detection (default: 2)
                              Ignored for active users (sliding window handles it)

    Returns:
        Warning message string if auth issues detected, None if OK

    v5.4.21 Changes:
        - FIX: Parse stdout even when returncode != 0 (CLI returns valid JSON
          with authenticated:false but exit code 1)
        - This fixes silent auth check failures after Mac sleep/wake

    v5.4.19 Changes:
        - DON'T warn active users (sliding window auto-extends tokens)
        - Check is_hard_cap_approaching for 7-day limit
        - Check last_used_at for idle detection
        - Only warn for: hard cap, idle+expiring, or actual expiration

    Note:
        Non-blocking - returns None on any error to avoid breaking workflow.
        ace-cli auto-refreshes tokens via SDK Core's ensureValidToken().
    """
    try:
        result = subprocess.run(
            _cmd('whoami', '--json'),
            capture_output=True,
            text=True,
            timeout=5
        )

        # v5.4.21 FIX: Parse stdout regardless of returncode
        # The CLI returns valid JSON even with exit code 1 when not authenticated
        # Example: returncode=1, stdout='{"authenticated":false,"message":"Not logged in"}'
        data = None
        if result.stdout:
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

        if data:
            if not data.get('authenticated', False):
                return "⚠️ [ACE] Not authenticated. Run /ace-login to setup."

            # v5.4.19: Check for hard cap approaching (7-day limit)
            if data.get('is_hard_cap_approaching', False):
                hard_cap_hours = data.get('hard_cap_hours_remaining', 0)
                if hard_cap_hours < 24:
                    return f"⚠️ [ACE] Session hard limit in {int(hard_cap_hours)}h. Must re-login after 7 days of continuous use."

            # v5.4.19: Check token expiration
            expires_in = data.get('token_expires_in')
            if expires_in is not None:
                # Token already expired
                if expires_in <= 0:
                    return "⚠️ [ACE] Session expired. Run /ace-login to re-authenticate."

                # v5.4.19: Check for idle state before warning
                # Only warn if user has been idle AND token expiring soon
                last_used_at = data.get('last_used_at')
                expires_in_hours = expires_in / 3600.0

                if last_used_at is not None:
                    # User has used the API before - check if idle
                    # If last_used_at is recent, DON'T warn (sliding window will extend)
                    # The server extends token +48h on every API call
                    # So if expires_in < warn_threshold AND last_used_at is old, warn
                    from datetime import datetime
                    try:
                        last_used = datetime.fromisoformat(last_used_at.replace('Z', '+00:00'))
                        now = datetime.now(last_used.tzinfo)
                        idle_hours = (now - last_used).total_seconds() / 3600.0

                        # Only warn if idle for 46+ hours AND token expiring soon
                        if idle_hours >= 46 and expires_in_hours < warn_threshold_hours:
                            mins = int(expires_in / 60)
                            return f"⚠️ [ACE] Been idle for {int(idle_hours)}h, token expires in {mins} min. Your next action will auto-refresh."
                    except (ValueError, TypeError):
                        pass  # Can't parse last_used_at, skip idle check

                elif expires_in_hours < warn_threshold_hours:
                    # last_used_at is null (first time) - only warn if actually expiring
                    # This shouldn't happen normally since new tokens have 48h TTL
                    mins = int(expires_in / 60)
                    if mins < 60:
                        return f"⚠️ [ACE] Token expires in {mins} minutes. Consider running /ace-login."

            else:
                # Fallback: Parse token_status string (legacy servers)
                token_status = data.get('token_status', '')
                if 'expired' in token_status.lower():
                    return "⚠️ [ACE] Session expired. Run /ace-login to re-authenticate."

        elif result.returncode != 0:
            # CLI failed and no valid JSON - check stderr for auth errors
            stderr = result.stderr or ''
            if '401' in stderr or 'unauthorized' in stderr.lower() or 'expired' in stderr.lower():
                return "⚠️ [ACE] Session expired. Run /ace-login to re-authenticate."

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Non-fatal

    return None
