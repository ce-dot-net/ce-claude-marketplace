#!/usr/bin/env python3
"""
Test file to verify ACE v5.1.22 quality filters work correctly.

This is a REAL implementation task that should:
1. Trigger PostToolUse hook (multiple tools used)
2. Pass quality filters (state-changing tools: Write, Edit)
3. NOT be filtered as trivial (actual implementation work)
"""

import sys
sys.path.insert(0, 'shared-hooks')
sys.path.insert(0, 'shared-hooks/utils')

from ace_after_task import is_trivial_task, has_substantial_work


def test_trivial_task_filter():
    """Test that trivial tasks are filtered correctly."""

    # These should be FILTERED (return True)
    trivial_cases = [
        "User request: <command-message>ace:ace-status is running</command-message>",
        "/ace-status",
        "ace:ace-patterns",
        "what is this?",
        "thanks",
        "Caveat: The messages below were generated",
    ]

    # These should NOT be filtered (return False)
    substantial_cases = [
        "User request: implement JWT authentication",
        "User request: fix the bug in login flow",
        "User request: create test file for quality filters",
    ]

    print("=== Testing is_trivial_task() ===\n")

    all_passed = True

    for case in trivial_cases:
        result = is_trivial_task(case)
        status = "✅ PASS" if result else "❌ FAIL"
        if not result:
            all_passed = False
        print(f"{status}: Should filter: {case[:50]}...")

    print()

    for case in substantial_cases:
        result = is_trivial_task(case)
        status = "✅ PASS" if not result else "❌ FAIL"
        if result:
            all_passed = False
        print(f"{status}: Should NOT filter: {case[:50]}...")

    return all_passed


def test_substantial_work_filter():
    """Test that substantial work detection works correctly."""

    print("\n=== Testing has_substantial_work() ===\n")

    # Should be REJECTED (return False)
    not_substantial = [
        {
            "task": "Session work",
            "trajectory": [{"action": "test"}],
            "result": {"output": "short"}
        },
        {
            "task": "User request: check status",
            "trajectory": [{"action": "Conversation with 5 exchanges", "result": "Discussion completed"}],
            "result": {"output": "chat"}
        },
    ]

    # Should be ACCEPTED (return True)
    substantial = [
        {
            "task": "User request: implement feature",
            "trajectory": [
                {"action": "Read file", "tool": "Read"},
                {"action": "Edit code", "tool": "Edit"},
                {"action": "Run tests", "tool": "Bash"}
            ],
            "result": {"output": "Feature implemented successfully"}
        },
    ]

    all_passed = True

    for trace in not_substantial:
        result = has_substantial_work(trace)
        status = "✅ PASS" if not result else "❌ FAIL"
        if result:
            all_passed = False
        print(f"{status}: Should reject: {trace['task'][:40]}...")

    for trace in substantial:
        result = has_substantial_work(trace)
        status = "✅ PASS" if result else "❌ FAIL"
        if not result:
            all_passed = False
        print(f"{status}: Should accept: {trace['task'][:40]}...")

    return all_passed


if __name__ == "__main__":
    print("ACE v5.1.22 Quality Filter Tests")
    print("=" * 50)

    test1 = test_trivial_task_filter()
    test2 = test_substantial_work_filter()

    print("\n" + "=" * 50)
    if test1 and test2:
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
