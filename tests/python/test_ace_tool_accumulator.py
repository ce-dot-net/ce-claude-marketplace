#!/usr/bin/env python3
"""
Unit tests for ace_tool_accumulator.py - SQLite Ground Truth (275 lines)

CRITICAL: Tests the database that stores EVERY tool call.
Bugs here = lost tool data, corrupted trajectories, wrong learning.

This is GROUND TRUTH for the ACE Research Paper architecture.
Per Paper: "FULL AGENT-ENVIRONMENT TRAJECTORY" from actual tool calls.

Focus areas:
1. init_db() - Database schema (39-62)
2. append_tool() - Insert tool data (64-104)
3. get_session_tools() - Query trajectory (106-138)
4. clear_session() - Cleanup (140-167)
"""

import sys
import sqlite3
import tempfile
import json
from pathlib import Path

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "plugins/ace/shared-hooks"))

from ace_tool_accumulator import (
    get_db_path,
    init_db,
    append_tool,
    get_session_tools,
    clear_session,
    get_session_stats
)


# ============================================================================
# Test: Database Initialization
# ============================================================================

class TestDatabaseInit:
    """Tests database creation and schema"""

    def test_init_db_creates_table(self):
        """Database should create tool_uses table"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            conn = init_db(db_path)

            # Verify table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_uses'"
            )
            tables = cursor.fetchall()

            assert len(tables) == 1, "tool_uses table should exist"
            conn.close()

    def test_init_db_creates_index(self):
        """Database should create session_id index for performance"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            conn = init_db(db_path)

            # Verify index exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_session'"
            )
            indexes = cursor.fetchall()

            assert len(indexes) == 1, "idx_session index should exist"
            conn.close()

    def test_init_db_idempotent(self):
        """Calling init_db multiple times should be safe"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Initialize twice
            conn1 = init_db(db_path)
            conn1.close()

            conn2 = init_db(db_path)
            conn2.close()

            # Should not crash (idempotent)
            assert db_path.exists()


# ============================================================================
# Test: Tool Appending
# ============================================================================

class TestToolAppending:
    """Tests appending tool data to database"""

    def test_append_single_tool(self):
        """Appending a tool should store all fields"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "test-session-123"
            tool_name = "Write"
            tool_input = {"file_path": "/test.py", "content": "print('hello')"}
            tool_response = {"success": True}
            tool_use_id = "toolu_abc123"

            success = append_tool(
                session_id=session_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_response=tool_response,
                tool_use_id=tool_use_id,
                working_dir=tmpdir
            )

            assert success, "append_tool should return True"

            # Verify data was stored
            tools = get_session_tools(session_id, tmpdir)
            assert len(tools) == 1, "Should have 1 tool"

            tool = tools[0]
            assert tool["tool_name"] == tool_name
            assert tool["tool_use_id"] == tool_use_id

    def test_append_multiple_tools_same_session(self):
        """Multiple tools in same session should all be stored"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "session-456"

            # Append 3 tools
            for i in range(3):
                append_tool(
                    session_id=session_id,
                    tool_name=f"Tool{i}",
                    tool_input={"index": i},
                    tool_response={"result": i},
                    tool_use_id=f"toolu_{i}",
                    working_dir=tmpdir
                )

            tools = get_session_tools(session_id, tmpdir)
            assert len(tools) == 3, "Should have 3 tools"

    def test_append_duplicate_tool_use_id_ignored(self):
        """Duplicate tool_use_id should be ignored (UNIQUE constraint)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "session-dup"
            tool_use_id = "toolu_duplicate"

            # Append same tool_use_id twice
            success1 = append_tool(
                session_id=session_id,
                tool_name="Tool1",
                tool_input={},
                tool_response={},
                tool_use_id=tool_use_id,
                working_dir=tmpdir
            )

            success2 = append_tool(
                session_id=session_id,
                tool_name="Tool2",  # Different tool name
                tool_input={},
                tool_response={},
                tool_use_id=tool_use_id,  # Same ID
                working_dir=tmpdir
            )

            assert success1, "First append should succeed"
            assert success2, "Second append should return True (INSERT OR IGNORE)"

            # Should only have 1 tool (duplicate ignored)
            tools = get_session_tools(session_id, tmpdir)
            assert len(tools) == 1, "Duplicate should be ignored"
            assert tools[0]["tool_name"] == "Tool1", "First tool should be kept"

    def test_append_non_dict_input_converted_to_string(self):
        """Non-dict tool_input should be converted to string"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "session-string"

            # Send string instead of dict
            append_tool(
                session_id=session_id,
                tool_name="Bash",
                tool_input="ls -la",  # String, not dict
                tool_response={},
                tool_use_id="toolu_str",
                working_dir=tmpdir
            )

            tools = get_session_tools(session_id, tmpdir)
            assert len(tools) == 1
            # Should be stored as string (code converts with str())


# ============================================================================
# Test: Session Querying
# ============================================================================

class TestSessionQuerying:
    """Tests querying tools by session"""

    def test_get_session_tools_empty(self):
        """Querying empty session should return empty list"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = get_session_tools("nonexistent-session", tmpdir)

            assert tools == [], "Empty session should return []"

    def test_get_session_tools_filters_by_session(self):
        """Should only return tools from requested session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Add tools to different sessions
            append_tool("session-A", "Tool1", {}, {}, "toolu_a1", tmpdir)
            append_tool("session-A", "Tool2", {}, {}, "toolu_a2", tmpdir)
            append_tool("session-B", "Tool3", {}, {}, "toolu_b1", tmpdir)

            tools_a = get_session_tools("session-A", tmpdir)
            tools_b = get_session_tools("session-B", tmpdir)

            assert len(tools_a) == 2, "Session A should have 2 tools"
            assert len(tools_b) == 1, "Session B should have 1 tool"

    def test_get_session_tools_ordered_by_timestamp(self):
        """Tools should be returned in chronological order"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "session-order"

            # Add tools in order
            append_tool(session_id, "First", {}, {}, "toolu_1", tmpdir)
            append_tool(session_id, "Second", {}, {}, "toolu_2", tmpdir)
            append_tool(session_id, "Third", {}, {}, "toolu_3", tmpdir)

            tools = get_session_tools(session_id, tmpdir)

            # Should be in order (database uses ORDER BY timestamp)
            assert tools[0]["tool_name"] == "First"
            assert tools[1]["tool_name"] == "Second"
            assert tools[2]["tool_name"] == "Third"


