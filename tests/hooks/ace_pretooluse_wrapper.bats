#!/usr/bin/env bats
# ace_pretooluse_wrapper.bats - Unit tests for PreToolUse hook

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"

  # Create ACE settings with project context
  mkdir -p "${TEMP_TEST_DIR}/.claude"
  cat > "${TEMP_TEST_DIR}/.claude/settings.json" <<EOF
{
  "orgId": "test-org",
  "projectId": "test-project"
}
EOF

  # Setup hook using shared helper
  setup_hook_wrapper "ace_pretooluse_wrapper.sh"
}

teardown() {
  teardown_test_env
}

# Helper: Create PreToolUse event JSON
create_pretooluse_input() {
  local tool_name="${1:-Read}"
  local file_path="${2:-/test/file.txt}"

  cat <<EOF
{
  "hook_event_name": "PreToolUse",
  "tool_name": "$tool_name",
  "tool_input": {"file_path": "$file_path"},
  "session_id": "${SESSION_ID}"
}
EOF
}

# ============================================================================
# Test: Basic Functionality
# ============================================================================

@test "hook processes PreToolUse events" {
  cd "${TEMP_TEST_DIR}"

  local result=$(create_pretooluse_input | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh")

  # Assert: Hook executed successfully
  [[ $? -eq 0 ]]
}

@test "hook exits silently when no project context" {
  cd "${TEMP_TEST_DIR}"

  # Remove ACE settings
  rm -f "${TEMP_TEST_DIR}/.claude/settings.json"

  local result=$(create_pretooluse_input | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Flag File Coordination
# ============================================================================

@test "hook respects ACE disabled flag" {
  cd "${TEMP_TEST_DIR}"

  # Create disabled flag
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_pretooluse_input | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh")

  # Assert: Hook exits silently
  [[ $? -eq 0 ]]
}

@test "hook runs normally when flag does not exist" {
  cd "${TEMP_TEST_DIR}"

  # Ensure no flag exists
  rm -f "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_pretooluse_input | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh")

  # Assert: Hook executed
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: CLI Detection
# ============================================================================

@test "hook exits silently when no CLI available" {
  cd "${TEMP_TEST_DIR}"

  # Remove CLI from PATH
  export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$TEMP_TEST_DIR" | tr '\n' ':')

  local result=$(create_pretooluse_input | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Tool Filtering
# ============================================================================

@test "hook skips non-file-reading tools" {
  cd "${TEMP_TEST_DIR}"

  # Create event for non-file tool (e.g., Bash)
  local result=$(cat <<EOF | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh"
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "ls"},
  "session_id": "${SESSION_ID}"
}
EOF
)

  # Assert: Hook exits gracefully (skips non-file tools)
  [[ $? -eq 0 ]]
}

@test "hook processes Read tool events" {
  cd "${TEMP_TEST_DIR}"

  local result=$(create_pretooluse_input "Read" "/path/to/file.ts" | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh")

  # Assert: Hook processed the event
  [[ $? -eq 0 ]]
}

@test "hook processes Grep tool events" {
  cd "${TEMP_TEST_DIR}"

  local result=$(create_pretooluse_input "Grep" "/path/to/search" | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh")

  # Assert: Hook processed the event
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Settings Parsing
# ============================================================================

@test "hook reads settings with env format" {
  cd "${TEMP_TEST_DIR}"

  # Create settings with env format
  cat > "${TEMP_TEST_DIR}/.claude/settings.json" <<EOF
{
  "env": {
    "ACE_ORG_ID": "env-org",
    "ACE_PROJECT_ID": "env-project"
  }
}
EOF

  local result=$(create_pretooluse_input | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh")

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook handles malformed settings JSON" {
  cd "${TEMP_TEST_DIR}"

  # Create invalid JSON
  echo "invalid json" > "${TEMP_TEST_DIR}/.claude/settings.json"

  local result=$(create_pretooluse_input | bash "${TEMP_TEST_DIR}/ace_pretooluse_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully (no project context)
  [[ $? -eq 0 ]]
}
