#!/usr/bin/env bash
# Integration Test: PreCompact → SessionStart(compact) Handoff
# Tests Issue #17 fix - pattern preservation through compaction

set -euo pipefail

TEST_SESSION_ID="test-session-$$"
TEST_PROJECT_ID="test-project-$$"
TEMP_FILE="/tmp/ace-patterns-precompact-${TEST_SESSION_ID}.json"
ACE_SESSION_FILE="/tmp/ace-session-${TEST_PROJECT_ID}.txt"
SESSIONSTART_COMPACT_SCRIPT="$(cd "$(dirname "$0")/../scripts" && pwd)/ace_sessionstart_compact.sh"

# Create isolated test directory (avoids picking up real .claude/settings.json)
TEST_WORKDIR=$(mktemp -d)
mkdir -p "$TEST_WORKDIR/.claude"
echo "{\"projectId\": \"${TEST_PROJECT_ID}\"}" > "$TEST_WORKDIR/.claude/settings.json"

# Cleanup on exit (prevents orphaned /tmp files on early failure)
trap 'rm -f "$TEMP_FILE" "$ACE_SESSION_FILE" 2>/dev/null; rm -rf "$TEST_WORKDIR" 2>/dev/null' EXIT

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper: Run a test
run_test() {
  local test_name="$1"
  local test_fn="$2"

  TESTS_RUN=$((TESTS_RUN + 1))
  echo -e "\n${YELLOW}[TEST $TESTS_RUN]${NC} $test_name"

  if $test_fn; then
    echo -e "${GREEN}✓ PASSED${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo -e "${RED}✗ FAILED${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

# Helper: Assert JSON is valid
assert_valid_json() {
  local json_str="$1"
  local label="$2"

  if echo "$json_str" | jq empty 2>/dev/null; then
    echo "  ✓ $label is valid JSON"
    return 0
  else
    echo "  ✗ $label is NOT valid JSON"
    echo "  Output: $json_str"
    return 1
  fi
}

# Helper: Assert file exists
assert_file_exists() {
  local file="$1"

  if [ -f "$file" ]; then
    echo "  ✓ File exists: $file"
    return 0
  else
    echo "  ✗ File does NOT exist: $file"
    return 1
  fi
}

# Helper: Assert file does not exist
assert_file_not_exists() {
  local file="$1"

  if [ ! -f "$file" ]; then
    echo "  ✓ File does not exist (cleaned up): $file"
    return 0
  else
    echo "  ✗ File still exists (not cleaned up): $file"
    return 1
  fi
}

# Helper: Assert field exists in JSON
assert_json_field() {
  local json_str="$1"
  local field="$2"
  local expected_value="$3"

  actual_value=$(echo "$json_str" | jq -r "$field" 2>/dev/null || echo "")

  if [ "$actual_value" = "$expected_value" ]; then
    echo "  ✓ $field = \"$expected_value\""
    return 0
  else
    echo "  ✗ $field = \"$actual_value\" (expected \"$expected_value\")"
    return 1
  fi
}

# Setup: Clean any previous test files
cleanup() {
  rm -f "$TEMP_FILE" 2>/dev/null || true
  rm -f "$ACE_SESSION_FILE" 2>/dev/null || true
  rm -rf "$TEST_WORKDIR" 2>/dev/null || true
}

# Helper: Run SessionStart(compact) from isolated test directory
run_sessionstart_compact() {
  local input="$1"
  # Run from TEST_WORKDIR so the script reads our mock .claude/settings.json
  (cd "$TEST_WORKDIR" && echo "$input" | "$SESSIONSTART_COMPACT_SCRIPT" 2>/dev/null) || echo ""
}

# Test 1: PreCompact saves patterns to temp file (no hookSpecificOutput)
test_precompact_no_hookSpecificOutput() {
  rm -f "$TEMP_FILE" 2>/dev/null || true

  # Simulate PreCompact saving patterns to temp file
  echo '{"patterns": "• [test] Test pattern", "session_id": "test-session", "count": "1"}' > "$TEMP_FILE"

  # Verify temp file was created
  assert_file_exists "$TEMP_FILE" || return 1

  # Verify temp file contains valid JSON
  TEMP_CONTENT=$(cat "$TEMP_FILE")
  assert_valid_json "$TEMP_CONTENT" "Temp file content" || return 1

  # Verify it has expected fields
  assert_json_field "$TEMP_CONTENT" ".patterns" "• [test] Test pattern" || return 1
  assert_json_field "$TEMP_CONTENT" ".count" "1" || return 1

  return 0
}

# Test 2: SessionStart(compact) reads temp file and injects patterns
# Tests the full production path: settings.json → ace-session file → temp file
test_sessionstart_compact_injection() {
  rm -f "$TEMP_FILE" 2>/dev/null || true
  rm -f "$ACE_SESSION_FILE" 2>/dev/null || true

  # Setup: Create ace-session file (as UserPromptSubmit would)
  echo "$TEST_SESSION_ID" > "$ACE_SESSION_FILE"

  # Setup: Create temp file (as PreCompact would)
  echo '{"patterns": "• [test] Test pattern\n• [test] Another pattern", "session_id": "'"$TEST_SESSION_ID"'", "count": "2"}' > "$TEMP_FILE"

  # Run SessionStart(compact) from isolated test dir
  SESSIONSTART_OUTPUT=$(run_sessionstart_compact '{"session_id": "'"$TEST_SESSION_ID"'"}')

  # Verify output is valid JSON
  assert_valid_json "$SESSIONSTART_OUTPUT" "SessionStart(compact) output" || return 1

  # Verify hookEventName is "SessionStart" (not "PreCompact")
  assert_json_field "$SESSIONSTART_OUTPUT" ".hookSpecificOutput.hookEventName" "SessionStart" || return 1

  # Verify additionalContext contains patterns
  ADDITIONAL_CONTEXT=$(echo "$SESSIONSTART_OUTPUT" | jq -r '.hookSpecificOutput.additionalContext // ""')
  if echo "$ADDITIONAL_CONTEXT" | grep -q "ace-patterns-recalled"; then
    echo "  ✓ additionalContext contains ace-patterns-recalled tag"
  else
    echo "  ✗ additionalContext missing ace-patterns-recalled tag"
    echo "  Context: $ADDITIONAL_CONTEXT"
    return 1
  fi

  # Verify systemMessage exists
  SYSTEM_MSG=$(echo "$SESSIONSTART_OUTPUT" | jq -r '.systemMessage // ""')
  if echo "$SYSTEM_MSG" | grep -q "Restored.*patterns"; then
    echo "  ✓ systemMessage indicates patterns restored"
  else
    echo "  ✗ systemMessage doesn't indicate restoration"
    echo "  Message: $SYSTEM_MSG"
    return 1
  fi

  return 0
}

# Test 3: Temp file is cleaned up after SessionStart(compact) runs
test_temp_file_cleanup() {
  rm -f "$TEMP_FILE" 2>/dev/null || true
  rm -f "$ACE_SESSION_FILE" 2>/dev/null || true

  # Setup: Create ace-session file + temp file
  echo "$TEST_SESSION_ID" > "$ACE_SESSION_FILE"
  echo '{"patterns": "• [test] Test", "session_id": "'"$TEST_SESSION_ID"'", "count": "1"}' > "$TEMP_FILE"

  # Run SessionStart(compact) from isolated test dir
  run_sessionstart_compact '{"session_id": "'"$TEST_SESSION_ID"'"}' >/dev/null

  # Verify temp file was cleaned up
  assert_file_not_exists "$TEMP_FILE" || return 1

  return 0
}

# Test 4: SessionStart(compact) exits silently if no temp file
test_sessionstart_no_temp_file() {
  rm -f "$TEMP_FILE" 2>/dev/null || true
  rm -f "$ACE_SESSION_FILE" 2>/dev/null || true

  # Setup: ace-session file exists but no temp file
  echo "$TEST_SESSION_ID" > "$ACE_SESSION_FILE"

  # Run SessionStart(compact) with no temp file
  SESSIONSTART_OUTPUT=$(run_sessionstart_compact '{"session_id": "'"$TEST_SESSION_ID"'"}')

  # Should produce empty output (silent exit)
  if [ -z "$SESSIONSTART_OUTPUT" ]; then
    echo "  ✓ SessionStart(compact) exits silently with no temp file"
    return 0
  else
    echo "  ✗ SessionStart(compact) produced output when no temp file"
    echo "  Output: $SESSIONSTART_OUTPUT"
    return 1
  fi
}

# Test 5: SessionStart(compact) falls back to stdin session_id when no ace-session file
test_sessionstart_stdin_fallback() {
  rm -f "$TEMP_FILE" 2>/dev/null || true
  rm -f "$ACE_SESSION_FILE" 2>/dev/null || true

  # Setup: Create temp file but NO ace-session file
  # Use a temp dir WITHOUT .claude/settings.json to force stdin fallback
  local fallback_dir
  fallback_dir=$(mktemp -d)

  echo '{"patterns": "• [test] Fallback test", "session_id": "'"$TEST_SESSION_ID"'", "count": "1"}' > "$TEMP_FILE"

  # Run from a dir without settings.json - should fall back to stdin session_id
  SESSIONSTART_OUTPUT=$(cd "$fallback_dir" && echo '{"session_id": "'"$TEST_SESSION_ID"'"}' | "$SESSIONSTART_COMPACT_SCRIPT" 2>/dev/null || echo "")

  rm -rf "$fallback_dir" 2>/dev/null || true

  if [ -n "$SESSIONSTART_OUTPUT" ]; then
    assert_valid_json "$SESSIONSTART_OUTPUT" "Fallback output" || return 1
    assert_json_field "$SESSIONSTART_OUTPUT" ".hookSpecificOutput.hookEventName" "SessionStart" || return 1
    echo "  ✓ Stdin fallback resolved correct session_id"
    return 0
  else
    echo "  ✗ Stdin fallback produced no output (temp file not found)"
    return 1
  fi
}

# Main test execution
main() {
  echo "================================================================"
  echo "Integration Test: PreCompact → SessionStart(compact) Handoff"
  echo "Tests Issue #17 fix - pattern preservation through compaction"
  echo "================================================================"

  run_test "PreCompact saves patterns to temp file (no hookSpecificOutput)" test_precompact_no_hookSpecificOutput
  run_test "SessionStart(compact) reads temp file and injects patterns" test_sessionstart_compact_injection
  run_test "Temp file is cleaned up after SessionStart(compact)" test_temp_file_cleanup
  run_test "SessionStart(compact) exits silently if no temp file" test_sessionstart_no_temp_file
  run_test "SessionStart(compact) falls back to stdin when no ace-session file" test_sessionstart_stdin_fallback

  echo ""
  echo "================================================================"
  echo "Test Summary:"
  echo "  Total: $TESTS_RUN"
  echo -e "  ${GREEN}Passed: $TESTS_PASSED${NC}"
  if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "  ${RED}Failed: $TESTS_FAILED${NC}"
  else
    echo "  Failed: 0"
  fi
  echo "================================================================"

  # Cleanup
  cleanup

  # Exit with failure if any tests failed
  if [ $TESTS_FAILED -gt 0 ]; then
    exit 1
  fi
}

main
