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


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 timestamp string to datetime (UTC)."""
    # Handle Z suffix
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str).astimezone(timezone.utc)


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

        # Execution metrics (use last execution if multiple)
        has_execution = len(executions) > 0
        if has_execution:
            active_count += 1
            last_exec = executions[-1]
            patterns_used = last_exec.get("patterns_used_count", 0)
            tools_executed = last_exec.get("tools_executed", 0)
            success = last_exec.get("success", False)
            learning_sent = last_exec.get("learning_sent", False)
        else:
            patterns_used = 0
            tools_executed = 0
            success = None
            learning_sent = False

        sessions.append({
            "session_id": sid,
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
        List of dicts with pattern_id, usage_count, sessions (unique session count)
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

    result = [
        {
            "pattern_id": pid,
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
            dur_str = f"{duration // 60}m {duration % 60}s" if duration > 0 else "< 1m"
            prompts = ", ".join(s.get("user_prompts", [])[:2])
            if len(s.get("user_prompts", [])) > 2:
                prompts += "..."

            lines.append(f"  [{status}] {s['session_id'][:12]}... ({dur_str})")
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


def format_insights_html(
    sessions: dict,
    helpfulness: dict,
    top_patterns: list,
    trends: dict,
    hours: int = 24,
) -> str:
    """
    Format analysis data into a shareable interactive HTML report.

    Styled to match Claude Code's /insights report aesthetic.
    """
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
        dur_str = f"{dur // 60}m {dur % 60}s" if dur > 0 else "&lt; 1m"
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

        session_rows += f"""
        <div class="session-card">
          <div class="session-header">
            <span class="session-status {status_class}">{status_text}</span>
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
        for i, p in enumerate(top_patterns[:10], 1):
            pct = int(p["usage_count"] / max_usage * 100) if max_usage else 0
            top_patterns_rows += f"""
            <div class="bar-row">
              <span class="bar-label">{_html_escape(p['pattern_id'][:20])}</span>
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
