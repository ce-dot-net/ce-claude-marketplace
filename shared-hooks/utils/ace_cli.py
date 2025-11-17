#!/usr/bin/env python3
"""ACE CLI Subprocess Wrapper - Calls ce-ace with --stdin pattern"""

import subprocess
import json
from typing import Optional, Dict, Any


def run_search(query: str, org: str, project: str) -> Optional[Dict[str, Any]]:
    """
    Call ce-ace search --stdin

    Args:
        query: Search query text
        org: Organization ID (org_xxx)
        project: Project ID (prj_xxx)

    Returns:
        Parsed JSON response or None on failure

    Note:
        Threshold is controlled by server-side config (ce-ace tune --constitution-threshold)
        No --threshold flag passed to allow server config to take precedence
    """
    try:
        result = subprocess.run(
            [
                'ce-ace',
                '--json',
                '--org', org,
                '--project', project,
                'search',
                '--stdin'
            ],
            input=query.encode('utf-8'),
            capture_output=True,
            timeout=10
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def run_learn(task: str, trajectory: str, success: bool, org: str, project: str, patterns_used: Optional[list] = None) -> bool:
    """
    Call ce-ace learn --stdin

    Args:
        task: Task description
        trajectory: Execution steps taken
        success: Whether task succeeded
        org: Organization ID
        project: Project ID
        patterns_used: Optional list of pattern IDs used

    Returns:
        True if learning succeeded, False otherwise
    """
    try:
        payload = {
            'task': task,
            'trajectory': trajectory,
            'success': success
        }

        if patterns_used:
            payload['patterns_used'] = patterns_used

        result = subprocess.run(
            [
                'ce-ace',
                '--org', org,
                '--project', project,
                'learn',
                '--stdin'
            ],
            input=json.dumps(payload).encode('utf-8'),
            capture_output=True,
            timeout=10
        )

        return result.returncode == 0

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def run_status(org: str, project: str) -> Optional[Dict[str, Any]]:
    """
    Call ce-ace status

    Args:
        org: Organization ID
        project: Project ID

    Returns:
        Parsed JSON status or None on failure
    """
    try:
        result = subprocess.run(
            [
                'ce-ace',
                '--json',
                '--org', org,
                '--project', project,
                'status'
            ],
            capture_output=True,
            timeout=5
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None
