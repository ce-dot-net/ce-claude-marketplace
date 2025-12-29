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
