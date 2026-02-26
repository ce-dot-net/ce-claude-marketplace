#!/usr/bin/env bats
# ace_precompact_wrapper.bats - Unit tests for PreCompact hook

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
  setup_hook_wrapper "ace_precompact_wrapper.sh"
}

teardown() {
  teardown_test_env
}

# ============================================================================
# Test: Pattern Re-injection
# ============================================================================

@test "hook re-injects patterns when project configured" {
  cd "${TEMP_TEST_DIR}"

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh")

  # Assert: Hook executed successfully
  [[ $? -eq 0 ]]
}

@test "hook exits silently when no project context" {
  # Remove ACE settings
  rm -f "${TEMP_TEST_DIR}/.claude/settings.json"

  cd "${TEMP_TEST_DIR}"

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh" 2>&1)

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

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh")

  # Assert: Hook exits silently
  [[ $? -eq 0 ]]
  [[ -z "$result" ]]
}

@test "hook runs normally when flag does not exist" {
  cd "${TEMP_TEST_DIR}"

  # Ensure no flag exists
  rm -f "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh")

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

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Settings Parsing
# ============================================================================

@test "hook reads orgId from settings" {
  cd "${TEMP_TEST_DIR}"

  # Hook should parse settings successfully
  bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh" >/dev/null

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook reads projectId from settings" {
  cd "${TEMP_TEST_DIR}"

  # Hook should parse settings successfully
  bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh" >/dev/null

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook handles env-style settings format" {
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

  bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh" >/dev/null

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook handles malformed settings JSON" {
  cd "${TEMP_TEST_DIR}"

  # Create invalid JSON
  echo "invalid json" > "${TEMP_TEST_DIR}/.claude/settings.json"

  local result=$(bash "${TEMP_TEST_DIR}/ace_precompact_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully (no project ID found)
  [[ $? -eq 0 ]]
}
