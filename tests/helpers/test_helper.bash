#!/usr/bin/env bash
# test_helper.bash - Shared test utilities for Bats tests

# Load Bats libraries (if installed via Homebrew)
# These are optional - tests work without them
if [[ -f "/opt/homebrew/lib/bats-support/load.bash" ]]; then
  load '/opt/homebrew/lib/bats-support/load.bash'
fi
if [[ -f "/opt/homebrew/lib/bats-assert/load.bash" ]]; then
  load '/opt/homebrew/lib/bats-assert/load.bash'
fi
if [[ -f "/opt/homebrew/lib/bats-file/load.bash" ]]; then
  load '/opt/homebrew/lib/bats-file/load.bash'
fi

# Project root
export PROJECT_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
export ACE_PLUGIN_ROOT="${PROJECT_ROOT}/plugins/ace"
export ACE_SCRIPTS_DIR="${ACE_PLUGIN_ROOT}/scripts"

# Test fixtures
export FIXTURES_DIR="${BATS_TEST_DIRNAME}/../fixtures"
export TEMP_TEST_DIR="${BATS_TEST_TMPDIR}/ace-test-$$"

# Setup function - creates isolated test environment
setup_test_env() {
  # Create temp directory for test
  mkdir -p "$TEMP_TEST_DIR"
  cd "$TEMP_TEST_DIR"

  # Create mock directories (using TEMP_TEST_DIR for isolation)
  mkdir -p .claude/data
  mkdir -p .claude/logs
  mkdir -p "${HOME}/.config/ace"

  # Set test environment variables
  export SESSION_ID="test-session-$$"
  export CLAUDE_SESSION_ID="$SESSION_ID"
  export CLAUDE_PROJECT_ROOT="$TEMP_TEST_DIR"
  export ACE_EVENT_LOGGING=0  # Disable by default for tests

  # Mock config file
  echo '{"org_id":"test-org","project_id":"test-project"}' > "${HOME}/.config/ace/config.json"

}

# Teardown function - cleans up test environment
teardown_test_env() {
  # Remove temp directory
  if [[ -d "$TEMP_TEST_DIR" ]]; then
    rm -rf "$TEMP_TEST_DIR"
  fi

  # Remove test flag files
  rm -f "/tmp/ace-disabled-${SESSION_ID}.flag"
}

# Mock ace-cli command
create_mock_ace_cli() {
  local behavior="${1:-success}"
  local delay="${2:-0}"

  cat > "${TEMP_TEST_DIR}/mock-ace-cli" <<EOF
#!/usr/bin/env bash
# Mock ace-cli for testing
sleep ${delay}
case "${behavior}" in
  success)
    echo '{"status":"success","patterns":[]}'
    exit 0
    ;;
  failure)
    echo '{"error":"Mock failure"}' >&2
    exit 1
    ;;
  timeout)
    sleep 30
    exit 0
    ;;
  *)
    echo '{"status":"unknown"}'
    exit 0
    ;;
esac
EOF
  chmod +x "${TEMP_TEST_DIR}/mock-ace-cli"
  export PATH="${TEMP_TEST_DIR}:${PATH}"
  export CLI_CMD="${TEMP_TEST_DIR}/mock-ace-cli"
}

# Mock uv run command
create_mock_uv() {
  cat > "${TEMP_TEST_DIR}/uv" <<'EOF'
#!/usr/bin/env bash
# Mock uv for testing - just execute the Python script directly
shift  # Remove 'run' argument
exec python3 "$@"
EOF
  chmod +x "${TEMP_TEST_DIR}/uv"
  export PATH="${TEMP_TEST_DIR}:${PATH}"
}

# Create mock Python hook script
create_mock_python_hook() {
  local script_name="$1"
  local behavior="${2:-success}"

  mkdir -p "${TEMP_TEST_DIR}/shared-hooks"
  cat > "${TEMP_TEST_DIR}/shared-hooks/${script_name}" <<EOF
#!/usr/bin/env python3
import sys
import json
import time

behavior = "${behavior}"

if behavior == "success":
    result = {"continue": True, "systemMessage": "✅ Mock success"}
    print(json.dumps(result))
    sys.exit(0)
elif behavior == "slow":
    time.sleep(5)
    result = {"continue": True, "systemMessage": "✅ Slow success"}
    print(json.dumps(result))
    sys.exit(0)
elif behavior == "failure":
    print("Mock failure", file=sys.stderr)
    sys.exit(1)
else:
    sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/${script_name}"
}

