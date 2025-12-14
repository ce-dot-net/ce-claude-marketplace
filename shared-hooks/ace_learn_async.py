#!/usr/bin/env python3
"""
ACE Async Learning Worker (Issue #3 Fix)

This script runs in the background after the Stop hook returns.
It performs the actual learning analysis and writes results to a status file.

Status file format: /tmp/ace-learning-status-{session_id}.json
{
  "session_id": "...",
  "state": "running" | "completed" | "failed",
  "started_at": "ISO timestamp",
  "completed_at": "ISO timestamp" (when done),
  "statistics": {...} (when completed),
  "error": "error message" (when failed)
}
"""

import json
import sys
import subprocess
import os
from pathlib import Path
from datetime import datetime


def write_status(session_id, state, **kwargs):
    """Write status to temp file for later retrieval."""
    status_file = Path(f"/tmp/ace-learning-status-{session_id}.json")

    status = {
        "session_id": session_id,
        "state": state,
        **kwargs
    }

    status_file.write_text(json.dumps(status, indent=2))


def main():
    """
    Background worker for async learning.

    Receives trace JSON on stdin, executes ce-ace learn, and writes status.
    """
    try:
        # Read input (trace + context) from stdin
        input_data = json.load(sys.stdin)

        trace = input_data['trace']
        context = input_data['context']
        session_id = input_data['session_id']
        verbosity = input_data.get('verbosity', 'detailed')

        # Write initial status: running
        write_status(
            session_id,
            state="running",
            started_at=datetime.now().isoformat()
        )

        # Build environment
        env = os.environ.copy()
        if context.get('org'):
            env['ACE_ORG_ID'] = context['org']
        if context.get('project'):
            env['ACE_PROJECT_ID'] = context['project']

        # Execute ce-ace learn --stdin
        result = subprocess.run(
            ['ce-ace', 'learn', '--stdin', '--json', '--timeout', '300000', '--verbosity', verbosity],
            input=json.dumps(trace),
            text=True,
            capture_output=True,
            timeout=300,  # 5 min safety margin
            env=env
        )

        if result.returncode == 0:
            # Parse response
            try:
                response = json.loads(result.stdout)
                stats = response.get('learning_statistics', {})

                # Handle nested structure
                if 'learning_statistics' in stats:
                    stats = stats.get('learning_statistics', {})

                # Write success status
                write_status(
                    session_id,
                    state="completed",
                    started_at=input_data.get('started_at', datetime.now().isoformat()),
                    completed_at=datetime.now().isoformat(),
                    statistics=stats
                )

                sys.exit(0)

            except json.JSONDecodeError:
                # CLI returned but output wasn't JSON
                write_status(
                    session_id,
                    state="completed",
                    started_at=input_data.get('started_at', datetime.now().isoformat()),
                    completed_at=datetime.now().isoformat(),
                    error="Invalid JSON response from ce-ace"
                )
                sys.exit(1)

        else:
            # ce-ace failed
            write_status(
                session_id,
                state="failed",
                started_at=input_data.get('started_at', datetime.now().isoformat()),
                completed_at=datetime.now().isoformat(),
                error=result.stderr or "Unknown error"
            )
            sys.exit(1)

    except subprocess.TimeoutExpired:
        write_status(
            session_id,
            state="failed",
            started_at=input_data.get('started_at', datetime.now().isoformat()),
            completed_at=datetime.now().isoformat(),
            error="Learning timed out after 5 minutes"
        )
        sys.exit(1)

    except Exception as e:
        # Unexpected error
        write_status(
            session_id,
            state="failed",
            started_at=input_data.get('started_at', datetime.now().isoformat()),
            completed_at=datetime.now().isoformat(),
            error=str(e)
        )
        sys.exit(1)


if __name__ == '__main__':
    main()
