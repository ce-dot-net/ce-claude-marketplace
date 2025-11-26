#!/usr/bin/env python3
"""
Integration tests for ACE v5.2.0 Per-Task + Delta Learning Architecture

Tests the complete hook chain:
1. get_task_messages() - Per-task parsing from last user prompt
2. Position tracking - PreCompact records, Stop uses delta
3. filter_garbage_trajectory() - Client-side garbage filtering
4. skip_learning() - User feedback on skip
5. has_substantial_work() - Relaxed min_steps for delta
"""

import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'shared-hooks'))

from ace_after_task import (
    get_task_messages,
    filter_garbage_trajectory,
    skip_learning,
    has_substantial_work,
    record_captured_position,
    get_captured_position,
    clear_captured_position,
    POSITION_STATE_FILE
)


def test_get_task_messages():
    """Test per-task parsing from last user prompt."""
    print("\n📝 Testing get_task_messages()...")

    # Create a mock transcript
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        # User message 1 (old task)
        f.write(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "First task - implement auth"}
        }) + '\n')

        # Assistant response
        f.write(json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "content": "I'll implement auth..."}
        }) + '\n')

        # User message 2 (current task) - THIS is the task boundary
        f.write(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "Now implement JWT tokens"}
        }) + '\n')

        # Assistant work on current task
        f.write(json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "content": "Implementing JWT..."}
        }) + '\n')
        f.write(json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "content": "JWT implementation complete!"}
        }) + '\n')

        transcript_path = f.name

    # Test parsing
    task_messages, user_prompt, last_idx = get_task_messages(transcript_path)

    # Verify results
    assert len(task_messages) == 2, f"Expected 2 messages after last user prompt, got {len(task_messages)}"
    assert "JWT tokens" in user_prompt, f"Expected user prompt to contain 'JWT tokens', got: {user_prompt}"
    assert last_idx == 2, f"Expected last user message at index 2, got {last_idx}"

    # Cleanup
    Path(transcript_path).unlink()
    print("  ✅ get_task_messages() correctly parses from last user prompt")


def test_position_tracking():
    """Test position-based delta tracking."""
    print("\n📝 Testing position tracking...")

    # Clean up any existing state
    if POSITION_STATE_FILE.exists():
        POSITION_STATE_FILE.unlink()

    session_id = "test-session-123"

    # Record position (simulating PreCompact)
    record_captured_position(session_id, 20, 'precompact')

    # Get position (simulating Stop)
    position = get_captured_position(session_id)
    assert position == 20, f"Expected position 20, got {position}"

    # Clear position
    clear_captured_position(session_id)

    # Verify cleared
    position = get_captured_position(session_id)
    assert position == 0, f"Expected position 0 after clear, got {position}"

    print("  ✅ Position tracking works correctly")


def test_filter_garbage_trajectory():
    """Test client-side garbage filtering."""
    print("\n📝 Testing filter_garbage_trajectory()...")

    trajectory = [
        # Should be FILTERED (empty description)
        {'action': 'Edit - ', 'result': 'done'},
        {'action': 'Write - ', 'result': 'done'},
        {'action': 'Bash - ls', 'result': 'files'},  # Too short (< 5 chars)
        {'action': 'Short', 'result': 'x'},  # Too short (< 10 chars)

        # Should be KEPT
        {'action': 'Edit - Updated authentication module with JWT', 'result': 'success'},
        {'action': 'Write - Created new config file for tokens', 'result': 'created'},
        {'action': 'Made architectural decisions about auth', 'result': 'Used JWT for auth'},
    ]

    filtered = filter_garbage_trajectory(trajectory)

    assert len(filtered) == 3, f"Expected 3 filtered items, got {len(filtered)}"
    assert all('- ' not in step['action'] or len(step['action'].split(' - ', 1)[1].strip()) >= 5
               for step in filtered), "Filtered trajectory contains garbage"

    print("  ✅ filter_garbage_trajectory() correctly filters garbage")


def test_skip_learning():
    """Test user feedback on skip."""
    print("\n📝 Testing skip_learning()...")

    result = skip_learning("No substantial work", None)

    assert result['continue'] == True, "Expected continue=True"
    assert '[ACE]' in result['systemMessage'], "Expected [ACE] tag in message"
    assert 'No substantial work' in result['systemMessage'], "Expected reason in message"

    print("  ✅ skip_learning() returns proper feedback structure")


def test_has_substantial_work_min_steps():
    """Test relaxed min_steps for delta captures."""
    print("\n📝 Testing has_substantial_work() with min_steps...")

    # Trace with only 1 step
    trace = {
        'task': 'User request: Implement feature',
        'trajectory': [
            {'step': 1, 'action': 'Made decisions about implementation', 'result': 'Decided approach'}
        ],
        'result': {
            'success': True,
            'output': 'Long output with lessons learned ' * 20  # > 200 chars
        }
    }

    # With default min_steps=2, should FAIL (only 1 step)
    assert has_substantial_work(trace, min_steps=2) == False, "Should fail with min_steps=2"

    # With min_steps=1 (for delta), should PASS
    assert has_substantial_work(trace, min_steps=1) == True, "Should pass with min_steps=1"

    print("  ✅ has_substantial_work() respects min_steps parameter")


def test_delta_learning_scenario():
    """Test complete delta learning scenario."""
    print("\n📝 Testing complete delta learning scenario...")

    # Clean up state
    if POSITION_STATE_FILE.exists():
        POSITION_STATE_FILE.unlink()

    session_id = "delta-test-session"

    # Scenario:
    # 1. PreCompact fires at step 20
    # 2. Stop fires at step 25
    # 3. Stop should capture delta (steps 21-25)

    # Step 1: PreCompact records position
    record_captured_position(session_id, 20, 'precompact')
    print("  📌 PreCompact recorded position: 20")

    # Step 2: Stop checks position
    last_position = get_captured_position(session_id)
    current_position = 25  # Simulated current task messages

    assert last_position == 20, f"Expected last position 20, got {last_position}"

    # Step 3: Calculate delta
    if last_position > 0 and last_position < current_position:
        delta = current_position - last_position
        print(f"  📊 Delta detected: {delta} new steps (positions {last_position+1} to {current_position})")
        assert delta == 5, f"Expected delta 5, got {delta}"

    # Step 4: Clear position after Stop
    clear_captured_position(session_id)

    print("  ✅ Complete delta learning scenario works correctly")


def run_all_tests():
    """Run all integration tests."""
    print("=" * 60)
    print("ACE v5.2.0 Per-Task + Delta Learning Integration Tests")
    print("=" * 60)

    tests = [
        test_get_task_messages,
        test_position_tracking,
        test_filter_garbage_trajectory,
        test_skip_learning,
        test_has_substantial_work_min_steps,
        test_delta_learning_scenario,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
