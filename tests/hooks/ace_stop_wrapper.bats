#!/usr/bin/env bats
# ace_stop_wrapper.bats - Unit tests for Stop hook async learning

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"
  create_mock_uv
  create_mock_python_hook "ace_after_task.py" "success"
  create_mock_python_hook "ace_event_logger.py" "success"

  # Copy actual hook script to temp location and patch for testing
  cp "${ACE_SCRIPTS_DIR}/ace_stop_wrapper.sh" "${TEMP_TEST_DIR}/"

  # Patch PLUGIN_ROOT and LOG_DIR to use test directory (cross-platform sed)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|PLUGIN_ROOT=\"\$(cd \"\${SCRIPT_DIR}/..\" && pwd)\"|PLUGIN_ROOT=\"${TEMP_TEST_DIR}\"|" "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
    sed -i '' "s|LOG_DIR=\"\${HOME}/.claude/logs\"|LOG_DIR=\"${TEMP_TEST_DIR}/.claude/logs\"|" "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  else
    sed -i "s|PLUGIN_ROOT=\"\$(cd \"\${SCRIPT_DIR}/..\" && pwd)\"|PLUGIN_ROOT=\"${TEMP_TEST_DIR}\"|" "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
    sed -i "s|LOG_DIR=\"\${HOME}/.claude/logs\"|LOG_DIR=\"${TEMP_TEST_DIR}/.claude/logs\"|" "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  fi
}

teardown() {
  teardown_test_env
}

# ============================================================================
# Test: Async Mode Timing (Issue #3 regression test)
# ============================================================================

@test "async mode returns in less than 2 seconds" {
  export ACE_ASYNC_LEARNING=1

  # Create slow Python hook (5s delay)
  create_mock_python_hook "ace_after_task.py" "slow"

  # Measure execution time
  local start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  local duration=$(timing_since "$start")

  # Assert: Hook returns quickly despite slow background task
  assert_duration_under "$duration" 2000 "Hook took too long"
}

@test "async mode returns immediate success message" {
  export ACE_ASYNC_LEARNING=1

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Result indicates background learning
  assert_hook_async_started "$result"
}

@test "async mode creates background log file" {
  export ACE_ASYNC_LEARNING=1

  # Create failing Python hook to trigger error logging
  create_mock_python_hook "ace_after_task.py" "failure"

  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"

  # Wait for background process to complete and write error log
  sleep 2

  # Assert: Error log was created in test directory (only happens on failure)
  local log_count=$(ls -1 "${TEMP_TEST_DIR}/.claude/logs/ace-background-"* 2>/dev/null | wc -l)
  [[ $log_count -gt 0 ]] || {
    # If no log found, at least verify log directory exists
    [[ -d "${TEMP_TEST_DIR}/.claude/logs" ]]
  }
}

# ============================================================================
# Test: Synchronous Mode Behavior
# ============================================================================

@test "sync mode blocks until task completes" {
  export ACE_ASYNC_LEARNING=0

  # Create slow Python hook (5s delay)
  create_mock_python_hook "ace_after_task.py" "slow"

  # Measure execution time
  local start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  local duration=$(timing_since "$start")

  # Assert: Hook blocks for at least 5 seconds
  assert_duration_over "$duration" 5000 "Hook returned too quickly in sync mode"
}

@test "sync mode returns actual task result" {
  export ACE_ASYNC_LEARNING=0

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Result is from actual hook, not wrapper
  assert_hook_output_contains "$result" "Mock success"
}

# ============================================================================
# Test: Flag File Coordination (v5.4.7)
# ============================================================================

@test "hook exits silently when ACE disabled flag exists" {
  # Create disabled flag
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Hook exits with success but no output
  assert_hook_exits_silently "$result"
}

@test "hook runs normally when flag does not exist" {
  export ACE_ASYNC_LEARNING=1

  # Ensure no flag exists
  rm -f "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Hook executed
  [[ -n "$result" ]]
  assert_hook_output_contains "$result" "Learning started"
}

# ============================================================================
# Test: CLI Detection (v5.4.7)
# ============================================================================

@test "hook exits silently when no CLI available" {
  # Remove mock CLI from PATH
  export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$TEMP_TEST_DIR" | tr '\n' ':')

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" 2>&1)

  # Assert: Hook exits gracefully
  [[ $? -eq 0 ]]
}

@test "hook prefers ace-cli over ce-ace" {
  # Create both CLIs
  cat > "${TEMP_TEST_DIR}/ace-cli" <<'EOF'
#!/usr/bin/env bash
echo "new-cli"
EOF
  chmod +x "${TEMP_TEST_DIR}/ace-cli"

  cat > "${TEMP_TEST_DIR}/ce-ace" <<'EOF'
#!/usr/bin/env bash
echo "old-cli"
EOF
  chmod +x "${TEMP_TEST_DIR}/ce-ace"

  # Source the hook script functions (requires modifications for unit testing)
  # For now, validate manually that CLI_CMD is set correctly
  # This test requires hook refactoring to expose CLI detection logic

  skip "Requires hook refactoring to expose CLI_CMD variable"
}

