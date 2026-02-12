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
    get_top_patterns,
    calculate_trends,
    format_insights_report,
    format_insights_html,
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
        """The command must contain a bash code block with the actual script."""
        import re
        bash_blocks = re.findall(r'```bash\n(.*?)```', insights_content, re.DOTALL)
        assert len(bash_blocks) >= 1, "ace-insights.md must contain at least one bash code block"

        # The main script block should have shebang and set -euo pipefail
        main_script = bash_blocks[0]
        assert "#!/usr/bin/env bash" in main_script, (
            "Main bash block must start with #!/usr/bin/env bash"
        )
        assert "set -euo pipefail" in main_script, (
            "Main bash block must contain 'set -euo pipefail' for safe execution"
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
        """The bash script must contain the Python analyzer call that generates the HTML report."""
        assert "ace_insights_analyzer" in insights_content, (
            "Bash script must import from ace_insights_analyzer module"
        )
        assert "format_insights_html" in insights_content, (
            "Bash script must call format_insights_html to generate the HTML report"
        )
        assert "format_insights_report" in insights_content, (
            "Bash script must call format_insights_report to generate the text summary"
        )