# Measure execution time in milliseconds
measure_time() {
  local start=$(python3 -c 'import time; print(int(time.time() * 1000))')
  "$@"
  local end=$(python3 -c 'import time; print(int(time.time() * 1000))')
  echo $((end - start))
}

# ============================================================================
# Timing Utilities (Sprint 1 Task 1 - Refactoring Infrastructure)
# ============================================================================
# Extracted from 17 duplicated instances across hook tests.
# Provides consistent timing measurement and assertion functions.
#
# Functions:
#   timing_get_ms()              - Get current timestamp in ms
#   timing_since "$start"        - Calculate elapsed time since start
#   assert_duration_under "$duration" "$threshold" ["msg"]
#   assert_duration_over "$duration" "$threshold" ["msg"]
# ============================================================================

# Get current timestamp in milliseconds
timing_get_ms() {
  python3 -c 'import time; print(int(time.time() * 1000))'
}

# Calculate elapsed time since start timestamp
timing_since() {
  local start="$1"
  local end=$(timing_get_ms)
  echo $((end - start))
}

# Assert duration is under threshold
assert_duration_under() {
  local duration="$1"
  local threshold="$2"
  local message="${3:-Duration exceeded threshold}"

  if [[ $duration -ge $threshold ]]; then
    echo "[FAIL] ${message}: ${duration}ms (expected <${threshold}ms)" >&2
    return 1
  fi
  return 0
}

# Assert duration is over threshold (for blocking tests)
assert_duration_over() {
  local duration="$1"
  local threshold="$2"
  local message="${3:-Duration below threshold}"

  if [[ $duration -lt $threshold ]]; then
    echo "[FAIL] ${message}: ${duration}ms (expected >=${threshold}ms)" >&2
    return 1
  fi
  return 0
}

# ============================================================================
# Semantic Hook Assertions (Sprint 1 Task 2)
# ============================================================================
# Provides high-level assertions that express test intent clearly.
# ============================================================================

# Assert hook exited silently (no output, exit 0)
assert_hook_exits_silently() {
  local result="$1"
  local message="${2:-Hook did not exit silently}"

  if [[ -n "$result" ]]; then
    echo "[FAIL] ${message}: Expected empty output, got: ${result}" >&2
    return 1
  fi
  return 0
}

# Assert hook succeeded (contains continue:true, exit 0)
assert_hook_succeeded() {
  local result="$1"
  local message="${2:-Hook did not succeed}"

  if ! echo "$result" | grep -q '"continue": true'; then
    echo "[FAIL] ${message}: Missing 'continue: true' in: ${result}" >&2
    return 1
  fi
  return 0
}

# Assert hook failed (exit code non-zero)
assert_hook_failed() {
  local exit_code="$1"
  local message="${2:-Hook did not fail as expected}"

  if [[ $exit_code -eq 0 ]]; then
    echo "[FAIL] ${message}: Exit code was 0" >&2
    return 1
  fi
  return 0
}

# Assert hook output contains string
assert_hook_output_contains() {
  local output="$1"
  local expected="$2"
  local message="${3:-Hook output missing expected string}"

  if ! echo "$output" | grep -q "$expected"; then
    echo "[FAIL] ${message}: Expected '${expected}' in: ${output}" >&2
    return 1
  fi
  return 0
}

# Assert hook output does NOT contain string
assert_hook_output_not_contains() {
  local output="$1"
  local unexpected="$2"
  local message="${3:-Hook output contains unexpected string}"

  if echo "$output" | grep -q "$unexpected"; then
    echo "[FAIL] ${message}: Found '${unexpected}' in: ${output}" >&2
    return 1
  fi
  return 0
}

# Assert hook JSON contains field with value
assert_hook_json_field() {
  local result="$1"
  local field="$2"
  local expected="$3"
  local message="${4:-Hook JSON field mismatch}"

  local actual=$(echo "$result" | jq -r ".${field}")
  if [[ "$actual" != "$expected" ]]; then
    echo "[FAIL] ${message}: Expected ${field}='${expected}', got '${actual}'" >&2
    return 1
  fi
  return 0
}

# Assert hook returned async background message
assert_hook_async_started() {
  local result="$1"
  local message="${2:-Hook did not indicate async start}"

  assert_hook_output_contains "$result" "Learning started in background" "$message" && \
  assert_hook_json_field "$result" "continue" "true" "$message"
}