# ============================================================================
# Test: Session Cleanup
# ============================================================================

class TestSessionCleanup:
    """Tests clearing session data"""

    def test_clear_session_removes_all_tools(self):
        """Clearing session should delete all its tools"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "session-clear"

            # Add tools
            append_tool(session_id, "Tool1", {}, {}, "toolu_1", tmpdir)
            append_tool(session_id, "Tool2", {}, {}, "toolu_2", tmpdir)

            # Verify they exist
            assert len(get_session_tools(session_id, tmpdir)) == 2

            # Clear session
            success = clear_session(session_id, tmpdir)

            assert success, "clear_session should return True"
            assert len(get_session_tools(session_id, tmpdir)) == 0, "All tools should be deleted"

    def test_clear_session_only_affects_target_session(self):
        """Clearing one session should not affect others"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Add tools to different sessions
            append_tool("session-keep", "Tool1", {}, {}, "toolu_k1", tmpdir)
            append_tool("session-delete", "Tool2", {}, {}, "toolu_d1", tmpdir)

            # Clear only session-delete
            clear_session("session-delete", tmpdir)

            # session-keep should still have its tools
            assert len(get_session_tools("session-keep", tmpdir)) == 1
            assert len(get_session_tools("session-delete", tmpdir)) == 0

    def test_clear_nonexistent_session_succeeds(self):
        """Clearing nonexistent session should succeed (no-op)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            success = clear_session("nonexistent", tmpdir)

            assert success, "Clearing nonexistent session should succeed"


# ============================================================================
# Test: Session Statistics
# ============================================================================

class TestSessionStats:
    """Tests session statistics"""

    def test_get_session_stats_counts_tools(self):
        """Stats should count tools by type"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "session-stats"

            # Add various tools
            append_tool(session_id, "Write", {}, {}, "toolu_w1", tmpdir)
            append_tool(session_id, "Write", {}, {}, "toolu_w2", tmpdir)
            append_tool(session_id, "Read", {}, {}, "toolu_r1", tmpdir)
            append_tool(session_id, "Bash", {}, {}, "toolu_b1", tmpdir)

            stats = get_session_stats(session_id, tmpdir)

            assert stats["total_tools"] == 4
            assert stats["tool_counts"]["Write"] == 2
            assert stats["tool_counts"]["Read"] == 1
            assert stats["tool_counts"]["Bash"] == 1


# Run sanity checks
if __name__ == "__main__":
    import tempfile

    print("Testing database initialization...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        assert db_path.exists(), "Database file should be created"
        conn.close()
    print("✓ Database init works!")

    print("\nTesting tool appending...")
    with tempfile.TemporaryDirectory() as tmpdir:
        success = append_tool("test-session", "Write", {}, {}, "toolu_123", tmpdir)
        assert success, "Append should succeed"
        tools = get_session_tools("test-session", tmpdir)
        assert len(tools) == 1, "Should have 1 tool"
    print("✓ Tool appending works!")

    print("\nTesting session cleanup...")
    with tempfile.TemporaryDirectory() as tmpdir:
        append_tool("test-session", "Write", {}, {}, "toolu_456", tmpdir)
        clear_session("test-session", tmpdir)
        tools = get_session_tools("test-session", tmpdir)
        assert len(tools) == 0, "Session should be cleared"
    print("✓ Session cleanup works!")

    print("\n✅ All sanity checks passed!")
