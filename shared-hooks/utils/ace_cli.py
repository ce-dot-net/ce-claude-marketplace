#!/usr/bin/env python3
"""ACE CLI Subprocess Wrapper - Calls ce-ace with --stdin pattern"""

import subprocess
import json
import os
from typing import Optional, Dict, Any


def run_search(query: str, org: str = None, project: str = None) -> Optional[Dict[str, Any]]:
    """
    Call ce-ace search --stdin

    Args:
        query: Search query text
        org: Organization ID (optional, passed via environment)
        project: Project ID (optional, passed via environment)

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
    """
    try:
        # Build environment with context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project

        result = subprocess.run(
            ['ce-ace', 'search', '--stdin', '--json'],
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


def run_learn(task: str, trajectory: str, success: bool, org: str = None, project: str = None, patterns_used: Optional[list] = None) -> bool:
    """
    Call ce-ace learn --stdin

    Args:
        task: Task description
        trajectory: Execution steps taken
        success: Whether task succeeded
        org: Organization ID (optional, passed via environment)
        project: Project ID (optional, passed via environment)
        patterns_used: Optional list of pattern IDs used

    Returns:
        True if learning succeeded, False otherwise

    Note:
        Context passed via environment variables (ACE_ORG_ID, ACE_PROJECT_ID).
        No need to pass --org or --project flags!
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
            ['ce-ace', 'learn', '--stdin'],
            input=json.dumps(payload).encode('utf-8'),
            capture_output=True,
            timeout=10,
            env=env
        )

        return result.returncode == 0

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def run_status(org: str = None, project: str = None) -> Optional[Dict[str, Any]]:
    """
    Call ce-ace status

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
            ['ce-ace', 'status', '--json'],
            capture_output=True,
            timeout=5,
            env=env
        )

        if result.returncode != 0:
            return None

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None
