#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
ACE Log Analyzer - Diagnostic tool for analyzing hook logs

Usage:
    # View last 10 Stop hook events
    uv run ace_log_analyzer.py --event-type Stop --last 10

    # Show Stop hook fire rate
    uv run ace_log_analyzer.py --event-type Stop --stats

    # Find errors in last 24 hours
    uv run ace_log_analyzer.py --errors --hours 24

    # Export to CSV
    uv run ace_log_analyzer.py --event-type Stop --export stop_hooks.csv
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict


class ACELogAnalyzer:
    """Analyze ACE hook logs."""

    def __init__(self, log_dir: str = ".claude/data/logs"):
        self.log_dir = Path(log_dir)

    def read_log(self, event_type: str) -> List[Dict[str, Any]]:
        """Read all entries from an event log."""
        log_path = self.log_dir / f"ace-{event_type.lower()}.jsonl"

        if not log_path.exists():
            return []

        entries = []
        with open(log_path, 'r') as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return entries

    def filter_by_time(
        self,
        entries: List[Dict[str, Any]],
        hours: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Filter entries by time window."""
        if not hours:
            return entries

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        filtered = []
        for entry in entries:
            try:
                timestamp = datetime.fromisoformat(entry['timestamp'])
                if timestamp >= cutoff:
                    filtered.append(entry)
            except (KeyError, ValueError):
                continue

        return filtered

    def calculate_stats(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics from log entries."""
        if not entries:
            return {
                "total_events": 0,
                "avg_execution_time_ms": 0,
                "error_rate": 0,
                "success_rate": 0
            }

        total = len(entries)
        execution_times = []
        errors = 0
        successes = 0

        for entry in entries:
            if entry.get('execution_time_ms'):
                execution_times.append(entry['execution_time_ms'])

            if entry.get('error'):
                errors += 1
            elif entry.get('exit_code') == 0:
                successes += 1

        return {
            "total_events": total,
            "avg_execution_time_ms": sum(execution_times) / len(execution_times) if execution_times else 0,
            "max_execution_time_ms": max(execution_times) if execution_times else 0,
            "min_execution_time_ms": min(execution_times) if execution_times else 0,
            "error_rate": (errors / total * 100) if total > 0 else 0,
            "success_rate": (successes / total * 100) if total > 0 else 0,
            "errors": errors,
            "successes": successes
        }

    def find_errors(self, hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """Find all errors across all logs."""
        errors_log = self.log_dir / "ace-errors.jsonl"

        if not errors_log.exists():
            return []

        errors = []
        with open(errors_log, 'r') as f:
            for line in f:
                try:
                    errors.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return self.filter_by_time(errors, hours)

    def print_table(self, entries: List[Dict[str, Any]], fields: List[str]):
        """Print entries as a formatted table."""
        if not entries:
            print("No entries found.")
            return

        # Calculate column widths
        widths = {field: len(field) for field in fields}
        for entry in entries[:10]:  # Sample first 10 for width calculation
            for field in fields:
                value = str(entry.get(field, ""))
                widths[field] = max(widths[field], len(value))

        # Print header
        header = " | ".join(f"{field:<{widths[field]}}" for field in fields)
        print(header)
        print("-" * len(header))

        # Print rows
        for entry in entries:
            row = " | ".join(
                f"{str(entry.get(field, '')):<{widths[field]}}"
                for field in fields
            )
            print(row)

    def export_csv(self, entries: List[Dict[str, Any]], output_file: str):
        """Export entries to CSV."""
        import csv

        if not entries:
            print("No entries to export.")
            return

        # Get all unique keys
        keys = set()
        for entry in entries:
            keys.update(entry.keys())
        keys = sorted(keys)

        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(entries)

        print(f"✅ Exported {len(entries)} entries to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze ACE hook logs"
    )
    parser.add_argument(
        "--event-type",
        help="Event type to analyze (Stop, PreCompact, etc.)"
    )
    parser.add_argument(
        "--last",
        type=int,
        help="Show last N entries"
    )
    parser.add_argument(
        "--hours",
        type=int,
        help="Filter entries from last N hours"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics"
    )
    parser.add_argument(
        "--errors",
        action="store_true",
        help="Show errors only"
    )
    parser.add_argument(
        "--export",
        help="Export to CSV file"
    )
    parser.add_argument(
        "--log-dir",
        default=".claude/data/logs",
        help="Log directory path"
    )

    args = parser.parse_args()

    analyzer = ACELogAnalyzer(log_dir=args.log_dir)

    # Show errors
    if args.errors:
        errors = analyzer.find_errors(hours=args.hours)
        print(f"\n🔴 Found {len(errors)} errors\n")
        analyzer.print_table(errors, ["timestamp", "event_type", "error"])
        return

    # Analyze specific event type
    if not args.event_type:
        print("[ERROR] --event-type required (or use --errors)")
        sys.exit(1)

    entries = analyzer.read_log(args.event_type)
    entries = analyzer.filter_by_time(entries, args.hours)

    if args.last:
        entries = entries[-args.last:]

    print(f"\n📊 {args.event_type} Hook Analysis")
    print(f"Total entries: {len(entries)}\n")

    if args.stats:
        stats = analyzer.calculate_stats(entries)
        print("Statistics:")
        print(f"  Total Events: {stats['total_events']}")
        print(f"  Avg Execution Time: {stats['avg_execution_time_ms']:.1f}ms")
        print(f"  Max Execution Time: {stats['max_execution_time_ms']:.1f}ms")
        print(f"  Success Rate: {stats['success_rate']:.1f}%")
        print(f"  Error Rate: {stats['error_rate']:.1f}%")
        print()

    if args.export:
        analyzer.export_csv(entries, args.export)
    else:
        analyzer.print_table(
            entries,
            ["timestamp", "phase", "execution_time_ms", "exit_code"]
        )


if __name__ == "__main__":
    main()
