#!/usr/bin/env python3
"""
ACE Relevance Logger - Tracks pattern relevance metrics

Logs pattern search and injection metrics to measure how relevant
injected patterns are to actual tasks.

Output: .claude/data/logs/ace-relevance.jsonl
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


class ACERelevanceLogger:
    """Logger for pattern relevance metrics with rotation."""

    # v5.4.5: Add rotation to prevent unbounded log growth
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_BACKUP_FILES = 3  # Keep 3 rotated files

    def __init__(self, log_dir: str = ".claude/data/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "ace-relevance.jsonl"

    def _rotate_if_needed(self) -> None:
        """Rotate log file if it exceeds MAX_FILE_SIZE."""
        try:
            if not self.log_path.exists():
                return
            if self.log_path.stat().st_size < self.MAX_FILE_SIZE:
                return

            # Rotate existing backups (3 -> delete, 2 -> 3, 1 -> 2)
            for i in range(self.MAX_BACKUP_FILES, 0, -1):
                old_path = self.log_dir / f"ace-relevance.{i}.jsonl"
                new_path = self.log_dir / f"ace-relevance.{i+1}.jsonl"
                if i == self.MAX_BACKUP_FILES and old_path.exists():
                    old_path.unlink()  # Delete oldest
                elif old_path.exists():
                    old_path.rename(new_path)

            # Rotate current to .1
            self.log_path.rename(self.log_dir / "ace-relevance.1.jsonl")
        except Exception:
            pass  # Silent fail

    def _write_log(self, entry: Dict[str, Any]) -> None:
        """Write a log entry to the JSONL file with rotation."""
        try:
            self._rotate_if_needed()
            with open(self.log_path, 'a') as f:
                f.write(json.dumps(entry, default=str) + '\n')
        except Exception as e:
            # Silent fail - don't break hooks for logging
            pass

    def log_search_metrics(
        self,
        hook: str,
        session_id: str,
        user_prompt: str,
        search_query: str,
        patterns_returned: List[Dict[str, Any]],
        patterns_injected: List[Dict[str, Any]],
        domains: List[str],
        project_id: Optional[str] = None,
        org_id: Optional[str] = None
    ) -> None:
        """
        Log pattern search and injection metrics.

        Called from UserPromptSubmit and PreToolUse hooks after pattern search.
        """
        # Calculate metrics
        avg_confidence = 0.0
        if patterns_injected:
            confidences = [p.get('confidence', 0) for p in patterns_injected]
            avg_confidence = sum(confidences) / len(confidences)

        top_patterns = [
            {
                'id': p.get('id', 'unknown'),
                'confidence': p.get('confidence', 0),
                'helpful': p.get('helpful', 0),
                'harmful': p.get('harmful', 0),
                'domain': p.get('domain', 'unknown'),
                'section': p.get('section', 'unknown')
            }
            for p in patterns_injected[:5]  # Top 5 patterns
        ]

        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': 'search',
            'hook': hook,
            'session_id': session_id,
            'project_id': project_id,
            'org_id': org_id,
            'user_prompt': user_prompt[:200] if user_prompt else '',  # Truncate long prompts
            'search_query': search_query[:100] if search_query else '',
            'patterns_returned': len(patterns_returned),
            'patterns_injected': len(patterns_injected),
            'patterns_filtered': len(patterns_returned) - len(patterns_injected),
            'avg_confidence': round(avg_confidence, 3),
            'domains': domains[:10],  # Limit to 10 domains
            'top_patterns': top_patterns
        }

        self._write_log(entry)

    def log_domain_shift(
        self,
        session_id: str,
        from_domain: str,
        to_domain: str,
        file_path: str,
        patterns_found: int,
        search_succeeded: bool,
        project_id: Optional[str] = None
    ) -> None:
        """
        Log domain shift detection and auto-search metrics.

        Called from PreToolUse hook when domain shift is detected.
        """
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': 'domain_shift',
            'hook': 'PreToolUse',
            'session_id': session_id,
            'project_id': project_id,
            'from_domain': from_domain,
            'to_domain': to_domain,
            'file_path': file_path[:200] if file_path else '',
            'patterns_found': patterns_found,
            'search_succeeded': search_succeeded
        }

        self._write_log(entry)

    def log_execution_metrics(
        self,
        session_id: str,
        patterns_used: List[str],
        tools_executed: int,
        state_changing_tools: int,
        success: bool,
        execution_time_seconds: float,
        learning_sent: bool,
        project_id: Optional[str] = None
    ) -> None:
        """
        Log task execution metrics for correlation with pattern usage.

        Called from Stop hook after task completion.
        """
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': 'execution',
            'hook': 'Stop',
            'session_id': session_id,
            'project_id': project_id,
            'patterns_used_count': len(patterns_used),
            'pattern_ids': patterns_used[:20],  # Limit to 20 IDs
            'tools_executed': tools_executed,
            'state_changing_tools': state_changing_tools,
            'success': success,
            'execution_time_seconds': round(execution_time_seconds, 2),
            'learning_sent': learning_sent
        }

        self._write_log(entry)


# Singleton instance for easy import
_logger = None

def get_relevance_logger() -> ACERelevanceLogger:
    """Get singleton relevance logger instance."""
    global _logger
    if _logger is None:
        _logger = ACERelevanceLogger()
    return _logger


def log_search_metrics(**kwargs) -> None:
    """Convenience function to log search metrics."""
    get_relevance_logger().log_search_metrics(**kwargs)


def log_domain_shift(**kwargs) -> None:
    """Convenience function to log domain shift metrics."""
    get_relevance_logger().log_domain_shift(**kwargs)


def log_execution_metrics(**kwargs) -> None:
    """Convenience function to log execution metrics."""
    get_relevance_logger().log_execution_metrics(**kwargs)


if __name__ == '__main__':
    # Test logging
    logger = ACERelevanceLogger()

    # Test search metrics
    logger.log_search_metrics(
        hook='UserPromptSubmit',
        session_id='test-session-123',
        user_prompt='Fix the domain matching bug',
        search_query='fix domain matching bug',
        patterns_returned=[{'id': '1'}, {'id': '2'}],
        patterns_injected=[{'id': '1', 'confidence': 0.8, 'domain': 'test'}],
        domains=['test-domain']
    )

    print(f"Test log written to: {logger.log_path}")
