#!/usr/bin/env python3
"""
Test script for session pinning and rich context extraction.

Tests:
1. Session pinning workflow (pin → recall)
2. Rich context extraction (no generic messages)
3. Version compatibility
4. Full workflow simulation
"""

import sys
import uuid
import json
import time
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent / 'utils'))

from ace_cli import run_search, recall_session, check_session_pinning_available
from ace_context import get_context


def test_version_check():
    """Test 1: Version compatibility check"""
    print("\n" + "="*60)
    print("TEST 1: Version Compatibility Check")
    print("="*60)

    available = check_session_pinning_available()
    print(f"Session pinning available: {available}")

    if not available:
        print("❌ FAIL: ce-ace v1.0.11+ required for session pinning")
        print("   Install: npm install -g @ace-sdk/cli@latest")
        return False

    print("✅ PASS: Session pinning is available")
    return True


def test_session_pinning():
    """Test 2: Session pinning and recall workflow"""
    print("\n" + "="*60)
    print("TEST 2: Session Pinning Workflow")
    print("="*60)

    # Get context - MUST have real project for this test
    context = get_context()
    if not context or not context.get('project'):
        print("❌ FAIL: No project context found - cannot test without real ACE project")
        print("   This test requires .claude/settings.json with ACE_PROJECT_ID")
        return False

    print(f"Using project: {context['project'][:20]}...")

    # Generate session ID
    session_id = str(uuid.uuid4())
    print(f"Generated session ID: {session_id}")

    # Store session ID (simulate ace_before_task.py)
    session_file = Path(f"/tmp/ace-session-{context['project']}.txt")
    session_file.write_text(session_id)
    print(f"Stored session ID to: {session_file}")

    # Search with pinning
    print("\nSearching with session pinning...")
    search_result = run_search(
        query="authentication patterns JWT tokens",
        org=context['org'],
        project=context['project'],
        session_id=session_id
    )

    if not search_result:
        print("❌ FAIL: Search returned no results")
        session_file.unlink(missing_ok=True)
        return False

    search_count = search_result.get('count', 0)
    print(f"✅ Search returned {search_count} patterns")

    # Wait a moment (simulate work)
    time.sleep(0.5)

    # Recall from session
    print("\nRecalling patterns from session...")
    start = time.time()
    recall_result = recall_session(
        session_id=session_id,
        org=context['org'],
        project=context['project']
    )
    duration_ms = (time.time() - start) * 1000

    if not recall_result:
        print("❌ FAIL: Session recall failed")
        session_file.unlink(missing_ok=True)
        return False

    recall_count = recall_result.get('count', 0)
    print(f"✅ Recalled {recall_count} patterns in {duration_ms:.1f}ms")

    # Verify counts match
    if search_count != recall_count:
        print(f"❌ FAIL: Pattern count mismatch (search={search_count}, recall={recall_count})")
        session_file.unlink(missing_ok=True)
        return False

    print("✅ PASS: Pattern counts match")

    # Verify performance (should be fast)
    if duration_ms > 100:
        print(f"⚠️  WARN: Slow recall ({duration_ms:.1f}ms, expected <100ms)")
    else:
        print(f"✅ PASS: Fast recall ({duration_ms:.1f}ms)")

    # Cleanup
    session_file.unlink(missing_ok=True)
    print("✅ Cleaned up test files")

    return True


