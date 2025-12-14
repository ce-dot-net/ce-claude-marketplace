#!/usr/bin/env python3
"""
Test async learning hook behavior (TDD for issue #3)

Tests verify that:
1. Learning hook returns quickly (<2s)
2. ce-ace learn runs in background
3. Status is written to temp file
4. Deferred feedback is shown in next session
"""

import json
import sys
import tempfile
import time
import subprocess
from pathlib import Path
from datetime import datetime

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'shared-hooks'))


def test_hook_returns_quickly():
    """Test that hook returns in <2 seconds (was 66s)."""
    print("\n📝 Testing hook returns quickly (<2s)...")

    # This test will FAIL initially because current implementation is synchronous
    # Expected: <2s return time
    # Actual (before fix): ~66s

    # Create mock event
    mock_event = {
        "hook_event_name": "Stop",
        "session_id": "test-async-123",
        "transcript_path": "/tmp/test-transcript.jsonl",
        "cwd": str(Path.cwd())
    }

    # Write mock transcript
    transcript_path = Path(mock_event["transcript_path"])
    with open(transcript_path, 'w') as f:
        # User prompt
        f.write(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "Implement async learning"}
        }) + '\n')
        # Assistant response
        f.write(json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "content": "Implementing..."}
        }) + '\n')

    # Measure execution time
    start = time.time()

    # FIXME: This will call the CURRENT (blocking) implementation
    # After fix, it should return quickly
    try:
        result = subprocess.run(
            ['uv', 'run', str(Path(__file__).parent.parent / 'shared-hooks' / 'ace_after_task.py')],
            input=json.dumps(mock_event),
            text=True,
            capture_output=True,
            timeout=5  # Should finish in <2s, but allow 5s buffer
        )

        elapsed = time.time() - start

        print(f"  ⏱️  Hook execution time: {elapsed:.1f}s")

        # Assertion: Should return in <2s
        assert elapsed < 2.0, f"Hook took {elapsed:.1f}s (expected <2s)"

        print("  ✅ Hook returns quickly (<2s) - PASSED")
        return True

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"  ❌ Hook timed out after {elapsed:.1f}s - FAILED (expected <2s)")
        return False
    finally:
        # Cleanup
        transcript_path.unlink(missing_ok=True)


def test_background_process_runs():
    """Test that ce-ace learn runs in background."""
    print("\n📝 Testing background process runs...")

    # This test will FAIL initially because we haven't implemented background execution
    # Expected: Background process running after hook returns
    # Actual: No background process (synchronous execution)

    # Create status file path
    status_file = Path("/tmp/ace-learning-status-test-async-123.json")
    status_file.unlink(missing_ok=True)

    # Mock event
    mock_event = {
        "hook_event_name": "Stop",
        "session_id": "test-async-123",
        "transcript_path": "/tmp/test-transcript-bg.jsonl",
        "cwd": str(Path.cwd())
    }

    # Write mock transcript
    transcript_path = Path(mock_event["transcript_path"])
    with open(transcript_path, 'w') as f:
        f.write(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "Test background execution"}
        }) + '\n')

    # Run hook
    try:
        result = subprocess.run(
            ['uv', 'run', str(Path(__file__).parent.parent / 'shared-hooks' / 'ace_after_task.py')],
            input=json.dumps(mock_event),
            text=True,
            capture_output=True,
            timeout=5
        )

        # After hook returns, check if status file was created
        # (Background process should create it)
        time.sleep(0.5)  # Give background process time to start

        if status_file.exists():
            status = json.loads(status_file.read_text())
            print(f"  ✅ Background process created status file")
            print(f"     Status: {status.get('state', 'unknown')}")
            return True
        else:
            print(f"  ❌ No status file found - background process not running")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ❌ Hook timed out - can't verify background process")
        return False
    finally:
        # Cleanup
        transcript_path.unlink(missing_ok=True)
        status_file.unlink(missing_ok=True)


def test_status_file_format():
    """Test that status file has correct format."""
    print("\n📝 Testing status file format...")

    # Expected format:
    # {
    #   "session_id": "...",
    #   "state": "running" | "completed" | "failed",
    #   "started_at": "ISO timestamp",
    #   "completed_at": "ISO timestamp" (if completed),
    #   "statistics": {...} (if completed)
    # }

    # This test will FAIL initially because status file isn't implemented yet

    print("  ⚠️  Status file format test - SKIPPED (not implemented)")
    return None


def test_immediate_feedback():
    """Test that hook provides immediate feedback even without completion."""
    print("\n📝 Testing immediate feedback...")

    # Expected: Hook should return a message like:
    # "✅ [ACE] Learning started in background - check /ace-status for progress"

    mock_event = {
        "hook_event_name": "Stop",
        "session_id": "test-async-feedback",
        "transcript_path": "/tmp/test-transcript-feedback.jsonl",
        "cwd": str(Path.cwd())
    }

    transcript_path = Path(mock_event["transcript_path"])
    with open(transcript_path, 'w') as f:
        f.write(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "Test feedback"}
        }) + '\n')

    try:
        result = subprocess.run(
            ['uv', 'run', str(Path(__file__).parent.parent / 'shared-hooks' / 'ace_after_task.py')],
            input=json.dumps(mock_event),
            text=True,
            capture_output=True,
            timeout=5
        )

        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                message = response.get('systemMessage', '')

                # Check for background execution message
                if 'background' in message.lower() or 'started' in message.lower():
                    print(f"  ✅ Immediate feedback provided: {message}")
                    return True
                else:
                    print(f"  ❌ No background execution message: {message}")
                    return False

            except json.JSONDecodeError:
                print(f"  ❌ Invalid JSON response: {result.stdout}")
                return False
        else:
            print(f"  ❌ Hook failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ❌ Hook timed out")
        return False
    finally:
        transcript_path.unlink(missing_ok=True)


def run_all_tests():
    """Run all async learning tests."""
    print("=" * 60)
    print("ACE Async Learning Tests (TDD for Issue #3)")
    print("=" * 60)

    results = []

    # Test 1: Quick return
    results.append(("Quick return (<2s)", test_hook_returns_quickly()))

    # Test 2: Background process
    results.append(("Background process", test_background_process_runs()))

    # Test 3: Status file format
    results.append(("Status file format", test_status_file_format()))

    # Test 4: Immediate feedback
    results.append(("Immediate feedback", test_immediate_feedback()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for name, result in results:
        if result is True:
            print(f"  ✅ {name} - PASSED")
        elif result is False:
            print(f"  ❌ {name} - FAILED")
        else:
            print(f"  ⚠️  {name} - SKIPPED")

    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)
    total = len(results)

    print(f"\n  Total: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}")
    print("=" * 60)

    # Return exit code
    return 1 if failed > 0 else 0


if __name__ == '__main__':
    sys.exit(run_all_tests())
