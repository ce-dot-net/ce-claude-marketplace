#!/usr/bin/env bats
# ace_after_task_wrapper.bats - Unit tests for AfterTask hook wrapper

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_uv
  create_mock_python_hook "ace_after_task.py" "success"

  # Setup hook using shared helper
  setup_hook_wrapper "ace_after_task_wrapper.sh"
}

teardown() {
  teardown_test_env
}

# ============================================================================
# Test: Basic Functionality
# ============================================================================

@test "hook forwards to Python script with exec" {
  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_after_task_wrapper.sh")

  # Assert: Python hook was called
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook passes arguments to Python script" {
  # Create Python hook that echoes its arguments
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py" <<'EOF'
#!/usr/bin/env python3
import sys
import json

# Echo arguments received
result = {"continue": True, "systemMessage": f"Args: {' '.join(sys.argv[1:])}"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_after_task_wrapper.sh" --test arg1 arg2)

  # Assert: Arguments were passed through (use grep -F for literal string match)
  echo "$result" | grep -qF "arg1 arg2" || {
    echo "[FAIL] Arguments not passed: ${result}" >&2
    return 1
  }
}

@test "hook fails when Python script missing" {
  # Remove mock hook script
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  run bash "${TEMP_TEST_DIR}/ace_after_task_wrapper.sh" <<< '{}'

  # Assert: Hook fails with error message
  [[ $status -ne 0 ]]
  [[ "$output" =~ "ace_after_task.py not found" ]]
}

# ============================================================================
# Test: Minimal Wrapper Behavior
# ============================================================================

@test "hook has no flag file check (minimal wrapper)" {
  # Create disabled flag (should be ignored)
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_after_task_wrapper.sh")

  # Assert: Hook still executes
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook has no CLI detection (minimal wrapper)" {
  # Remove CLI from PATH
  export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$TEMP_TEST_DIR" | tr '\n' ':')

  local result=$(echo '{}' | bash "${TEMP_TEST_DIR}/ace_after_task_wrapper.sh")

  # Assert: Hook still works
  assert_hook_output_contains "$result" "Mock success"
}