def test_rich_context_extraction():
    """Test 3: Rich context extraction (no generic messages)"""
    print("\n" + "="*60)
    print("TEST 3: Rich Context Extraction")
    print("="*60)

    # Import the extract functions
    sys.path.insert(0, str(Path(__file__).parent))
    from ace_task_complete import extract_task_trace
    from ace_after_task import extract_execution_trace

    # Test PostToolUse (ace_task_complete.py)
    print("\nTesting PostToolUse rich context...")

    event_posttooluse = {
        'tool_name': 'Edit',
        'description': 'Update hero.tsx with JWT authentication flow',
        'result': {
            'summary': 'Modified authentication to use JWT tokens',
            'output': 'Successfully replaced session-based auth with JWT tokens'
        }
    }

    trace_post = extract_task_trace(event_posttooluse)
    task_desc_post = trace_post['task']

    print(f"Task description: {task_desc_post}")

    # Check for generic patterns (should NOT contain these)
    generic_patterns = ['Edit:', 'Edit: ', 'unknown']
    is_generic_post = any(pattern == task_desc_post or task_desc_post.startswith(pattern) for pattern in generic_patterns)

    if is_generic_post:
        print(f"❌ FAIL: PostToolUse still using generic pattern: '{task_desc_post}'")
        return False

    if len(task_desc_post) < 20:
        print(f"❌ FAIL: PostToolUse context too short: '{task_desc_post}'")
        return False

    print("✅ PASS: PostToolUse uses rich context")

    # Test PreCompact (ace_after_task.py)
    print("\nTesting PreCompact rich context...")

    event_precompact = {
        'messages': [
            {'role': 'user', 'content': 'Implement JWT authentication with refresh tokens'},
            {'role': 'assistant', 'content': 'I implemented JWT auth with token rotation and CORS fixes'}
        ],
        'tool_uses': [
            {
                'tool_name': 'Edit',
                'description': 'Update hero.tsx authentication flow',
                'result': {'summary': 'Modified authentication'}
            },
            {
                'tool_name': 'Edit',
                'description': 'Update middleware.ts CORS headers',
                'result': {'summary': 'Fixed CORS issue'}
            }
        ],
        'summary': 'Implemented authentication'
    }

    trace_pre = extract_execution_trace(event_precompact)
    task_desc_pre = trace_pre['task']

    print(f"Task description: {task_desc_pre}")

    # Check for generic patterns (should NOT contain these)
    if task_desc_pre == 'Session work':
        print(f"❌ FAIL: PreCompact still using generic 'Session work'")
        return False

    if len(task_desc_pre) < 20:
        print(f"❌ FAIL: PreCompact context too short: '{task_desc_pre}'")
        return False

    if 'User request:' not in task_desc_pre and 'Implement' not in task_desc_pre:
        print(f"⚠️  WARN: PreCompact might not include user request")

    print("✅ PASS: PreCompact uses rich context")

    return True


def test_full_workflow():
    """Test 4: Full workflow simulation"""
    print("\n" + "="*60)
    print("TEST 4: Full Workflow Simulation")
    print("="*60)

    context = get_context()
    if not context or not context.get('project'):
        print("❌ FAIL: No project context found - cannot test without real ACE project")
        return False

    print("\nSimulating full workflow:")
    print("1. UserPromptSubmit → Search + Pin")
    print("2. Work happens (edits, writes)")
    print("3. Context compaction")
    print("4. PreCompact → Recall + Learn")

    # Step 1: UserPromptSubmit
    session_id = str(uuid.uuid4())
    session_file = Path(f"/tmp/ace-session-{context['project']}.txt")
    session_file.write_text(session_id)

    search_result = run_search(
        query="JWT authentication patterns",
        org=context['org'],
        project=context['project'],
        session_id=session_id
    )

    if not search_result:
        print("❌ FAIL: Initial search failed")
        session_file.unlink(missing_ok=True)
        return False

    print(f"✅ Step 1: Pinned {search_result.get('count', 0)} patterns to session")

    # Step 2: Simulate work (wait)
    time.sleep(0.5)
    print("✅ Step 2: Work completed (simulated)")

    # Step 3: Simulate compaction (patterns would be lost from context)
    print("⚠️  Step 3: Context compaction (patterns lost from memory)")

    # Step 4: PreCompact recall
    recall_result = recall_session(
        session_id=session_id,
        org=context['org'],
        project=context['project']
    )

    if not recall_result:
        print("❌ FAIL: Pattern recall failed after compaction")
        session_file.unlink(missing_ok=True)
        return False

    print(f"✅ Step 4: Recalled {recall_result.get('count', 0)} patterns (survived compaction!)")

    # Cleanup
    session_file.unlink(missing_ok=True)

    print("\n✅ PASS: Full workflow completed successfully")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("ACE Session Pinning & Rich Context Test Suite")
    print("="*60)

    results = {
        "Version Check": test_version_check(),
        "Session Pinning": False,
        "Rich Context": False,
        "Full Workflow": False
    }

    # Only run remaining tests if version check passes
    if results["Version Check"]:
        results["Session Pinning"] = test_session_pinning()
        results["Rich Context"] = test_rich_context_extraction()
        results["Full Workflow"] = test_full_workflow()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())

    if all_passed:
        print("\n🎉 All tests passed! Implementation is working correctly.")
        return 0
    else:
        print("\n❌ Some tests failed. Review the output above for details.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
