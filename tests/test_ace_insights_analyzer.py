#!/usr/bin/env python3
"""
TDD RED Phase: Tests for ACE Insights Analyzer.

Tests the session-level analysis module at:
  plugins/ace/shared-hooks/utils/ace_insights_analyzer.py

The module analyses ACE relevance data logged to:
  .claude/data/logs/ace-relevance.jsonl

Three event types are logged:
  - search   (UserPromptSubmit hook)
  - domain_shift (PreToolUse hook)
  - execution (Stop hook)

Functions under test:
  1. analyze_sessions(entries, hours=24) -> dict
  2. calculate_helpfulness(entries) -> dict
  3. get_top_patterns(entries, limit=10) -> list
  4. calculate_trends(entries, current_hours=24, previous_hours=24) -> dict
  5. format_insights_report(sessions, helpfulness, top_patterns, trends) -> str

Run with: pytest tests/test_ace_insights_analyzer.py -v
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

# ---------------------------------------------------------------------------
# Path setup -- the utils directory has no __init__.py
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "ace" / "shared-hooks"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "ace" / "shared-hooks" / "utils"))

from ace_insights_analyzer import (
    analyze_sessions,
    calculate_helpfulness,
    compute_ace_engagement,
    extract_task_data_for_evaluation,
    generate_evaluated_html,
    get_top_patterns,
    calculate_trends,
    format_insights_report,
    format_insights_html,
    deduplicate_events,
    extract_pattern_names,
    split_into_tasks,
)


# =========================================================================
# Fixtures -- realistic JSONL entries matching ACERelevanceLogger output
# =========================================================================

def _ts(dt: datetime) -> str:
    """Format a datetime as an ISO-8601 UTC string (matching logger output)."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture
