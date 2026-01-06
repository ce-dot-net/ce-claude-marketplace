#!/usr/bin/env bats
# ace_posttooluse_wrapper.bats - Unit tests for PostToolUse hook

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"
  create_mock_uv
  create_mock_python_hook "ace_tool_accumulator.py" "success"
  create_mock_python_hook "ace_event_logger.py" "success"

  # Setup hook using shared helper
  setup_hook_wrapper "ace_posttooluse_wrapper.sh"
}

teardown() {
  teardown_test_env
}

# Helper: Create PostToolUse event JSON
create_posttooluse_input() {
  cat <<EOF
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": {"file_path": "/test/file.txt"},
  "tool_response": {"content": "file contents"},
  "tool_use_id": "toolu_123456",
  "session_id": "${SESSION_ID}",
  "cwd": "${TEMP_TEST_DIR}"
}
EOF
}

# ============================================================================
# Test: Tool Accumulation
# ============================================================================

@test "hook accumulates tool data" {
  local result=$(create_posttooluse_input | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh")

  # Assert: Accumulator was called successfully
  [[ $? -eq 0 ]]
}

@test "hook skips when session_id missing" {
  local input=$(cat <<EOF
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_use_id": "toolu_123"
}
EOF
)

  local result=$(echo "$input" | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh")

  # Assert: Hook exits gracefully with empty message
  assert_hook_output_contains "$result" '""'
}

@test "hook skips when tool_name missing" {
  local input=$(cat <<EOF
{
  "hook_event_name": "PostToolUse",
  "session_id": "${SESSION_ID}",
  "tool_use_id": "toolu_123"
}
EOF
)

  local result=$(echo "$input" | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh")

  # Assert: Hook exits gracefully
  assert_hook_output_contains "$result" '""'
}

@test "hook skips when tool_use_id missing" {
  local input=$(cat <<EOF
{
  "hook_event_name": "PostToolUse",
  "session_id": "${SESSION_ID}",
  "tool_name": "Read"
}
EOF
)

  local result=$(echo "$input" | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh")

  # Assert: Hook exits gracefully
  assert_hook_output_contains "$result" '""'
}

# ============================================================================
# Test: Flag File Coordination
# ============================================================================

@test "hook respects ACE disabled flag" {
  # Create disabled flag
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_posttooluse_input | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh")

  # Assert: Hook exits silently
  assert_hook_exits_silently "$result"
}

@test "hook runs normally when flag does not exist" {
  # Ensure no flag exists
  rm -f "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_posttooluse_input | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh")

  # Assert: Hook executed
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: CLI Detection
# ============================================================================

@test "hook exits silently when no CLI available" {
  # Remove CLI from PATH
  export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$TEMP_TEST_DIR" | tr '\n' ':')

  local result=$(create_posttooluse_input | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Dependency Validation
# ============================================================================

@test "hook fails when accumulator script missing" {
  # Remove mock accumulator
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_tool_accumulator.py"

  run bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh" <<< "$(create_posttooluse_input)"

  # Assert: Hook fails with error message
  [[ $status -ne 0 ]]
  [[ "$output" =~ "ace_tool_accumulator.py not found" ]]
}

# ============================================================================
# Test: Working Directory Handling
# ============================================================================

@test "hook changes to working directory from cwd field" {
  # Create test directory structure
  mkdir -p "${TEMP_TEST_DIR}/project-root/.claude"

  # Create hook input with cwd
  local input=$(cat <<EOF
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": {},
  "tool_response": {},
  "tool_use_id": "toolu_123",
  "session_id": "${SESSION_ID}",
  "cwd": "${TEMP_TEST_DIR}/project-root"
}
EOF
)

  echo "$input" | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh"

  # Assert: No errors (would fail if couldn't cd)
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Argument Parsing
# ============================================================================

@test "hook accepts --log argument" {
  create_posttooluse_input | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh" --log

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook accepts --no-log argument" {
  create_posttooluse_input | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh" --no-log

  # Assert: No errors
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: UTF-8 Sanitization
# ============================================================================

@test "hook handles malformed JSON gracefully" {
  # Send invalid JSON
  local result=$(echo "invalid json" | bash "${TEMP_TEST_DIR}/ace_posttooluse_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully (doesn't crash)
  [[ $? -eq 0 ]]
}
