#!/usr/bin/env python3
"""ACE CLI Subprocess Wrapper - Calls ace-cli (or ace-cli fallback) with --stdin pattern"""

import subprocess
import json
import os
import shutil
from typing import Optional, Dict, Any


def get_cli_command() -> str:
    """
    Get the ACE CLI command name (ace-cli preferred, ace-cli fallback)

    Returns:
        'ace-cli' if available, otherwise 'ce-ace'
    """
    if shutil.which('ace-cli'):
        return 'ace-cli'
    return 'ce-ace'


# Cache the CLI command at module load time
CLI_CMD = get_cli_command()


def run_search(query: str, org: str = None, project: str = None, session_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Call ace-cli search --stdin with optional session pinning

    Args:
        query: Search query text
        org: Organization ID (optional, passed via environment)
        project: Project ID (optional, passed via environment)
        session_id: Session ID to pin results to (optional, requires ace-cli v1.0.11+)

    Returns:
        Parsed JSON response or None on failure

    Response includes:
        - similar_patterns: List of matching patterns
        - domains_summary: {abstract: [...], concrete: [...]} (if available)
        - count: Number of patterns returned
        - threshold: Similarity threshold used

    Note:
        Context passed via environment variables (ACE_ORG_ID, ACE_PROJECT_ID).
        CLI reads server config (search_top_k, constitution_threshold) automatically.
        No need to pass --org, --project flags!

    Session Pinning (v1.0.11+):
        If session_id provided, patterns are pinned to session storage for 24h.
        Enables fast recall after context compaction via recall_session().
    """
    try:
        # Build environment with context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project

        # Build command with optional session pinning
        cmd = [CLI_CMD, 'search', '--stdin', '--json']
        if session_id:
            cmd.extend(['--pin-session', session_id])

        result = subprocess.run(
            cmd,
            input=query.encode('utf-8'),
            capture_output=True,
            timeout=10,
            env=env
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def run_learn(task: str, trajectory: str, success: bool, org: str = None, project: str = None, patterns_used: Optional[list] = None) -> Optional[Dict[str, Any]]:
    """
    Call ace-cli learn --stdin with JSON response parsing (v1.0.13+)

    Args:
        task: Task description
        trajectory: Execution steps taken
        success: Whether task succeeded
        org: Organization ID (optional, passed via environment)
        project: Project ID (optional, passed via environment)
        patterns_used: Optional list of pattern IDs used

    Returns:
        Parsed JSON response or None on failure

    Response includes (v1.0.13+):
        - success: bool
        - analysis_performed: bool
        - learning_statistics: {
            patterns_created: int,
            patterns_updated: int,
            patterns_pruned: int,
            average_confidence: float,
            by_section: {...},
            ...
          } (optional, only on new servers)

    Note:
        Context passed via environment variables (ACE_ORG_ID, ACE_PROJECT_ID).
        No need to pass --org or --project flags!

    Backward Compatibility:
        Old servers (v3.9.x) won't include learning_statistics field.
        Always check: response.get('learning_statistics') before accessing.
    """
    try:
        payload = {
            'task': task,
            'trajectory': trajectory,
            'success': success
        }

        if patterns_used:
            payload['patterns_used'] = patterns_used

        # Build environment with context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project

        result = subprocess.run(
            [CLI_CMD, 'learn', '--stdin', '--json'],
            input=json.dumps(payload).encode('utf-8'),
            capture_output=True,
            timeout=10,
            env=env
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def run_status(org: str = None, project: str = None) -> Optional[Dict[str, Any]]:
    """
    Call ace-cli status

    Args:
        org: Organization ID (optional, passed via environment)
        project: Project ID (optional, passed via environment)

    Returns:
        Parsed JSON status or None on failure

    Note:
        Context passed via environment variables (ACE_ORG_ID, ACE_PROJECT_ID).
        No need to pass --org or --project flags!
    """
    try:
        # Build environment with context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project

        result = subprocess.run(
            [CLI_CMD, 'status', '--json'],
            capture_output=True,
            timeout=5,
            env=env
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def run_domains(org: str = None, project: str = None, min_patterns: int = None) -> Optional[Dict[str, Any]]:
    """
    Call ace-cli domains --json to list available pattern domains (v3.4.0+)

    Args:
        org: Organization ID (optional, passed via environment)
        project: Project ID (optional, passed via environment)
        min_patterns: Minimum pattern count to include domain (optional, v3.4.1+)

    Returns:
        Parsed JSON response or None on failure

    Response includes:
        - domains: List of {name: str, count: int} objects
        - total_domains: Total number of domains
        - total_patterns: Total patterns across all domains

    Note:
        Context passed via environment variables (ACE_ORG_ID, ACE_PROJECT_ID).
        Requires ace-cli v3.4.0+

    Use Case:
        Users need to discover domain names to use --allowed-domains filtering
        in /ace-search command. Without this, they'd have to guess domain names.
    """
    try:
        # Build environment with context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project

        # Build command with optional min-patterns filter
        cmd = [CLI_CMD, 'domains', '--json']
        if min_patterns is not None and min_patterns > 1:
            cmd.extend(['--min-patterns', str(min_patterns)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )

        if result.returncode != 0:
            return None

        # Filter out update notification lines (💡) before parsing JSON
        stdout_clean = '\n'.join(
            line for line in result.stdout.split('\n')
            if not line.startswith('💡')
        )

        return json.loads(stdout_clean)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def recall_session(session_id: str, org: str = None, project: str = None) -> Optional[Dict[str, Any]]:
    """
    Recall pinned patterns from session storage (v1.0.11+)

    Args:
        session_id: Session ID to recall
        org: Organization ID (optional, passed via environment)
        project: Project ID (optional, passed via environment)

    Returns:
        Recalled patterns as dict, or None on error

    Note:
        Session recall is FAST (~10ms) and does NOT make server calls.
        Sessions expire after 24 hours (configurable TTL).
        Non-fatal failure - returns None if session not found/expired.

    Response format (same as run_search):
        {
            "similar_patterns": [...],
            "count": N,
            "threshold": 0.75,
            "session_id": "uuid",
            "pinned_at": timestamp,
            "expires_at": timestamp
        }
    """
    try:
        # Build environment with context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project

        result = subprocess.run(
            [CLI_CMD, 'cache', 'recall', '--session', session_id, '--json'],
            capture_output=True,
            timeout=5,  # Fast recall, should be <10ms
            env=env
        )

        if result.returncode != 0:
            # Session not found or expired - this is non-fatal
            return None

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def check_auth_status(warn_threshold_hours: float = 2.0) -> Optional[str]:
    """
    Check ACE authentication status - WARNING UX v5.4.19

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
            [CLI_CMD, 'whoami', '--json'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
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

            except json.JSONDecodeError:
                pass
        else:
            # CLI failed - check stderr for auth errors
            stderr = result.stderr or ''
            if '401' in stderr or 'unauthorized' in stderr.lower() or 'expired' in stderr.lower():
                return "⚠️ [ACE] Session expired. Run /ace-login to re-authenticate."

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Non-fatal

    return None


def check_session_pinning_available() -> bool:
    """
    Check if ace-cli CLI supports session pinning (v1.0.11+)

    Returns:
        True if session pinning available, False otherwise

    Usage:
        if check_session_pinning_available():
            # Use session pinning
            run_search(query, session_id=session_id)
        else:
            # Gracefully degrade
            run_search(query)
    """
    try:
        result = subprocess.run(
            [CLI_CMD, '--version'],
            capture_output=True,
            timeout=5
        )

        if result.returncode != 0:
            return False

        version_str = result.stdout.decode('utf-8').strip()

        # Parse version (e.g., "1.0.11" -> [1, 0, 11])
        parts = version_str.split('.')
        if len(parts) < 3:
            return False

        try:
            major, minor, patch = map(int, parts[:3])
        except ValueError:
            return False

        # Session pinning requires v1.0.11+
        if major > 1:
            return True
        if major == 1 and minor > 0:
            return True
        if major == 1 and minor == 0 and patch >= 11:
            return True

        return False

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
