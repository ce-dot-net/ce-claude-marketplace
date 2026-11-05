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


def _utc_now() -> str:
    """UTC ISO-8601 with a trailing 'Z' (v8: one timestamp format everywhere)."""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def archive_relevance_log(log_dir: Optional[str] = None) -> None:
    """Size-based rotation only (50 MB, .1-.3 chain), never a startup wipe.
    Delegates to the logger's single rotation scheme. Never raises."""
    try:
        ACERelevanceLogger(log_dir)._rotate_if_needed()
    except Exception:
        pass


class ACERelevanceLogger:
    """Logger for pattern relevance metrics with rotation."""

    # v5.4.5: Add rotation to prevent unbounded log growth
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (v8)
    MAX_BACKUP_FILES = 3  # Keep 3 rotated files

    def __init__(self, log_dir: Optional[str] = None):
        """log_dir None = <log root>/.claude/data/logs (8.1.0: the repo's main checkout, never a subfolder or worktree)."""
        self.base = None
        if log_dir is None:
            try:
                from ace_project_context import log_root
                self.base = log_root()
                log_dir = os.path.join(self.base, '.claude', 'data', 'logs')
            except Exception:
                log_dir = '.claude/data/logs'
        self.log_dir = Path(log_dir)
        self.log_path = self.log_dir / "ace-relevance.jsonl"  # the dir is created on the first (checked) write

    def _rotate_if_needed(self) -> bool:
        """Rotate log file if it exceeds MAX_FILE_SIZE. False = do not write (a planted chain entry, as mod APPEND_SH)."""
        try:
            if not self.log_path.exists():
                return True
            if self.log_path.stat().st_size < self.MAX_FILE_SIZE:
                return True
            for i in range(1, self.MAX_BACKUP_FILES + 1):  # §31 §24 addendum: a symlink/dir in the chain drops the row
                b = self.log_dir / f"ace-relevance.{i}.jsonl"
                if b.is_symlink() or b.is_dir():
                    return False

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
        return True

    def _write_log(self, entry: Dict[str, Any]) -> None:
        """Write a log entry to the JSONL file with rotation."""
        try:
            from plugin_data_dir import open_project_log, project_log_unsafe
            if project_log_unsafe(self.log_path, self.base):  # §24: never write through a symlink out of the project
                return
            if not self._rotate_if_needed():
                return
            f = open_project_log(self.log_path, base=self.base)  # creates the dir (relative: cwd may change after init)
            if f is None:
                return
            with f:
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
        org_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        render_cohort: Optional[str] = None,
        hook_ms: Optional[int] = None,
        cache_hit: Optional[bool] = None,
        parent_task_id: Optional[str] = None,
        query_source: Optional[str] = None,
        task_session_id: Optional[str] = None,
    ) -> None:
        """
        Log pattern search and injection metrics.

        patterns_returned / patterns_injected: a list of pattern dicts or an int
        count (v8 C5: UPS logs AFTER render with the real injected count).
        """
        returned_n = patterns_returned if isinstance(patterns_returned, int) else len(patterns_returned)
        if isinstance(patterns_injected, int):
            injected_n, patterns_injected = patterns_injected, []
        else:
            injected_n = len(patterns_injected)
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
                'section': p.get('section', 'unknown'),
                'content': p.get('content', '')[:100] + ('...' if len(p.get('content', '')) > 100 else ''),
                # v15 reward-model fields — present on ACE-1.5 search responses;
                # default to None so old log entries without them do not crash.
                'cumulative_v15_reward': p.get('cumulative_v15_reward', None),
                'isAtRisk': p.get('isAtRisk', None),
                'n_hot_pos': p.get('n_hot_pos', None),
                'n_hot_neg': p.get('n_hot_neg', None),
            }
            for p in patterns_injected[:5]  # Top 5 patterns
        ]

        entry = {
            'timestamp': _utc_now(),
            'event': 'search',
            'hook': hook,
            'session_id': session_id,
            'project_id': project_id,
            'org_id': org_id,
            'agent_type': agent_type or 'main',
            'user_prompt': user_prompt[:200] if user_prompt else '',  # Truncate long prompts
            'search_query': search_query[:100] if search_query else '',
            'patterns_returned': returned_n,
            'patterns_injected': injected_n,
            'patterns_filtered': returned_n - injected_n,
            'avg_confidence': round(avg_confidence, 3),
            'domains': domains[:10],  # Limit to 10 domains
            'top_patterns': top_patterns,
            'render_cohort': render_cohort,
        }
        if hook_ms is not None:
            entry['hook_ms'] = hook_ms
        if cache_hit is not None:
            entry['cache_hit'] = cache_hit
        if parent_task_id:
            entry['parent_task_id'] = parent_task_id
        if query_source:
            entry['query_source'] = query_source
        if task_session_id:  # fix 5b: the task pin, as the mod's search row
            entry['task_session_id'] = task_session_id

        self._write_log(entry)

    def log_search_skipped(self, hook, reason, session_id=None, project_id=None) -> None:
        """C5: public entry for the `search_skipped` event (machine prompt, too short, ...)."""
        self._write_log({'timestamp': _utc_now(), 'event': 'search_skipped', 'hook': hook,
                         'reason': reason, 'session_id': session_id, 'project_id': project_id})

    def log_domain_shift(
        self,
        session_id: str,
        from_domain: str,
        to_domain: str,
        file_path: str,
        patterns_found: int,
        search_succeeded: bool,
        project_id: Optional[str] = None,
        hook: str = 'PostToolUse',
        **extra
    ) -> None:
        """
        Log domain shift detection and auto-search metrics.

        Called from the PostToolUse domain-shift hook when domain shift is detected.
        """
        entry = {
            'timestamp': _utc_now(),
            'event': 'domain_shift',
            'hook': hook,
            'session_id': session_id,
            'project_id': project_id,
            'from_domain': from_domain,
            'to_domain': to_domain,
            'file_path': file_path[:200] if file_path else '',
            'patterns_found': patterns_found,
            'search_succeeded': search_succeeded
        }
        entry.update({k: v for k, v in extra.items() if v is not None})  # C5: patterns_injected, hook_ms, agent_id

        self._write_log(entry)

    def log_compact_event(
        self,
        session_id: str,
    ) -> None:
        """
        Log a context compaction event.

        Called from PostCompact hook when Claude Code compacts the conversation.
        """
        entry = {
            'timestamp': _utc_now(),
            'event': 'compact',
            'session_id': session_id,
        }

        self._write_log(entry)

    def log_stop_telemetry(
        self,
        session_id: Optional[str],
        hook_type: str,
        background_tasks_count: Optional[int],
        learn_lock_present: bool,
        learn_lock_age_seconds: Optional[int] = None,
    ) -> None:
        """
        Log Stop/SubagentStop background-task telemetry.

        ADDITIVE / TELEMETRY ONLY (CC v2.1.145 `background_tasks` field).

        Records how many CC-managed background tasks were running at
        session-stop time, alongside the in-flight learn-lock state. This is
        purely informational — it never influences the
        plugin-data learn-inflight lock mechanism.

        Robustness (risk #3): never raises; malformed inputs degrade to safe
        defaults so a logging failure cannot break the Stop hook.
        """
        try:
            try:
                bg_count = int(background_tasks_count) if background_tasks_count is not None else 0
            except (TypeError, ValueError):
                bg_count = 0

            entry: Dict[str, Any] = {
                'timestamp': _utc_now(),
                'event': 'hook_stop_telemetry',
                'hook_type': hook_type,
                'session_id': session_id,
                'background_tasks_count': bg_count,
                'learn_lock_present': bool(learn_lock_present),
                'learn_lock_age_seconds': learn_lock_age_seconds,
            }

            self._write_log(entry)
        except Exception:
            # Graceful degradation — telemetry must never break the hook.
            pass

    def log_execution_metrics(
        self,
        session_id: str,
        patterns_used: List[str],
        tools_executed: int,
        state_changing_tools: int,
        success: bool,
        execution_time_seconds: float,
        learning_sent: bool,
        project_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        used_ids_count: Optional[int] = None,
        used_source: Optional[str] = None,
        hook: str = 'Stop',
        used_ids_capped: bool = False,
        agent_id: Optional[str] = None,
        task_session_id: Optional[str] = None,
        render_cohort: Optional[str] = None,
        failed_steps: Optional[int] = None,
        outcome_rule: Optional[str] = None,
    ) -> None:
        """
        Log task execution metrics for correlation with pattern usage.

        Called from Stop hook after task completion.
        """
        entry = {
            'timestamp': _utc_now(),
            'event': 'execution',
            'hook': hook,  # fix 5c: Stop or SubagentStop
            'session_id': session_id,
            'project_id': project_id,
            'agent_type': agent_type or 'main',
            'patterns_used_count': len(patterns_used),
            'pattern_ids': patterns_used[:20],  # Limit to 20 IDs
            'tools_executed': tools_executed,
            'state_changing_tools': state_changing_tools,
            'success': success,
            'execution_time_seconds': round(execution_time_seconds, 2),
            'learning_sent': learning_sent,
            'source': 'python', 'agent_id': agent_id, 'task_session_id': task_session_id, 'render_cohort': render_cohort,
        }
        if outcome_rule:  # 8.1.3: success = end outcome; the rule version shows in /ace:ace-doctor
            entry['failed_steps'] = failed_steps or 0
            entry['outcome_rule'] = outcome_rule
        if used_ids_count is not None:  # item H: how many injected ids the task evidenced, and by what
            entry['used_ids_count'] = used_ids_count
            entry['used_source'] = used_source or 'none'
            entry['used_ids_tokens'] = used_ids_count  # item 2: H2 is the Python chain's only source
            entry['used_ids_model'] = 0
        if used_ids_capped:  # server 5.15.8: applied_log_ids were cut to 20
            entry['used_ids_capped'] = True

        self._write_log(entry)

    def log_hook_error(
        self,
        location: str,
        session_id: Optional[str],
        project_id: Optional[str],
        hook: str,
        error: Exception,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a structured hook error event to ace-relevance.jsonl.

        Replaces silent `except: pass` blocks with visible telemetry
        consumed by server, statusline, and ace-doctor.
        """
        try:
            error_message = str(error)
            if len(error_message) > 500:
                error_message = error_message[:500]

            entry: Dict[str, Any] = {}
            if extra:
                try:
                    entry.update(extra)
                except Exception:
                    pass

            # Required fields — set after extra so they cannot be clobbered
            entry['timestamp'] = _utc_now()
            entry['event'] = 'error'
            entry['hook'] = hook
            entry['location'] = location
            entry['session_id'] = session_id
            entry['project_id'] = project_id
            entry['error_type'] = type(error).__name__
            entry['error_message'] = error_message

            self._write_log(entry)
        except Exception:
            # Graceful degradation — never raise from error logger
            pass


# Singleton instance for easy import
_logger = None

def get_relevance_logger() -> ACERelevanceLogger:
    """Get singleton relevance logger instance."""
    global _logger
    if _logger is None or (_logger.base is not None and _logger.base != _current_root()):
        _logger = ACERelevanceLogger()  # the hooks chdir to the event cwd: the log follows that repo's root
    return _logger


def _current_root():
    try:
        from ace_project_context import log_root
        return log_root()
    except Exception:
        return None


def log_event(event, **fields) -> None:
    """Generic row (keymap / degenerate skip / playbook_load): rotation + UTC timestamp via _write_log."""
    get_relevance_logger()._write_log({"timestamp": _utc_now(), "event": event, **fields})


def log_search_skipped(hook, reason, session_id=None, project_id=None) -> None:
    get_relevance_logger().log_search_skipped(hook, reason, session_id, project_id)


def log_search_metrics(**kwargs) -> None:
    """Convenience function to log search metrics."""
    get_relevance_logger().log_search_metrics(**kwargs)


def log_search(patterns_returned=0, patterns_injected=0, hook_ms=None, hook="UserPromptSubmit",
               session_id=None, user_prompt="", search_query="", domains=None, **kw) -> None:
    """C5: search event with real counts (int or list) and hook latency."""
    try:
        get_relevance_logger().log_search_metrics(
            hook=hook, session_id=session_id, user_prompt=user_prompt,
            search_query=search_query, patterns_returned=patterns_returned,
            patterns_injected=patterns_injected, domains=domains or [],
            hook_ms=hook_ms, **kw)
    except Exception:
        pass


def log_error(hook: str, location: str, session_id=None, project_id=None, error=None,
              extra=None) -> None:
    """C5: error event tagged with the real hook name."""
    err = error if error is not None else Exception("")
    log_hook_error(location=location, session_id=session_id, project_id=project_id,
                   hook=hook, error=err, extra=extra)
    try:  # DESIGN §4: one error log for all hooks
        import plugin_data_dir
        plugin_data_dir.append_error("%s %s %s: %s" % (_utc_now(), hook, location, str(err)[:300]))
    except Exception:
        pass


def log_domain_shift(**kwargs) -> None:
    """Convenience function to log domain shift metrics."""
    get_relevance_logger().log_domain_shift(**kwargs)


def log_compact_event(**kwargs) -> None:
    """Convenience function to log compact events."""
    get_relevance_logger().log_compact_event(**kwargs)


def log_execution_metrics(**kwargs) -> None:
    """Convenience function to log execution metrics."""
    get_relevance_logger().log_execution_metrics(**kwargs)


def log_stop_telemetry(**kwargs) -> None:
    """Convenience function to log Stop/SubagentStop background-task telemetry."""
    try:
        get_relevance_logger().log_stop_telemetry(**kwargs)
    except Exception:
        pass


def log_hook_error(
    location: str,
    session_id: Optional[str],
    project_id: Optional[str],
    hook: str,
    error: Exception,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """Convenience function to log a hook error event."""
    try:
        get_relevance_logger().log_hook_error(
            location=location,
            session_id=session_id,
            project_id=project_id,
            hook=hook,
            error=error,
            extra=extra,
        )
    except Exception:
        pass


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
