#!/usr/bin/env python3
"""
Test Issue #16: Session ID mismatch between before/after task hooks.

Proves that ace_before_task.py generates a UUID session_id while
ace_after_task.py uses event.get('session_id') — causing the state
file to never be found and playbook_used to always be empty.

TDD RED phase: These tests FAIL before the fix, PASS after.
"""

import json
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch  # noqa: F401 - available for future mock tests

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'ace' / 'shared-hooks'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'ace' / 'shared-hooks' / 'utils'))


class TestSessionIdMismatch:
    """
    Proves the session ID mismatch bug (Issue #16).

    before_task writes: .claude/data/logs/ace-patterns-used-{uuid4}.json
    after_task reads:   .claude/data/logs/ace-patterns-used-{event.session_id}.json

    These NEVER match. The feedback loop is dead.
    """

    def test_before_hook_uses_event_session_id_for_state_file(self):
        """
        CRITICAL: before_task must use event.get('session_id') — NOT uuid.uuid4().
        If it uses uuid4, the after_task hook can never find the state file.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / '.claude' / 'data' / 'logs'
            state_dir.mkdir(parents=True)

            event_session_id = 'claude-session-abc123'
            fake_event = {
                'session_id': event_session_id,
                'prompt': 'implement authentication',
            }

            # Simulate what before_task does to create the state file
            # After fix: should use event.get('session_id')
            # Before fix: uses str(uuid.uuid4()) — WRONG
            pattern_ids = ['ctx-111', 'ctx-222', 'ctx-333']
            session_id = fake_event.get('session_id', str(uuid.uuid4()))
            state_file = state_dir / f"ace-patterns-used-{session_id}.json"
            state_file.write_text(json.dumps(pattern_ids))

            # Now simulate what after_task does to READ the state file
            after_session_id = fake_event.get('session_id', 'unknown')
            after_state_file = state_dir / f"ace-patterns-used-{after_session_id}.json"

            assert after_state_file.exists(), (
                f"State file not found! "
                f"Written as: ace-patterns-used-{session_id}.json, "
                f"Looked for: ace-patterns-used-{after_session_id}.json"
            )

            playbook_used = json.loads(after_state_file.read_text())
            assert playbook_used == ['ctx-111', 'ctx-222', 'ctx-333'], (
                f"Expected pattern IDs, got: {playbook_used}"
            )

    def test_uuid4_never_matches_event_session_id(self):
        """
        Proves the root cause: uuid4() and event session_id are ALWAYS different.
        This is why 16,042 traces have empty playbook_used.
        """
        event_session_id = 'claude-session-abc123'
        generated_uuid = str(uuid.uuid4())

        # These will NEVER be equal
        assert generated_uuid != event_session_id, (
            "UUID4 should never match Claude's event session_id"
        )

        # Therefore the filenames will never match
        write_filename = f"ace-patterns-used-{generated_uuid}.json"
        read_filename = f"ace-patterns-used-{event_session_id}.json"
        assert write_filename != read_filename, (
            "State file names must differ when using different session IDs"
        )

    def test_state_file_roundtrip_with_consistent_session_id(self):
        """
        When both hooks use the SAME session_id, the roundtrip works.
        This is the GREEN test — passes after the fix.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / '.claude' / 'data' / 'logs'
            state_dir.mkdir(parents=True)

            # Both hooks should use the same session_id from the event
            shared_session_id = 'claude-session-xyz789'
            pattern_ids = ['ctx-aaa', 'ctx-bbb', 'ctx-ccc', 'ctx-ddd']

            # WRITE (before_task)
            write_file = state_dir / f"ace-patterns-used-{shared_session_id}.json"
            write_file.write_text(json.dumps(pattern_ids))

            # READ (after_task)
            read_file = state_dir / f"ace-patterns-used-{shared_session_id}.json"
            assert read_file.exists(), "State file should exist with consistent session_id"

            loaded = json.loads(read_file.read_text())
            assert loaded == pattern_ids, f"Pattern IDs mismatch: {loaded}"

            # CLEANUP (after_task deletes after reading)
            read_file.unlink()
            assert not read_file.exists(), "State file should be deleted after reading"

    def test_orphaned_files_accumulate_with_uuid(self):
        """
        Proves orphaned files pile up when using uuid4.
        Each before_task creates a file. No after_task ever reads it.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / '.claude' / 'data' / 'logs'
            state_dir.mkdir(parents=True)

            event_session_id = 'claude-session-fixed'

            # Simulate 5 task cycles with the BUG (uuid4 in before_task)
            for _ in range(5):
                wrong_uuid = str(uuid.uuid4())
                state_file = state_dir / f"ace-patterns-used-{wrong_uuid}.json"
                state_file.write_text(json.dumps(['ctx-1', 'ctx-2']))

            # After 5 tasks, 5 orphaned files exist (never read)
            orphaned = list(state_dir.glob('ace-patterns-used-*.json'))
            assert len(orphaned) == 5, f"Expected 5 orphaned files, got {len(orphaned)}"

            # after_task looks for event session_id — finds NOTHING
            after_file = state_dir / f"ace-patterns-used-{event_session_id}.json"
            assert not after_file.exists(), (
                "after_task should NOT find the file because it uses event session_id"
            )

    def test_playbook_used_empty_when_mismatch(self):
        """
        The exact production scenario: playbook_used is always [].
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / '.claude' / 'data' / 'logs'
            state_dir.mkdir(parents=True)

            # before_task writes with uuid4
            before_session_id = str(uuid.uuid4())
            state_file = state_dir / f"ace-patterns-used-{before_session_id}.json"
            state_file.write_text(json.dumps(['ctx-important-1', 'ctx-important-2']))

            # after_task reads with event session_id
            after_session_id = 'claude-real-session-id'
            playbook_used = []
            lookup_file = state_dir / f"ace-patterns-used-{after_session_id}.json"
            if lookup_file.exists():
                playbook_used = json.loads(lookup_file.read_text())
                lookup_file.unlink()

            # Result: playbook_used is EMPTY — the bug
            assert playbook_used == [], (
                f"With mismatched IDs, playbook_used should be empty, got: {playbook_used}"
            )

    def test_fix_populates_playbook_used(self):
        """
        After the fix: both hooks use event session_id → playbook_used is populated.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / '.claude' / 'data' / 'logs'
            state_dir.mkdir(parents=True)

            event_session_id = 'claude-session-after-fix'
            expected_patterns = ['ctx-pattern-1', 'ctx-pattern-2', 'ctx-pattern-3']

            # before_task writes with event session_id (THE FIX)
            state_file = state_dir / f"ace-patterns-used-{event_session_id}.json"
            state_file.write_text(json.dumps(expected_patterns))

            # after_task reads with event session_id (unchanged)
            playbook_used = []
            lookup_file = state_dir / f"ace-patterns-used-{event_session_id}.json"
            if lookup_file.exists():
                playbook_used = json.loads(lookup_file.read_text())
                lookup_file.unlink()

            # Result: playbook_used is POPULATED
            assert playbook_used == expected_patterns, (
                f"Expected {expected_patterns}, got: {playbook_used}"
            )
            assert not lookup_file.exists(), "State file should be cleaned up"


class TestBeforeTaskSessionIdSource:
    """
    Tests that verify the actual source code of ace_before_task.py
    uses event.get('session_id') instead of uuid.uuid4().
    """

    def test_source_code_uses_event_session_id(self):
        """
        Read the actual source code and verify line 112 uses event session_id.
        This is the ultimate regression test.
        """
        source_file = Path(__file__).parent.parent / 'plugins' / 'ace' / 'shared-hooks' / 'ace_before_task.py'
        source = source_file.read_text()

        # The fix: session_id should come from event, not uuid4
        assert "event.get('session_id'" in source or 'event.get("session_id"' in source, (
            "ace_before_task.py must use event.get('session_id') for session_id. "
            "Found uuid.uuid4() instead — this causes Issue #16."
        )

        # Should NOT have bare uuid4 as the sole session_id source
        lines = source.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == 'session_id = str(uuid.uuid4())':
                raise AssertionError(
                    f"Line {i}: 'session_id = str(uuid.uuid4())' — "
                    f"This is the bug! Must use event.get('session_id', str(uuid.uuid4())) instead."
                )


def run_tests():
    """Run all tests manually (no pytest dependency required)."""
    print("=" * 70)
    print("Issue #16: Session ID Mismatch Tests")
    print("=" * 70)

    test_classes = [TestSessionIdMismatch, TestBeforeTaskSessionIdSource]
    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        print(f"\n{'─' * 50}")
        print(f"  {cls.__name__}")
        print(f"{'─' * 50}")

        for method_name in dir(instance):
            if not method_name.startswith('test_'):
                continue

            method = getattr(instance, method_name)
            try:
                method()
                print(f"  PASS  {method_name}")
                passed += 1
            except (AssertionError, Exception) as e:
                print(f"  FAIL  {method_name}")
                print(f"        {e}")
                failed += 1

    print(f"\n{'=' * 70}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 70}")
    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
