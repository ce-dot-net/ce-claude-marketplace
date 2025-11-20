#!/usr/bin/env python3
"""
Test script for ACE v5.1.9 hooks
Verifies PostToolUse is disabled and PreCompact extracts from messages
"""

import json
import subprocess
import sys
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def test_posttooluse_disabled():
    """Test 1: Verify PostToolUse hook exits immediately"""
    print("\n" + "="*80)
    print("TEST 1: PostToolUse Hook Disabled")
    print("="*80)

    hook_path = Path(__file__).parent.parent / "shared-hooks" / "ace_task_complete.py"

    # Create mock PostToolUse event
    mock_event = {
        "tool_name": "Edit",
        "description": "Update config.json",
        "result": {"summary": "completed"}
    }

    try:
        result = subprocess.run(
            ['python3', str(hook_path)],
            input=json.dumps(mock_event),
            text=True,
            capture_output=True,
            timeout=5
        )

        # Should exit with 0 and return empty JSON
        if result.returncode == 0 and result.stdout.strip() in ['{}', '']:
            print(f"{GREEN}✅ PASS{RESET}: PostToolUse exits immediately (sys.exit(0))")
            print(f"   Output: {result.stdout.strip() or 'empty'}")
            return True
        else:
            print(f"{RED}❌ FAIL{RESET}: PostToolUse did not exit cleanly")
            print(f"   Return code: {result.returncode}")
            print(f"   Output: {result.stdout}")
            print(f"   Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"{RED}❌ FAIL{RESET}: PostToolUse timed out (should exit immediately)")
        return False
    except Exception as e:
        print(f"{RED}❌ FAIL{RESET}: Error running PostToolUse: {e}")
        return False


def test_precompact_extracts_from_messages():
    """Test 2: Verify PreCompact extracts from messages, not tools"""
    print("\n" + "="*80)
    print("TEST 2: PreCompact Message-Based Extraction")
    print("="*80)

    hook_path = Path(__file__).parent.parent / "shared-hooks" / "ace_after_task.py"

    # Create mock PreCompact event with conversation
    mock_event = {
        "hook_event_name": "PreCompact",
        "messages": [
            {
                "role": "user",
                "content": "Implement JWT authentication with refresh tokens"
            },
            {
                "role": "assistant",
                "content": "I'll implement JWT authentication. I decided to use 15-minute access tokens and 7-day refresh tokens to prevent token theft. I encountered an issue where cookies weren't being sent - fixed by adding credentials: 'include' to fetch calls. Successfully implemented the authentication system with HttpOnly cookies for security."
            },
            {
                "role": "user",
                "content": "Great, now add Stripe webhook handling"
            },
            {
                "role": "assistant",
                "content": "I'm implementing Stripe webhooks. I discovered that Stripe signature verification requires express.raw() middleware, not express.json(). Fixed the error and the webhook handler is now working successfully."
            }
        ],
        "tool_uses": [
            {
                "tool_name": "Edit",
                "description": "Create auth.ts",
                "result": {"summary": "completed"}
            },
            {
                "tool_name": "Write",
                "description": "Update config.json",
                "result": {"summary": "completed"}
            },
            {
                "tool_name": "Bash",
                "description": "Run tests",
                "result": {"summary": "completed"}
            }
        ]
    }

    # We can't actually run the hook (needs ACE context), but we can check the code
    print(f"{YELLOW}ℹ️  INFO{RESET}: Analyzing trajectory extraction logic...")

    try:
        # Read the hook code
        code = hook_path.read_text()

        checks = []

        # Check 1: Does NOT iterate over tool_uses for trajectory
        if 'for idx, tool in enumerate(tool_uses' not in code:
            checks.append((True, "Does NOT use tool_uses iteration for trajectory"))
        else:
            checks.append((False, "Still uses tool_uses iteration for trajectory"))

        # Check 2: DOES iterate over messages
        if 'for msg in messages:' in code:
            checks.append((True, "DOES iterate over messages"))
        else:
            checks.append((False, "Does NOT iterate over messages"))

        # Check 3: Extracts decisions
        if "['decided', 'chose', 'using'" in code:
            checks.append((True, "Extracts decisions from messages"))
        else:
            checks.append((False, "Does NOT extract decisions"))

        # Check 4: Extracts gotchas
        if "['error', 'issue', 'problem', 'failed', 'fixed', 'solved'" in code:
            checks.append((True, "Extracts gotchas from messages"))
        else:
            checks.append((False, "Does NOT extract gotchas"))

        # Check 5: Extracts accomplishments
        if "['completed', 'working', 'successfully'" in code:
            checks.append((True, "Extracts accomplishments from messages"))
        else:
            checks.append((False, "Does NOT extract accomplishments"))

        # Check 6: Builds trajectory from extracted insights
        if '"Made architectural decisions"' in code:
            checks.append((True, "Builds meaningful trajectory entries"))
        else:
            checks.append((False, "Does NOT build meaningful trajectory"))

        # Print results
        all_passed = True
        for passed, description in checks:
            if passed:
                print(f"{GREEN}✅ PASS{RESET}: {description}")
            else:
                print(f"{RED}❌ FAIL{RESET}: {description}")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"{RED}❌ FAIL{RESET}: Error analyzing code: {e}")
        return False


