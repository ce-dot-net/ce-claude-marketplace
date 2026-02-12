#!/usr/bin/env python3
"""
ACE Insights Analyzer - Session-level analysis of ACE relevance data.

Analyzes .claude/data/logs/ace-relevance.jsonl to provide per-session
insights about how helpful ACE patterns were during Claude tasks.

Functions:
    analyze_sessions()      - Group events by session, build per-session summaries
    calculate_helpfulness() - Correlate patterns with task success
    get_top_patterns()      - Find most-used pattern IDs
    calculate_trends()      - Compare current vs previous period
    format_insights_report() - Human-readable report string
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional


def _format_duration(seconds: int) -> str:
    """Format a duration in seconds into a human-readable string.

    - < 60s: "< 1m"
    - < 3600s (1 hour): "14m 0s"
    - < 86400s (1 day): "2h 15m"
    - >= 86400s: "3d 5h"
    """
    if seconds <= 0:
        return "< 1m"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{days}d {hours}h"


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 timestamp string to datetime (UTC)."""
    # Handle Z suffix
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str).astimezone(timezone.utc)


def deduplicate_events(
    entries: List[Dict[str, Any]], window_seconds: int = 30
) -> tuple:
    """
    Remove near-duplicate execution events.

    Near-duplicates: same session_id, within window_seconds, same tools_executed.
    Search and domain_shift events are never deduplicated.

    Returns:
        Tuple of (cleaned_list, duplicate_count)
    """
    if not entries:
        return [], 0

    # Sort by timestamp first
    sorted_entries = sorted(entries, key=lambda e: e.get("timestamp", ""))

    cleaned: List[Dict[str, Any]] = []
    dup_count = 0

    for entry in sorted_entries:
        if entry.get("event") != "execution":
            cleaned.append(entry)
            continue

        # Check if this is a duplicate of a recent execution
        is_dup = False
        sid = entry.get("session_id", "")
        tools = entry.get("tools_executed", -1)
        ts_str = entry.get("timestamp", "")

        if ts_str:
            try:
                ts = _parse_timestamp(ts_str)
            except (ValueError, TypeError):
                cleaned.append(entry)
                continue

            # Walk backwards through cleaned to find recent executions
            for prev in reversed(cleaned):
                if prev.get("event") != "execution":
                    continue
                if prev.get("session_id", "") != sid:
                    continue
                prev_ts_str = prev.get("timestamp", "")
                if not prev_ts_str:
                    continue
                try:
                    prev_ts = _parse_timestamp(prev_ts_str)
                except (ValueError, TypeError):
                    continue
                gap = abs((ts - prev_ts).total_seconds())
                if gap > window_seconds:
                    break  # Too far apart, stop checking
                if prev.get("tools_executed", -2) == tools:
                    is_dup = True
                    break

        if is_dup:
            dup_count += 1
        else:
            cleaned.append(entry)

    return cleaned, dup_count


