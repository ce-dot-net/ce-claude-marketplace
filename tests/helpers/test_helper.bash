#!/usr/bin/env bash
# test_helper.bash - Shared test utilities for Bats tests

# Load Bats libraries (if installed via Homebrew)
if [[ -d "/opt/homebrew/lib" ]]; then
  load '/opt/homebrew/lib/bats-support/load.bash'
  load '/opt/homebrew/lib/bats-assert/load.bash'
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

  # Create mock directories
  mkdir -p .claude/data
  mkdir -p "${HOME}/.claude/logs"
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

  # Clean up background logs
  rm -f "${HOME}/.claude/logs/ace-background-"*"-$$.log"
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
