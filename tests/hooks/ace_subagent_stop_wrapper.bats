#!/usr/bin/env bats
# ace_subagent_stop_wrapper.bats - Unit tests for SubagentStop hook

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"
  create_mock_uv
  create_mock_python_hook "ace_after_task.py" "success"
  create_mock_python_hook "ace_event_logger.py" "success"

  # Setup hook using shared helper
  setup_hook_wrapper "ace_subagent_stop_wrapper.sh"
}

teardown() {
  teardown_test_env
}

# ============================================================================
# Test: Basic Functionality (Always Synchronous)
# ============================================================================

@test "hook always runs synchronously (no async mode)" {
  # Create slow Python hook (5s delay)
  create_mock_python_hook "ace_after_task.py" "slow"

  # Measure execution time
  local start=$(timing_get_ms)
  create_hook_input "SubagentStop" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh"
  local duration=$(timing_since "$start")

  # Assert: Hook blocks for at least 5 seconds (no background spawn)
  assert_duration_over "$duration" 5000 "Hook returned too quickly"
}

@test "hook returns actual task result" {
  local result=$(create_hook_input "SubagentStop" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh")

  # Assert: Result is from Python hook, not wrapper
  assert_hook_output_contains "$result" "Mock success"
}

@test "hook injects hook_event_name into JSON" {
  # Create Python hook that verifies hook_event_name
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py" <<'EOF'
#!/usr/bin/env python3
import sys
import json

data = json.load(sys.stdin)

# Verify hook_event_name was injected
assert data.get("hook_event_name") == "SubagentStop", f"Expected SubagentStop, got {data.get('hook_event_name')}"

result = {"continue": True, "systemMessage": "✅ Event name injected"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  local result=$(create_hook_input "SubagentStop" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh")

  assert_hook_output_contains "$result" "Event name injected"
}

# ============================================================================
# Test: Flag File Coordination (v5.4.7)
# ============================================================================

@test "hook respects ACE disabled flag" {
  test_hook_respects_disable_flag "ace_subagent_stop_wrapper.sh" "SubagentStop"
}

@test "hook runs normally when flag does not exist" {
  # Ensure no flag exists
  rm -f "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_hook_input "SubagentStop" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh")

  # Assert: Hook executed
  [[ -n "$result" ]]
  assert_hook_output_contains "$result" "Mock success"
}

# ============================================================================
# Test: CLI Detection (v5.4.7)
# ============================================================================

@test "hook exits silently when no CLI available" {
  test_hook_requires_cli "ace_subagent_stop_wrapper.sh" "SubagentStop"
}

# ============================================================================
# Test: Dependency Validation
# ============================================================================

@test "hook fails when logger script missing" {
  # Remove mock logger
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_event_logger.py"

  run bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh" <<< "$(create_hook_input 'SubagentStop')"

  # Assert: Hook fails with error message
  [[ $status -ne 0 ]]
  [[ "$output" =~ "ace_event_logger.py not found" ]]
}

@test "hook fails when after_task script missing" {
  # Remove mock hook script
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  run bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh" <<< "$(create_hook_input 'SubagentStop')"

  # Assert: Hook fails with error message
  [[ $status -ne 0 ]]
  [[ "$output" =~ "ace_after_task.py not found" ]]
}

# ============================================================================
# Test: Working Directory Handling
# ============================================================================

@test "hook changes to working directory from cwd field" {
  test_hook_extracts_working_dir "ace_subagent_stop_wrapper.sh" "SubagentStop"
}

@test "hook falls back to inferring directory from transcript_path" {
  # Create transcript in expected location
  mkdir -p "${TEMP_TEST_DIR}/.claude/data"
  touch "${TEMP_TEST_DIR}/.claude/data/transcript-test.jsonl"

  # Create hook input WITHOUT cwd
  local input=$(cat <<EOF
{
  "hook_event_name": "SubagentStop",
  "transcript_path": "${TEMP_TEST_DIR}/.claude/data/transcript-test.jsonl",
  "session_id": "${SESSION_ID}"
}
EOF
)

  echo "$input" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh"

  # Assert: No errors
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Argument Parsing
# ============================================================================

@test "hook accepts --log argument" {
  create_hook_input "SubagentStop" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh" --log

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook accepts --no-log argument" {
  create_hook_input "SubagentStop" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh" --no-log

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook accepts multiple arguments" {
  create_hook_input "SubagentStop" | bash "${TEMP_TEST_DIR}/ace_subagent_stop_wrapper.sh" --log --chat --notify

  # Assert: No errors
  [[ $? -eq 0 ]]
}
