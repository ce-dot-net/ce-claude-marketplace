#!/usr/bin/env bats
# ace_before_task_wrapper.bats - Unit tests for BeforeTask hook

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"
  create_mock_uv
  create_mock_python_hook "ace_before_task.py" "success"

  # Setup hook using shared helper
  setup_hook_wrapper "ace_before_task_wrapper.sh"
}

teardown() {
  teardown_test_env
}

# ============================================================================
# Test: Basic Functionality
# ============================================================================

@test "hook forwards input to Python script" {
  local result=$(create_hook_input "UserPromptSubmit" | bash "${TEMP_TEST_DIR}/ace_before_task_wrapper.sh")

  # Assert: Python hook was called and returned success
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook changes to working directory from cwd field" {
  test_hook_extracts_working_dir "ace_before_task_wrapper.sh" "UserPromptSubmit"
}

@test "hook falls back to inferring directory from transcript_path" {
  # Create transcript in expected location
  mkdir -p "${TEMP_TEST_DIR}/.claude/data"
  touch "${TEMP_TEST_DIR}/.claude/data/transcript-test.jsonl"

  # Create hook input WITHOUT cwd
  local input=$(cat <<EOF
{
  "hook_event_name": "UserPromptSubmit",
  "transcript_path": "${TEMP_TEST_DIR}/.claude/data/transcript-test.jsonl",
  "session_id": "${SESSION_ID}"
}
EOF
)

  echo "$input" | bash "${TEMP_TEST_DIR}/ace_before_task_wrapper.sh"

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook fails when Python script missing" {
  # Remove mock hook script
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_before_task.py"

  run bash "${TEMP_TEST_DIR}/ace_before_task_wrapper.sh" <<< "$(create_hook_input 'UserPromptSubmit')"

  # Assert: Hook fails with error message
  [[ $status -ne 0 ]]
  [[ "$output" =~ "ace_before_task.py not found" ]]
}

@test "hook preserves stdin JSON correctly" {
  # Create Python hook that echoes the input it receives
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_before_task.py" <<'EOF'
#!/usr/bin/env python3
import sys
import json

# Read stdin
data = json.load(sys.stdin)

# Verify we received the correct fields
assert "hook_event_name" in data
assert "session_id" in data

result = {"continue": True, "systemMessage": "✅ Input preserved"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_before_task.py"

  local result=$(create_hook_input "UserPromptSubmit" | bash "${TEMP_TEST_DIR}/ace_before_task_wrapper.sh")

  # Assert: Python script received and processed input
  assert_hook_output_contains "$result" "Input preserved"
}

# ============================================================================
# Test: Minimal Hook Behavior
# ============================================================================

@test "hook has no flag file check (forwards to all sessions)" {
  # Create disabled flag (should be ignored by this hook)
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_hook_input "UserPromptSubmit" | bash "${TEMP_TEST_DIR}/ace_before_task_wrapper.sh")

  # Assert: Hook still executes (does not respect disable flag)
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook has no CLI detection (minimal wrapper)" {
  # Remove CLI from PATH
  export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$TEMP_TEST_DIR" | tr '\n' ':')

  local result=$(create_hook_input "UserPromptSubmit" | bash "${TEMP_TEST_DIR}/ace_before_task_wrapper.sh")

  # Assert: Hook still works (no CLI dependency in wrapper)
  assert_hook_output_contains "$result" "Mock success"
}