# Assert file exists within timeout
assert_file_eventually_exists() {
  local file="$1"
  local timeout="${2:-5}"
  local elapsed=0

  while [[ $elapsed -lt $timeout ]]; do
    if [[ -f "$file" ]]; then
      return 0
    fi
    sleep 0.1
    elapsed=$((elapsed + 1))
  done

  echo "File did not appear within ${timeout}s: $file" >&2
  return 1
}

# ============================================================================
# Reusable Hook Test Patterns
# ============================================================================
# Generic test helpers for common hook wrapper behaviors
# ============================================================================

# Setup hook wrapper for testing - copies and patches for isolation
setup_hook_wrapper() {
  local hook_name="$1"  # e.g., "ace_stop_wrapper.sh"
  local patch_log_dir="${2:-false}"  # Optional: patch LOG_DIR for hooks that use it

  # Copy hook to test directory
  cp "${ACE_SCRIPTS_DIR}/${hook_name}" "${TEMP_TEST_DIR}/"

  # Patch PLUGIN_ROOT to use test directory (cross-platform sed)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|PLUGIN_ROOT=\"\$(cd \"\${SCRIPT_DIR}/..\" && pwd)\"|PLUGIN_ROOT=\"${TEMP_TEST_DIR}\"|" "${TEMP_TEST_DIR}/${hook_name}"

    # Optionally patch LOG_DIR for hooks that create background logs
    if [[ "$patch_log_dir" == "true" ]]; then
      sed -i '' "s|LOG_DIR=\"\${HOME}/.claude/logs\"|LOG_DIR=\"${TEMP_TEST_DIR}/.claude/logs\"|" "${TEMP_TEST_DIR}/${hook_name}"
    fi
  else
    sed -i "s|PLUGIN_ROOT=\"\$(cd \"\${SCRIPT_DIR}/..\" && pwd)\"|PLUGIN_ROOT=\"${TEMP_TEST_DIR}\"|" "${TEMP_TEST_DIR}/${hook_name}"

    if [[ "$patch_log_dir" == "true" ]]; then
      sed -i "s|LOG_DIR=\"\${HOME}/.claude/logs\"|LOG_DIR=\"${TEMP_TEST_DIR}/.claude/logs\"|" "${TEMP_TEST_DIR}/${hook_name}"
    fi
  fi
}

# Test that hook respects ACE_DISABLED_FLAG
test_hook_respects_disable_flag() {
  local hook_name="$1"
  local event_type="${2:-Stop}"

  # Create disabled flag
  touch "/tmp/ace-disabled-${SESSION_ID}.flag"

  local result=$(create_hook_input "$event_type" | bash "${TEMP_TEST_DIR}/${hook_name}")

  # Assert: Hook exits silently
  assert_hook_exits_silently "$result"
}

# Test that hook exits when CLI not available
test_hook_requires_cli() {
  local hook_name="$1"
  local event_type="${2:-Stop}"

  # Remove CLI from PATH
  export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$TEMP_TEST_DIR" | tr '\n' ':')

  local result=$(create_hook_input "$event_type" | bash "${TEMP_TEST_DIR}/${hook_name}" 2>&1)

  # Assert: Hook exits gracefully (exit 0)
  [[ $? -eq 0 ]]
}

# Test that hook extracts working directory from event JSON
test_hook_extracts_working_dir() {
  local hook_name="$1"
  local event_type="${2:-Stop}"

  # Create test directory structure
  mkdir -p "${TEMP_TEST_DIR}/project-root/.claude"
  echo '{}' > "${TEMP_TEST_DIR}/project-root/.claude/settings.json"

  # Create hook input with cwd
  local input=$(cat <<EOF
{
  "hook_event_name": "${event_type}",
  "cwd": "${TEMP_TEST_DIR}/project-root",
  "session_id": "${SESSION_ID}"
}
EOF
)

  # Hook should execute in project-root
  echo "$input" | bash "${TEMP_TEST_DIR}/${hook_name}" >/dev/null 2>&1

  # Assert: No errors (would fail if couldn't cd)
  [[ $? -eq 0 ]]
}

# Create test input JSON for hooks
create_hook_input() {
  local hook_event="${1:-Stop}"

  cat <<EOF
{
  "hook_event_name": "${hook_event}",
  "cwd": "${TEMP_TEST_DIR}",
  "working_directory": "${TEMP_TEST_DIR}",
  "session_id": "${SESSION_ID}",
  "transcript_path": "${TEMP_TEST_DIR}/.claude/data/transcript-test.jsonl"
}
EOF
}