def now():
    """A fixed 'now' for deterministic time-window tests."""
    return datetime(2026, 1, 15, 16, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def session_a_search(now):
    """A single search event for session A."""
    return {
        "timestamp": _ts(now - timedelta(minutes=14)),
        "event": "search",
        "hook": "UserPromptSubmit",
        "session_id": "ses-aaa-111",
        "project_id": "prj_abc",
        "org_id": "org_xyz",
        "user_prompt": "Fix the auth bug",
        "search_query": "fix auth bug",
        "patterns_returned": 19,
        "patterns_injected": 12,
        "patterns_filtered": 7,
        "avg_confidence": 0.845,
        "domains": ["auth", "api"],
        "top_patterns": [
            {"id": "ctx-123", "confidence": 0.95, "helpful": 10, "harmful": 1, "domain": "auth", "section": "strategies"},
            {"id": "ctx-456", "confidence": 0.82, "helpful": 6, "harmful": 0, "domain": "api", "section": "patterns"},
        ],
    }


@pytest.fixture
def session_a_domain_shift(now):
    """A domain_shift event for session A."""
    return {
        "timestamp": _ts(now - timedelta(minutes=10)),
        "event": "domain_shift",
        "hook": "PreToolUse",
        "session_id": "ses-aaa-111",
        "project_id": "prj_abc",
        "from_domain": "auth",
        "to_domain": "cache",
        "file_path": "src/cache/redis.ts",
        "patterns_found": 5,
        "search_succeeded": True,
    }


@pytest.fixture
def session_a_execution(now):
    """An execution event for session A (success)."""
    return {
        "timestamp": _ts(now),
        "event": "execution",
        "hook": "Stop",
        "session_id": "ses-aaa-111",
        "project_id": "prj_abc",
        "patterns_used_count": 8,
        "pattern_ids": ["ctx-123", "ctx-456", "ctx-789", "ctx-100", "ctx-101", "ctx-102", "ctx-103", "ctx-104"],
        "tools_executed": 27,
        "state_changing_tools": 15,
        "success": True,
        "execution_time_seconds": 45.2,
        "learning_sent": True,
    }


@pytest.fixture
def session_a_full(session_a_search, session_a_domain_shift, session_a_execution):
    """All 3 event types for session A."""
    return [session_a_search, session_a_domain_shift, session_a_execution]


@pytest.fixture
def session_b_search_only(now):
    """Session B: only a search event (no execution -- not 'active')."""
    return [
        {
            "timestamp": _ts(now - timedelta(minutes=5)),
            "event": "search",
            "hook": "UserPromptSubmit",
            "session_id": "ses-bbb-222",
            "project_id": "prj_abc",
            "org_id": "org_xyz",
            "user_prompt": "Explain the caching layer",
            "search_query": "caching layer explanation",
            "patterns_returned": 10,
            "patterns_injected": 6,
            "patterns_filtered": 4,
            "avg_confidence": 0.72,
            "domains": ["cache"],
            "top_patterns": [
                {"id": "ctx-200", "confidence": 0.78, "helpful": 3, "harmful": 0, "domain": "cache", "section": "overview"},
            ],
        }
    ]


@pytest.fixture
def session_c_failed_execution(now):
    """Session C: a search + failed execution (success=False, no patterns)."""
    return [
        {
            "timestamp": _ts(now - timedelta(minutes=20)),
            "event": "search",
            "hook": "UserPromptSubmit",
            "session_id": "ses-ccc-333",
            "project_id": "prj_abc",
            "org_id": "org_xyz",
            "user_prompt": "Deploy to production",
            "search_query": "deploy production",
            "patterns_returned": 2,
            "patterns_injected": 0,
            "patterns_filtered": 2,
            "avg_confidence": 0.0,
            "domains": [],
            "top_patterns": [],
        },
        {
            "timestamp": _ts(now - timedelta(minutes=15)),
            "event": "execution",
            "hook": "Stop",
            "session_id": "ses-ccc-333",
            "project_id": "prj_abc",
            "patterns_used_count": 0,
            "pattern_ids": [],
            "tools_executed": 5,
            "state_changing_tools": 2,
            "success": False,
            "execution_time_seconds": 12.0,
            "learning_sent": False,
        },
    ]


@pytest.fixture
def session_d_multiple_searches(now):
    """Session D: two searches with duplicate prompts, one execution."""
    return [
        {
            "timestamp": _ts(now - timedelta(minutes=30)),
            "event": "search",
            "hook": "UserPromptSubmit",
            "session_id": "ses-ddd-444",
            "project_id": "prj_def",
            "org_id": "org_xyz",
            "user_prompt": "Add rate limiting",
            "search_query": "add rate limiting",
            "patterns_returned": 15,
            "patterns_injected": 10,
            "patterns_filtered": 5,
            "avg_confidence": 0.88,
            "domains": ["api", "middleware"],
            "top_patterns": [
                {"id": "ctx-300", "confidence": 0.92, "helpful": 8, "harmful": 0, "domain": "api", "section": "strategies"},
            ],
        },
        {
            "timestamp": _ts(now - timedelta(minutes=25)),
            "event": "search",
            "hook": "UserPromptSubmit",
            "session_id": "ses-ddd-444",
            "project_id": "prj_def",
            "org_id": "org_xyz",
            "user_prompt": "Add rate limiting",  # duplicate prompt
            "search_query": "rate limiting middleware",
            "patterns_returned": 8,
            "patterns_injected": 5,
            "patterns_filtered": 3,
            "avg_confidence": 0.80,
            "domains": ["middleware"],
            "top_patterns": [
                {"id": "ctx-123", "confidence": 0.85, "helpful": 10, "harmful": 1, "domain": "middleware", "section": "patterns"},
            ],
        },
        {
            "timestamp": _ts(now - timedelta(minutes=20)),
            "event": "execution",
            "hook": "Stop",
            "session_id": "ses-ddd-444",
            "project_id": "prj_def",
            "patterns_used_count": 6,
            "pattern_ids": ["ctx-300", "ctx-123", "ctx-301", "ctx-302", "ctx-303", "ctx-304"],
            "tools_executed": 18,
            "state_changing_tools": 10,
            "success": True,
            "execution_time_seconds": 60.5,
            "learning_sent": True,
        },
    ]


@pytest.fixture
def all_sessions(session_a_full, session_b_search_only, session_c_failed_execution, session_d_multiple_searches):
    """All entries from sessions A, B, C, D combined."""
    return session_a_full + session_b_search_only + session_c_failed_execution + session_d_multiple_searches


# -- Previous-period fixtures (for trend tests) --

@pytest.fixture
def previous_period_entries(now):
    """Entries from 24-48 hours ago (previous period for trend comparison)."""
    prev_base = now - timedelta(hours=36)
    return [
        {
            "timestamp": _ts(prev_base),
            "event": "search",
            "hook": "UserPromptSubmit",
            "session_id": "ses-prev-001",
            "project_id": "prj_abc",
            "org_id": "org_xyz",
            "user_prompt": "Refactor database module",
            "search_query": "refactor database",
            "patterns_returned": 12,
            "patterns_injected": 8,
            "patterns_filtered": 4,
            "avg_confidence": 0.75,
            "domains": ["database"],
            "top_patterns": [],
        },
        {
            "timestamp": _ts(prev_base + timedelta(minutes=30)),
            "event": "execution",
            "hook": "Stop",
            "session_id": "ses-prev-001",
            "project_id": "prj_abc",
            "patterns_used_count": 4,
            "pattern_ids": ["ctx-old-1", "ctx-old-2", "ctx-old-3", "ctx-old-4"],
            "tools_executed": 20,
            "state_changing_tools": 12,
            "success": True,
            "execution_time_seconds": 55.0,
            "learning_sent": True,
        },
        {
            "timestamp": _ts(prev_base + timedelta(hours=2)),
            "event": "search",
            "hook": "UserPromptSubmit",
            "session_id": "ses-prev-002",
            "project_id": "prj_abc",
            "org_id": "org_xyz",
            "user_prompt": "Update CI pipeline",
            "search_query": "update CI pipeline",
            "patterns_returned": 6,
            "patterns_injected": 3,
            "patterns_filtered": 3,
            "avg_confidence": 0.65,
            "domains": ["devops"],
            "top_patterns": [],
        },
        {
            "timestamp": _ts(prev_base + timedelta(hours=3)),
            "event": "execution",
            "hook": "Stop",
            "session_id": "ses-prev-002",
            "project_id": "prj_abc",
            "patterns_used_count": 2,
            "pattern_ids": ["ctx-old-5", "ctx-old-6"],
            "tools_executed": 14,
            "state_changing_tools": 8,
            "success": False,
            "execution_time_seconds": 30.0,
            "learning_sent": False,
        },
    ]


# =========================================================================
# 1. analyze_sessions() tests
# =========================================================================

class TestAnalyzeSessions:
    """Tests for analyze_sessions(entries, hours=24) -> dict."""

    def test_single_session_all_event_types(self, session_a_full):
        """A session with search + domain_shift + execution produces a complete summary."""
        result = analyze_sessions(session_a_full)

        assert result["total_sessions"] == 1
        assert result["active_sessions"] == 1

        session = result["sessions"][0]
        assert session["session_id"] == "ses-aaa-111"
        assert session["searches"] == 1
        assert session["patterns_injected"] == 12
        assert session["patterns_used"] == 8
        assert session["domain_shifts"] == 1
        assert session["tools_executed"] == 27
        assert session["success"] is True
        assert session["learning_sent"] is True
        assert "auth" in session["domains"]
        assert "cache" in session["domains"]
        assert "Fix the auth bug" in session["user_prompts"]

    def test_multiple_sessions_grouped_correctly(self, all_sessions):
        """Entries from different session_ids are grouped into separate sessions."""
        result = analyze_sessions(all_sessions)

        assert result["total_sessions"] == 4
        session_ids = {s["session_id"] for s in result["sessions"]}
        assert session_ids == {"ses-aaa-111", "ses-bbb-222", "ses-ccc-333", "ses-ddd-444"}

    def test_search_only_session_not_active(self, session_b_search_only):
        """A session with only search events (no execution) is not counted as active."""
        result = analyze_sessions(session_b_search_only)

        assert result["total_sessions"] == 1
        assert result["active_sessions"] == 0

        session = result["sessions"][0]
        assert session["searches"] == 1
        assert session["patterns_used"] == 0
        assert session["tools_executed"] == 0
        assert session["success"] is None  # or False -- no execution happened

    def test_active_sessions_count(self, all_sessions):
        """active_sessions counts only sessions that have at least one execution event."""
        result = analyze_sessions(all_sessions)
        # sessions A, C, D have execution events; B does not
        assert result["active_sessions"] == 3

    def test_empty_entries(self):
        """An empty entries list returns zeros and an empty sessions list."""
        result = analyze_sessions([])

        assert result["sessions"] == []
        assert result["total_sessions"] == 0
        assert result["active_sessions"] == 0

    def test_session_duration_calculated(self, session_a_full):
        """Duration is the difference between earliest and latest timestamps in the session."""
        result = analyze_sessions(session_a_full)
        session = result["sessions"][0]

        assert session["start_time"] is not None
        assert session["end_time"] is not None
        assert session["duration_seconds"] > 0
        # Session A spans 14 minutes = 840 seconds
        assert session["duration_seconds"] == 840

    def test_user_prompts_collected_and_deduplicated(self, session_d_multiple_searches):
        """user_prompts are collected from search events, deduplicated."""
        result = analyze_sessions(session_d_multiple_searches)
        session = result["sessions"][0]

        # "Add rate limiting" appears in two search events but should only appear once
        assert session["user_prompts"] == ["Add rate limiting"]

    def test_user_prompts_truncated(self):
        """Very long user prompts are truncated in the session summary."""
        long_prompt = "A" * 500
        entries = [
            {
                "timestamp": "2026-01-15T15:46:45Z",
                "event": "search",
                "hook": "UserPromptSubmit",
                "session_id": "ses-long",
                "project_id": "prj_abc",
                "user_prompt": long_prompt,
                "search_query": "aaa",
                "patterns_returned": 1,
                "patterns_injected": 1,
                "patterns_filtered": 0,
                "avg_confidence": 0.5,
                "domains": [],
                "top_patterns": [],
            }
        ]
        result = analyze_sessions(entries)
        session = result["sessions"][0]
        # Prompts should be truncated to a reasonable length (200 chars as per logger convention)
        assert all(len(p) <= 200 for p in session["user_prompts"])

    def test_domains_merged_across_events(self, session_a_full):
        """Domains from search events and domain_shift to_domain are merged."""
        result = analyze_sessions(session_a_full)
        session = result["sessions"][0]
        # search has ["auth", "api"], domain_shift adds "cache"
        assert set(session["domains"]) >= {"auth", "api", "cache"}

    def test_patterns_injected_summed_across_searches(self, session_d_multiple_searches):
        """patterns_injected is the sum across all search events in the session."""
        result = analyze_sessions(session_d_multiple_searches)
        session = result["sessions"][0]
        # First search: 10, second search: 5
        assert session["patterns_injected"] == 15


# =========================================================================
# 2. calculate_helpfulness() tests
# =========================================================================

class TestCalculateHelpfulness:
    """Tests for calculate_helpfulness(entries) -> dict."""

    def test_mix_of_with_and_without_patterns(self, all_sessions):
        """Sessions with patterns vs without, mixed success."""
        result = calculate_helpfulness(all_sessions)

        # Session A: 8 patterns, success=True
        # Session C: 0 patterns, success=False
        # Session D: 6 patterns, success=True
        # Session B: no execution event at all (not counted as a task)
        assert result["tasks_with_patterns"] == 2
        assert result["tasks_without_patterns"] == 1
        assert result["success_rate_with_patterns"] == 100.0  # 2/2 = 100%
        assert result["success_rate_without_patterns"] == 0.0   # 0/1 = 0%
        assert result["pattern_advantage"] == 100.0

    def test_all_tasks_have_patterns(self, session_a_full, session_d_multiple_searches):
        """When all tasks have patterns, tasks_without_patterns is 0 and that rate is N/A."""
        entries = session_a_full + session_d_multiple_searches
        result = calculate_helpfulness(entries)

        assert result["tasks_with_patterns"] == 2
        assert result["tasks_without_patterns"] == 0
        # success_rate_without_patterns should be 0 or some sentinel indicating N/A
        # pattern_advantage should handle this gracefully
        assert isinstance(result["success_rate_with_patterns"], (int, float))

    def test_no_execution_events(self, session_b_search_only):
        """When there are no execution events, everything should be zero."""
        result = calculate_helpfulness(session_b_search_only)

        assert result["tasks_with_patterns"] == 0
        assert result["tasks_without_patterns"] == 0
        assert result["success_rate_with_patterns"] == 0
        assert result["success_rate_without_patterns"] == 0
        assert result["pattern_advantage"] == 0

    def test_equal_success_rate_zero_advantage(self):
        """When success rates are equal, pattern_advantage is 0."""
        entries = [
            # Task 1: with patterns, success
            {
                "timestamp": "2026-01-15T15:00:00Z", "event": "execution", "hook": "Stop",
                "session_id": "ses-eq-1", "project_id": "prj_x",
                "patterns_used_count": 3, "pattern_ids": ["ctx-1", "ctx-2", "ctx-3"],
                "tools_executed": 10, "state_changing_tools": 5,
                "success": True, "execution_time_seconds": 20.0, "learning_sent": True,
            },
            # Task 2: without patterns, success
            {
                "timestamp": "2026-01-15T15:30:00Z", "event": "execution", "hook": "Stop",
                "session_id": "ses-eq-2", "project_id": "prj_x",
                "patterns_used_count": 0, "pattern_ids": [],
                "tools_executed": 8, "state_changing_tools": 4,
                "success": True, "execution_time_seconds": 15.0, "learning_sent": False,
            },
        ]
        result = calculate_helpfulness(entries)

        assert result["tasks_with_patterns"] == 1
        assert result["tasks_without_patterns"] == 1
        assert result["success_rate_with_patterns"] == 100.0
        assert result["success_rate_without_patterns"] == 100.0
        assert result["pattern_advantage"] == 0.0

    def test_avg_patterns_per_task(self, all_sessions):
        """avg_patterns_per_task is the mean of patterns_used_count across tasks with patterns."""
        result = calculate_helpfulness(all_sessions)

        # Tasks with patterns: A (8 patterns), D (6 patterns) => avg = 7.0
        assert result["avg_patterns_per_task"] == 7.0

    def test_avg_confidence_across_searches(self, all_sessions):
        """avg_confidence is computed from search events that fed into tasks."""
        result = calculate_helpfulness(all_sessions)
        assert isinstance(result["avg_confidence"], float)
        assert 0.0 <= result["avg_confidence"] <= 1.0


# =========================================================================
# 3. get_top_patterns() tests
# =========================================================================

class TestGetTopPatterns:
    """Tests for get_top_patterns(entries, limit=10) -> list."""

    def test_patterns_counted_across_executions(self, all_sessions):
        """A pattern_id referenced in multiple executions has its usage_count summed."""
        result = get_top_patterns(all_sessions)

        # ctx-123 appears in session A execution AND session D execution
        ctx_123 = next((p for p in result if p["pattern_id"] == "ctx-123"), None)
        assert ctx_123 is not None
        assert ctx_123["usage_count"] == 2

    def test_sessions_count_unique(self, all_sessions):
        """sessions field counts unique sessions, not total references."""
        result = get_top_patterns(all_sessions)

        ctx_123 = next((p for p in result if p["pattern_id"] == "ctx-123"), None)
        assert ctx_123 is not None
        assert ctx_123["sessions"] == 2  # appears in ses-aaa-111 and ses-ddd-444

    def test_limit_parameter(self, all_sessions):
        """The limit parameter caps the number of returned patterns."""
        result = get_top_patterns(all_sessions, limit=3)
        assert len(result) <= 3

    def test_sorted_by_usage_count_descending(self, all_sessions):
        """Results are sorted by usage_count in descending order."""
        result = get_top_patterns(all_sessions)

        for i in range(len(result) - 1):
            assert result[i]["usage_count"] >= result[i + 1]["usage_count"]

    def test_empty_pattern_ids_handled(self):
        """Execution events with empty pattern_ids don't cause errors."""
        entries = [
            {
                "timestamp": "2026-01-15T16:00:00Z", "event": "execution", "hook": "Stop",
                "session_id": "ses-empty", "project_id": "prj_x",
                "patterns_used_count": 0, "pattern_ids": [],
                "tools_executed": 3, "state_changing_tools": 1,
                "success": True, "execution_time_seconds": 5.0, "learning_sent": False,
            },
        ]
        result = get_top_patterns(entries)
        assert result == []

    def test_no_execution_events(self, session_b_search_only):
        """When there are no execution events, an empty list is returned."""
        result = get_top_patterns(session_b_search_only)
        assert result == []

    def test_single_execution_single_pattern(self):
        """A single execution referencing one pattern returns that pattern."""
        entries = [
            {
                "timestamp": "2026-01-15T16:00:00Z", "event": "execution", "hook": "Stop",
                "session_id": "ses-single", "project_id": "prj_x",
                "patterns_used_count": 1, "pattern_ids": ["ctx-solo"],
                "tools_executed": 5, "state_changing_tools": 2,
                "success": True, "execution_time_seconds": 10.0, "learning_sent": True,
            },
        ]
        result = get_top_patterns(entries, limit=10)
        assert len(result) == 1
        assert result[0]["pattern_id"] == "ctx-solo"
        assert result[0]["usage_count"] == 1
        assert result[0]["sessions"] == 1

    def test_default_limit_is_ten(self):
        """Without specifying limit, at most 10 patterns are returned."""
        # Create 15 unique patterns across execution events
        entries = [
            {
                "timestamp": "2026-01-15T16:00:00Z", "event": "execution", "hook": "Stop",
                "session_id": f"ses-many-{i}", "project_id": "prj_x",
                "patterns_used_count": 1, "pattern_ids": [f"ctx-many-{i}"],
                "tools_executed": 5, "state_changing_tools": 2,
                "success": True, "execution_time_seconds": 10.0, "learning_sent": True,
            }
            for i in range(15)
        ]
        result = get_top_patterns(entries)
        assert len(result) <= 10


# =========================================================================
# 4. calculate_trends() tests
# =========================================================================

class TestCalculateTrends:
    """Tests for calculate_trends(entries, current_hours=24, previous_hours=24) -> dict."""

    def test_both_periods_have_data(self, all_sessions, previous_period_entries, now):
        """When both periods have data, percentage changes are calculated."""
        combined = all_sessions + previous_period_entries
        result = calculate_trends(combined, current_hours=24, previous_hours=24, reference_time=now)

        assert "current_period" in result
        assert "previous_period" in result
        assert "changes" in result

        # Current period should have data from all_sessions
        assert result["current_period"]["searches"] > 0
        assert result["current_period"]["tasks"] > 0

        # Previous period should have data from previous_period_entries
        assert result["previous_period"]["searches"] > 0
        assert result["previous_period"]["tasks"] > 0

        # Changes should be calculated
        assert "searches" in result["changes"]
        assert "tasks" in result["changes"]
        assert "success_rate" in result["changes"]
        assert "patterns_injected" in result["changes"]

    def test_previous_period_empty(self):
        """When the previous period has no data, changes should show 'N/A'."""
        current_entries = [
            {
                "timestamp": _ts(datetime.now(timezone.utc) - timedelta(hours=1)),
                "event": "search", "hook": "UserPromptSubmit",
                "session_id": "ses-curr", "project_id": "prj_x", "org_id": "org_x",
                "user_prompt": "test", "search_query": "test",
                "patterns_returned": 5, "patterns_injected": 3, "patterns_filtered": 2,
                "avg_confidence": 0.7, "domains": ["test"], "top_patterns": [],
            },
        ]
        result = calculate_trends(current_entries, current_hours=24, previous_hours=24)

        assert result["previous_period"]["searches"] == 0
        assert result["changes"]["searches"] == "N/A"
        assert result["changes"]["tasks"] == "N/A"

    def test_current_period_empty(self, previous_period_entries):
        """When the current period has no data, current metrics are all zero."""
        # Use entries only from the previous period (36+ hours ago)
        result = calculate_trends(previous_period_entries, current_hours=24, previous_hours=24)

        assert result["current_period"]["searches"] == 0
        assert result["current_period"]["tasks"] == 0
        assert result["current_period"]["success_rate"] == 0.0
        assert result["current_period"]["patterns_injected"] == 0

    def test_decrease_shown_as_negative(self):
        """Decreases in metrics should be shown as negative percentages."""
        now_ts = datetime.now(timezone.utc)
        # Current period: 1 search
        # Previous period: 3 searches
        entries = [
            # Current: 1 search
            {
                "timestamp": _ts(now_ts - timedelta(hours=2)),
                "event": "search", "hook": "UserPromptSubmit",
                "session_id": "ses-dec-1", "project_id": "prj_x", "org_id": "org_x",
                "user_prompt": "test", "search_query": "test",
                "patterns_returned": 5, "patterns_injected": 3, "patterns_filtered": 2,
                "avg_confidence": 0.7, "domains": ["test"], "top_patterns": [],
            },
            # Previous: 3 searches
            {
                "timestamp": _ts(now_ts - timedelta(hours=30)),
                "event": "search", "hook": "UserPromptSubmit",
                "session_id": "ses-dec-2", "project_id": "prj_x", "org_id": "org_x",
                "user_prompt": "test1", "search_query": "test1",
                "patterns_returned": 5, "patterns_injected": 3, "patterns_filtered": 2,
                "avg_confidence": 0.7, "domains": ["test"], "top_patterns": [],
            },
            {
                "timestamp": _ts(now_ts - timedelta(hours=31)),
                "event": "search", "hook": "UserPromptSubmit",
                "session_id": "ses-dec-3", "project_id": "prj_x", "org_id": "org_x",
                "user_prompt": "test2", "search_query": "test2",
                "patterns_returned": 5, "patterns_injected": 3, "patterns_filtered": 2,
                "avg_confidence": 0.7, "domains": ["test"], "top_patterns": [],
            },
            {
                "timestamp": _ts(now_ts - timedelta(hours=32)),
                "event": "search", "hook": "UserPromptSubmit",
                "session_id": "ses-dec-4", "project_id": "prj_x", "org_id": "org_x",
                "user_prompt": "test3", "search_query": "test3",
                "patterns_returned": 5, "patterns_injected": 3, "patterns_filtered": 2,
                "avg_confidence": 0.7, "domains": ["test"], "top_patterns": [],
            },
        ]
        result = calculate_trends(entries, current_hours=24, previous_hours=24)

        # Searches went from 3 to 1, so the change should be negative
        change = result["changes"]["searches"]
        assert change.startswith("-"), f"Expected negative change, got: {change}"

    def test_success_rate_uses_percentage_points(self):
        """success_rate changes are expressed in percentage points (pp), not percent."""
        now_ts = datetime.now(timezone.utc)
        entries = [
            # Current: 1 task, success
            {
                "timestamp": _ts(now_ts - timedelta(hours=2)),
                "event": "execution", "hook": "Stop",
                "session_id": "ses-pp-1", "project_id": "prj_x",
                "patterns_used_count": 1, "pattern_ids": ["ctx-1"],
                "tools_executed": 5, "state_changing_tools": 2,
                "success": True, "execution_time_seconds": 10.0, "learning_sent": True,
            },
            # Previous: 1 task, failure
            {
                "timestamp": _ts(now_ts - timedelta(hours=30)),
                "event": "execution", "hook": "Stop",
                "session_id": "ses-pp-2", "project_id": "prj_x",
                "patterns_used_count": 1, "pattern_ids": ["ctx-2"],
                "tools_executed": 5, "state_changing_tools": 2,
                "success": False, "execution_time_seconds": 10.0, "learning_sent": False,
            },
        ]
        result = calculate_trends(entries, current_hours=24, previous_hours=24)

        # Success rate went from 0% to 100%, so +100.0pp
        change_str = result["changes"]["success_rate"]
        assert "pp" in change_str, f"success_rate change should use 'pp', got: {change_str}"

    def test_result_structure(self, all_sessions, previous_period_entries, now):
        """The result has the expected top-level keys and nested structure."""
        combined = all_sessions + previous_period_entries
        result = calculate_trends(combined, current_hours=24, previous_hours=24, reference_time=now)

        # Top-level keys
        assert set(result.keys()) == {"current_period", "previous_period", "changes"}

        # Period keys
        for period_key in ("current_period", "previous_period"):
            period = result[period_key]
            assert "searches" in period
            assert "tasks" in period
            assert "success_rate" in period
            assert "patterns_injected" in period


# =========================================================================
# 5. format_insights_report() tests
# =========================================================================

class TestFormatInsightsReport:
    """Tests for format_insights_report(sessions, helpfulness, top_patterns, trends) -> str."""

    @pytest.fixture
    def sample_sessions_data(self):
        return {
            "sessions": [
                {
                    "session_id": "ses-aaa-111",
                    "start_time": "2026-01-15T15:46:00Z",
                    "end_time": "2026-01-15T16:00:00Z",
                    "duration_seconds": 840,
                    "searches": 1,
                    "patterns_injected": 12,
                    "patterns_used": 8,
                    "domain_shifts": 1,
                    "domains": ["auth", "cache"],
                    "tools_executed": 27,
                    "success": True,
                    "learning_sent": True,
                    "user_prompts": ["Fix the auth bug"],
                },
            ],
            "total_sessions": 1,
            "active_sessions": 1,
        }

    @pytest.fixture
    def sample_helpfulness_data(self):
        return {
            "tasks_with_patterns": 2,
            "tasks_without_patterns": 1,
            "success_rate_with_patterns": 100.0,
            "success_rate_without_patterns": 0.0,
            "pattern_advantage": 100.0,
            "avg_patterns_per_task": 7.0,
            "avg_confidence": 0.83,
        }

    @pytest.fixture
    def sample_top_patterns_data(self):
        return [
            {"pattern_id": "ctx-123", "usage_count": 2, "sessions": 2},
            {"pattern_id": "ctx-456", "usage_count": 1, "sessions": 1},
        ]

    @pytest.fixture
    def sample_trends_data(self):
        return {
            "current_period": {"searches": 4, "tasks": 3, "success_rate": 66.7, "patterns_injected": 28},
            "previous_period": {"searches": 2, "tasks": 2, "success_rate": 50.0, "patterns_injected": 11},
            "changes": {
                "searches": "+100.0%",
                "tasks": "+50.0%",
                "success_rate": "+16.7pp",
                "patterns_injected": "+154.5%",
            },
        }

    def test_output_contains_session_count(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """The report string includes the total session count."""
        report = format_insights_report(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert isinstance(report, str)
        assert "1" in report  # total_sessions = 1

    def test_output_contains_helpfulness_summary(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """The report includes helpfulness metrics like success rates."""
        report = format_insights_report(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert "100.0" in report  # success_rate_with_patterns
        assert "pattern" in report.lower()

    def test_output_contains_top_patterns(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """The report lists top patterns with their IDs."""
        report = format_insights_report(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert "ctx-123" in report
        assert "ctx-456" in report

    def test_output_contains_trend_indicators(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """The report contains trend direction indicators (up/down arrows or +/- signs)."""
        report = format_insights_report(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        # Should contain some form of positive trend indicator
        has_up_indicator = "+" in report or "up" in report.lower() or "\u2191" in report
        assert has_up_indicator, "Report should contain upward trend indicators"

    def test_empty_data_produces_no_data_message(self):
        """When all data is empty, the report shows 'No data' messages instead of crashing."""
        empty_sessions = {"sessions": [], "total_sessions": 0, "active_sessions": 0}
        empty_helpfulness = {
            "tasks_with_patterns": 0, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 0, "success_rate_without_patterns": 0,
            "pattern_advantage": 0, "avg_patterns_per_task": 0, "avg_confidence": 0,
        }
        empty_patterns = []
        empty_trends = {
            "current_period": {"searches": 0, "tasks": 0, "success_rate": 0, "patterns_injected": 0},
            "previous_period": {"searches": 0, "tasks": 0, "success_rate": 0, "patterns_injected": 0},
            "changes": {"searches": "N/A", "tasks": "N/A", "success_rate": "N/A", "patterns_injected": "N/A"},
        }

        report = format_insights_report(empty_sessions, empty_helpfulness, empty_patterns, empty_trends)
        assert isinstance(report, str)
        assert len(report) > 0
        assert "no data" in report.lower() or "no session" in report.lower() or "0" in report

    def test_report_is_multiline(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """The report is a multi-line, human-readable string."""
        report = format_insights_report(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        lines = report.strip().split("\n")
        assert len(lines) > 5, "Report should be a multi-line document"

    def test_report_contains_trend_decrease_indicator(self):
        """When trends are negative, the report shows decrease indicators."""
        sessions = {"sessions": [], "total_sessions": 0, "active_sessions": 0}
        helpfulness = {
            "tasks_with_patterns": 0, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 0, "success_rate_without_patterns": 0,
            "pattern_advantage": 0, "avg_patterns_per_task": 0, "avg_confidence": 0,
        }
        patterns = []
        trends = {
            "current_period": {"searches": 2, "tasks": 1, "success_rate": 50.0, "patterns_injected": 5},
            "previous_period": {"searches": 5, "tasks": 3, "success_rate": 80.0, "patterns_injected": 15},
            "changes": {
                "searches": "-60.0%",
                "tasks": "-66.7%",
                "success_rate": "-30.0pp",
                "patterns_injected": "-66.7%",
            },
        }

        report = format_insights_report(sessions, helpfulness, patterns, trends)
        has_down_indicator = "-" in report or "down" in report.lower() or "\u2193" in report
        assert has_down_indicator, "Report should contain downward trend indicators for decreases"


# =========================================================================
# 6. format_insights_html() tests
# =========================================================================

class TestFormatInsightsHtml:
    """Tests for format_insights_html(sessions, helpfulness, top_patterns, trends, hours) -> str."""

    @pytest.fixture
    def sample_sessions_data(self):
        return {
            "sessions": [
                {
                    "session_id": "ses-aaa-111",
                    "start_time": "2026-01-15T15:46:00Z",
                    "end_time": "2026-01-15T16:00:00Z",
                    "duration_seconds": 840,
                    "searches": 1,
                    "patterns_injected": 12,
                    "patterns_used": 8,
                    "domain_shifts": 1,
                    "domains": ["auth", "cache"],
                    "tools_executed": 27,
                    "success": True,
                    "learning_sent": True,
                    "user_prompts": ["Fix the auth bug"],
                },
            ],
            "total_sessions": 1,
            "active_sessions": 1,
        }

    @pytest.fixture
    def sample_helpfulness_data(self):
        return {
            "tasks_with_patterns": 2,
            "tasks_without_patterns": 1,
            "success_rate_with_patterns": 100.0,
            "success_rate_without_patterns": 0.0,
            "pattern_advantage": 100.0,
            "avg_patterns_per_task": 7.0,
            "avg_confidence": 0.83,
        }

    @pytest.fixture
    def sample_top_patterns_data(self):
        return [
            {"pattern_id": "ctx-123", "usage_count": 2, "sessions": 2},
            {"pattern_id": "ctx-456", "usage_count": 1, "sessions": 1},
        ]

    @pytest.fixture
    def sample_trends_data(self):
        return {
            "current_period": {"searches": 4, "tasks": 3, "success_rate": 66.7, "patterns_injected": 28},
            "previous_period": {"searches": 2, "tasks": 2, "success_rate": 50.0, "patterns_injected": 11},
            "changes": {
                "searches": "+100.0%",
                "tasks": "+50.0%",
                "success_rate": "+16.7pp",
                "patterns_injected": "+154.5%",
            },
        }

    def test_returns_valid_html(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """Output starts with <!DOCTYPE html> and contains <html>, </html>, <head>, <body>."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert html.strip().startswith("<!DOCTYPE html>"), "HTML output must start with <!DOCTYPE html>"
        assert "<html>" in html or "<html " in html, "Missing <html> tag"
        assert "</html>" in html, "Missing </html> tag"
        assert "<head>" in html, "Missing <head> tag"
        assert "<body>" in html or "<body " in html, "Missing <body> tag"

    def test_self_contained_css(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """All CSS is inline in a <style> tag (no external stylesheet links except fonts)."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert "<style>" in html, "CSS must be in an inline <style> tag"

        # Check there are no <link rel="stylesheet"> tags (font links are OK)
        import re
        stylesheet_links = re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]*>', html)
        for link in stylesheet_links:
            assert "fonts.googleapis.com" in link, (
                f"External stylesheet link found (non-font): {link}"
            )

    def test_contains_session_data(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """Output includes session IDs from the sessions data."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        # Session ID ses-aaa-111 should appear (possibly truncated but recognizable)
        assert "ses-aaa-111" in html, "Session ID 'ses-aaa-111' should appear in HTML output"

    def test_contains_helpfulness_metrics(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """Output includes success rates and pattern advantage."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert "100.0" in html, "Success rate (100.0%) should appear in HTML"
        assert "100.0pp" in html or "+100.0pp" in html, "Pattern advantage should appear in HTML"

    def test_contains_top_pattern_ids(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """Output includes pattern IDs like 'ctx-123'."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert "ctx-123" in html, "Pattern ID 'ctx-123' should appear in HTML output"
        assert "ctx-456" in html, "Pattern ID 'ctx-456' should appear in HTML output"

    def test_contains_trend_changes(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """Output includes trend change values like '+100.0%'."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert "+100.0%" in html, "Trend change '+100.0%' should appear in HTML output"

    def test_empty_data_no_crash(self):
        """Empty data produces valid HTML without errors."""
        empty_sessions = {"sessions": [], "total_sessions": 0, "active_sessions": 0}
        empty_helpfulness = {
            "tasks_with_patterns": 0, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 0, "success_rate_without_patterns": 0,
            "pattern_advantage": 0, "avg_patterns_per_task": 0, "avg_confidence": 0,
        }
        empty_patterns = []
        empty_trends = {
            "current_period": {"searches": 0, "tasks": 0, "success_rate": 0, "patterns_injected": 0},
            "previous_period": {"searches": 0, "tasks": 0, "success_rate": 0, "patterns_injected": 0},
            "changes": {"searches": "N/A", "tasks": "N/A", "success_rate": "N/A", "patterns_injected": "N/A"},
        }

        html = format_insights_html(empty_sessions, empty_helpfulness, empty_patterns, empty_trends)
        assert html.strip().startswith("<!DOCTYPE html>"), "Empty-data HTML must still start with <!DOCTYPE html>"
        assert "</html>" in html, "Empty-data HTML must still close </html>"

    def test_html_escapes_user_input(self):
        """Special characters in user prompts are HTML-escaped (no XSS)."""
        xss_sessions = {
            "sessions": [
                {
                    "session_id": "ses-xss-001",
                    "start_time": "2026-01-15T15:00:00Z",
                    "end_time": "2026-01-15T15:10:00Z",
                    "duration_seconds": 600,
                    "searches": 1,
                    "patterns_injected": 5,
                    "patterns_used": 3,
                    "domain_shifts": 0,
                    "domains": ["test"],
                    "tools_executed": 10,
                    "success": True,
                    "learning_sent": True,
                    "user_prompts": ['<script>alert("xss")</script>'],
                },
            ],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 3.0, "avg_confidence": 0.9,
        }
        patterns = [{"pattern_id": "ctx-xss", "usage_count": 1, "sessions": 1}]
        trends = {
            "current_period": {"searches": 1, "tasks": 1, "success_rate": 100.0, "patterns_injected": 5},
            "previous_period": {"searches": 0, "tasks": 0, "success_rate": 0, "patterns_injected": 0},
            "changes": {"searches": "N/A", "tasks": "N/A", "success_rate": "N/A", "patterns_injected": "N/A"},
        }

        html = format_insights_html(xss_sessions, helpfulness, patterns, trends)
        # The raw <script> tag must NOT appear unescaped
        assert "<script>" not in html, "User input must be HTML-escaped to prevent XSS"
        # The escaped form should be present
        assert "&lt;script&gt;" in html, "Escaped <script> tag should appear in output"

    def test_contains_hours_parameter(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """The hours value appears in the report."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data,
            sample_top_patterns_data, sample_trends_data, hours=48
        )
        assert "48" in html, "The hours parameter value (48) should appear in the HTML report"

    def test_contains_inter_font(
        self, sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
    ):
        """Uses Inter font (matching Claude Code's style)."""
        html = format_insights_html(
            sample_sessions_data, sample_helpfulness_data, sample_top_patterns_data, sample_trends_data
        )
        assert "Inter" in html, "HTML report should reference the Inter font family"


# =========================================================================
# TestAgentType -- agent_type field in sessions and HTML
# =========================================================================

class TestAgentType:
    """Test that agent_type is captured from log entries and displayed."""

    def test_agent_type_from_execution_event(self, now):
        """Sessions with agent_type in execution event should capture it."""
        entries = [
            {
                "timestamp": _ts(now - timedelta(minutes=5)),
                "event": "search",
                "hook": "UserPromptSubmit",
                "session_id": "ses-tdd-001",
                "agent_type": "tdd",
                "user_prompt": "Write tests for auth",
                "search_query": "auth tests",
                "patterns_returned": 5,
                "patterns_injected": 3,
                "patterns_filtered": 2,
                "avg_confidence": 0.8,
                "domains": ["testing"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-tdd-001",
                "agent_type": "tdd",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1", "ctx-2", "ctx-3"],
                "tools_executed": 15,
                "state_changing_tools": 8,
                "success": True,
                "execution_time_seconds": 30.0,
                "learning_sent": True,
            },
        ]
        result = analyze_sessions(entries)
        assert result["sessions"][0]["agent_type"] == "tdd"

    def test_agent_type_defaults_to_main(self, now):
        """Sessions without agent_type should default to 'main'."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-main-001",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 5,
                "state_changing_tools": 3,
                "success": True,
                "execution_time_seconds": 10.0,
                "learning_sent": False,
            },
        ]
        result = analyze_sessions(entries)
        assert result["sessions"][0]["agent_type"] == "main"

    def test_agent_type_shown_in_text_report(self, now):
        """Non-main agent_type should appear in text report."""
        sessions = {
            "sessions": [{
                "session_id": "ses-tdd-001",
                "agent_type": "tdd",
                "start_time": _ts(now),
                "end_time": _ts(now),
                "duration_seconds": 30,
                "searches": 1,
                "patterns_injected": 3,
                "patterns_used": 3,
                "domain_shifts": 0,
                "domains": ["testing"],
                "tools_executed": 15,
                "success": True,
                "learning_sent": True,
                "user_prompts": ["Write tests"],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 3.0, "avg_confidence": 0.8,
        }
        report = format_insights_report(sessions, helpfulness, [], {"current_period": {}, "previous_period": {}, "changes": {}})
        assert "[tdd]" in report

    def test_agent_type_badge_in_html(self, now):
        """agent_type should appear as a badge in HTML report."""
        sessions = {
            "sessions": [{
                "session_id": "ses-coder-001",
                "agent_type": "coder",
                "start_time": _ts(now),
                "end_time": _ts(now),
                "duration_seconds": 60,
                "searches": 2,
                "patterns_injected": 5,
                "patterns_used": 4,
                "domain_shifts": 1,
                "domains": ["api"],
                "tools_executed": 20,
                "success": True,
                "learning_sent": True,
                "user_prompts": ["Build API endpoint"],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 4.0, "avg_confidence": 0.9,
        }
        html = format_insights_html(sessions, helpfulness, [], {"current_period": {}, "previous_period": {}, "changes": {}})
        assert "agent-coder" in html
        assert "coder" in html

    def test_main_agent_no_tag_in_text_report(self, now):
        """Main agent should not show [main] tag in text report."""
        sessions = {
            "sessions": [{
                "session_id": "ses-main-001",
                "agent_type": "main",
                "start_time": _ts(now),
                "end_time": _ts(now),
                "duration_seconds": 60,
                "searches": 1,
                "patterns_injected": 2,
                "patterns_used": 2,
                "domain_shifts": 0,
                "domains": [],
                "tools_executed": 10,
                "success": True,
                "learning_sent": True,
                "user_prompts": ["Fix bug"],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 2.0, "avg_confidence": 0.7,
        }
        report = format_insights_report(sessions, helpfulness, [], {"current_period": {}, "previous_period": {}, "changes": {}})
        assert "[main]" not in report


# =========================================================================
# TestAgentTypeEdgeCases -- additional coverage for agent_type
# =========================================================================

class TestAgentTypeEdgeCases:
    """Additional edge-case tests for agent_type handling.

    Gaps identified during TDD review:
      - agent_type=None in log entries
      - agent_type="" (empty string) in log entries
      - XSS via malicious agent_type values in HTML
      - agent_type from search event only (no execution)
      - Mixed agent_type across events in same session
    """

    def test_agent_type_none_in_entry_defaults_to_main(self, now):
        """Entries with agent_type=None should result in 'main'."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-none-agent",
                "agent_type": None,
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-1", "ctx-2"],
                "tools_executed": 5,
                "state_changing_tools": 3,
                "success": True,
                "execution_time_seconds": 10.0,
                "learning_sent": False,
            },
        ]
        result = analyze_sessions(entries)
        assert result["sessions"][0]["agent_type"] == "main"

    def test_agent_type_empty_string_defaults_to_main(self, now):
        """Entries with agent_type='' (empty string) should default to 'main'."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-empty-agent",
                "agent_type": "",
                "patterns_used_count": 1,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 3,
                "state_changing_tools": 1,
                "success": True,
                "execution_time_seconds": 5.0,
                "learning_sent": False,
            },
        ]
        result = analyze_sessions(entries)
        assert result["sessions"][0]["agent_type"] == "main"

    def test_agent_type_from_search_event_only(self, now):
        """When only search event has agent_type, it should still be captured."""
        entries = [
            {
                "timestamp": _ts(now - timedelta(minutes=5)),
                "event": "search",
                "hook": "UserPromptSubmit",
                "session_id": "ses-search-only-agent",
                "agent_type": "researcher",
                "user_prompt": "Analyze codebase",
                "search_query": "analyze codebase",
                "patterns_returned": 3,
                "patterns_injected": 2,
                "patterns_filtered": 1,
                "avg_confidence": 0.7,
                "domains": ["code"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-search-only-agent",
                # No agent_type on execution event
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-1", "ctx-2"],
                "tools_executed": 10,
                "state_changing_tools": 5,
                "success": True,
                "execution_time_seconds": 20.0,
                "learning_sent": True,
            },
        ]
        result = analyze_sessions(entries)
        assert result["sessions"][0]["agent_type"] == "researcher"

    def test_mixed_agent_type_across_events_prefers_non_main(self, now):
        """When events have different agent_types, the first non-main type wins."""
        entries = [
            {
                "timestamp": _ts(now - timedelta(minutes=5)),
                "event": "search",
                "hook": "UserPromptSubmit",
                "session_id": "ses-mixed-agent",
                "agent_type": "main",
                "user_prompt": "Do something",
                "search_query": "something",
                "patterns_returned": 1,
                "patterns_injected": 1,
                "patterns_filtered": 0,
                "avg_confidence": 0.5,
                "domains": [],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-mixed-agent",
                "agent_type": "refactorer",
                "patterns_used_count": 1,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 8,
                "state_changing_tools": 4,
                "success": True,
                "execution_time_seconds": 15.0,
                "learning_sent": True,
            },
        ]
        result = analyze_sessions(entries)
        # The analyzer scans for the first non-main agent_type
        assert result["sessions"][0]["agent_type"] == "refactorer"

    def test_html_escapes_malicious_agent_type(self, now):
        """Malicious agent_type values must be HTML-escaped in the HTML report (XSS prevention)."""
        sessions = {
            "sessions": [{
                "session_id": "ses-xss-agent",
                "agent_type": '<img src=x onerror="alert(1)">',
                "start_time": _ts(now),
                "end_time": _ts(now),
                "duration_seconds": 30,
                "searches": 1,
                "patterns_injected": 1,
                "patterns_used": 1,
                "domain_shifts": 0,
                "domains": [],
                "tools_executed": 5,
                "success": True,
                "learning_sent": False,
                "user_prompts": ["Test"],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 1.0, "avg_confidence": 0.5,
        }
        html = format_insights_html(sessions, helpfulness, [], {
            "current_period": {}, "previous_period": {}, "changes": {}
        })
        # The raw <img> tag must NOT appear unescaped
        assert '<img ' not in html, "agent_type must be HTML-escaped to prevent XSS"
        assert '&lt;img' in html, "Escaped <img> tag should appear in output"

    def test_all_known_agent_types_have_css_classes(self, now):
        """Known agent types (tdd, coder, refactorer, researcher) should have matching CSS classes."""
        # We only need to verify CSS exists in the HTML output
        sessions = {
            "sessions": [],
            "total_sessions": 0,
            "active_sessions": 0,
        }
        helpfulness = {
            "tasks_with_patterns": 0, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 0, "success_rate_without_patterns": 0,
            "pattern_advantage": 0, "avg_patterns_per_task": 0, "avg_confidence": 0,
        }
        html = format_insights_html(sessions, helpfulness, [], {
            "current_period": {}, "previous_period": {}, "changes": {}
        })
        # Verify CSS definitions exist for known agent types
        for agent in ("main", "tdd", "coder", "refactorer", "researcher"):
            assert f".agent-{agent}" in html, (
                f"CSS class .agent-{agent} must be defined in the HTML report"
            )


# =========================================================================
# TestLoggerAgentType -- unit tests for ACERelevanceLogger agent_type
# =========================================================================

class TestLoggerAgentType:
    """Unit tests for ACERelevanceLogger writing agent_type to JSONL."""

    def test_log_search_metrics_includes_agent_type(self, tmp_path):
        """log_search_metrics() must write agent_type to the JSONL entry."""
        import json
        sys.path.insert(0, str(Path(__file__).parent.parent / "plugins" / "ace" / "shared-hooks" / "utils"))
        from ace_relevance_logger import ACERelevanceLogger

        logger = ACERelevanceLogger(log_dir=str(tmp_path))
        logger.log_search_metrics(
            hook="UserPromptSubmit",
            session_id="ses-logger-001",
            user_prompt="Test prompt",
            search_query="test",
            patterns_returned=[{"id": "ctx-1"}],
            patterns_injected=[{"id": "ctx-1", "confidence": 0.8}],
            domains=["test"],
            agent_type="tdd",
        )

        log_file = tmp_path / "ace-relevance.jsonl"
        assert log_file.exists(), "Log file should be created"
        entry = json.loads(log_file.read_text().strip())
        assert entry["agent_type"] == "tdd"

    def test_log_search_metrics_agent_type_defaults_to_main(self, tmp_path):
        """log_search_metrics() with agent_type=None writes 'main'."""
        import json
        from ace_relevance_logger import ACERelevanceLogger

        logger = ACERelevanceLogger(log_dir=str(tmp_path))
        logger.log_search_metrics(
            hook="UserPromptSubmit",
            session_id="ses-logger-002",
            user_prompt="Test",
            search_query="test",
            patterns_returned=[],
            patterns_injected=[],
            domains=[],
            agent_type=None,
        )

        entry = json.loads((tmp_path / "ace-relevance.jsonl").read_text().strip())
        assert entry["agent_type"] == "main"

    def test_log_execution_metrics_includes_agent_type(self, tmp_path):
        """log_execution_metrics() must write agent_type to the JSONL entry."""
        import json
        from ace_relevance_logger import ACERelevanceLogger

        logger = ACERelevanceLogger(log_dir=str(tmp_path))
        logger.log_execution_metrics(
            session_id="ses-logger-003",
            patterns_used=["ctx-1", "ctx-2"],
            tools_executed=10,
            state_changing_tools=5,
            success=True,
            execution_time_seconds=25.0,
            learning_sent=True,
            agent_type="coder",
        )

        entry = json.loads((tmp_path / "ace-relevance.jsonl").read_text().strip())
        assert entry["agent_type"] == "coder"

    def test_log_execution_metrics_agent_type_defaults_to_main(self, tmp_path):
        """log_execution_metrics() with no agent_type writes 'main'."""
        import json
        from ace_relevance_logger import ACERelevanceLogger

        logger = ACERelevanceLogger(log_dir=str(tmp_path))
        logger.log_execution_metrics(
            session_id="ses-logger-004",
            patterns_used=[],
            tools_executed=3,
            state_changing_tools=1,
            success=False,
            execution_time_seconds=5.0,
            learning_sent=False,
            # agent_type not passed -- should default
        )

        entry = json.loads((tmp_path / "ace-relevance.jsonl").read_text().strip())
        assert entry["agent_type"] == "main"

    def test_log_search_metrics_empty_string_agent_type_becomes_main(self, tmp_path):
        """log_search_metrics() with agent_type='' writes 'main' (falsy default)."""
        import json
        from ace_relevance_logger import ACERelevanceLogger

        logger = ACERelevanceLogger(log_dir=str(tmp_path))
        logger.log_search_metrics(
            hook="UserPromptSubmit",
            session_id="ses-logger-005",
            user_prompt="Test",
            search_query="test",
            patterns_returned=[],
            patterns_injected=[],
            domains=[],
            agent_type="",
        )

        entry = json.loads((tmp_path / "ace-relevance.jsonl").read_text().strip())
        assert entry["agent_type"] == "main"


# =========================================================================
# TestAceInsightsCommand -- command markdown format validation
# =========================================================================

class TestAceInsightsCommand:
    """Tests that ace-insights.md command file follows the working command pattern.

    The /ace:ace-insights command fails because its markdown is structured as
    documentation rather than instructions for Claude. Working commands like
    ace-status.md and ace-doctor.md have an "Instructions for Claude" section
    that tells Claude to execute bash blocks. Without this section, Claude
    displays the markdown as text instead of running the script.

    These tests verify the command file structure matches working commands.
    """

    COMMANDS_DIR = PROJECT_ROOT / "plugins" / "ace" / "commands"
    INSIGHTS_CMD = COMMANDS_DIR / "ace-insights.md"
    STATUS_CMD = COMMANDS_DIR / "ace-status.md"
    DOCTOR_CMD = COMMANDS_DIR / "ace-doctor.md"

    @pytest.fixture
    def insights_content(self):
        """Read the ace-insights.md command file."""
        return self.INSIGHTS_CMD.read_text()

    @pytest.fixture
    def status_content(self):
        """Read the ace-status.md command file (known working)."""
        return self.STATUS_CMD.read_text()

    @pytest.fixture
    def doctor_content(self):
        """Read the ace-doctor.md command file (known working)."""
        return self.DOCTOR_CMD.read_text()

    def test_command_file_exists(self):
        """The ace-insights.md command file must exist."""
        assert self.INSIGHTS_CMD.exists(), (
            f"Command file not found: {self.INSIGHTS_CMD}"
        )

    def test_has_instructions_for_claude_section(self, insights_content):
        """The command must have an 'Instructions for Claude' section (like working commands)."""
        assert "## Instructions for Claude" in insights_content, (
            "ace-insights.md must contain '## Instructions for Claude' section. "
            "Without it, Claude displays the markdown as text instead of executing the bash script."
        )

    def test_instructions_section_appears_before_bash_block(self, insights_content):
        """The 'Instructions for Claude' section must appear before the main bash code block."""
        instructions_pos = insights_content.find("## Instructions for Claude")
        bash_pos = insights_content.find("```bash")
        assert instructions_pos != -1, "Missing '## Instructions for Claude' section"
        assert bash_pos != -1, "Missing bash code block"
        assert instructions_pos < bash_pos, (
            "The 'Instructions for Claude' section must appear BEFORE the bash code block. "
            f"Instructions at position {instructions_pos}, bash at position {bash_pos}."
        )

    def test_has_bash_code_block_with_script(self, insights_content):
        """The command must contain a bash code block with a python3 -c command."""
        import re
        bash_blocks = re.findall(r'```bash\n(.*?)```', insights_content, re.DOTALL)
        assert len(bash_blocks) >= 1, "ace-insights.md must contain at least one bash code block"

        # The main script block should start with python3 -c to match permission pattern
        main_script = bash_blocks[0].strip()
        assert main_script.startswith("python3 -c"), (
            "Main bash block must start with 'python3 -c' to match Bash(python3 -c *) permission pattern"
        )

    def test_no_documentation_sections_before_instructions(self, insights_content):
        """No documentation-only sections (Usage, What You'll See, etc.) should appear
        BEFORE the Instructions for Claude section, as they cause Claude to display
        text instead of executing the script."""
        doc_sections = [
            "## Usage",
            "## What You'll See",
            "## Interpreting Results",
            "## See Also",
        ]
        instructions_pos = insights_content.find("## Instructions for Claude")
        if instructions_pos == -1:
            pytest.fail("Missing '## Instructions for Claude' section")

        for section in doc_sections:
            section_pos = insights_content.find(section)
            if section_pos != -1:
                assert section_pos > instructions_pos, (
                    f"Documentation section '{section}' appears at position {section_pos}, "
                    f"which is BEFORE 'Instructions for Claude' at position {instructions_pos}. "
                    f"This causes Claude to display the section as text instead of executing the script."
                )

    def test_no_usage_examples_before_script(self, insights_content):
        """Usage examples (like '/ace:ace-insights --hours 1') should not appear before
        the main bash block, as they confuse Claude into displaying documentation."""
        instructions_pos = insights_content.find("## Instructions for Claude")
        if instructions_pos == -1:
            pytest.fail("Missing '## Instructions for Claude' section")

        # Check that usage example patterns don't appear before the instructions
        before_instructions = insights_content[:instructions_pos]
        assert "/ace:ace-insights" not in before_instructions, (
            "Usage examples with '/ace:ace-insights' found before Instructions section. "
            "This causes Claude to display documentation instead of executing."
        )

    def test_matches_working_command_pattern(self, insights_content, status_content, doctor_content):
        """The ace-insights.md structure should match the pattern of working commands:
        frontmatter -> title -> brief description -> Instructions for Claude -> bash block."""
        # All working commands have this pattern
        for name, content in [("ace-status", status_content), ("ace-doctor", doctor_content)]:
            assert "## Instructions for Claude" in content, (
                f"Reference command {name}.md unexpectedly missing Instructions section"
            )

        # ace-insights must also follow this pattern
        assert "## Instructions for Claude" in insights_content

    def test_frontmatter_preserved(self, insights_content):
        """The YAML frontmatter with description and argument-hint must be preserved."""
        assert insights_content.startswith("---"), "Must start with YAML frontmatter"
        assert "description:" in insights_content, "Frontmatter must include description"

    def test_bash_script_contains_python_analyzer_call(self, insights_content):
        """The bash script must contain the Python analyzer calls for the 3-step LLM-evaluated flow."""
        assert "ace_insights_analyzer" in insights_content, (
            "Bash script must import from ace_insights_analyzer module"
        )
        assert "extract_task_data_for_evaluation" in insights_content, (
            "Bash script must call extract_task_data_for_evaluation for Step 1 data extraction"
        )
        assert "generate_evaluated_html" in insights_content, (
            "Bash script must call generate_evaluated_html for Step 3 HTML generation"
        )

    def test_uses_claude_plugin_root(self, insights_content):
        """The command must use CLAUDE_PLUGIN_ROOT env var for analyzer path.

        CLAUDE_PLUGIN_ROOT is the official Claude Code env var that resolves to
        the plugin's absolute path. It is available in all command markdown files
        and eliminates the need for fragile find-based path detection.
        """
        assert "CLAUDE_PLUGIN_ROOT" in insights_content, (
            "ace-insights.md must use CLAUDE_PLUGIN_ROOT env var to locate the "
            "analyzer module. This is the official Claude Code env var that "
            "resolves to the plugin's absolute path."
        )

    def test_no_find_commands(self, insights_content):
        """The command must NOT use find commands for path detection.

        The old approach used 'find "${HOME}/.claude/plugins' which is fragile
        and slow. CLAUDE_PLUGIN_ROOT makes find-based detection unnecessary.
        """
        assert 'find "${HOME}/.claude/plugins' not in insights_content, (
            "ace-insights.md must not use find commands for path detection. "
            "Use CLAUDE_PLUGIN_ROOT instead."
        )

    def test_no_hardcoded_marketplace_name(self, insights_content):
        """The command must NOT contain any hardcoded marketplace name.

        Hardcoded names like 'ce-dot-net-marketplace' break for users who
        install from different marketplaces. CLAUDE_PLUGIN_ROOT is universal.
        """
        assert "ce-dot-net-marketplace" not in insights_content, (
            "ace-insights.md must not contain hardcoded marketplace name "
            "'ce-dot-net-marketplace'. Use CLAUDE_PLUGIN_ROOT instead."
        )

    def test_analyzer_path_uses_plugin_root(self, insights_content):
        """The analyzer path must be constructed from CLAUDE_PLUGIN_ROOT.

        In the python3 -c approach, the path is built via:
        Path(os.environ.get('CLAUDE_PLUGIN_ROOT', '')) / 'shared-hooks' / 'utils' / 'ace_insights_analyzer.py'
        """
        assert "CLAUDE_PLUGIN_ROOT" in insights_content, (
            "ace-insights.md must reference CLAUDE_PLUGIN_ROOT env var for analyzer path"
        )
        assert "ace_insights_analyzer.py" in insights_content, (
            "ace-insights.md must reference ace_insights_analyzer.py module"
        )

    def test_step1_and_step3_same_path(self, insights_content):
        """Both Step 1 and Step 3 bash blocks must use the same CLAUDE_PLUGIN_ROOT path pattern.

        Previously, Step 1 and Step 3 had different path detection blocks which
        could lead to inconsistencies. Both must now use the identical
        CLAUDE_PLUGIN_ROOT-based path via os.environ.get('CLAUDE_PLUGIN_ROOT', '').
        """
        import re
        bash_blocks = re.findall(r'```bash\n(.*?)```', insights_content, re.DOTALL)
        assert len(bash_blocks) >= 2, (
            "ace-insights.md must have at least 2 bash blocks (Step 1 and Step 3)"
        )
        expected = "os.environ.get('CLAUDE_PLUGIN_ROOT', '')"
        step1_block = bash_blocks[0]
        step3_block = bash_blocks[1]
        assert expected in step1_block, (
            f"Step 1 bash block must contain: {expected}"
        )
        assert expected in step3_block, (
            f"Step 3 bash block must contain: {expected}"
        )


# =========================================================================
# BUG FIX TESTS: Duration formatting, patterns_used aggregation
# =========================================================================
# These tests were added after analyzing raw JSONL data from the production
# ace-relevance.jsonl log. The analysis revealed:
#
# BUG A: Duration formatting only uses m/s, never hours or days.
#        A session spanning 33 days shows as "47350m 39s" instead of "32d 21h".
#
# BUG B: patterns_used takes only the LAST execution event's count,
#        ignoring all prior executions in the same session.
#        A session with 18 execution events (some with patterns_used_count=40)
#        shows "0 used" because the last event happened to have 0.
# =========================================================================

class TestDurationFormatting:
    """Tests for human-readable duration formatting in reports.

    BUG A: The report formats all durations as "{minutes}m {seconds}s",
    which produces unreadable values like "47350m 39s" for a 33-day session.
    Large durations should show days and hours.
    """

    def test_duration_over_one_hour_shows_hours(self):
        """A session spanning 2 hours should display hours, not just minutes."""
        sessions = {
            "sessions": [{
                "session_id": "ses-2h-001",
                "agent_type": "main",
                "start_time": "2026-01-15T14:00:00Z",
                "end_time": "2026-01-15T16:00:00Z",
                "duration_seconds": 7200,  # 2 hours
                "searches": 1,
                "patterns_injected": 5,
                "patterns_used": 3,
                "domain_shifts": 0,
                "domains": ["api"],
                "tools_executed": 20,
                "success": True,
                "learning_sent": True,
                "user_prompts": ["Build endpoint"],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 3.0, "avg_confidence": 0.8,
        }
        report = format_insights_report(
            sessions, helpfulness, [],
            {"current_period": {}, "previous_period": {}, "changes": {}}
        )
        # Should NOT show "120m 0s" -- should show hours
        assert "120m" not in report, (
            "Duration of 2 hours should NOT be displayed as '120m 0s'. "
            "It should show hours, e.g. '2h 0m'."
        )

    def test_duration_over_one_day_shows_days(self):
        """A session spanning 33 days should display days, not minutes."""
        sessions = {
            "sessions": [{
                "session_id": "ses-33d-001",
                "agent_type": "main",
                "start_time": "2025-12-27T21:49:57Z",
                "end_time": "2026-01-29T19:00:36Z",
                "duration_seconds": 2841039,  # ~33 days
                "searches": 0,
                "patterns_injected": 0,
                "patterns_used": 0,
                "domain_shifts": 0,
                "domains": [],
                "tools_executed": 82,
                "success": True,
                "learning_sent": True,
                "user_prompts": [],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 0, "tasks_without_patterns": 1,
            "success_rate_with_patterns": 0, "success_rate_without_patterns": 100.0,
            "pattern_advantage": 0, "avg_patterns_per_task": 0, "avg_confidence": 0,
        }
        report = format_insights_report(
            sessions, helpfulness, [],
            {"current_period": {}, "previous_period": {}, "changes": {}}
        )
        # Should NOT show "47350m 39s" -- should show days
        assert "47350m" not in report, (
            "Duration of 33 days should NOT be displayed as '47350m 39s'. "
            "It should show days, e.g. '32d 21h'."
        )

    def test_duration_over_one_hour_shows_hours_in_html(self):
        """HTML report should also format large durations with hours."""
        sessions = {
            "sessions": [{
                "session_id": "ses-2h-html",
                "agent_type": "main",
                "start_time": "2026-01-15T14:00:00Z",
                "end_time": "2026-01-15T16:00:00Z",
                "duration_seconds": 7200,
                "searches": 1,
                "patterns_injected": 5,
                "patterns_used": 3,
                "domain_shifts": 0,
                "domains": ["api"],
                "tools_executed": 20,
                "success": True,
                "learning_sent": True,
                "user_prompts": ["Build endpoint"],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 3.0, "avg_confidence": 0.8,
        }
        html = format_insights_html(
            sessions, helpfulness, [],
            {"current_period": {}, "previous_period": {}, "changes": {}}
        )
        assert "120m" not in html, (
            "HTML duration of 2 hours should NOT be displayed as '120m 0s'. "
            "It should show hours."
        )

    def test_short_duration_still_uses_minutes(self):
        """A 14-minute session should still show in m/s format."""
        sessions = {
            "sessions": [{
                "session_id": "ses-14m-001",
                "agent_type": "main",
                "start_time": "2026-01-15T15:46:00Z",
                "end_time": "2026-01-15T16:00:00Z",
                "duration_seconds": 840,  # 14 minutes
                "searches": 1,
                "patterns_injected": 5,
                "patterns_used": 3,
                "domain_shifts": 0,
                "domains": ["api"],
                "tools_executed": 10,
                "success": True,
                "learning_sent": True,
                "user_prompts": ["Fix bug"],
            }],
            "total_sessions": 1,
            "active_sessions": 1,
        }
        helpfulness = {
            "tasks_with_patterns": 1, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 100.0, "success_rate_without_patterns": 0,
            "pattern_advantage": 100.0, "avg_patterns_per_task": 3.0, "avg_confidence": 0.8,
        }
        report = format_insights_report(
            sessions, helpfulness, [],
            {"current_period": {}, "previous_period": {}, "changes": {}}
        )
        # 14m 0s is fine for a short duration
        assert "14m" in report, "Short duration (14 minutes) should still show minutes"


class TestPatternsUsedAggregation:
    """Tests for patterns_used aggregation across multiple execution events.

    BUG B: analyze_sessions() only looks at the LAST execution event to get
    patterns_used. In a session with many execution events, the last one may
    have patterns_used_count=0 while earlier ones had high counts (e.g. 40).
    The summary should aggregate (sum) patterns_used across ALL executions.
    """

    def test_patterns_used_sums_across_all_executions(self, now):
        """patterns_used should be the SUM of patterns_used_count from ALL
        execution events in the session, not just the last one."""
        entries = [
            {
                "timestamp": _ts(now - timedelta(minutes=30)),
                "event": "search",
                "hook": "UserPromptSubmit",
                "session_id": "ses-multi-exec",
                "user_prompt": "Build feature",
                "search_query": "build feature",
                "patterns_returned": 10,
                "patterns_injected": 8,
                "patterns_filtered": 2,
                "avg_confidence": 0.85,
                "domains": ["api"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now - timedelta(minutes=20)),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-multi-exec",
                "patterns_used_count": 5,
                "pattern_ids": ["ctx-1", "ctx-2", "ctx-3", "ctx-4", "ctx-5"],
                "tools_executed": 10,
                "state_changing_tools": 5,
                "success": True,
                "execution_time_seconds": 20.0,
                "learning_sent": True,
            },
            {
                "timestamp": _ts(now - timedelta(minutes=10)),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-multi-exec",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-6", "ctx-7", "ctx-8"],
                "tools_executed": 8,
                "state_changing_tools": 4,
                "success": True,
                "execution_time_seconds": 15.0,
                "learning_sent": True,
            },
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-multi-exec",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 4,
                "state_changing_tools": 2,
                "success": True,
                "execution_time_seconds": 10.0,
                "learning_sent": False,
            },
        ]
        result = analyze_sessions(entries)
        session = result["sessions"][0]

        # The first two executions used 5 + 3 = 8 patterns total.
        # The last execution used 0 patterns.
        # BUG: current code takes last_exec.patterns_used_count = 0
        # EXPECTED: should sum all executions = 8
        assert session["patterns_used"] == 8, (
            f"patterns_used should be the SUM across all execution events (5+3+0=8), "
            f"not just the last execution's count. Got: {session['patterns_used']}"
        )

    def test_patterns_used_not_just_last_execution(self, now):
        """Even when the last execution has 0 patterns, earlier ones should count."""
        entries = [
            {
                "timestamp": _ts(now - timedelta(minutes=10)),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-last-zero",
                "patterns_used_count": 12,
                "pattern_ids": [f"ctx-{i}" for i in range(12)],
                "tools_executed": 20,
                "state_changing_tools": 10,
                "success": True,
                "execution_time_seconds": 30.0,
                "learning_sent": True,
            },
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-last-zero",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 2,
                "state_changing_tools": 1,
                "success": True,
                "execution_time_seconds": 5.0,
                "learning_sent": False,
            },
        ]
        result = analyze_sessions(entries)
        session = result["sessions"][0]

        assert session["patterns_used"] > 0, (
            f"patterns_used should not be 0 when earlier executions used 12 patterns. "
            f"Got: {session['patterns_used']}"
        )
        assert session["patterns_used"] == 12, (
            f"Expected patterns_used=12 (sum of all executions), got: {session['patterns_used']}"
        )

    def test_tools_executed_sums_across_all_executions(self, now):
        """tools_executed should be summed across all execution events."""
        entries = [
            {
                "timestamp": _ts(now - timedelta(minutes=10)),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-tools-sum",
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-1", "ctx-2"],
                "tools_executed": 15,
                "state_changing_tools": 8,
                "success": True,
                "execution_time_seconds": 20.0,
                "learning_sent": True,
            },
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-tools-sum",
                "patterns_used_count": 1,
                "pattern_ids": ["ctx-3"],
                "tools_executed": 10,
                "state_changing_tools": 5,
                "success": True,
                "execution_time_seconds": 15.0,
                "learning_sent": True,
            },
        ]
        result = analyze_sessions(entries)
        session = result["sessions"][0]

        # tools_executed should be summed: 15 + 10 = 25
        assert session["tools_executed"] == 25, (
            f"tools_executed should be the SUM across all execution events (15+10=25), "
            f"not just the last execution's count. Got: {session['tools_executed']}"
        )

    def test_success_reflects_any_failure(self, now):
        """If ANY execution in a session failed, the session success should be False."""
        entries = [
            {
                "timestamp": _ts(now - timedelta(minutes=10)),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-mixed-success",
                "patterns_used_count": 5,
                "pattern_ids": ["ctx-1", "ctx-2", "ctx-3", "ctx-4", "ctx-5"],
                "tools_executed": 20,
                "state_changing_tools": 10,
                "success": False,  # FAILED
                "execution_time_seconds": 30.0,
                "learning_sent": False,
            },
            {
                "timestamp": _ts(now),
                "event": "execution",
                "hook": "Stop",
                "session_id": "ses-mixed-success",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 5,
                "state_changing_tools": 2,
                "success": True,  # success
                "execution_time_seconds": 10.0,
                "learning_sent": False,
            },
        ]
        result = analyze_sessions(entries)
        session = result["sessions"][0]

        # If any execution failed, the session had a failure
        assert session["success"] is False, (
            "Session success should be False when any execution event failed. "
            "Current code takes only the last execution's success flag."
        )


# =========================================================================
# TestDeduplicateEvents -- Step 1: Remove near-duplicate execution events
# =========================================================================

class TestDeduplicateEvents:
    """Tests for deduplicate_events(entries, window_seconds=30).

    Near-duplicate execution events: same session, within window_seconds,
    same tools_executed count. Returns (cleaned_list, duplicate_count).
    """

    def test_removes_near_duplicate_executions(self, now):
        """Two execution events from the same session within 30s with same
        tools_executed should be deduplicated to one."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-dup-001",
                "tools_executed": 10,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(seconds=5)),
                "event": "execution",
                "session_id": "ses-dup-001",
                "tools_executed": 10,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
        ]
        cleaned, count = deduplicate_events(entries)
        assert len(cleaned) == 1
        assert count == 1

    def test_keeps_non_duplicate_executions(self, now):
        """Two execution events separated by > 30s should both be kept."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-nodup-001",
                "tools_executed": 10,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-nodup-001",
                "tools_executed": 10,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
        ]
        cleaned, count = deduplicate_events(entries)
        assert len(cleaned) == 2
        assert count == 0

    def test_preserves_search_events(self, now):
        """Search events should never be deduplicated."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-search-001",
                "user_prompt": "Fix bug",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(seconds=5)),
                "event": "search",
                "session_id": "ses-search-001",
                "user_prompt": "Fix bug",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [],
            },
        ]
        cleaned, count = deduplicate_events(entries)
        assert len(cleaned) == 2
        assert count == 0

    def test_different_tools_executed_kept(self, now):
        """Execution events with different tools_executed are not duplicates."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-diff-tools",
                "tools_executed": 10,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(seconds=5)),
                "event": "execution",
                "session_id": "ses-diff-tools",
                "tools_executed": 20,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
        ]
        cleaned, count = deduplicate_events(entries)
        assert len(cleaned) == 2
        assert count == 0

    def test_different_session_kept(self, now):
        """Execution events from different sessions are never duplicates."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-a",
                "tools_executed": 10,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(seconds=5)),
                "event": "execution",
                "session_id": "ses-b",
                "tools_executed": 10,
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "success": True,
            },
        ]
        cleaned, count = deduplicate_events(entries)
        assert len(cleaned) == 2
        assert count == 0

    def test_empty_input(self):
        """Empty entries should return empty list and 0 duplicates."""
        cleaned, count = deduplicate_events([])
        assert cleaned == []
        assert count == 0


# =========================================================================
# TestExtractPatternNames -- Step 2: Build pattern_id → name mapping
# =========================================================================

class TestExtractPatternNames:
    """Tests for extract_pattern_names(entries) -> Dict[str, str].

    Builds mapping from search events' top_patterns field.
    Format: 'domain / section' for each pattern_id.
    """

    def test_extracts_domain_and_section(self, now):
        """Should build 'domain / section' name from top_patterns."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-name-001",
                "top_patterns": [
                    {"id": "ctx-123", "domain": "auth", "section": "strategies"},
                    {"id": "ctx-456", "domain": "api", "section": "patterns"},
                ],
            },
        ]
        names = extract_pattern_names(entries)
        assert names["ctx-123"] == "auth / strategies"
        assert names["ctx-456"] == "api / patterns"

    def test_first_occurrence_wins(self, now):
        """If same pattern_id appears in multiple searches, first name wins."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-first-001",
                "top_patterns": [
                    {"id": "ctx-123", "domain": "auth", "section": "strategies"},
                ],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "search",
                "session_id": "ses-first-002",
                "top_patterns": [
                    {"id": "ctx-123", "domain": "security", "section": "rules"},
                ],
            },
        ]
        names = extract_pattern_names(entries)
        assert names["ctx-123"] == "auth / strategies"

    def test_handles_missing_fields(self, now):
        """Patterns without domain or section should be handled gracefully."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-missing-001",
                "top_patterns": [
                    {"id": "ctx-789"},
                ],
            },
        ]
        names = extract_pattern_names(entries)
        # Should still have an entry, just with fallback values
        assert "ctx-789" in names

    def test_no_search_events(self, now):
        """If there are no search events, return empty dict."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-nonames-001",
                "tools_executed": 10,
                "success": True,
            },
        ]
        names = extract_pattern_names(entries)
        assert names == {}

    def test_empty_top_patterns(self, now):
        """Search events with empty top_patterns should be skipped."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-empty-tp",
                "top_patterns": [],
            },
        ]
        names = extract_pattern_names(entries)
        assert names == {}


# =========================================================================
# TestSplitIntoTasks -- Step 3: Time-gap task splitting
# =========================================================================

class TestSplitIntoTasks:
    """Tests for split_into_tasks(entries, gap_minutes=30).

    Core algorithm: group events by time gaps into logical tasks.
    Returns dict with tasks, total_tasks, search_only_count, duplicates_removed.
    """

    def test_single_cluster_becomes_one_task(self, now):
        """Events within 30min of each other form a single task."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Fix auth bug",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [{"id": "ctx-1", "domain": "auth", "section": "strategies"}],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=10)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 15,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        assert result["total_tasks"] == 1
        assert len(result["tasks"]) == 1

    def test_gap_splits_into_two_tasks(self, now):
        """A gap > 30min between events splits into two tasks."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Fix auth bug",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=10)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 15,
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Build API endpoint",
                "patterns_injected": 8,
                "avg_confidence": 0.9,
                "domains": ["api"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(hours=2, minutes=15)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 6,
                "pattern_ids": ["ctx-2"],
                "tools_executed": 20,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        assert result["total_tasks"] == 2
        assert len(result["tasks"]) == 2

    def test_user_prompt_from_first_search(self, now):
        """Task's user_prompt comes from the first search event."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "First prompt",
                "patterns_injected": 3,
                "avg_confidence": 0.7,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Second prompt",
                "patterns_injected": 2,
                "avg_confidence": 0.6,
                "domains": ["api"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=10)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        assert result["tasks"][0]["user_prompt"] == "First prompt"

    def test_aggregates_patterns(self, now):
        """Task should aggregate patterns_injected and patterns_used across events."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Do work",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "More work",
                "patterns_injected": 3,
                "avg_confidence": 0.7,
                "domains": ["api"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=10)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 4,
                "pattern_ids": ["ctx-1", "ctx-2", "ctx-3", "ctx-4"],
                "tools_executed": 20,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        task = result["tasks"][0]
        assert task["patterns_injected"] == 8  # 5 + 3
        assert task["patterns_used"] == 4

    def test_success_reflects_any_failure(self, now):
        """If any execution in a task failed, task success is False."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-2"],
                "tools_executed": 8,
                "success": False,
            },
        ]
        result = split_into_tasks(entries)
        assert result["tasks"][0]["success"] is False

    def test_search_only_separated(self, now):
        """Tasks with only search events (no execution) counted as search_only."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Research something",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["research"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Fix bug",
                "patterns_injected": 3,
                "avg_confidence": 0.7,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(hours=2, minutes=10)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 15,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        # First cluster (search-only) should be counted separately
        assert result["search_only_count"] >= 1
        # Only task with execution should be in tasks list
        assert all(t.get("tools_executed", 0) > 0 for t in result["tasks"])

    def test_domains_merged(self, now):
        """Task should merge domains from all search events in the cluster."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Work",
                "patterns_injected": 3,
                "avg_confidence": 0.7,
                "domains": ["auth", "api"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "More",
                "patterns_injected": 2,
                "avg_confidence": 0.6,
                "domains": ["cache", "api"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=10)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        domains = result["tasks"][0]["domains"]
        assert set(domains) == {"auth", "api", "cache"}

    def test_duration_calculated(self, now):
        """Task duration should be the time span from first to last event."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Work",
                "patterns_injected": 3,
                "avg_confidence": 0.7,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5, seconds=23)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 15,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        assert result["tasks"][0]["duration_seconds"] == 323  # 5m 23s

    def test_agent_type_detected(self, now):
        """Task should capture agent_type from events."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "agent_type": "tdd",
                "user_prompt": "Write tests",
                "patterns_injected": 3,
                "avg_confidence": 0.7,
                "domains": ["testing"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-001",
                "agent_type": "tdd",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 15,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        assert result["tasks"][0]["agent_type"] == "tdd"

    def test_custom_gap_minutes(self, now):
        """Should respect custom gap_minutes parameter."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(minutes=10)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-2"],
                "tools_executed": 8,
                "success": True,
            },
        ]
        # With gap_minutes=5, the 10-minute gap should split
        result = split_into_tasks(entries, gap_minutes=5)
        assert result["total_tasks"] == 2

    def test_empty_entries(self):
        """Empty entries should return empty result."""
        result = split_into_tasks([])
        assert result["tasks"] == []
        assert result["total_tasks"] == 0
        assert result["search_only_count"] == 0
        assert result["duplicates_removed"] == 0

    def test_sequential_task_ids(self, now):
        """Tasks should have sequential numeric IDs starting from 1."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-2"],
                "tools_executed": 8,
                "success": True,
            },
        ]
        result = split_into_tasks(entries)
        ids = [t["task_id"] for t in result["tasks"]]
        assert ids == [1, 2]


