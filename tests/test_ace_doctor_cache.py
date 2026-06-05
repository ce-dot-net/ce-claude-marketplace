"""
RED tests for #32 — ace-doctor.md: accurate cache diagnostics section.

These tests assert that ace-doctor.md contains a Check 9 (Cache Diagnostics)
section documenting the TWO distinct caches and the behaviour of `cache clear`.

All tests are expected to FAIL until Check 9 is added to the command file.
"""

from pathlib import Path

ACE_DOCTOR_MD = (
    Path(__file__).parent.parent
    / "plugins"
    / "ace"
    / "commands"
    / "ace-doctor.md"
)


def _content() -> str:
    return ACE_DOCTOR_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Structural: Check 9 exists
# ---------------------------------------------------------------------------

def test_check_9_heading_present():
    """ace-doctor.md must contain a Check 9 heading for Cache Diagnostics."""
    content = _content()
    assert "Check 9" in content, (
        "ace-doctor.md is missing a 'Check 9' section — "
        "add Check 9: Cache Diagnostics (issue #32)"
    )


def test_cache_diagnostics_section_present():
    """ace-doctor.md must have a cache diagnostics section."""
    content = _content()
    assert "Cache Diagnostics" in content or "cache diagnostics" in content.lower(), (
        "ace-doctor.md is missing a Cache Diagnostics section (issue #32)"
    )


# ---------------------------------------------------------------------------
# In-memory cache (client-side LRU)
# ---------------------------------------------------------------------------

def test_in_memory_cache_mentioned():
    """Check 9 must explicitly mention the in-memory client cache."""
    content = _content()
    assert "in-memory" in content.lower(), (
        "ace-doctor.md does not mention the in-memory cache "
        "(issue #32: two distinct caches must be documented)"
    )


def test_cache_clear_section_present():
    """Check 9 must reference `cache clear` so users know what it clears."""
    content = _content()
    assert "cache clear" in content.lower(), (
        "ace-doctor.md does not mention 'cache clear' in the cache diagnostics "
        "(issue #32)"
    )


def test_cache_clear_only_clears_in_memory():
    """Check 9 must note that cache clear only clears the in-memory cache in 4.0.1."""
    content = _content()
    lower = content.lower()
    # The section must warn that cache clear does NOT clear the SQLite graph cache
    assert "only" in lower and "in-memory" in lower, (
        "ace-doctor.md does not note that 'cache clear' only clears the "
        "in-memory cache (not SQLite) in ace-cli 4.0.1 (issue #32)"
    )


# ---------------------------------------------------------------------------
# SQLite graph cache
# ---------------------------------------------------------------------------

def test_ace_cache_path_mentioned():
    """Check 9 must document the ~/.ace-cache/ path for the SQLite graph cache."""
    content = _content()
    assert "~/.ace-cache" in content, (
        "ace-doctor.md does not mention ~/.ace-cache path (issue #32)"
    )


def test_sqlite_graph_cache_mentioned():
    """Check 9 must mention the SQLite graph cache (org__project.db pattern)."""
    content = _content()
    lower = content.lower()
    assert "sqlite" in lower or ".db" in lower, (
        "ace-doctor.md does not mention the SQLite graph cache (.db file) "
        "(issue #32)"
    )


def test_seven_day_ttl_mentioned():
    """Check 9 must document the 7-day TTL on the SQLite graph cache."""
    content = _content()
    assert "7-day" in content or "7 day" in content.lower() or "7day" in content.lower(), (
        "ace-doctor.md does not document the 7-day TTL of the SQLite graph cache "
        "(issue #32)"
    )


def test_sqlite_not_cleared_by_cache_clear():
    """Check 9 must explicitly note that the SQLite graph cache is NOT cleared by cache clear."""
    content = _content()
    lower = content.lower()
    # Must say SQLite/graph cache is NOT cleared by cache clear
    has_not_cleared = (
        ("not cleared" in lower or "does not clear" in lower or "not clear" in lower)
        and ("sqlite" in lower or "graph cache" in lower or ".db" in lower)
    )
    assert has_not_cleared, (
        "ace-doctor.md does not explicitly state that the SQLite graph cache "
        "is NOT cleared by 'cache clear' (issue #32)"
    )


# ---------------------------------------------------------------------------
# Session recall DB
# ---------------------------------------------------------------------------

def test_sessions_db_mentioned():
    """Check 9 must document the sessions.db at ~/.ace-cache/sessions.db."""
    content = _content()
    assert "sessions.db" in content, (
        "ace-doctor.md does not mention sessions.db (issue #32)"
    )


def test_sessions_db_path_is_correct():
    """sessions.db must be referenced with the full ~/.ace-cache/sessions.db path."""
    content = _content()
    assert "~/.ace-cache/sessions.db" in content or (
        "~/.ace-cache" in content and "sessions.db" in content
    ), (
        "ace-doctor.md does not document ~/.ace-cache/sessions.db path (issue #32)"
    )


# ---------------------------------------------------------------------------
# Final report format includes Check 9
# ---------------------------------------------------------------------------

def test_final_report_includes_check_9():
    """The Final Report Format example must include a [9] Cache Diagnostics line."""
    content = _content()
    assert "[9]" in content, (
        "ace-doctor.md Final Report Format does not include a [9] line for "
        "Cache Diagnostics (issue #32)"
    )
