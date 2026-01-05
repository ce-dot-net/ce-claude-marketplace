#!/usr/bin/env bats
# ace_stop_wrapper.bats - Unit tests for Stop hook async learning

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"
  create_mock_uv
  create_mock_python_hook "ace_after_task.py" "success"
  create_mock_python_hook "ace_event_logger.py" "success"

  # Copy actual hook script to temp location
  cp "${ACE_SCRIPTS_DIR}/ace_stop_wrapper.sh" "${TEMP_TEST_DIR}/"

  # Patch hook script to use mock paths
  sed -i.bak "s|PLUGIN_ROOT=.*|PLUGIN_ROOT=\"${TEMP_TEST_DIR}\"|" "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
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
  local start=$(python3 -c 'import time; print(int(time.time() * 1000))')
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  local end=$(python3 -c 'import time; print(int(time.time() * 1000))')
  local duration=$((end - start))

  # Assert: Hook returns quickly despite slow background task
  [[ $duration -lt 2000 ]] || {
    echo "Hook took ${duration}ms (expected <2000ms)" >&2
    return 1
  }
}

@test "async mode returns immediate success message" {
  export ACE_ASYNC_LEARNING=1

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Result indicates background learning
  echo "$result" | grep -q "Learning started in background"
  echo "$result" | grep -q '"continue": true'
}

@test "async mode creates background log file" {
  export ACE_ASYNC_LEARNING=1

  # Create failing Python hook to trigger error logging
  create_mock_python_hook "ace_after_task.py" "failure"

  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"

  # Wait for background process to complete
  sleep 1

  # Assert: Error log was created
  local log_count=$(ls -1 "${HOME}/.claude/logs/ace-background-"* 2>/dev/null | wc -l)
  [[ $log_count -gt 0 ]] || {
    echo "No background log files created" >&2
    return 1
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
  local start=$(python3 -c 'import time; print(int(time.time() * 1000))')
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  local end=$(python3 -c 'import time; print(int(time.time() * 1000))')
  local duration=$((end - start))

  # Assert: Hook blocks for at least 5 seconds
  [[ $duration -ge 5000 ]] || {
    echo "Hook returned too quickly in sync mode: ${duration}ms" >&2
    return 1
  }
}

@test "sync mode returns actual task result" {
  export ACE_ASYNC_LEARNING=0

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Result is from actual hook, not wrapper
  echo "$result" | grep -q "Mock success"
}

# ============================================================================
# Test: Flag File Coordination (v5.4.7)
# ============================================================================

@test "hook exits silently when ACE disabled flag exists" {
  # Create disabled flag
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Hook exits with success but no output
  [[ -z "$result" ]]
}

@test "hook runs normally when flag does not exist" {
  export ACE_ASYNC_LEARNING=1

  # Ensure no flag exists
  rm -f "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh")

  # Assert: Hook executed
  [[ -n "$result" ]]
  echo "$result" | grep -q "Learning started"
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
  mkdir -p "${TEMP_TEST_DIR}/project-root"
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

  local async_start=$(python3 -c 'import time; print(int(time.time() * 1000))')
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" >/dev/null
  local async_end=$(python3 -c 'import time; print(int(time.time() * 1000))')
  local async_duration=$((async_end - async_start))

  # Measure sync mode
  export ACE_ASYNC_LEARNING=0

  local sync_start=$(python3 -c 'import time; print(int(time.time() * 1000))')
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" >/dev/null
  local sync_end=$(python3 -c 'import time; print(int(time.time() * 1000))')
  local sync_duration=$((sync_end - sync_start))

  # Assert: Async is significantly faster
  local speedup=$((sync_duration / async_duration))
  [[ $speedup -ge 10 ]] || {
    echo "Async mode only ${speedup}x faster (expected >=10x)" >&2
    echo "Async: ${async_duration}ms, Sync: ${sync_duration}ms" >&2
    return 1
  }
}