def extract_pattern_names(entries: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Build mapping: pattern_id -> "domain / section" from search events.

    First occurrence wins when the same pattern_id appears in multiple searches.

    Returns:
        Dict mapping pattern_id to human-readable name string.
    """
    names: Dict[str, str] = {}

    for entry in entries:
        if entry.get("event") != "search":
            continue
        for pat in entry.get("top_patterns", []):
            pid = pat.get("id")
            if not pid or pid in names:
                continue
            domain = pat.get("domain", "unknown")
            section = pat.get("section", "unknown")
            names[pid] = f"{domain} / {section}"

    return names


def split_into_tasks(
    entries: List[Dict[str, Any]], gap_minutes: int = 30
) -> dict:
    """
    Split events into logical tasks based on time gaps.

    A logical task is a cluster of events where consecutive events are
    within gap_minutes of each other.

    Returns:
        Dict with tasks, total_tasks, search_only_count, duplicates_removed
    """
    if not entries:
        return {
            "tasks": [],
            "total_tasks": 0,
            "search_only_count": 0,
            "duplicates_removed": 0,
        }

    # Step 1: Deduplicate
    cleaned, dup_count = deduplicate_events(entries)

    if not cleaned:
        return {
            "tasks": [],
            "total_tasks": 0,
            "search_only_count": 0,
            "duplicates_removed": dup_count,
        }

    # Step 2: Sort by timestamp
    def _ts_key(e):
        ts = e.get("timestamp", "")
        try:
            return _parse_timestamp(ts) if ts else datetime.min.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=timezone.utc)

    sorted_entries = sorted(cleaned, key=_ts_key)

    # Step 3: Walk entries, split into clusters by time gap
    gap_seconds = gap_minutes * 60
    clusters: List[List[Dict[str, Any]]] = []
    current_cluster: List[Dict[str, Any]] = [sorted_entries[0]]

    for i in range(1, len(sorted_entries)):
        prev_ts = _ts_key(sorted_entries[i - 1])
        curr_ts = _ts_key(sorted_entries[i])
        gap = (curr_ts - prev_ts).total_seconds()

        if gap > gap_seconds:
            clusters.append(current_cluster)
            current_cluster = [sorted_entries[i]]
        else:
            current_cluster.append(sorted_entries[i])

    clusters.append(current_cluster)

    # Step 4: Build task dicts per cluster
    tasks = []
    search_only_count = 0
    task_id = 0

    # Build pattern names once
    pattern_names = extract_pattern_names(cleaned)

    for cluster in clusters:
        searches = [e for e in cluster if e.get("event") == "search"]
        executions = [e for e in cluster if e.get("event") == "execution"]

        has_execution = len(executions) > 0

        if not has_execution:
            search_only_count += 1
            continue

        task_id += 1

        # User prompt from first search
        user_prompt = ""
        for s in searches:
            p = s.get("user_prompt", "")
            if p:
                user_prompt = p
                break

        # Aggregate patterns
        patterns_injected = sum(s.get("patterns_injected", 0) for s in searches)
        patterns_used = sum(e.get("patterns_used_count", 0) for e in executions)

        # Collect pattern_ids
        all_pattern_ids = []
        for e in executions:
            all_pattern_ids.extend(e.get("pattern_ids", []))

        # Resolve pattern names for this task
        task_pattern_names = {}
        for pid in all_pattern_ids:
            if pid and pid not in task_pattern_names:
                task_pattern_names[pid] = pattern_names.get(pid, pid)

        # Domains from searches
        domains = set()
        for s in searches:
            for d in s.get("domains", []):
                domains.add(d)

        # Tools executed
        tools_executed = sum(e.get("tools_executed", 0) for e in executions)

        # Success: False if any execution failed
        success = all(e.get("success", False) for e in executions)

        # Agent type: first non-main
        agent_type = "main"
        for e in cluster:
            at = e.get("agent_type")
            if at and at != "main":
                agent_type = at
                break
        if agent_type == "main":
            for e in cluster:
                at = e.get("agent_type")
                if at:
                    agent_type = at
                    break

        # Duration from first to last event
        timestamps = []
        for e in cluster:
            ts = e.get("timestamp")
            if ts:
                try:
                    timestamps.append(_parse_timestamp(ts))
                except (ValueError, TypeError):
                    pass
        timestamps.sort()
        duration = int((timestamps[-1] - timestamps[0]).total_seconds()) if len(timestamps) >= 2 else 0
        start_time = timestamps[0].isoformat().replace("+00:00", "Z") if timestamps else None

        # Average confidence from searches
        confidences = [s.get("avg_confidence", 0) for s in searches if s.get("avg_confidence")]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        tasks.append({
            "task_id": task_id,
            "user_prompt": user_prompt,
            "start_time": start_time,
            "duration_seconds": duration,
            "agent_type": agent_type,
            "patterns_injected": patterns_injected,
            "patterns_used": patterns_used,
            "pattern_ids": list(set(all_pattern_ids)),
            "pattern_names": task_pattern_names,
            "domains": sorted(domains),
            "tools_executed": tools_executed,
            "success": success,
            "avg_confidence": round(avg_confidence, 3),
            "searches": len(searches),
            "executions": len(executions),
        })

    return {
        "tasks": tasks,
        "total_tasks": len(tasks) + search_only_count,
        "search_only_count": search_only_count,
        "duplicates_removed": dup_count,
    }



def extract_task_data_for_evaluation(
    entries: List[Dict[str, Any]],
    hours: int = 24,
) -> dict:
    """
    Enrich split_into_tasks() output with per-task pattern details.

    Produces a JSON-serializable dict intended for LLM evaluation of
    how helpful ACE patterns were during each task.

    Args:
        entries: List of JSONL log entries (dicts).
        hours: Time window label included in metadata.

    Returns:
        Dict with metadata, tasks (each enriched with pattern_details),
        search_only_count, top_patterns, and trends.
    """
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if not entries:
        return {
            "metadata": {
                "generated_at": generated_at,
                "hours": hours,
                "total_entries": 0,
                "duplicates_removed": 0,
            },
            "tasks": [],
            "search_only_count": 0,
            "top_patterns": [],
            "trends": calculate_trends(entries),
        }

    # Step 1: Get tasks from split_into_tasks
    task_data = split_into_tasks(entries)
    tasks = task_data["tasks"]
    dup_count = task_data["duplicates_removed"]

    # Step 2: Deduplicate + sort entries (same logic as split_into_tasks)
    cleaned, _ = deduplicate_events(entries)

    def _ts_key(e):
        ts = e.get("timestamp", "")
        try:
            return _parse_timestamp(ts) if ts else datetime.min.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=timezone.utc)

    sorted_entries = sorted(cleaned, key=_ts_key)

    # Step 3: Build pattern name mapping
    pattern_names = extract_pattern_names(entries)

    # Step 4: For each task, find search events in time window and extract pattern_details
    for task in tasks:
        start_str = task.get("start_time")
        duration = task.get("duration_seconds", 0)

        if not start_str:
            task["pattern_details"] = []
            continue

        try:
            task_start = _parse_timestamp(start_str)
        except (ValueError, TypeError):
            task["pattern_details"] = []
            continue

        task_end = task_start + timedelta(seconds=max(duration, 0))

        # Collect search events within this task's time window
        # Use a generous window: from task_start to task_end
        # (search events precede or overlap with executions)
        task_searches = []
        for e in sorted_entries:
            if e.get("event") != "search":
                continue
            ts_str = e.get("timestamp", "")
            if not ts_str:
                continue
            try:
                ets = _parse_timestamp(ts_str)
            except (ValueError, TypeError):
                continue
            # Include search events within [start - 1min buffer, end + 1min buffer]
            if task_start - timedelta(minutes=1) <= ets <= task_end + timedelta(minutes=1):
                task_searches.append(e)

        # Step 5: Extract and deduplicate pattern details by ID
        seen_patterns: Dict[str, Dict[str, Any]] = {}
        for s in task_searches:
            for pat in s.get("top_patterns", []):
                pid = pat.get("id")
                if not pid:
                    continue
                conf = pat.get("confidence", 0)
                if pid not in seen_patterns or conf > seen_patterns[pid].get("confidence", 0):
                    seen_patterns[pid] = {
                        "id": pid,
                        "name": pattern_names.get(pid, pid),
                        "confidence": conf,
                        "domain": pat.get("domain", "unknown"),
                        "section": pat.get("section", "unknown"),
                        "helpful_votes": pat.get("helpful", 0),
                        "harmful_votes": pat.get("harmful", 0),
                    }

        task["pattern_details"] = list(seen_patterns.values())

    return {
        "metadata": {
            "generated_at": generated_at,
            "hours": hours,
            "total_entries": len(entries),
            "duplicates_removed": dup_count,
        },
        "tasks": tasks,
        "search_only_count": task_data["search_only_count"],
        "top_patterns": get_top_patterns(entries),
        "trends": calculate_trends(entries),
    }


def generate_evaluated_html(
    task_data: dict,
    evaluations: dict,
    hours: int = 24,
) -> str:
    """
    Generate a self-contained HTML report with LLM-evaluated helpfulness.

    Args:
        task_data: Output from extract_task_data_for_evaluation().
        evaluations: Claude's evaluation dict with per-task helpfulness
                     and overall summary. May be None.
        hours: Time window label for the report header.

    Returns:
        Self-contained HTML string with inline CSS, dark theme.
    """
    # Normalize evaluations
    if evaluations is None:
        evaluations = {"evaluations": [], "overall_helpfulness_pct": 0, "overall_summary": ""}

    evals_list = evaluations.get("evaluations", [])
    overall_pct = evaluations.get("overall_helpfulness_pct", 0)
    overall_summary = _html_escape(evaluations.get("overall_summary", ""))

    # Build eval lookup: task_id -> eval dict
    eval_by_id: Dict[int, dict] = {}
    for ev in evals_list:
        tid = ev.get("task_id")
        if tid is not None:
            eval_by_id[tid] = ev

    # Tasks and metadata
    tasks = task_data.get("tasks", [])
    metadata = task_data.get("metadata", {})
    top_patterns = task_data.get("top_patterns", [])
    total_tasks = len(tasks)
    generated = metadata.get("generated_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    # Sort tasks newest first by start_time
    def _sort_key(t):
        st = t.get("start_time", "")
        try:
            return _parse_timestamp(st) if st else datetime.min.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=timezone.utc)

    tasks_sorted = sorted(tasks, key=_sort_key, reverse=True)

    # Overall helpfulness color
    if overall_pct > 70:
        overall_color = "#10b981"
    elif overall_pct >= 40:
        overall_color = "#f59e0b"
    else:
        overall_color = "#ef4444"

    # Build task cards
    task_cards_html = ""
    for t in tasks_sorted:
        tid = t.get("task_id")
        prompt = _html_escape(t.get("user_prompt", "Unnamed task"))[:120]
        if not prompt:
            prompt = "Unnamed task"
        success = t.get("success")
        success_class = "status-ok" if success else "status-fail"
        success_text = "SUCCESS" if success else "FAIL"
        dur = t.get("duration_seconds", 0)
        dur_str = _format_duration(dur)
        te = t.get("tools_executed", 0)
        domains = t.get("domains", [])
        domain_tags = " ".join(
            f'<span class="domain-tag">{_html_escape(d)}</span>' for d in domains
        )
        pattern_details = t.get("pattern_details", [])
        pattern_tags = ""
        for pd in pattern_details[:5]:
            pname = _html_escape(pd.get("name", pd.get("id", "unknown")))
            conf = pd.get("confidence", 0)
            pattern_tags += f'<span class="pattern-tag">{pname} ({conf:.0%})</span> '
        if len(pattern_details) > 5:
            pattern_tags += f'<span class="pattern-tag">+{len(pattern_details) - 5} more</span>'

        # Helpfulness evaluation
        ev = eval_by_id.get(tid)
        if ev is not None:
            help_pct = ev.get("helpfulness_pct", 0)
            reasoning = _html_escape(ev.get("reasoning", ""))
            if help_pct > 70:
                help_color = "#10b981"
                help_class = "help-green"
            elif help_pct >= 40:
                help_color = "#f59e0b"
                help_class = "help-yellow"
            else:
                help_color = "#ef4444"
                help_class = "help-red"
            help_bar = f"""
            <div class="help-bar-section">
              <div class="help-bar-label {help_class}">{help_pct}%</div>
              <div class="help-bar-track"><div class="help-bar-fill {help_class}" style="width:{min(help_pct, 100)}%;background:{help_color}"></div></div>
            </div>
            <div class="eval-reasoning">{reasoning}</div>
            """
        else:
            help_bar = '<div class="not-evaluated">Not evaluated</div>'

        task_cards_html += f"""
        <div class="task-card">
          <div class="task-header">
            <span class="task-prompt">{prompt}</span>
            <span class="task-duration">({dur_str})</span>
          </div>
          <div class="task-badges">
            <span class="session-status {success_class}">{success_text}</span>
            <span class="task-tools">{te} tools</span>
          </div>
          {help_bar}
          <div class="task-details">
            {f'<div class="task-domains">{domain_tags}</div>' if domain_tags else ""}
            {f'<div class="task-patterns">{pattern_tags}</div>' if pattern_tags else ""}
          </div>
        </div>"""

    # Top patterns bar chart
    top_patterns_rows = ""
    if top_patterns:
        max_usage = top_patterns[0].get("usage_count", 1) if top_patterns else 1
        for p in top_patterns[:10]:
            pct = int(p.get("usage_count", 0) / max_usage * 100) if max_usage else 0
            name = _html_escape(p.get("pattern_name", p.get("pattern_id", "unknown"))[:30])
            count = p.get("usage_count", 0)
            sessions = p.get("sessions", 0)
            top_patterns_rows += f"""
            <div class="bar-row">
              <span class="bar-label">{name}</span>
              <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:#6366f1"></div></div>
              <span class="bar-value">{count}x</span>
              <span class="bar-sessions">{sessions}s</span>
            </div>"""
    else:
        top_patterns_rows = '<div class="empty">No pattern usage data yet</div>'

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ACE Insights — LLM-Evaluated Report</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; line-height: 1.6; padding: 48px 24px; }}
    .container {{ max-width: 800px; margin: 0 auto; }}
    h1 {{ font-size: 28px; font-weight: 700; color: #f0f6fc; margin-bottom: 8px; }}
    h2 {{ font-size: 18px; font-weight: 600; color: #f0f6fc; margin-top: 40px; margin-bottom: 16px; }}
    .subtitle {{ color: #8b949e; font-size: 14px; margin-bottom: 32px; }}

    .summary-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin-bottom: 32px; text-align: center; }}
    .overall-pct {{ font-size: 56px; font-weight: 700; }}
    .overall-label {{ font-size: 14px; color: #8b949e; margin-top: 4px; }}
    .overall-summary {{ font-size: 14px; color: #c9d1d9; margin-top: 12px; padding: 12px 16px; background: #0d1117; border-radius: 8px; }}

    .stats-row {{ display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }}
    .stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center; flex: 1; min-width: 100px; }}
    .stat-value {{ font-size: 24px; font-weight: 700; color: #f0f6fc; }}
    .stat-label {{ font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}

    .task-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
    .task-header {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
    .task-prompt {{ font-size: 15px; font-weight: 600; color: #f0f6fc; }}
    .task-duration {{ font-size: 12px; color: #8b949e; }}
    .task-badges {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }}
    .task-tools {{ font-size: 12px; color: #8b949e; }}
    .task-details {{ font-size: 12px; color: #8b949e; margin-top: 8px; }}
    .task-domains {{ margin-bottom: 4px; display: flex; flex-wrap: wrap; gap: 4px; }}
    .task-patterns {{ display: flex; flex-wrap: wrap; gap: 4px; }}

    .session-status {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; }}
    .status-ok {{ background: #1a3a2a; color: #3fb950; }}
    .status-fail {{ background: #3d1f1f; color: #f85149; }}

    .domain-tag {{ display: inline-block; font-size: 11px; padding: 2px 8px; background: #1c2333; color: #58a6ff; border-radius: 4px; }}
    .pattern-tag {{ display: inline-block; font-size: 11px; padding: 2px 8px; background: #1c1d2e; color: #bc8cff; border-radius: 4px; }}

    .help-bar-section {{ display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }}
    .help-bar-label {{ font-size: 14px; font-weight: 700; min-width: 42px; }}
    .help-bar-track {{ flex: 1; height: 8px; background: #21262d; border-radius: 4px; }}
    .help-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s ease; }}
    .help-green {{ color: #10b981; }}
    .help-yellow {{ color: #f59e0b; }}
    .help-red {{ color: #ef4444; }}
    .eval-reasoning {{ font-size: 13px; color: #8b949e; font-style: italic; margin-bottom: 8px; }}
    .not-evaluated {{ font-size: 13px; color: #6e7681; font-style: italic; margin-bottom: 8px; }}

    .chart-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
    .chart-title {{ font-size: 12px; font-weight: 600; color: #8b949e; text-transform: uppercase; margin-bottom: 16px; }}
    .bar-row {{ display: flex; align-items: center; margin-bottom: 8px; }}
    .bar-label {{ width: 180px; font-size: 11px; font-family: monospace; color: #c9d1d9; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-track {{ flex: 1; height: 8px; background: #21262d; border-radius: 4px; margin: 0 12px; }}
    .bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s ease; }}
    .bar-value {{ width: 32px; font-size: 12px; font-weight: 600; color: #c9d1d9; text-align: right; }}
    .bar-sessions {{ width: 32px; font-size: 11px; color: #8b949e; text-align: right; }}

    .empty {{ color: #6e7681; font-size: 13px; padding: 12px 0; }}
    .footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid #30363d; font-size: 12px; color: #6e7681; text-align: center; }}
  </style>
</head>
<body>
<div class="container">
  <h1>ACE Insights &mdash; LLM-Evaluated Report</h1>
  <div class="subtitle">Per-task helpfulness evaluation &middot; Last {hours} hours</div>

  <div class="summary-card">
    <div class="overall-pct" style="color:{overall_color}">{overall_pct}%</div>
    <div class="overall-label">Overall Helpfulness</div>
    {f'<div class="overall-summary">{overall_summary}</div>' if overall_summary else ""}
  </div>

  <div class="stats-row">
    <div class="stat"><div class="stat-value">{total_tasks}</div><div class="stat-label">Tasks</div></div>
    <div class="stat"><div class="stat-value">{overall_pct}%</div><div class="stat-label">Helpfulness</div></div>
  </div>

  <h2>Tasks</h2>
  {task_cards_html if task_cards_html else '<div class="empty">No tasks recorded yet</div>'}

  <h2>Top Patterns</h2>
  <div class="chart-card">
    <div class="chart-title">Most-Used Patterns (usage count &middot; sessions)</div>
    {top_patterns_rows}
  </div>

  <div class="footer">
    ACE Insights &mdash; LLM-Evaluated Report &middot; Generated {_html_escape(generated)} &middot; {hours}h window
  </div>
</div>
</body>
</html>"""

def compute_ace_engagement(tasks: List[Dict]) -> dict:
    """Compute ACE engagement metrics from logical tasks.

    Args:
        tasks: List of task dicts as returned by split_into_tasks()["tasks"].
               Each task has: searches, patterns_injected, avg_confidence,
               domains, success.

    Returns:
        Dict with aggregate engagement metrics:
          total_tasks, ace_assisted_tasks, ace_coverage_pct,
          avg_confidence, avg_patterns_per_task, avg_domains_per_task,
          ace_success_rate, overall_success_rate
    """
    if not tasks:
        return {
            "total_tasks": 0,
            "ace_assisted_tasks": 0,
            "ace_coverage_pct": 0,
            "avg_confidence": 0,
            "avg_patterns_per_task": 0,
            "avg_domains_per_task": 0,
            "ace_success_rate": 0,
            "overall_success_rate": 0,
        }

    total = len(tasks)
    ace_tasks = [t for t in tasks if t.get("searches", 0) > 0]
    ace_count = len(ace_tasks)

    coverage_pct = round(ace_count / total * 100, 1) if total else 0

    if ace_count:
        avg_confidence = round(
            sum(t.get("avg_confidence", 0) for t in ace_tasks) / ace_count, 1
        )
        avg_patterns = round(
            sum(t.get("patterns_injected", 0) for t in ace_tasks) / ace_count, 1
        )
        avg_domains = round(
            sum(len(t.get("domains", [])) for t in ace_tasks) / ace_count, 1
        )
        ace_successes = sum(1 for t in ace_tasks if t.get("success"))
        ace_success_rate = round(ace_successes / ace_count * 100, 1)
    else:
        avg_confidence = 0
        avg_patterns = 0
        avg_domains = 0
        ace_success_rate = 0

    overall_successes = sum(1 for t in tasks if t.get("success"))
    overall_rate = round(overall_successes / total * 100, 1) if total else 0

    return {
        "total_tasks": total,
        "ace_assisted_tasks": ace_count,
        "ace_coverage_pct": coverage_pct,
        "avg_confidence": avg_confidence,
        "avg_patterns_per_task": avg_patterns,
        "avg_domains_per_task": avg_domains,
        "ace_success_rate": ace_success_rate,
        "overall_success_rate": overall_rate,
    }


def analyze_sessions(entries: List[Dict[str, Any]], hours: int = 24) -> dict:
    """
    Group log entries by session_id and return per-session summaries.

    Args:
        entries: List of JSONL log entries (dicts)
        hours: Time window in hours (unused for grouping, entries are pre-filtered)

    Returns:
        Dict with 'sessions' list, 'total_sessions', 'active_sessions'
    """
    if not entries:
        return {"sessions": [], "total_sessions": 0, "active_sessions": 0}

    # Group entries by session_id
    sessions_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        sid = entry.get("session_id", "unknown")
        sessions_map[sid].append(entry)

    sessions = []
    active_count = 0

    for sid, events in sessions_map.items():
        # Parse timestamps for duration
        timestamps = []
        for e in events:
            ts = e.get("timestamp")
            if ts:
                try:
                    timestamps.append(_parse_timestamp(ts))
                except (ValueError, TypeError):
                    pass

        timestamps.sort()
        start_time = timestamps[0].isoformat().replace("+00:00", "Z") if timestamps else None
        end_time = timestamps[-1].isoformat().replace("+00:00", "Z") if timestamps else None
        duration = int((timestamps[-1] - timestamps[0]).total_seconds()) if len(timestamps) >= 2 else 0

        # Collect search metrics
        searches = [e for e in events if e.get("event") == "search"]
        domain_shifts = [e for e in events if e.get("event") == "domain_shift"]
        executions = [e for e in events if e.get("event") == "execution"]

        # Patterns injected = sum across all searches
        patterns_injected = sum(e.get("patterns_injected", 0) for e in searches)

        # User prompts: deduplicated, truncated
        seen_prompts = []
        for s in searches:
            prompt = s.get("user_prompt", "")
            if prompt:
                truncated = prompt[:200]
                if truncated not in seen_prompts:
                    seen_prompts.append(truncated)

        # Domains: merge from search domains + domain_shift to_domain
        domains = set()
        for s in searches:
            for d in s.get("domains", []):
                domains.add(d)
        for ds in domain_shifts:
            to_d = ds.get("to_domain")
            if to_d:
                domains.add(to_d)

        # Detect agent_type from any event in this session
        agent_type = "main"
        for e in events:
            at = e.get("agent_type")
            if at and at != "main":
                agent_type = at
                break
        # Fallback: check all events for any agent_type
        if agent_type == "main":
            for e in events:
                at = e.get("agent_type")
                if at:
                    agent_type = at
                    break

        # Execution metrics (aggregate across ALL executions in the session)
        has_execution = len(executions) > 0
        if has_execution:
            active_count += 1
            patterns_used = sum(e.get("patterns_used_count", 0) for e in executions)
            tools_executed = sum(e.get("tools_executed", 0) for e in executions)
            # Session failed if ANY execution failed
            success = all(e.get("success", False) for e in executions)
            learning_sent = any(e.get("learning_sent", False) for e in executions)
        else:
            patterns_used = 0
            tools_executed = 0
            success = None
            learning_sent = False

        sessions.append({
            "session_id": sid,
            "agent_type": agent_type,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration,
            "searches": len(searches),
            "patterns_injected": patterns_injected,
            "patterns_used": patterns_used,
            "domain_shifts": len(domain_shifts),
            "domains": sorted(domains),
            "tools_executed": tools_executed,
            "success": success,
            "learning_sent": learning_sent,
            "user_prompts": seen_prompts,
        })

    # Sort sessions by start_time
    sessions.sort(key=lambda s: s.get("start_time") or "")

    return {
        "sessions": sessions,
        "total_sessions": len(sessions),
        "active_sessions": active_count,
    }


def calculate_helpfulness(entries: List[Dict[str, Any]]) -> dict:
    """
    Correlate patterns with task success.

    A "task" is an execution event. Tasks "with patterns" have patterns_used_count > 0.

    Returns:
        Dict with tasks_with_patterns, tasks_without_patterns,
        success_rate_with_patterns, success_rate_without_patterns,
        pattern_advantage, avg_patterns_per_task, avg_confidence
    """
    executions = [e for e in entries if e.get("event") == "execution"]
    searches = [e for e in entries if e.get("event") == "search"]

    if not executions:
        return {
            "tasks_with_patterns": 0,
            "tasks_without_patterns": 0,
            "success_rate_with_patterns": 0,
            "success_rate_without_patterns": 0,
            "pattern_advantage": 0,
            "avg_patterns_per_task": 0,
            "avg_confidence": 0,
        }

    with_patterns = [e for e in executions if e.get("patterns_used_count", 0) > 0]
    without_patterns = [e for e in executions if e.get("patterns_used_count", 0) == 0]

    success_with = sum(1 for e in with_patterns if e.get("success"))
    success_without = sum(1 for e in without_patterns if e.get("success"))

    rate_with = (success_with / len(with_patterns) * 100) if with_patterns else 0
    rate_without = (success_without / len(without_patterns) * 100) if without_patterns else 0

    advantage = rate_with - rate_without if with_patterns and without_patterns else (
        rate_with if with_patterns else 0
    )

    # Average patterns per task (only tasks with patterns)
    avg_patterns = (
        sum(e.get("patterns_used_count", 0) for e in with_patterns) / len(with_patterns)
        if with_patterns else 0
    )

    # Average confidence from search events
    confidences = [s.get("avg_confidence", 0) for s in searches if s.get("avg_confidence")]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0

    return {
        "tasks_with_patterns": len(with_patterns),
        "tasks_without_patterns": len(without_patterns),
        "success_rate_with_patterns": round(rate_with, 1),
        "success_rate_without_patterns": round(rate_without, 1),
        "pattern_advantage": round(advantage, 1),
        "avg_patterns_per_task": round(avg_patterns, 1),
        "avg_confidence": round(avg_conf, 3),
    }


def get_top_patterns(entries: List[Dict[str, Any]], limit: int = 10) -> list:
    """
    Find most-used pattern IDs across all execution events.

    Returns:
        List of dicts with pattern_id, pattern_name, usage_count, sessions
    """
    executions = [e for e in entries if e.get("event") == "execution"]

    pattern_usage: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"usage_count": 0, "session_ids": set()}
    )

    for ex in executions:
        sid = ex.get("session_id", "unknown")
        for pid in ex.get("pattern_ids", []):
            if pid:
                pattern_usage[pid]["usage_count"] += 1
                pattern_usage[pid]["session_ids"].add(sid)

    if not pattern_usage:
        return []

    # Build pattern name mapping from search events
    names = extract_pattern_names(entries)

    result = [
        {
            "pattern_id": pid,
            "pattern_name": names.get(pid, pid),
            "usage_count": data["usage_count"],
            "sessions": len(data["session_ids"]),
        }
        for pid, data in pattern_usage.items()
    ]

    result.sort(key=lambda x: x["usage_count"], reverse=True)
    return result[:limit]