# =========================================================================
# TestGetTopPatternsWithNames -- Step 4: pattern_name field
# =========================================================================

class TestGetTopPatternsWithNames:
    """Tests for get_top_patterns pattern_name field addition."""

    def test_pattern_name_included(self, now):
        """Each result should include a pattern_name field."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "top_patterns": [
                    {"id": "ctx-123", "domain": "auth", "section": "strategies"},
                ],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 1,
                "pattern_ids": ["ctx-123"],
                "tools_executed": 10,
                "success": True,
            },
        ]
        result = get_top_patterns(entries)
        assert len(result) > 0
        assert "pattern_name" in result[0]

    def test_name_from_search_events(self, now):
        """pattern_name should come from search events' top_patterns."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "top_patterns": [
                    {"id": "ctx-123", "domain": "auth", "section": "strategies"},
                ],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 1,
                "pattern_ids": ["ctx-123"],
                "tools_executed": 10,
                "success": True,
            },
        ]
        result = get_top_patterns(entries)
        assert result[0]["pattern_name"] == "auth / strategies"

    def test_fallback_to_pattern_id(self, now):
        """When no search event provides a name, fall back to pattern_id."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 1,
                "pattern_ids": ["ctx-999"],
                "tools_executed": 10,
                "success": True,
            },
        ]
        result = get_top_patterns(entries)
        assert result[0]["pattern_name"] == "ctx-999"


# =========================================================================
# TestFormatInsightsHtmlV2 -- Step 5: New task-based HTML layout
# =========================================================================

class TestFormatInsightsHtmlV2:
    """Tests for format_insights_html with raw_entries parameter (v2 layout)."""

    def _make_task_entries(self, now):
        """Helper: create entries that form one task with execution."""
        return [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-v2-001",
                "user_prompt": "Fix the auth bug",
                "search_query": "auth bug",
                "patterns_returned": 10,
                "patterns_injected": 8,
                "patterns_filtered": 2,
                "avg_confidence": 0.84,
                "domains": ["auth", "api"],
                "top_patterns": [
                    {"id": "ctx-123", "domain": "auth", "section": "strategies"},
                    {"id": "ctx-456", "domain": "api", "section": "patterns"},
                ],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-v2-001",
                "agent_type": "tdd",
                "patterns_used_count": 6,
                "pattern_ids": ["ctx-123", "ctx-456"],
                "tools_executed": 27,
                "state_changing_tools": 12,
                "success": True,
                "execution_time_seconds": 60.0,
                "learning_sent": True,
            },
        ]

    def test_task_cards_rendered(self, now):
        """HTML should contain task cards when raw_entries provided."""
        entries = self._make_task_entries(now)
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        assert "task-card" in html

    def test_user_prompt_shown(self, now):
        """Task cards should show the user prompt."""
        entries = self._make_task_entries(now)
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        assert "Fix the auth bug" in html

    def test_pattern_names_shown(self, now):
        """Task cards should show human-readable pattern names."""
        entries = self._make_task_entries(now)
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        assert "auth / strategies" in html

    def test_success_badge(self, now):
        """Task cards should show SUCCESS or FAIL badge."""
        entries = self._make_task_entries(now)
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        assert "SUCCESS" in html or "success" in html.lower()

    def test_search_only_note(self, now):
        """Search-only tasks should be collapsed into a note, not cards."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-search-only",
                "user_prompt": "Just browsing",
                "patterns_injected": 3,
                "avg_confidence": 0.5,
                "domains": ["misc"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "search",
                "session_id": "ses-with-exec",
                "user_prompt": "Fix bug",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(hours=2, minutes=10)),
                "event": "execution",
                "session_id": "ses-with-exec",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 15,
                "success": True,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=3))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # Should mention search-only tasks in a summary note
        assert "search" in html.lower()

    def test_summary_dashboard(self, now):
        """HTML should contain a summary dashboard with task count."""
        entries = self._make_task_entries(now)
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # Should show task count in the summary
        assert "1" in html  # At least shows "1 Task"
        assert "Task" in html

    def test_backward_compatible_without_raw_entries(self, now):
        """Without raw_entries, should use old session-based layout."""
        entries = self._make_task_entries(now)
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        # No raw_entries -- should use old code path
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
        )
        # Old layout has session cards, not task cards
        assert "session-card" in html
        assert "task-card" not in html

    def test_self_contained_html(self, now):
        """HTML should be self-contained (no external JS, inline CSS)."""
        entries = self._make_task_entries(now)
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        assert "<style>" in html
        assert "<!DOCTYPE html>" in html
        # No external script tags (google fonts link is ok)
        assert "<script src=" not in html

    def test_xss_prevention(self, now):
        """User prompts with HTML should be escaped."""
        entries = [
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-xss",
                "user_prompt": '<script>alert("xss")</script>',
                "patterns_injected": 3,
                "avg_confidence": 0.5,
                "domains": ["test"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-xss",
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=1))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_empty_data(self, now):  # noqa: ARG002
        """Empty raw_entries should produce valid HTML with no task cards."""
        sessions = {"sessions": [], "total_sessions": 0, "active_sessions": 0}
        helpfulness = {
            "tasks_with_patterns": 0, "tasks_without_patterns": 0,
            "success_rate_with_patterns": 0, "success_rate_without_patterns": 0,
            "pattern_advantage": 0, "avg_patterns_per_task": 0, "avg_confidence": 0,
        }
        trends = {"current_period": {}, "previous_period": {}, "changes": {}}
        html = format_insights_html(
            sessions, helpfulness, [], trends,
            raw_entries=[],
        )
        assert "<!DOCTYPE html>" in html
        assert "0" in html  # Shows 0 tasks

    def test_helpfulness_uses_task_level_not_events(self, now):
        """Helpfulness section should show ACE Engagement metrics, not old comparison.

        The old 'Pattern Advantage' comparing with/without ACE was misleading.
        The new section shows engagement metrics: coverage, confidence, success rate.
        """
        entries = [
            # Task 1: search + 2 executions (ACE-assisted) → SUCCESS
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Task with patterns",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=2)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 5,
                "success": True,
            },
            # Task 2: execution only (not ACE-assisted) → FAIL
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "execution",
                "session_id": "ses-002",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 8,
                "success": False,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=3))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # v2 helpfulness section should show ACE Engagement metrics
        # NOT the old "Pattern Advantage" comparison
        assert "ACE Engagement" in html, "Should show ACE Engagement heading"
        assert "Coverage" in html, "Should show Coverage metric"
        assert "Relevance" in html or "Confidence" in html, "Should show relevance/confidence"
        assert "Success Rate" in html, "Should show success rate"
        # Should NOT have the old misleading comparison
        assert "Pattern Advantage" not in html, "Old Pattern Advantage should be removed"
        assert "Without ACE Context" not in html, "Old comparison card should be removed"

    def test_helpfulness_shows_engagement_metrics_in_grid(self, now):
        """The helpfulness grid should show engagement metrics, not with/without comparison."""
        entries = [
            # Task 1: ACE-assisted with search
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "ACE task",
                "patterns_injected": 8,
                "avg_confidence": 0.85,
                "domains": ["auth", "cache"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 5,
                "pattern_ids": ["ctx-1", "ctx-2"],
                "tools_executed": 15,
                "success": True,
            },
            # Task 2: not ACE-assisted
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "execution",
                "session_id": "ses-002",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 5,
                "success": True,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=3))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        import re
        # Find the helpfulness grid section
        grid_match = re.search(
            r'class="helpfulness-grid">(.*?)</div>\s*</div>\s*</div>',
            html, re.DOTALL,
        )
        assert grid_match, "Helpfulness grid not found in HTML"
        grid_html = grid_match.group(1)
        # Grid should show engagement-related cards, not with/without comparison
        assert "Coverage" in grid_html or "coverage" in grid_html.lower(), (
            f"Grid should show Coverage metric. Grid HTML: {grid_html[:500]}"
        )
        # Should NOT have old "With Patterns" / "Without Patterns" labels
        assert "With ACE Context" not in grid_html, "Old comparison labels should be gone"
        assert "Without ACE Context" not in grid_html, "Old comparison labels should be gone"