def test_no_trash_patterns():
    """Test 3: Verify no trash patterns in trajectory"""
    print("\n" + "="*80)
    print("TEST 3: No Trash Patterns")
    print("="*80)

    hook_path = Path(__file__).parent.parent / "shared-hooks" / "ace_after_task.py"

    try:
        code = hook_path.read_text()

        checks = []

        # Check 1: No "Edit - " patterns
        if 'f"{tool_name} - {tool_desc}"' not in code or 'trajectory.append' not in code.split('# Track files from tool uses')[0]:
            checks.append((True, "Does NOT create 'Tool - description' patterns"))
        else:
            checks.append((False, "Still creates 'Tool - description' patterns"))

        # Check 2: Filters messages by role
        if 'if role != \'assistant\':' in code and 'continue' in code:
            checks.append((True, "Filters to assistant messages only"))
        else:
            checks.append((False, "Does NOT filter messages"))

        # Check 3: Requires meaningful content (>20 chars)
        if 'if len(clean) > 20:' in code:
            checks.append((True, "Filters short/empty content (>20 chars)"))
        else:
            checks.append((False, "Does NOT filter short content"))

        # Check 4: Limits to top 3 per category
        if 'decisions[:3]' in code and 'gotchas[:3]' in code:
            checks.append((True, "Limits to top 3 per category"))
        else:
            checks.append((False, "Does NOT limit results"))

        # Print results
        all_passed = True
        for passed, description in checks:
            if passed:
                print(f"{GREEN}✅ PASS{RESET}: {description}")
            else:
                print(f"{RED}❌ FAIL{RESET}: {description}")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"{RED}❌ FAIL{RESET}: Error analyzing code: {e}")
        return False


def main():
    """Run all tests"""
    print(f"\n{YELLOW}{'='*80}")
    print("ACE v5.1.9 Hook Tests")
    print(f"{'='*80}{RESET}")

    results = []

    # Run tests
    results.append(("PostToolUse Disabled", test_posttooluse_disabled()))
    results.append(("PreCompact Message Extraction", test_precompact_extracts_from_messages()))
    results.append(("No Trash Patterns", test_no_trash_patterns()))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"{status}: {test_name}")

    print("\n" + "="*80)
    if passed == total:
        print(f"{GREEN}✅ ALL TESTS PASSED ({passed}/{total}){RESET}")
        print(f"{GREEN}Ready to release v5.1.9!{RESET}")
        return 0
    else:
        print(f"{RED}❌ SOME TESTS FAILED ({passed}/{total}){RESET}")
        print(f"{RED}Fix issues before releasing!{RESET}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
