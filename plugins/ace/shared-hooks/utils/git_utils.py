#!/usr/bin/env python3
"""
Git context extraction utilities for ACE learning pipeline.

Per Issue #6: Add git context to ExecutionTrace for AI-Trail correlation.
This allows correlating learning patterns with specific commits and changes.

v5.2.10: Initial implementation
"""

import subprocess
import os
import json
import re
from typing import Optional, Dict, List
from pathlib import Path


def is_git_repo(repo_path: str) -> bool:
    """
    Check if path is inside a git repository.

    Args:
        repo_path: Path to check

    Returns:
        True if inside a git repository
    """
    if not repo_path:
        return False

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except Exception:
        return False


def get_git_context(repo_path: str) -> Optional[Dict]:
    """
    Extract comprehensive git context from repository.

    Per Issue #6: Capture current commit state for AI-Trail correlation.

    Args:
        repo_path: Path to git repository

    Returns:
        Dict with git context or None if not a git repo
        {
            'commit_hash': str,
            'commit_message': str,
            'author': str,
            'author_email': str,
            'timestamp': str (ISO format),
            'branch': str,
            'files_changed': int,
            'insertions': int,
            'deletions': int
        }
    """
    if not repo_path or not is_git_repo(repo_path):
        return None

    context = {}

    try:
        # Get commit hash
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            context['commit_hash'] = result.stdout.strip()

        # Get commit message
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%s'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            context['commit_message'] = result.stdout.strip()

        # Get author name
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%an'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            context['author'] = result.stdout.strip()

        # Get author email
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%ae'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            context['author_email'] = result.stdout.strip()

        # Get timestamp (ISO format)
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%aI'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            context['timestamp'] = result.stdout.strip()

        # Get branch name
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            context['branch'] = result.stdout.strip()

        # Get diff stats (files changed, insertions, deletions)
        result = subprocess.run(
            ['git', 'diff', '--stat', 'HEAD~1..HEAD'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            stats = parse_diff_stat(result.stdout)
            context.update(stats)
        else:
            # Fallback: first commit has no parent
            context['files_changed'] = 0
            context['insertions'] = 0
            context['deletions'] = 0

        return context if context.get('commit_hash') else None

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def parse_diff_stat(diff_output: str) -> Dict[str, int]:
    """
    Parse git diff --stat output to extract statistics.

    Example output:
        "3 files changed, 45 insertions(+), 12 deletions(-)"

    Args:
        diff_output: Output from git diff --stat

    Returns:
        Dict with files_changed, insertions, deletions
    """
    stats = {
        'files_changed': 0,
        'insertions': 0,
        'deletions': 0
    }

    if not diff_output:
        return stats

    # Parse the summary line (last line)
    lines = diff_output.strip().split('\n')
    if not lines:
        return stats

    summary = lines[-1]

    # Extract files changed
    files_match = re.search(r'(\d+)\s+files?\s+changed', summary)
    if files_match:
        stats['files_changed'] = int(files_match.group(1))

    # Extract insertions
    ins_match = re.search(r'(\d+)\s+insertions?\(\+\)', summary)
    if ins_match:
        stats['insertions'] = int(ins_match.group(1))

    # Extract deletions
    del_match = re.search(r'(\d+)\s+deletions?\(-\)', summary)
    if del_match:
        stats['deletions'] = int(del_match.group(1))

    return stats


def detect_commits_in_session(tools: List) -> List[str]:
    """
    Find git commits made during session by scanning Bash tool calls.

    Per Issue #6: Track commits made during the coding session for
    correlating patterns with specific changes.

    Args:
        tools: List of tuples (tool_name, tool_input, tool_response, tool_use_id)

    Returns:
        List of commit SHAs detected from git commit commands
    """
    commits = []

    for tool_name, tool_input_json, tool_response_json, _ in tools:
        if tool_name != 'Bash':
            continue

        try:
            tool_input = json.loads(tool_input_json) if tool_input_json else {}
            command = tool_input.get('command', '')

            # Check for git commit command
            if 'git commit' not in command:
                continue

            # Parse response for commit SHA
            tool_response = json.loads(tool_response_json) if tool_response_json else {}
            stdout = tool_response.get('stdout', '')

            # Git commit output contains: "[branch SHA] message"
            # Example: "[main abc1234] Fix bug"
            sha_match = re.search(r'\[[\w\-/]+\s+([a-f0-9]{7,40})\]', stdout)
            if sha_match:
                commits.append(sha_match.group(1))

        except (json.JSONDecodeError, TypeError):
            continue

    return commits


def get_uncommitted_changes(repo_path: str) -> Optional[Dict]:
    """
    Check for uncommitted changes in the repository.

    Useful for understanding if learning occurred before or after commit.

    Args:
        repo_path: Path to git repository

    Returns:
        Dict with staged and unstaged file counts, or None
    """
    if not repo_path or not is_git_repo(repo_path):
        return None

    try:
        # Check for staged changes
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        staged_files = len([f for f in result.stdout.strip().split('\n') if f])

        # Check for unstaged changes
        result = subprocess.run(
            ['git', 'diff', '--name-only'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        unstaged_files = len([f for f in result.stdout.strip().split('\n') if f])

        return {
            'staged_files': staged_files,
            'unstaged_files': unstaged_files,
            'has_uncommitted': staged_files > 0 or unstaged_files > 0
        }

    except Exception:
        return None
