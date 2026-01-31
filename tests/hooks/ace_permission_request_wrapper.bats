#!/usr/bin/env bats
# ace_permission_request_wrapper.bats - Unit tests for PermissionRequest hook

load '../helpers/test_helper'

setup() {
  setup_test_env

  # Ensure shared-hooks directory exists
  mkdir -p "${TEMP_TEST_DIR}/shared-hooks"

  # Create mock Python hook
  create_mock_python_hook "ace_permission_request.py" "success"

  # Copy hook to test directory
  cp "${ACE_SCRIPTS_DIR}/ace_permission_request_wrapper.sh" "${TEMP_TEST_DIR}/"

  # Patch PLUGIN_ROOT calculation (this hook uses different pattern)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' 's|PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"|PLUGIN_ROOT="${TEMP_TEST_DIR}"|' "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh"
  else
    sed -i 's|PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"|PLUGIN_ROOT="${TEMP_TEST_DIR}"|' "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh"
  fi

  # Replace TEMP_TEST_DIR variable reference with actual value
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|\${TEMP_TEST_DIR}|${TEMP_TEST_DIR}|g" "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh"
  else
    sed -i "s|\${TEMP_TEST_DIR}|${TEMP_TEST_DIR}|g" "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh"
  fi
}

teardown() {
  teardown_test_env
}

# Helper: Create PermissionRequest event JSON
create_permission_input() {
  local command="${1:-ace-cli search 'test'}"

  cat <<EOF
{
  "hook_event_name": "PermissionRequest",
  "command": "$command",
  "session_id": "${SESSION_ID}"
}
EOF
}

# ============================================================================
# Test: Basic Functionality
# ============================================================================

@test "hook forwards to Python permission handler" {
  local result=$(create_permission_input | bash "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh")

  # Assert: Python hook was called
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook fails when Python script missing" {
  # Remove mock hook script
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_permission_request.py"

  run bash "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh" <<< "$(create_permission_input)"

  # Assert: Hook fails (bash -e mode)
  [[ $status -ne 0 ]]
}

# ============================================================================
# Test: Minimal Wrapper Behavior
# ============================================================================

@test "hook has no flag file check (security gate must always run)" {
  # Create disabled flag (should be ignored)
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_permission_input | bash "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh")

  # Assert: Hook still executes (security gate always active)
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook has no CLI detection (minimal wrapper)" {
  # Remove CLI from PATH
  export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$TEMP_TEST_DIR" | tr '\n' ':')

  local result=$(create_permission_input | bash "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh")

  # Assert: Hook still works
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook preserves stdin for Python script" {
  # Create Python hook that echoes input
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_permission_request.py" <<'EOF'
#!/usr/bin/env python3
import sys
import json

data = json.load(sys.stdin)

# Verify required fields
assert "command" in data

result = {"allow": True, "systemMessage": "✅ Input preserved"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_permission_request.py"

  local result=$(create_permission_input | bash "${TEMP_TEST_DIR}/ace_permission_request_wrapper.sh")

  assert_hook_output_contains "$result" "Input preserved"
}