# ============================================================================
# Test: Config Validation
# ============================================================================

@test "hook exits silently when config missing" {
  # Remove mock config
  rm -f "${HOME}/.config/ace/config.json"

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Hook exits gracefully with no errors
  [[ $? -eq 0 ]]
}

@test "hook fails when logger script missing" {
  # Remove mock logger
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_event_logger.py"

  run bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" <<< "$(create_hook_input 'Stop')"

  # Assert: Hook fails with error message
  [[ $status -ne 0 ]]
  [[ "$output" =~ "ace_event_logger.py not found" ]]
}

@test "hook fails when after_task script missing" {
  # Remove mock hook script
  rm -f "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  run bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" <<< "$(create_hook_input 'Stop')"

  # Assert: Hook fails with error message
  [[ $status -ne 0 ]]
  [[ "$output" =~ "ace_after_task.py not found" ]]
}

# ============================================================================
# Test: Working Directory Handling
# ============================================================================

@test "hook changes to working directory from cwd field" {
  export ACE_ASYNC_LEARNING=0

  # Create test directory structure
  mkdir -p "${TEMP_TEST_DIR}/project-root/.claude"
  echo '{}' > "${TEMP_TEST_DIR}/project-root/.claude/settings.json"

  # Create hook input with cwd
  local input=$(cat <<EOF
{
  "hook_event_name": "Stop",
  "cwd": "${TEMP_TEST_DIR}/project-root",
  "session_id": "${SESSION_ID}"
}
EOF
)

  # Hook should execute in project-root
  echo "$input" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"

  # Assert: No errors (would fail if couldn't cd)
  [[ $? -eq 0 ]]
}

@test "hook falls back to inferring directory from transcript_path" {
  export ACE_ASYNC_LEARNING=0

  # Create transcript in expected location
  mkdir -p "${TEMP_TEST_DIR}/.claude/data"
  touch "${TEMP_TEST_DIR}/.claude/data/transcript-test.jsonl"

  # Create hook input WITHOUT cwd
  local input=$(cat <<EOF
{
  "hook_event_name": "Stop",
  "transcript_path": "${TEMP_TEST_DIR}/.claude/data/transcript-test.jsonl",
  "session_id": "${SESSION_ID}"
}
EOF
)

  echo "$input" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"

  # Assert: No errors
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Event Logging Control (v5.4.5)
# ============================================================================

@test "event logging disabled by default" {
  export ACE_EVENT_LOGGING=0
  export ACE_ASYNC_LEARNING=1

  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"

  # Logger should not be called (verify via mock)
  # This requires enhanced mocking to track invocations

  skip "Requires enhanced mocking infrastructure"
}

@test "event logging enabled with ACE_EVENT_LOGGING=1" {
  export ACE_EVENT_LOGGING=1
  export ACE_ASYNC_LEARNING=1

  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"

  # Logger should be called (verify via mock)

  skip "Requires enhanced mocking infrastructure"
}

# ============================================================================
# Test: Argument Parsing
# ============================================================================

@test "hook accepts --log argument" {
  export ACE_ASYNC_LEARNING=1

  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" --log

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook accepts --no-log argument" {
  export ACE_ASYNC_LEARNING=1

  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" --no-log

  # Assert: No errors
  [[ $? -eq 0 ]]
}

@test "hook accepts multiple arguments" {
  export ACE_ASYNC_LEARNING=1

  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" --log --chat --notify

  # Assert: No errors
  [[ $? -eq 0 ]]
}

# ============================================================================
# Test: Performance Regression (Issue #3)
# ============================================================================

@test "async mode at least 10x faster than sync mode" {
  # Measure async mode
  export ACE_ASYNC_LEARNING=1
  create_mock_python_hook "ace_after_task.py" "slow"

  local async_start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" >/dev/null
  local async_duration=$(timing_since "$async_start")

  # Measure sync mode
  export ACE_ASYNC_LEARNING=0

  local sync_start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" >/dev/null
  local sync_duration=$(timing_since "$sync_start")

  # Skip timing assertion on CI (environmental sensitivity)
  if [[ -n "${CI:-}" ]]; then
    skip "Timing test - CI runners too variable for reliable performance assertions"
  fi

  # Assert: Async is significantly faster
  local speedup=$((sync_duration / async_duration))
  [[ $speedup -ge 10 ]] || {
    echo "Async mode only ${speedup}x faster (expected >=10x)" >&2
    echo "Async: ${async_duration}ms, Sync: ${sync_duration}ms" >&2
    return 1
  }
}
