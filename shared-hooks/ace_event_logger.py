#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
ACE Event Logger - Core logging utility for ACE hooks

Logs all hook events to .claude/data/logs/ in JSONL format.
Provides full visibility into hook execution, performance, and errors.

Usage:
    echo '{"event": "data"}' | uv run ace_event_logger.py --event-type Stop --phase start
    echo '{"result": "data"}' | uv run ace_event_logger.py --event-type Stop --phase end --exit-code 0
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional


class ACEEventLogger:
    """Core logging utility for ACE hook events."""

    def __init__(self, log_dir: str = ".claude/data/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_log_path(self, event_type: str) -> Path:
        """Get log file path for event type."""
        filename = f"ace-{event_type.lower()}.jsonl"
        return self.log_dir / filename

    def log_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        phase: str = "complete",
        metadata: Optional[Dict[str, Any]] = None,
        execution_time_ms: Optional[int] = None,
        exit_code: Optional[int] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Log a hook event to JSONL file.

        Args:
            event_type: Hook event type (Stop, PreCompact, etc.)
            event_data: Event data from hook (input or output)
            phase: Event phase (start, end, complete)
            metadata: Optional metadata (plugin version, model, etc.)
            execution_time_ms: Execution time in milliseconds
            exit_code: Exit code of command (if applicable)
            error: Error message (if failed)
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "phase": phase,
            "event_data": event_data,
            "metadata": metadata or {},
            "execution_time_ms": execution_time_ms,
            "exit_code": exit_code,
            "error": error
        }

        log_path = self.get_log_path(event_type)

        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            print(f"[ERROR] Failed to write log: {e}", file=sys.stderr)

    def log_error(
        self,
        event_type: str,
        error: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an error to both event-specific log and errors log.

        Args:
            event_type: Hook event type
            error: Error message
            context: Optional error context
        """
        error_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "error": error,
            "context": context or {}
        }

        # Log to event-specific log
        event_log_path = self.get_log_path(event_type)
        try:
            with open(event_log_path, 'a') as f:
                f.write(json.dumps({**error_entry, "phase": "error"}) + '\n')
        except Exception as e:
            print(f"[ERROR] Failed to write event log: {e}", file=sys.stderr)

        # Log to errors log
        errors_log_path = self.log_dir / "ace-errors.jsonl"
        try:
            with open(errors_log_path, 'a') as f:
                f.write(json.dumps(error_entry) + '\n')
        except Exception as e:
            print(f"[ERROR] Failed to write errors log: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Log ACE hook events to JSONL files"
    )
    parser.add_argument(
        "--event-type",
        required=True,
        help="Hook event type (Stop, PreCompact, UserPromptSubmit, etc.)"
    )
    parser.add_argument(
        "--phase",
        default="complete",
        choices=["start", "end", "complete", "error"],
        help="Event phase (start, end, complete, error)"
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        help="Exit code of command (for end phase)"
    )
    parser.add_argument(
        "--execution-time-ms",
        type=int,
        help="Execution time in milliseconds (for end phase)"
    )
    parser.add_argument(
        "--log-dir",
        default=".claude/data/logs",
        help="Log directory path"
    )
    parser.add_argument(
        "--error",
        help="Error message (for error phase)"
    )

    args = parser.parse_args()

    # Read event data from stdin
    try:
        event_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    # Get metadata from environment
    metadata = {
        "plugin_version": os.getenv("ACE_PLUGIN_VERSION", "unknown"),
        "claude_version": os.getenv("CLAUDE_VERSION", "unknown"),
        "model": os.getenv("CLAUDE_MODEL", "unknown")
    }

    # Initialize logger
    logger = ACEEventLogger(log_dir=args.log_dir)

    # Log event
    if args.phase == "error" or args.error:
        logger.log_error(
            event_type=args.event_type,
            error=args.error or "Unknown error",
            context=event_data
        )
    else:
        logger.log_event(
            event_type=args.event_type,
            event_data=event_data,
            phase=args.phase,
            metadata=metadata,
            execution_time_ms=args.execution_time_ms,
            exit_code=args.exit_code,
            error=args.error
        )

    # Echo input to stdout (for piping)
    print(json.dumps(event_data))


if __name__ == "__main__":
    main()