def calculate_trends(
    entries: List[Dict[str, Any]],
    current_hours: int = 24,
    previous_hours: int = 24,
    reference_time: Optional[datetime] = None,
) -> dict:
    """
    Compare current period vs previous period.

    Current period: now - current_hours to now
    Previous period: now - current_hours - previous_hours to now - current_hours

    Returns:
        Dict with current_period, previous_period, changes
    """
    now = reference_time or datetime.now(timezone.utc)
    current_start = now - timedelta(hours=current_hours)
    previous_start = current_start - timedelta(hours=previous_hours)

    current_entries = []
    previous_entries = []

    for entry in entries:
        ts_str = entry.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = _parse_timestamp(ts_str)
        except (ValueError, TypeError):
            continue

        if ts >= current_start:
            current_entries.append(entry)
        elif ts >= previous_start:
            previous_entries.append(entry)

    def _period_stats(period_entries):
        searches = [e for e in period_entries if e.get("event") == "search"]
        executions = [e for e in period_entries if e.get("event") == "execution"]
        success_count = sum(1 for e in executions if e.get("success"))
        success_rate = (success_count / len(executions) * 100) if executions else 0.0
        patterns_injected = sum(e.get("patterns_injected", 0) for e in searches)

        return {
            "searches": len(searches),
            "tasks": len(executions),
            "success_rate": round(success_rate, 1),
            "patterns_injected": patterns_injected,
        }

    current = _period_stats(current_entries)
    previous = _period_stats(previous_entries)

    def _calc_change(curr_val, prev_val, is_rate=False):
        if is_rate:
            # For rates (percentage points), 0% is valid data
            # Only N/A if both periods had no tasks (both 0)
            if not previous_entries and not current_entries:
                return "N/A"
            diff = curr_val - prev_val
            sign = "+" if diff >= 0 else ""
            return f"{sign}{diff:.1f}pp"
        else:
            if prev_val == 0 and curr_val == 0:
                return "N/A"
            if prev_val == 0:
                return "N/A"
            pct = ((curr_val - prev_val) / prev_val) * 100
            sign = "+" if pct >= 0 else ""
            return f"{sign}{pct:.1f}%"

    changes = {
        "searches": _calc_change(current["searches"], previous["searches"]),
        "tasks": _calc_change(current["tasks"], previous["tasks"]),
        "success_rate": _calc_change(current["success_rate"], previous["success_rate"], is_rate=True),
        "patterns_injected": _calc_change(current["patterns_injected"], previous["patterns_injected"]),
    }

    return {
        "current_period": current,
        "previous_period": previous,
        "changes": changes,
    }