# =========================================================================
# TestComputeAceEngagement -- Per-task ACE engagement scoring
# =========================================================================

class TestComputeAceEngagement:
    """Tests for compute_ace_engagement() function.

    This function computes aggregate engagement metrics from a list of
    tasks (as returned by split_into_tasks()["tasks"]).
    """

    def test_basic_engagement_metrics(self):
        """3 tasks (2 with searches, 1 without) should compute all fields correctly."""
        tasks = [
            {
                "task_id": 1,
                "searches": 2,
                "patterns_injected": 10,
                "avg_confidence": 85.0,
                "domains": ["auth", "cache"],
                "success": True,
            },
            {
                "task_id": 2,
                "searches": 1,
                "patterns_injected": 5,
                "avg_confidence": 70.0,
                "domains": ["database"],
                "success": False,
            },
            {
                "task_id": 3,
                "searches": 0,
                "patterns_injected": 0,
                "avg_confidence": 0,
                "domains": [],
                "success": True,
            },
        ]
        result = compute_ace_engagement(tasks)

        assert result["total_tasks"] == 3
        assert result["ace_assisted_tasks"] == 2
        assert result["ace_coverage_pct"] == pytest.approx(66.7, abs=0.1)
        # avg confidence across ACE tasks: (85 + 70) / 2 = 77.5
        assert result["avg_confidence"] == pytest.approx(77.5, abs=0.1)
        # avg patterns per ACE task: (10 + 5) / 2 = 7.5
        assert result["avg_patterns_per_task"] == pytest.approx(7.5, abs=0.1)
        # avg domains per ACE task: (2 + 1) / 2 = 1.5
        assert result["avg_domains_per_task"] == pytest.approx(1.5, abs=0.1)
        # ACE success rate: 1 success out of 2 ACE tasks = 50%
        assert result["ace_success_rate"] == pytest.approx(50.0, abs=0.1)
        # Overall success rate: 2 out of 3 = 66.7%
        assert result["overall_success_rate"] == pytest.approx(66.7, abs=0.1)

    def test_zero_ace_tasks(self):
        """All tasks with searches=0 should yield ace_coverage_pct=0 and avg_confidence=0."""
        tasks = [
            {
                "task_id": 1,
                "searches": 0,
                "patterns_injected": 0,
                "avg_confidence": 0,
                "domains": [],
                "success": True,
            },
            {
                "task_id": 2,
                "searches": 0,
                "patterns_injected": 0,
                "avg_confidence": 0,
                "domains": [],
                "success": False,
            },
        ]
        result = compute_ace_engagement(tasks)

        assert result["total_tasks"] == 2
        assert result["ace_assisted_tasks"] == 0
        assert result["ace_coverage_pct"] == 0
        assert result["avg_confidence"] == 0
        assert result["avg_patterns_per_task"] == 0
        assert result["avg_domains_per_task"] == 0
        assert result["ace_success_rate"] == 0
        assert result["overall_success_rate"] == pytest.approx(50.0, abs=0.1)

    def test_all_ace_tasks(self):
        """All tasks with searches>0 should yield ace_coverage_pct=100."""
        tasks = [
            {
                "task_id": 1,
                "searches": 3,
                "patterns_injected": 12,
                "avg_confidence": 90.0,
                "domains": ["auth"],
                "success": True,
            },
            {
                "task_id": 2,
                "searches": 1,
                "patterns_injected": 4,
                "avg_confidence": 80.0,
                "domains": ["database", "cache"],
                "success": True,
            },
        ]
        result = compute_ace_engagement(tasks)

        assert result["total_tasks"] == 2
        assert result["ace_assisted_tasks"] == 2
        assert result["ace_coverage_pct"] == 100.0
        assert result["ace_success_rate"] == 100.0
        assert result["overall_success_rate"] == 100.0

    def test_empty_tasks(self):
        """Empty list should return all zeros."""
        result = compute_ace_engagement([])

        assert result["total_tasks"] == 0
        assert result["ace_assisted_tasks"] == 0
        assert result["ace_coverage_pct"] == 0
        assert result["avg_confidence"] == 0
        assert result["avg_patterns_per_task"] == 0
        assert result["avg_domains_per_task"] == 0
        assert result["ace_success_rate"] == 0
        assert result["overall_success_rate"] == 0

    def test_confidence_averaging(self):
        """Confidence should be averaged across ACE-assisted tasks only."""
        tasks = [
            {
                "task_id": 1,
                "searches": 2,
                "patterns_injected": 8,
                "avg_confidence": 92.0,
                "domains": ["auth"],
                "success": True,
            },
            {
                "task_id": 2,
                "searches": 1,
                "patterns_injected": 3,
                "avg_confidence": 68.0,
                "domains": ["cache"],
                "success": True,
            },
            {
                "task_id": 3,
                "searches": 0,
                "patterns_injected": 0,
                "avg_confidence": 0,
                "domains": [],
                "success": True,
            },
        ]
        result = compute_ace_engagement(tasks)

        # Should average only ACE tasks: (92 + 68) / 2 = 80
        assert result["avg_confidence"] == pytest.approx(80.0, abs=0.1)

    def test_domain_counting(self):
        """avg_domains_per_task should count domains per ACE task."""
        tasks = [
            {
                "task_id": 1,
                "searches": 1,
                "patterns_injected": 5,
                "avg_confidence": 75.0,
                "domains": ["auth", "cache", "database"],
                "success": True,
            },
            {
                "task_id": 2,
                "searches": 2,
                "patterns_injected": 10,
                "avg_confidence": 85.0,
                "domains": ["api"],
                "success": True,
            },
            {
                "task_id": 3,
                "searches": 0,
                "patterns_injected": 0,
                "avg_confidence": 0,
                "domains": [],
                "success": False,
            },
        ]
        result = compute_ace_engagement(tasks)

        # ACE tasks: task1 has 3 domains, task2 has 1 domain → avg = 2.0
        assert result["avg_domains_per_task"] == pytest.approx(2.0, abs=0.1)


# =========================================================================
# TestAceCoverage -- Meaningful helpfulness: ACE context vs no context
# =========================================================================

class TestAceCoverage:
    """Tests for ACE coverage metrics in v2 HTML report.

    The old 'patterns_used_count' metric is misleading because it's
    just the saved injection IDs, not actual usage tracking.

    The meaningful split is: tasks WITH ACE search (patterns injected
    into context) vs tasks WITHOUT any search (no ACE context at all).
    """

    def test_ace_coverage_shown_in_html(self, now):
        """v2 HTML should show ACE coverage: how many tasks had ACE context."""
        entries = [
            # Task 1: has search → ACE context present
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-001",
                "user_prompt": "Fix bug",
                "patterns_injected": 8,
                "avg_confidence": 0.84,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-001",
                "patterns_used_count": 0,  # Not tracked, but patterns WERE in context
                "pattern_ids": [],
                "tools_executed": 20,
                "success": True,
            },
            # Task 2: NO search → no ACE context
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "execution",
                "session_id": "ses-002",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 10,
                "success": False,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=3))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # Should show ACE Engagement section
        assert "ACE" in html
        # Should show coverage info — 1 out of 2 tasks had ACE search
        assert "1/2 tasks" in html or "50.0%" in html, (
            "Should show ACE coverage: 1 of 2 tasks ACE-assisted"
        )

    def test_confidence_correlation_shown(self, now):
        """v2 HTML should show confidence correlation with success."""
        entries = [
            # High confidence task → SUCCESS
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-hi",
                "user_prompt": "High conf task",
                "patterns_injected": 10,
                "avg_confidence": 0.92,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-hi",
                "patterns_used_count": 5,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 20,
                "success": True,
            },
            # Low confidence task → FAIL
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "search",
                "session_id": "ses-lo",
                "user_prompt": "Low conf task",
                "patterns_injected": 2,
                "avg_confidence": 0.35,
                "domains": ["misc"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(hours=2, minutes=5)),
                "event": "execution",
                "session_id": "ses-lo",
                "patterns_used_count": 1,
                "pattern_ids": ["ctx-2"],
                "tools_executed": 8,
                "success": False,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=3))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # Should show some form of confidence info
        assert "confidence" in html.lower() or "Confidence" in html