def format_insights_report(
    sessions: dict,
    helpfulness: dict,
    top_patterns: list,
    trends: dict,
) -> str:
    """
    Format all analysis data into a human-readable report string.

    Args:
        sessions: Output from analyze_sessions()
        helpfulness: Output from calculate_helpfulness()
        top_patterns: Output from get_top_patterns()
        trends: Output from calculate_trends()

    Returns:
        Multi-line formatted report string
    """
    lines = []
    lines.append("ACE Insights Report")
    lines.append("=" * 40)
    lines.append("")

    # Session summary
    total = sessions.get("total_sessions", 0)
    active = sessions.get("active_sessions", 0)

    if total == 0:
        lines.append("Sessions: No data available")
    else:
        lines.append(f"Sessions: {total} total, {active} active (with task execution)")
        lines.append("")

        for s in sessions.get("sessions", []):
            status = "OK" if s.get("success") else ("FAIL" if s.get("success") is False else "---")
            duration = s.get("duration_seconds", 0)
            dur_str = _format_duration(duration)
            prompts = ", ".join(s.get("user_prompts", [])[:2])
            if len(s.get("user_prompts", [])) > 2:
                prompts += "..."

            agent = s.get("agent_type", "main")
            agent_tag = f" [{agent}]" if agent != "main" else ""
            lines.append(f"  [{status}]{agent_tag} {s['session_id'][:12]}... ({dur_str})")
            if prompts:
                lines.append(f"         Task: {prompts}")
            lines.append(
                f"         Patterns: {s.get('patterns_injected', 0)} injected, "
                f"{s.get('patterns_used', 0)} used | "
                f"Tools: {s.get('tools_executed', 0)} | "
                f"Domains: {', '.join(s.get('domains', []))}"
            )

    lines.append("")

    # Helpfulness
    lines.append("Pattern Helpfulness")
    lines.append("-" * 40)

    tasks_with = helpfulness.get("tasks_with_patterns", 0)
    tasks_without = helpfulness.get("tasks_without_patterns", 0)

    if tasks_with == 0 and tasks_without == 0:
        lines.append("  No task execution data available")
    else:
        rate_with = helpfulness.get("success_rate_with_patterns", 0)
        rate_without = helpfulness.get("success_rate_without_patterns", 0)
        advantage = helpfulness.get("pattern_advantage", 0)

        lines.append(f"  Tasks with patterns:    {tasks_with} (success: {rate_with}%)")
        lines.append(f"  Tasks without patterns: {tasks_without} (success: {rate_without}%)")
        lines.append(f"  Pattern advantage:      {'+' if advantage >= 0 else ''}{advantage}pp")
        lines.append(f"  Avg patterns/task:      {helpfulness.get('avg_patterns_per_task', 0)}")
        lines.append(f"  Avg confidence:         {helpfulness.get('avg_confidence', 0):.1%}")

    lines.append("")

    # Top patterns
    lines.append("Top Patterns")
    lines.append("-" * 40)

    if not top_patterns:
        lines.append("  No pattern usage data available")
    else:
        for i, p in enumerate(top_patterns[:10], 1):
            lines.append(
                f"  {i}. {p['pattern_id']} "
                f"(used {p['usage_count']}x across {p['sessions']} session{'s' if p['sessions'] != 1 else ''})"
            )

    lines.append("")

    # Trends
    lines.append("Trends (current vs previous period)")
    lines.append("-" * 40)

    curr = trends.get("current_period", {})
    changes = trends.get("changes", {})

    for metric in ("searches", "tasks", "success_rate", "patterns_injected"):
        val = curr.get(metric, 0)
        change = changes.get(metric, "N/A")
        label = metric.replace("_", " ").title()

        if change == "N/A":
            indicator = ""
        elif change.startswith("+"):
            indicator = " ^"
        elif change.startswith("-"):
            indicator = " v"
        else:
            indicator = ""

        unit = "%" if metric == "success_rate" else ""
        lines.append(f"  {label}: {val}{unit} ({change}){indicator}")

    lines.append("")
    return "\n".join(lines)


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_insights_html_v2(
    helpfulness: dict,
    top_patterns: list,
    trends: dict,
    raw_entries: List[Dict[str, Any]],
    hours: int = 24,
) -> str:
    """Render the v2 task-based HTML layout."""
    task_data = split_into_tasks(raw_entries)
    pattern_names = extract_pattern_names(raw_entries)
    tasks = task_data["tasks"]
    total_tasks = task_data["total_tasks"]
    search_only = task_data["search_only_count"]
    dups_removed = task_data["duplicates_removed"]

    # Compute ACE engagement metrics at TASK level
    engagement = compute_ace_engagement(tasks)
    # Average confidence from task data (for top-level stat)
    task_confs = [t.get("avg_confidence", 0) for t in tasks if t.get("avg_confidence")]
    avg_conf = sum(task_confs) / len(task_confs) if task_confs else 0
    # Total patterns injected across all tasks
    total_injected = sum(t.get("patterns_injected", 0) for t in tasks)
    curr = trends.get("current_period", {})
    prev = trends.get("previous_period", {})
    changes = trends.get("changes", {})

    # Count successes/failures
    success_count = sum(1 for t in tasks if t.get("success") is True)
    task_count = len(tasks)
    success_rate = round(success_count / task_count * 100) if task_count else 0

    # Build daily breakdown
    daily_data: Dict[str, Dict[str, Any]] = {}
    for t in tasks:
        start = t.get("start_time", "")
        if start:
            try:
                dt = _parse_timestamp(start)
                day_key = dt.strftime("%b %d")
            except (ValueError, TypeError):
                continue
        else:
            continue
        if day_key not in daily_data:
            daily_data[day_key] = {"tasks": 0, "success": 0, "fail": 0, "patterns": 0, "sort_key": dt.date()}
        daily_data[day_key]["tasks"] += 1
        if t.get("success"):
            daily_data[day_key]["success"] += 1
        else:
            daily_data[day_key]["fail"] += 1
        daily_data[day_key]["patterns"] += t.get("patterns_injected", 0)

    # Sort daily data newest first
    daily_sorted = sorted(daily_data.items(), key=lambda x: x[1]["sort_key"], reverse=True)

    daily_rows = ""
    for day, d in daily_sorted:
        day_rate = round(d["success"] / d["tasks"] * 100) if d["tasks"] else 0
        bar_pct = min(day_rate, 100)
        bar_color = "#22c55e" if day_rate >= 80 else ("#eab308" if day_rate >= 50 else "#ef4444")
        daily_rows += f"""
        <div class="daily-row">
          <span class="daily-date">{day}</span>
          <span class="daily-tasks">{d['tasks']} task{"s" if d['tasks'] != 1 else ""}</span>
          <div class="daily-bar-track"><div class="daily-bar-fill" style="width:{bar_pct}%;background:{bar_color}"></div></div>
          <span class="daily-rate">{day_rate}%</span>
          <span class="daily-patterns">{d['patterns']} pat</span>
        </div>"""

    # Build task cards (newest first)
    tasks_reversed = list(reversed(tasks))
    task_cards = ""
    for t in tasks_reversed:
        tid = t["task_id"]
        prompt = _html_escape(t.get("user_prompt", "Unnamed task"))[:120]
        if not prompt:
            prompt = "Unnamed task"
        dur = t.get("duration_seconds", 0)
        dur_str = _format_duration(dur)
        success = t.get("success")
        success_class = "status-ok" if success else "status-fail"
        success_text = "SUCCESS" if success else "FAIL"
        agent = _html_escape(t.get("agent_type", "main"))
        agent_badge = f'<span class="agent-badge agent-{agent}">{agent}</span>' if agent != "main" else ""

        pi = t.get("patterns_injected", 0)
        pu = t.get("patterns_used", 0)
        te = t.get("tools_executed", 0)
        conf = t.get("avg_confidence", 0)
        domains = ", ".join(_html_escape(d) for d in t.get("domains", []))

        # Pattern names
        pnames = t.get("pattern_names", {})
        pattern_tags = ""
        for pid, name in list(pnames.items())[:5]:
            pattern_tags += f'<span class="pattern-tag">{_html_escape(name)}</span> '
        if len(pnames) > 5:
            pattern_tags += f'<span class="pattern-tag">+{len(pnames)-5} more</span>'

        # Start time
        start = t.get("start_time", "")
        if start:
            try:
                dt = _parse_timestamp(start)
                time_str = dt.strftime("%b %d, %H:%M")
            except (ValueError, TypeError):
                time_str = ""
        else:
            time_str = ""

        task_cards += f"""
        <div class="task-card">
          <div class="task-header">
            <span class="task-prompt">{prompt}</span>
            <span class="task-duration">({dur_str})</span>
          </div>
          <div class="task-badges">
            <span class="session-status {success_class}">{success_text}</span>
            {agent_badge}
            <span class="task-time">{time_str}</span>
          </div>
          <div class="task-flow">
            ACE injected {pi} patterns ({conf:.0%} confidence) &rarr;
            {pu} patterns used &rarr; {te} tools executed &rarr;
            {"Success" if success else "Failed"}
          </div>
          <div class="task-details">
            {f'<div class="task-domains">Domains: {domains}</div>' if domains else ''}
            <div class="task-patterns">Patterns: {pattern_tags if pattern_tags else "none"}</div>
          </div>
        </div>"""

    # Engagement indicator based on coverage
    eng_coverage = engagement["ace_coverage_pct"]
    if eng_coverage >= 70:
        eng_class = "adv-positive"
    elif eng_coverage >= 40:
        eng_class = "adv-neutral"
    else:
        eng_class = "adv-negative"

    # Top patterns rows with names
    top_patterns_rows = ""
    if top_patterns:
        max_usage = top_patterns[0]["usage_count"] if top_patterns else 1
        for i, p in enumerate(top_patterns[:10], 1):
            pct = int(p["usage_count"] / max_usage * 100) if max_usage else 0
            name = _html_escape(p.get("pattern_name", p["pattern_id"])[:30])
            top_patterns_rows += f"""
            <div class="bar-row">
              <span class="bar-label">{name}</span>
              <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:#6366f1"></div></div>
              <span class="bar-value">{p['usage_count']}x</span>
              <span class="bar-sessions">{p['sessions']}s</span>
            </div>"""
    else:
        top_patterns_rows = '<div class="empty">No pattern usage data yet</div>'

    # Trend indicator helper
    def _trend_indicator(change_str):
        if change_str == "N/A":
            return '<span class="trend-na">N/A</span>'
        elif change_str.startswith("+"):
            return f'<span class="trend-up">{_html_escape(change_str)}</span>'
        elif change_str.startswith("-"):
            return f'<span class="trend-down">{_html_escape(change_str)}</span>'
        return f'<span>{_html_escape(change_str)}</span>'

    # Search-only note
    search_note = ""
    if search_only > 0:
        search_note = f'<div class="search-only-note">{search_only} search{"es" if search_only != 1 else ""} had no follow-up task completion</div>'

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ACE Insights</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; color: #334155; line-height: 1.65; padding: 48px 24px; }}
    .container {{ max-width: 800px; margin: 0 auto; }}
    h1 {{ font-size: 32px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }}
    h2 {{ font-size: 20px; font-weight: 600; color: #0f172a; margin-top: 48px; margin-bottom: 16px; }}
    .subtitle {{ color: #64748b; font-size: 15px; margin-bottom: 32px; }}
    .stats-row {{ display: flex; gap: 24px; margin-bottom: 40px; padding: 20px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap; }}
    .stat {{ text-align: center; flex: 1; min-width: 100px; }}
    .stat-value {{ font-size: 28px; font-weight: 700; color: #0f172a; }}
    .stat-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}

    .advantage-card {{ border-radius: 12px; padding: 20px 24px; margin-bottom: 32px; text-align: center; }}
    .adv-positive {{ background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #22c55e; }}
    .adv-negative {{ background: linear-gradient(135deg, #fef2f2 0%, #fecaca 100%); border: 1px solid #ef4444; }}
    .adv-neutral {{ background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%); border: 1px solid #eab308; }}
    .advantage-value {{ font-size: 36px; font-weight: 700; }}
    .adv-positive .advantage-value {{ color: #16a34a; }}
    .adv-negative .advantage-value {{ color: #dc2626; }}
    .adv-neutral .advantage-value {{ color: #ca8a04; }}
    .advantage-label {{ font-size: 13px; color: #64748b; margin-top: 4px; }}

    .helpfulness-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
    .help-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
    .help-card-title {{ font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .help-card-value {{ font-size: 24px; font-weight: 700; color: #0f172a; }}
    .help-card-sub {{ font-size: 12px; color: #94a3b8; }}

    .task-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
    .task-header {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
    .task-prompt {{ font-size: 15px; font-weight: 600; color: #0f172a; }}
    .task-duration {{ font-size: 12px; color: #94a3b8; }}
    .task-badges {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
    .task-time {{ font-size: 12px; color: #94a3b8; margin-left: auto; }}
    .task-flow {{ font-size: 13px; color: #475569; margin-bottom: 8px; padding: 8px 12px; background: #f8fafc; border-radius: 6px; }}
    .task-details {{ font-size: 12px; color: #64748b; }}
    .task-domains {{ margin-bottom: 4px; }}
    .task-patterns {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .pattern-tag {{ display: inline-block; font-size: 11px; padding: 2px 8px; background: #ede9fe; color: #7c3aed; border-radius: 4px; }}

    .session-status {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; }}
    .status-ok {{ background: #dcfce7; color: #16a34a; }}
    .status-fail {{ background: #fecaca; color: #dc2626; }}
    .agent-badge {{ font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .agent-main {{ background: #f1f5f9; color: #64748b; }}
    .agent-tdd {{ background: #ede9fe; color: #7c3aed; }}
    .agent-coder {{ background: #dbeafe; color: #2563eb; }}
    .agent-refactorer {{ background: #fef3c7; color: #d97706; }}
    .agent-researcher {{ background: #d1fae5; color: #059669; }}

    .search-only-note {{ background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px; color: #92400e; }}

    .daily-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
    .daily-row {{ display: flex; align-items: center; margin-bottom: 8px; gap: 12px; }}
    .daily-date {{ width: 60px; font-size: 13px; font-weight: 600; color: #334155; }}
    .daily-tasks {{ width: 70px; font-size: 12px; color: #64748b; }}
    .daily-bar-track {{ flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; }}
    .daily-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s ease; }}
    .daily-rate {{ width: 40px; font-size: 12px; font-weight: 600; color: #475569; text-align: right; }}
    .daily-patterns {{ width: 50px; font-size: 11px; color: #94a3b8; text-align: right; }}

    .chart-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
    .chart-title {{ font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 16px; }}
    .bar-row {{ display: flex; align-items: center; margin-bottom: 8px; }}
    .bar-label {{ width: 180px; font-size: 11px; font-family: monospace; color: #475569; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-track {{ flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; margin: 0 12px; }}
    .bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s ease; }}
    .bar-value {{ width: 32px; font-size: 12px; font-weight: 600; color: #475569; text-align: right; }}
    .bar-sessions {{ width: 32px; font-size: 11px; color: #94a3b8; text-align: right; }}

    .trends-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
    .trend-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
    .trend-label {{ font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }}
    .trend-values {{ display: flex; align-items: baseline; gap: 12px; }}
    .trend-current {{ font-size: 24px; font-weight: 700; color: #0f172a; }}
    .trend-change {{ font-size: 13px; font-weight: 600; }}
    .trend-up {{ color: #16a34a; }}
    .trend-down {{ color: #dc2626; }}
    .trend-na {{ color: #94a3b8; }}
    .trend-prev {{ font-size: 11px; color: #94a3b8; }}

    .empty {{ color: #94a3b8; font-size: 13px; padding: 12px 0; }}
    .footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }}
  </style>
</head>
<body>
<div class="container">
  <h1>ACE Insights</h1>
  <div class="subtitle">Task-level helpfulness analysis &middot; Last {hours} hours &middot; Generated {generated}</div>

  <div class="stats-row">
    <div class="stat"><div class="stat-value">{task_count}</div><div class="stat-label">Tasks</div></div>
    <div class="stat"><div class="stat-value">{success_rate}%</div><div class="stat-label">Success Rate</div></div>
    <div class="stat"><div class="stat-value">{total_injected}</div><div class="stat-label">Patterns Injected</div></div>
    <div class="stat"><div class="stat-value">{avg_conf:.0%}</div><div class="stat-label">Avg Confidence</div></div>
  </div>

  {search_note}

  <h2>Daily Summary</h2>
  <div class="daily-card">
    {daily_rows if daily_rows else '<div class="empty">No daily data yet</div>'}
  </div>

  <h2>Tasks</h2>
  {task_cards if task_cards else '<div class="empty">No tasks recorded yet</div>'}

  <h2>ACE Engagement</h2>

  <div class="advantage-card {eng_class}">
    <div class="advantage-value">{engagement["ace_coverage_pct"]}%</div>
    <div class="advantage-label">Coverage &middot; {engagement["ace_assisted_tasks"]}/{engagement["total_tasks"]} tasks ACE-assisted</div>
  </div>

  <div class="helpfulness-grid">
    <div class="help-card">
      <div class="help-card-title">Coverage</div>
      <div class="help-card-value">{engagement["ace_coverage_pct"]}%</div>
      <div class="help-card-sub">{engagement["ace_assisted_tasks"]}/{engagement["total_tasks"]} tasks</div>
    </div>
    <div class="help-card">
      <div class="help-card-title">Avg Relevance (Confidence)</div>
      <div class="help-card-value">{engagement["avg_confidence"]}%</div>
      <div class="help-card-sub">semantic match quality</div>
    </div>
    <div class="help-card">
      <div class="help-card-title">Success Rate (ACE-assisted)</div>
      <div class="help-card-value">{engagement["ace_success_rate"]}%</div>
      <div class="help-card-sub">{engagement["ace_assisted_tasks"]} ACE tasks</div>
    </div>
    <div class="help-card">
      <div class="help-card-title">Avg Patterns/Task</div>
      <div class="help-card-value">{engagement["avg_patterns_per_task"]}</div>
      <div class="help-card-sub">{engagement["avg_domains_per_task"]} avg domains</div>
    </div>
  </div>

  <h2>Top Patterns</h2>
  <div class="chart-card">
    <div class="chart-title">Most-Used Patterns (usage count &middot; sessions)</div>
    {top_patterns_rows}
  </div>

  <h2>Trends</h2>
  <div class="trends-grid">
    <div class="trend-card">
      <div class="trend-label">Searches</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('searches', 0)}</span>
        {_trend_indicator(changes.get('searches', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('searches', 0)}</div>
    </div>
    <div class="trend-card">
      <div class="trend-label">Tasks</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('tasks', 0)}</span>
        {_trend_indicator(changes.get('tasks', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('tasks', 0)}</div>
    </div>
    <div class="trend-card">
      <div class="trend-label">Success Rate</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('success_rate', 0)}%</span>
        {_trend_indicator(changes.get('success_rate', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('success_rate', 0)}%</div>
    </div>
    <div class="trend-card">
      <div class="trend-label">Patterns Injected</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('patterns_injected', 0)}</span>
        {_trend_indicator(changes.get('patterns_injected', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('patterns_injected', 0)}</div>
    </div>
  </div>

  <div class="footer">
    ACE Insights v2 &middot; Task-Level Analysis &middot; <a href="https://github.com/ce-dot-net/ace-sdk" style="color:#64748b">ace-sdk</a>
  </div>
</div>
</body>
</html>"""


def format_insights_html(
    sessions: dict,
    helpfulness: dict,
    top_patterns: list,
    trends: dict,
    hours: int = 24,
    raw_entries: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Format analysis data into a shareable interactive HTML report.

    When raw_entries is provided, renders v2 task-based layout.
    When raw_entries is None, renders legacy session-based layout.
    """
    if raw_entries is not None:
        return _format_insights_html_v2(
            helpfulness, top_patterns, trends, raw_entries, hours=hours,
        )

    total = sessions.get("total_sessions", 0)
    active = sessions.get("active_sessions", 0)
    tasks_with = helpfulness.get("tasks_with_patterns", 0)
    tasks_without = helpfulness.get("tasks_without_patterns", 0)
    rate_with = helpfulness.get("success_rate_with_patterns", 0)
    rate_without = helpfulness.get("success_rate_without_patterns", 0)
    advantage = helpfulness.get("pattern_advantage", 0)
    avg_conf = helpfulness.get("avg_confidence", 0)
    avg_ppt = helpfulness.get("avg_patterns_per_task", 0)
    curr = trends.get("current_period", {})
    prev = trends.get("previous_period", {})
    changes = trends.get("changes", {})

    # Build session rows
    session_rows = ""
    for s in sessions.get("sessions", []):
        if s.get("success") is True:
            status_class = "status-ok"
            status_text = "OK"
        elif s.get("success") is False:
            status_class = "status-fail"
            status_text = "FAIL"
        else:
            status_class = "status-pending"
            status_text = "---"

        dur = s.get("duration_seconds", 0)
        dur_str = _format_duration(dur) if dur > 0 else "&lt; 1m"
        prompts = ", ".join(_html_escape(p)[:80] for p in s.get("user_prompts", [])[:2])
        if not prompts:
            prompts = "<em>No prompt recorded</em>"
        domains = ", ".join(_html_escape(d) for d in s.get("domains", []))
        if not domains:
            domains = "none"
        pi = s.get("patterns_injected", 0)
        pu = s.get("patterns_used", 0)
        te = s.get("tools_executed", 0)
        lr = "Yes" if s.get("learning_sent") else "No"

        agent_type = _html_escape(s.get('agent_type', 'main'))
        agent_badge = f'<span class="agent-badge agent-{agent_type}">{agent_type}</span>' if agent_type != 'main' else '<span class="agent-badge agent-main">main</span>'

        session_rows += f"""
        <div class="session-card">
          <div class="session-header">
            <span class="session-status {status_class}">{status_text}</span>
            {agent_badge}
            <span class="session-id">{_html_escape(s['session_id'][:16])}...</span>
            <span class="session-duration">{dur_str}</span>
          </div>
          <div class="session-task">{prompts}</div>
          <div class="session-metrics">
            <span>Patterns: {pi} injected, {pu} used</span>
            <span>Tools: {te}</span>
            <span>Domains: {domains}</span>
            <span>Learning: {lr}</span>
          </div>
        </div>"""

    # Build top patterns rows
    top_patterns_rows = ""
    if top_patterns:
        max_usage = top_patterns[0]["usage_count"] if top_patterns else 1
        for p in top_patterns[:10]:
            pct = int(p["usage_count"] / max_usage * 100) if max_usage else 0
            name = p.get("pattern_name", p["pattern_id"][:20])
            top_patterns_rows += f"""
            <div class="bar-row">
              <span class="bar-label">{_html_escape(name)}</span>
              <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:#6366f1"></div></div>
              <span class="bar-value">{p['usage_count']}x</span>
              <span class="bar-sessions">{p['sessions']}s</span>
            </div>"""
    else:
        top_patterns_rows = '<div class="empty">No pattern usage data yet</div>'

    # Build trend cards
    def _trend_indicator(change_str):
        if change_str == "N/A":
            return '<span class="trend-na">N/A</span>'
        elif change_str.startswith("+"):
            return f'<span class="trend-up">{_html_escape(change_str)}</span>'
        elif change_str.startswith("-"):
            return f'<span class="trend-down">{_html_escape(change_str)}</span>'
        return f'<span>{_html_escape(change_str)}</span>'

    # Advantage indicator
    if advantage > 10:
        adv_class = "adv-positive"
        adv_emoji = "Strong positive impact"
    elif advantage > 0:
        adv_class = "adv-positive"
        adv_emoji = "Positive impact"
    elif advantage == 0:
        adv_class = "adv-neutral"
        adv_emoji = "Neutral"
    else:
        adv_class = "adv-negative"
        adv_emoji = "Needs improvement"

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ACE Insights</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; color: #334155; line-height: 1.65; padding: 48px 24px; }}
    .container {{ max-width: 800px; margin: 0 auto; }}
    h1 {{ font-size: 32px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }}
    h2 {{ font-size: 20px; font-weight: 600; color: #0f172a; margin-top: 48px; margin-bottom: 16px; }}
    .subtitle {{ color: #64748b; font-size: 15px; margin-bottom: 32px; }}
    .stats-row {{ display: flex; gap: 24px; margin-bottom: 40px; padding: 20px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; flex-wrap: wrap; }}
    .stat {{ text-align: center; flex: 1; min-width: 100px; }}
    .stat-value {{ font-size: 28px; font-weight: 700; color: #0f172a; }}
    .stat-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}

    .at-a-glance {{ background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 1px solid #3b82f6; border-radius: 12px; padding: 20px 24px; margin-bottom: 32px; }}
    .glance-title {{ font-size: 16px; font-weight: 700; color: #1e40af; margin-bottom: 12px; }}
    .glance-text {{ font-size: 14px; color: #1e3a5f; line-height: 1.7; }}
    .glance-text strong {{ color: #1e40af; }}

    .advantage-card {{ border-radius: 12px; padding: 20px 24px; margin-bottom: 32px; text-align: center; }}
    .adv-positive {{ background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #22c55e; }}
    .adv-negative {{ background: linear-gradient(135deg, #fef2f2 0%, #fecaca 100%); border: 1px solid #ef4444; }}
    .adv-neutral {{ background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%); border: 1px solid #eab308; }}
    .advantage-value {{ font-size: 36px; font-weight: 700; }}
    .adv-positive .advantage-value {{ color: #16a34a; }}
    .adv-negative .advantage-value {{ color: #dc2626; }}
    .adv-neutral .advantage-value {{ color: #ca8a04; }}
    .advantage-label {{ font-size: 13px; color: #64748b; margin-top: 4px; }}

    .helpfulness-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
    .help-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
    .help-card-title {{ font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }}
    .help-card-value {{ font-size: 24px; font-weight: 700; color: #0f172a; }}
    .help-card-sub {{ font-size: 12px; color: #94a3b8; }}

    .session-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
    .session-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
    .session-status {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; }}
    .status-ok {{ background: #dcfce7; color: #16a34a; }}
    .status-fail {{ background: #fecaca; color: #dc2626; }}
    .status-pending {{ background: #f1f5f9; color: #94a3b8; }}
    .agent-badge {{ font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .agent-main {{ background: #f1f5f9; color: #64748b; }}
    .agent-tdd {{ background: #ede9fe; color: #7c3aed; }}
    .agent-coder {{ background: #dbeafe; color: #2563eb; }}
    .agent-refactorer {{ background: #fef3c7; color: #d97706; }}
    .agent-researcher {{ background: #d1fae5; color: #059669; }}
    .session-id {{ font-size: 13px; font-family: monospace; color: #64748b; }}
    .session-duration {{ font-size: 12px; color: #94a3b8; margin-left: auto; }}
    .session-task {{ font-size: 14px; color: #334155; margin-bottom: 8px; font-weight: 500; }}
    .session-metrics {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: #64748b; }}

    .chart-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
    .chart-title {{ font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 16px; }}
    .bar-row {{ display: flex; align-items: center; margin-bottom: 8px; }}
    .bar-label {{ width: 150px; font-size: 11px; font-family: monospace; color: #475569; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-track {{ flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; margin: 0 12px; }}
    .bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s ease; }}
    .bar-value {{ width: 32px; font-size: 12px; font-weight: 600; color: #475569; text-align: right; }}
    .bar-sessions {{ width: 32px; font-size: 11px; color: #94a3b8; text-align: right; }}

    .trends-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
    .trend-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
    .trend-label {{ font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }}
    .trend-values {{ display: flex; align-items: baseline; gap: 12px; }}
    .trend-current {{ font-size: 24px; font-weight: 700; color: #0f172a; }}
    .trend-change {{ font-size: 13px; font-weight: 600; }}
    .trend-up {{ color: #16a34a; }}
    .trend-down {{ color: #dc2626; }}
    .trend-na {{ color: #94a3b8; }}
    .trend-prev {{ font-size: 11px; color: #94a3b8; }}

    .empty {{ color: #94a3b8; font-size: 13px; padding: 12px 0; }}
    .footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; }}
  </style>
</head>
<body>
<div class="container">
  <h1>ACE Insights</h1>
  <div class="subtitle">Pattern relevance &amp; helpfulness analysis &middot; Last {hours} hours &middot; Generated {generated}</div>

  <div class="stats-row">
    <div class="stat"><div class="stat-value">{total}</div><div class="stat-label">Sessions</div></div>
    <div class="stat"><div class="stat-value">{active}</div><div class="stat-label">Active Tasks</div></div>
    <div class="stat"><div class="stat-value">{tasks_with + tasks_without}</div><div class="stat-label">Executions</div></div>
    <div class="stat"><div class="stat-value">{curr.get('patterns_injected', 0)}</div><div class="stat-label">Patterns Injected</div></div>
    <div class="stat"><div class="stat-value">{avg_conf:.0%}</div><div class="stat-label">Avg Confidence</div></div>
  </div>

  <div class="at-a-glance">
    <div class="glance-title">At a Glance</div>
    <div class="glance-text">
      Across <strong>{total} session{"s" if total != 1 else ""}</strong>, ACE injected patterns into
      <strong>{tasks_with} task{"s" if tasks_with != 1 else ""}</strong> with a
      <strong>{rate_with}%</strong> success rate.
      {"Tasks <em>without</em> patterns had a <strong>" + str(rate_without) + "%</strong> success rate." if tasks_without > 0 else ""}
      {"The <strong>pattern advantage</strong> is <strong>" + ("+" if advantage >= 0 else "") + str(advantage) + "pp</strong>." if tasks_with > 0 and tasks_without > 0 else ""}
    </div>
  </div>

  <h2>Pattern Helpfulness</h2>

  <div class="advantage-card {adv_class}">
    <div class="advantage-value">{"+" if advantage >= 0 else ""}{advantage}pp</div>
    <div class="advantage-label">Pattern Advantage &middot; {adv_emoji}</div>
  </div>

  <div class="helpfulness-grid">
    <div class="help-card">
      <div class="help-card-title">With Patterns</div>
      <div class="help-card-value">{rate_with}%</div>
      <div class="help-card-sub">{tasks_with} task{"s" if tasks_with != 1 else ""} &middot; avg {avg_ppt} patterns/task</div>
    </div>
    <div class="help-card">
      <div class="help-card-title">Without Patterns</div>
      <div class="help-card-value">{rate_without}%</div>
      <div class="help-card-sub">{tasks_without} task{"s" if tasks_without != 1 else ""}</div>
    </div>
  </div>

  <h2>Sessions</h2>
  {session_rows if session_rows else '<div class="empty">No sessions recorded yet</div>'}

  <h2>Top Patterns</h2>
  <div class="chart-card">
    <div class="chart-title">Most-Used Pattern IDs (usage count &middot; sessions)</div>
    {top_patterns_rows}
  </div>

  <h2>Trends</h2>
  <div class="trends-grid">
    <div class="trend-card">
      <div class="trend-label">Searches</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('searches', 0)}</span>
        {_trend_indicator(changes.get('searches', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('searches', 0)}</div>
    </div>
    <div class="trend-card">
      <div class="trend-label">Tasks</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('tasks', 0)}</span>
        {_trend_indicator(changes.get('tasks', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('tasks', 0)}</div>
    </div>
    <div class="trend-card">
      <div class="trend-label">Success Rate</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('success_rate', 0)}%</span>
        {_trend_indicator(changes.get('success_rate', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('success_rate', 0)}%</div>
    </div>
    <div class="trend-card">
      <div class="trend-label">Patterns Injected</div>
      <div class="trend-values">
        <span class="trend-current">{curr.get('patterns_injected', 0)}</span>
        {_trend_indicator(changes.get('patterns_injected', 'N/A'))}
      </div>
      <div class="trend-prev">Previous: {prev.get('patterns_injected', 0)}</div>
    </div>
  </div>

  <div class="footer">
    ACE Insights &middot; Generated by ACE Plugin v5.4.30 &middot; <a href="https://github.com/ce-dot-net/ace-sdk" style="color:#64748b">ace-sdk</a>
  </div>
</div>
</body>
</html>"""