# =========================================================================
# TestDailyBreakdown -- Daily task summary in v2 report
# =========================================================================

class TestDailyBreakdown:
    """Tests for daily breakdown section in v2 HTML report."""

    def test_daily_breakdown_shown(self, now):
        """v2 HTML should show a daily breakdown of tasks."""
        entries = [
            # Day 1 task
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-d1",
                "user_prompt": "Day 1 work",
                "patterns_injected": 5,
                "avg_confidence": 0.8,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=10)),
                "event": "execution",
                "session_id": "ses-d1",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 15,
                "success": True,
            },
            # Day 2 task (next day)
            {
                "timestamp": _ts(now + timedelta(days=1)),
                "event": "search",
                "session_id": "ses-d2",
                "user_prompt": "Day 2 work",
                "patterns_injected": 3,
                "avg_confidence": 0.6,
                "domains": ["api"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(days=1, minutes=10)),
                "event": "execution",
                "session_id": "ses-d2",
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-2"],
                "tools_executed": 10,
                "success": False,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(days=2))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # Should have a daily section
        assert "daily" in html.lower() or "Daily" in html

    def test_daily_shows_task_counts_and_success(self, now):
        """Daily breakdown should show task counts and success rate per day."""
        entries = [
            # Two tasks on the same day, one success one fail
            {
                "timestamp": _ts(now),
                "event": "execution",
                "session_id": "ses-1",
                "patterns_used_count": 3,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
            {
                "timestamp": _ts(now + timedelta(hours=2)),
                "event": "execution",
                "session_id": "ses-2",
                "patterns_used_count": 0,
                "pattern_ids": [],
                "tools_executed": 5,
                "success": False,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(hours=3))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # Should show "Jan 15" (now fixture date) and task counts
        assert "Jan" in html  # The date from the fixture


# =========================================================================
# TestRecentTasksLimit -- Only show most recent tasks
# =========================================================================

class TestRecentTasksLimit:
    """Tests that v2 HTML limits displayed tasks to recent ones."""

    def test_tasks_ordered_newest_first(self, now):
        """Task cards should be ordered with newest first."""
        entries = [
            # Old task
            {
                "timestamp": _ts(now),
                "event": "search",
                "session_id": "ses-old",
                "user_prompt": "Old task from long ago",
                "patterns_injected": 3,
                "avg_confidence": 0.5,
                "domains": ["misc"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(minutes=5)),
                "event": "execution",
                "session_id": "ses-old",
                "patterns_used_count": 2,
                "pattern_ids": ["ctx-1"],
                "tools_executed": 10,
                "success": True,
            },
            # New task
            {
                "timestamp": _ts(now + timedelta(days=10)),
                "event": "search",
                "session_id": "ses-new",
                "user_prompt": "Recent task just now",
                "patterns_injected": 8,
                "avg_confidence": 0.9,
                "domains": ["auth"],
                "top_patterns": [],
            },
            {
                "timestamp": _ts(now + timedelta(days=10, minutes=5)),
                "event": "execution",
                "session_id": "ses-new",
                "patterns_used_count": 6,
                "pattern_ids": ["ctx-2"],
                "tools_executed": 25,
                "success": True,
            },
        ]
        sessions = analyze_sessions(entries)
        helpfulness = calculate_helpfulness(entries)
        top_pats = get_top_patterns(entries)
        trends = calculate_trends(entries, reference_time=now + timedelta(days=11))
        html = format_insights_html(
            sessions, helpfulness, top_pats, trends,
            raw_entries=entries,
        )
        # "Recent task" should appear BEFORE "Old task" in HTML
        recent_pos = html.find("Recent task just now")
        old_pos = html.find("Old task from long ago")
        assert recent_pos != -1, "Recent task should appear in HTML"
        assert old_pos != -1, "Old task should appear in HTML"
        assert recent_pos < old_pos, (
            "Recent tasks should appear before older tasks in the HTML"
        )


# =====================================================================
# TestExtractTaskDataForEvaluation  (8 tests)
# =====================================================================

def _ts(dt: datetime) -> str:
    """Format datetime to ISO-8601 with Z suffix."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_search_event(
    ts: datetime,
    session_id: str = "sess-1",
    user_prompt: str = "Fix the auth bug",
    patterns: list | None = None,
) -> dict:
    """Helper to build a search event entry."""
    if patterns is None:
        patterns = [
            {
                "id": "ctx-111-aaa",
                "confidence": 0.85,
                "domain": "auth",
                "section": "strategies_and_hard_rules",
                "helpful": 5,
                "harmful": 0,
            },
        ]
    return {
        "timestamp": _ts(ts),
        "event": "search",
        "session_id": session_id,
        "user_prompt": user_prompt,
        "search_query": "auth bug",
        "patterns_returned": len(patterns),
        "patterns_injected": len(patterns),
        "avg_confidence": 0.85,
        "domains": list({p["domain"] for p in patterns}),
        "top_patterns": patterns,
    }


def _make_exec_event(
    ts: datetime,
    session_id: str = "sess-1",
    success: bool = True,
    tools: int = 15,
    patterns_used: int = 2,
    pattern_ids: list | None = None,
) -> dict:
    """Helper to build an execution event entry."""
    return {
        "timestamp": _ts(ts),
        "event": "execution",
        "session_id": session_id,
        "success": success,
        "tools_executed": tools,
        "patterns_used_count": patterns_used,
        "pattern_ids": pattern_ids or [],
    }


class TestExtractTaskDataForEvaluation:
    """Tests for extract_task_data_for_evaluation()."""

    # -- Shared fixture: a simple task with one search + one execution --
    @staticmethod
    def _simple_task_entries():
        """Return entries forming one logical task (search + execution)."""
        base = datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc)
        search = _make_search_event(
            base,
            patterns=[
                {
                    "id": "ctx-111-aaa",
                    "confidence": 0.85,
                    "domain": "auth",
                    "section": "strategies_and_hard_rules",
                    "helpful": 5,
                    "harmful": 0,
                },
                {
                    "id": "ctx-222-bbb",
                    "confidence": 0.70,
                    "domain": "cache",
                    "section": "troubleshooting_and_pitfalls",
                    "helpful": 2,
                    "harmful": 1,
                },
            ],
        )
        execution = _make_exec_event(
            base + timedelta(minutes=5),
            pattern_ids=["ctx-111-aaa", "ctx-222-bbb"],
        )
        return [search, execution]

    # 1. Metadata fields
    def test_returns_metadata(self):
        """Verify metadata contains generated_at, hours, total_entries, duplicates_removed."""
        entries = self._simple_task_entries()
        result = extract_task_data_for_evaluation(entries)
        meta = result["metadata"]
        assert "generated_at" in meta
        assert "hours" in meta
        assert meta["hours"] == 24
        assert "total_entries" in meta
        assert meta["total_entries"] == 2
        assert "duplicates_removed" in meta

    # 2. Tasks have pattern_details
    def test_tasks_have_pattern_details(self):
        """A task with a search event must have a non-empty pattern_details list."""
        entries = self._simple_task_entries()
        result = extract_task_data_for_evaluation(entries)
        tasks = result["tasks"]
        assert len(tasks) >= 1
        task = tasks[0]
        assert "pattern_details" in task
        assert len(task["pattern_details"]) > 0

    # 3. Pattern detail structure
    def test_pattern_details_structure(self):
        """Each pattern detail has id, name, confidence, domain, section, helpful_votes, harmful_votes."""
        entries = self._simple_task_entries()
        result = extract_task_data_for_evaluation(entries)
        pd = result["tasks"][0]["pattern_details"][0]
        assert "id" in pd
        assert "name" in pd
        assert "confidence" in pd
        assert "domain" in pd
        assert "section" in pd
        assert "helpful_votes" in pd
        assert "harmful_votes" in pd

    # 4. Dedup by pattern ID, keep highest confidence
    def test_pattern_dedup_by_id(self):
        """Same pattern ID from two searches keeps only the highest confidence."""
        base = datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc)
        search1 = _make_search_event(
            base,
            patterns=[
                {"id": "ctx-dup", "confidence": 0.60, "domain": "auth",
                 "section": "strategies_and_hard_rules", "helpful": 1, "harmful": 0},
            ],
        )
        search2 = _make_search_event(
            base + timedelta(minutes=2),
            patterns=[
                {"id": "ctx-dup", "confidence": 0.90, "domain": "auth",
                 "section": "strategies_and_hard_rules", "helpful": 3, "harmful": 0},
            ],
        )
        execution = _make_exec_event(
            base + timedelta(minutes=5),
            pattern_ids=["ctx-dup"],
        )
        entries = [search1, search2, execution]
        result = extract_task_data_for_evaluation(entries)
        details = result["tasks"][0]["pattern_details"]
        dup_entries = [d for d in details if d["id"] == "ctx-dup"]
        assert len(dup_entries) == 1, "Should deduplicate by pattern ID"
        assert dup_entries[0]["confidence"] == 0.90, "Should keep highest confidence"

    # 5. Task without search has empty pattern_details
    def test_task_without_search_has_empty_details(self):
        """An execution-only task (no preceding search) has pattern_details=[]."""
        base = datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc)
        # Only execution, no search -- but split_into_tasks skips search-only
        # clusters, so we need at least an execution to form a task.
        execution = _make_exec_event(base, pattern_ids=[])
        result = extract_task_data_for_evaluation([execution])
        tasks = result["tasks"]
        assert len(tasks) >= 1
        assert tasks[0]["pattern_details"] == []

    # 6. Output includes top_patterns and trends keys
    def test_includes_top_patterns_and_trends(self):
        """Result dict must have top_patterns list and trends dict."""
        entries = self._simple_task_entries()
        result = extract_task_data_for_evaluation(entries)
        assert "top_patterns" in result
        assert isinstance(result["top_patterns"], list)
        assert "trends" in result
        assert isinstance(result["trends"], dict)

    # 7. Empty entries returns safe defaults
    def test_empty_entries(self):
        """Empty list returns empty tasks, zeroed metadata, and safe defaults."""
        result = extract_task_data_for_evaluation([])
        assert result["tasks"] == []
        assert result["metadata"]["total_entries"] == 0
        assert result["search_only_count"] == 0
        assert result["top_patterns"] == []
        assert isinstance(result["trends"], dict)

    # 8. Pattern name sourced from extract_pattern_names
    def test_pattern_name_from_extract(self):
        """pattern_details[].name matches extract_pattern_names() output."""
        entries = self._simple_task_entries()
        expected_names = extract_pattern_names(entries)
        result = extract_task_data_for_evaluation(entries)
        for pd in result["tasks"][0]["pattern_details"]:
            pid = pd["id"]
            if pid in expected_names:
                assert pd["name"] == expected_names[pid], (
                    f"Pattern {pid} name should match extract_pattern_names output"
                )


# =========================================================================
# TestGenerateEvaluatedHtml -- LLM-evaluated HTML report
# =========================================================================

class TestGenerateEvaluatedHtml:
    """Tests for generate_evaluated_html() function.

    Generates a self-contained HTML report with Claude's per-task
    helpfulness evaluations baked in.
    """

    # -- Helpers --

    def _make_task_data(self, tasks=None, top_patterns=None):
        """Create minimal task_data structure."""
        return {
            "metadata": {"generated_at": "2026-02-12T10:00:00Z", "hours": 24, "total_entries": 10, "duplicates_removed": 0},
            "tasks": tasks or [],
            "search_only_count": 0,
            "top_patterns": top_patterns or [],
            "trends": {"searches": {"current": 5, "previous": 3}, "tasks": {"current": 3, "previous": 2}, "success_rate": {"current": 80.0, "previous": 70.0}, "patterns_injected": {"current": 10, "previous": 8}},
        }

    def _make_task(self, task_id=1, prompt="Fix auth bug", success=True, start_time="2026-02-12T10:00:00Z", **kwargs):
        """Create minimal task."""
        return {
            "task_id": task_id, "user_prompt": prompt, "success": success,
            "start_time": start_time, "end_time": "2026-02-12T10:05:00Z",
            "duration_seconds": 300, "tools_executed": 15, "searches": 2,
            "patterns_injected": 5, "domains": ["auth"], "confidence_avg": 82.0,
            "agent_type": "main", "pattern_details": [],
            **kwargs,
        }

    def _make_evaluations(self, evals=None, overall_pct=75, summary="ACE was helpful."):
        """Create minimal evaluations structure."""
        return {
            "evaluations": evals or [],
            "overall_helpfulness_pct": overall_pct,
            "overall_summary": summary,
        }

    # -- Tests --

    def test_returns_valid_html(self):
        """Output starts with <!DOCTYPE html> and contains </html>."""
        task_data = self._make_task_data(tasks=[self._make_task()])
        evaluations = self._make_evaluations()
        html = generate_evaluated_html(task_data, evaluations)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_overall_helpfulness(self):
        """HTML contains the overall_helpfulness_pct value."""
        task_data = self._make_task_data(tasks=[self._make_task()])
        evaluations = self._make_evaluations(overall_pct=72)
        html = generate_evaluated_html(task_data, evaluations)
        assert "72" in html

    def test_contains_overall_summary(self):
        """HTML contains Claude's overall_summary text."""
        task_data = self._make_task_data(tasks=[self._make_task()])
        evaluations = self._make_evaluations(
            summary="ACE was helpful on 7 of 10 tasks, providing relevant domain-specific patterns."
        )
        html = generate_evaluated_html(task_data, evaluations)
        assert "ACE was helpful on 7 of 10 tasks" in html

    def test_task_card_shows_prompt(self):
        """HTML contains the user_prompt text (escaped)."""
        task_data = self._make_task_data(tasks=[self._make_task(prompt="Refactor the login module")])
        evaluations = self._make_evaluations()
        html = generate_evaluated_html(task_data, evaluations)
        assert "Refactor the login module" in html

    def test_task_card_shows_helpfulness_bar(self):
        """HTML contains helpfulness percentage per task."""
        task_data = self._make_task_data(tasks=[self._make_task(task_id=1)])
        evaluations = self._make_evaluations(
            evals=[{"task_id": 1, "helpfulness_pct": 85, "reasoning": "Patterns matched well."}]
        )
        html = generate_evaluated_html(task_data, evaluations)
        assert "85" in html

    def test_task_card_shows_reasoning(self):
        """HTML contains Claude's reasoning text per task."""
        task_data = self._make_task_data(tasks=[self._make_task(task_id=1)])
        evaluations = self._make_evaluations(
            evals=[{
                "task_id": 1,
                "helpfulness_pct": 90,
                "reasoning": "Auth patterns directly matched the authentication bug fix task.",
            }]
        )
        html = generate_evaluated_html(task_data, evaluations)
        assert "Auth patterns directly matched the authentication bug fix task." in html

    def test_xss_prevention(self):
        """HTML-escapes user prompts and reasoning containing <script> tags."""
        evil_prompt = '<script>alert("xss")</script>'
        evil_reasoning = '<img src=x onerror=alert(1)>'
        task_data = self._make_task_data(tasks=[self._make_task(task_id=1, prompt=evil_prompt)])
        evaluations = self._make_evaluations(
            evals=[{"task_id": 1, "helpfulness_pct": 50, "reasoning": evil_reasoning}]
        )
        html = generate_evaluated_html(task_data, evaluations)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html
        assert '<img src=x onerror' not in html
        assert "&lt;img src=x onerror" in html

    def test_tasks_ordered_newest_first(self):
        """Task with later start_time appears before earlier one in HTML."""
        old_task = self._make_task(task_id=1, prompt="Old task first", start_time="2026-02-12T08:00:00Z")
        new_task = self._make_task(task_id=2, prompt="New task second", start_time="2026-02-12T14:00:00Z")
        task_data = self._make_task_data(tasks=[old_task, new_task])
        evaluations = self._make_evaluations()
        html = generate_evaluated_html(task_data, evaluations)
        new_pos = html.find("New task second")
        old_pos = html.find("Old task first")
        assert new_pos != -1 and old_pos != -1, "Both tasks should appear in HTML"
        assert new_pos < old_pos, "Newer task should appear before older task"

    def test_graceful_without_evaluations(self):
        """When evaluations is None, still generates valid HTML."""
        task_data = self._make_task_data(tasks=[self._make_task()])
        html = generate_evaluated_html(task_data, None)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_task_without_matching_eval(self):
        """Task with no matching evaluation shows 'Not evaluated'."""
        task_data = self._make_task_data(tasks=[self._make_task(task_id=99)])
        evaluations = self._make_evaluations(
            evals=[{"task_id": 1, "helpfulness_pct": 80, "reasoning": "Good."}]
        )
        html = generate_evaluated_html(task_data, evaluations)
        assert "Not evaluated" in html

    def test_helpfulness_color_coding(self):
        """High % gets green class, low % gets red class."""
        high_task = self._make_task(task_id=1, prompt="High help task")
        low_task = self._make_task(task_id=2, prompt="Low help task")
        task_data = self._make_task_data(tasks=[high_task, low_task])
        evaluations = self._make_evaluations(
            evals=[
                {"task_id": 1, "helpfulness_pct": 90, "reasoning": "Great."},
                {"task_id": 2, "helpfulness_pct": 20, "reasoning": "Poor."},
            ]
        )
        html = generate_evaluated_html(task_data, evaluations)
        assert "help-green" in html or "#10b981" in html
        assert "help-red" in html or "#ef4444" in html

    def test_top_patterns_section(self):
        """HTML contains top patterns from task_data."""
        patterns = [
            {"pattern_id": "ctx-1", "usage_count": 5, "sessions": 2, "pattern_name": "auth / strategies"},
            {"pattern_id": "ctx-2", "usage_count": 3, "sessions": 1, "pattern_name": "cache / rules"},
        ]
        task_data = self._make_task_data(
            tasks=[self._make_task()],
            top_patterns=patterns,
        )
        evaluations = self._make_evaluations()
        html = generate_evaluated_html(task_data, evaluations)
        assert "auth / strategies" in html
        assert "cache / rules" in html


# ---------------------------------------------------------------------------
# ACE Status Command – jq template field validation (Issue: flat vs nested)
# ---------------------------------------------------------------------------

class TestAceStatusCommand:
    """Validate that ace-status.md jq template references correct API fields.

    The actual ``ace-cli status --json`` response nests playbook data under
    ``.playbook`` and subscription data under ``.subscription``.  Earlier
    versions of the jq template used flat root-level fields that never existed
    in the real response, causing every value to render as 0 / "Not configured".
    """

    ACE_STATUS_MD = (
        Path(__file__).parent.parent
        / "plugins"
        / "ace"
        / "commands"
        / "ace-status.md"
    )

    @pytest.fixture()
    def jq_block(self) -> str:
        """Extract the jq formatting block from ace-status.md (Step 3 only)."""
        content = self.ACE_STATUS_MD.read_text()
        # Target the STATUS_OUTPUT formatting jq block, not the auth jq line
        in_jq = False
        lines: list[str] = []
        for line in content.splitlines():
            if "STATUS_OUTPUT" in line and "jq -r" in line:
                in_jq = True
                lines.append(line)
                continue
            if in_jq:
                lines.append(line)
                # jq block ends at the closing single-quote line
                if line.strip() == "'":
                    break
        return "\n".join(lines)

    # -- 1. Total patterns must use nested path --------------------------

    def test_status_jq_references_playbook_total_patterns(self, jq_block: str):
        """jq must reference ``.playbook.total_patterns``, not ``.total_bullets``."""
        assert ".playbook.total_patterns" in jq_block, (
            "jq template should reference .playbook.total_patterns"
        )

    # -- 2. Section counts must be under .playbook.by_section ------------

    def test_status_jq_references_playbook_by_section(self, jq_block: str):
        """Section counts must be nested under ``.playbook.by_section``."""
        assert ".playbook.by_section.strategies_and_hard_rules" in jq_block, (
            "jq template should reference .playbook.by_section.strategies_and_hard_rules"
        )
        assert ".playbook.by_section.useful_code_snippets" in jq_block
        assert ".playbook.by_section.troubleshooting_and_pitfalls" in jq_block
        assert ".playbook.by_section.apis_to_use" in jq_block

    # -- 3. No legacy flat .total_bullets --------------------------------

    def test_status_jq_no_flat_total_bullets(self, jq_block: str):
        """``.total_bullets`` must NOT appear -- it was never in the API."""
        assert ".total_bullets" not in jq_block, (
            "jq template must not reference the non-existent .total_bullets field"
        )

    # -- 4. No flat .org_id (not in API response) ------------------------

    def test_status_jq_no_flat_org_id(self, jq_block: str):
        """``.org_id`` must NOT appear -- the status API does not return it."""
        assert ".org_id" not in jq_block, (
            "jq template must not reference .org_id (not in ace-cli status response)"
        )

    # -- 5. Helpful / harmful for confidence calculation -----------------

    def test_status_jq_references_helpful_harmful(self, jq_block: str):
        """Confidence should be computed from ``.playbook.helpful_total`` and
        ``.playbook.harmful_total``."""
        assert ".playbook.helpful_total" in jq_block, (
            "jq template should reference .playbook.helpful_total"
        )
        assert ".playbook.harmful_total" in jq_block, (
            "jq template should reference .playbook.harmful_total"
        )
