#!/usr/bin/env bats
# ace_regression_tests.bats - Regression tests to catch if async behavior breaks

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"
  create_mock_uv
  create_mock_python_hook "ace_event_logger.py" "success"

  # Copy actual hook script to temp location and patch for testing
  cp "${ACE_SCRIPTS_DIR}/ace_stop_wrapper.sh" "${TEMP_TEST_DIR}/"

  # Patch PLUGIN_ROOT to use test directory (cross-platform sed)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|PLUGIN_ROOT=\"\$(cd \"\${SCRIPT_DIR}/..\" && pwd)\"|PLUGIN_ROOT=\"${TEMP_TEST_DIR}\"|" "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  else
    sed -i "s|PLUGIN_ROOT=\"\$(cd \"\${SCRIPT_DIR}/..\" && pwd)\"|PLUGIN_ROOT=\"${TEMP_TEST_DIR}\"|" "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  fi
}

teardown() {
  teardown_test_env
}

# ============================================================================
# REGRESSION: Verify Async ACTUALLY Runs in Background
# ============================================================================

@test "REGRESSION: async mode spawns actual background process" {
  export ACE_ASYNC_LEARNING=1

  # Create slow Python hook (10s delay) that leaves a marker file
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py" <<EOF
#!/usr/bin/env python3
import sys
import json
import time
import os

# Create marker file to prove we ran (using TEMP_TEST_DIR for isolation)
marker = os.path.join('${TEMP_TEST_DIR}', '.claude/logs/background-marker.txt')
os.makedirs(os.path.dirname(marker), exist_ok=True)

with open(marker, 'w') as f:
    f.write('background process executed\\n')

# Sleep to simulate long-running task
time.sleep(10)

result = {"continue": True, "systemMessage": "✅ Slow success"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  # Delete any existing marker (using Python instead of rm)
  python3 -c "import os; f='${TEMP_TEST_DIR}/.claude/logs/background-marker.txt'; os.path.exists(f) and os.remove(f)"

  # Run hook in async mode
  local start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  local duration=$(timing_since "$start")

  # CRITICAL: Hook MUST return in <2s even though task takes 10s
  if [[ $duration -ge 2000 ]]; then
    echo "REGRESSION: Async mode took ${duration}ms (expected <2000ms)" >&2
    echo "This means async execution is BROKEN - not actually running in background!" >&2
    return 1
  fi

  # Marker should NOT exist yet (background still running)
  if [[ -f "${TEMP_TEST_DIR}/.claude/logs/background-marker.txt" ]]; then
    echo "REGRESSION: Background task completed too quickly!" >&2
    echo "Expected task to still be running in background" >&2
    return 1
  fi

  # Wait for background task to complete
  sleep 11

  # NOW marker should exist (proves background task ran)
  [[ -f "${TEMP_TEST_DIR}/.claude/logs/background-marker.txt" ]] || {
    echo "REGRESSION: Background task never ran!" >&2
    echo "Marker file not found - async execution is BROKEN" >&2
    return 1
  }

  # Cleanup using Python
  python3 -c "import os; f='${TEMP_TEST_DIR}/.claude/logs/background-marker.txt'; os.path.exists(f) and os.remove(f)"
}

@test "REGRESSION: sync mode does NOT spawn background process" {
  export ACE_ASYNC_LEARNING=0

  # Create slow Python hook (5s delay) that leaves a marker file
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py" <<EOF
#!/usr/bin/env python3
import sys
import json
import time
import os

# Create marker file immediately (using TEMP_TEST_DIR for isolation)
marker = os.path.join('${TEMP_TEST_DIR}', '.claude/logs/sync-marker.txt')
os.makedirs(os.path.dirname(marker), exist_ok=True)

with open(marker, 'w') as f:
    f.write('sync process executed\\n')

# Sleep to simulate processing
time.sleep(5)

result = {"continue": True, "systemMessage": "✅ Sync success"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  # Delete any existing marker
  python3 -c "import os; f='${TEMP_TEST_DIR}/.claude/logs/sync-marker.txt'; os.path.exists(f) and os.remove(f)"

  # Run hook in sync mode
  local start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh"
  local duration=$(timing_since "$start")

  # CRITICAL: Hook MUST block for at least 5s
  if [[ $duration -lt 5000 ]]; then
    echo "REGRESSION: Sync mode took only ${duration}ms (expected >=5000ms)" >&2
    echo "This means sync mode is NOT blocking - async logic leaked into sync!" >&2
    return 1
  fi

  # Marker MUST exist immediately after return (task ran synchronously)
  [[ -f "${TEMP_TEST_DIR}/.claude/logs/sync-marker.txt" ]] || {
    echo "REGRESSION: Sync task didn't run or didn't create marker" >&2
    return 1
  }

  # Cleanup
  python3 -c "import os; f='${TEMP_TEST_DIR}/.claude/logs/sync-marker.txt'; os.path.exists(f) and os.remove(f)"
}

@test "REGRESSION: disabling async via ACE_ASYNC_LEARNING=0 actually works" {
  # This test ensures ACE_ASYNC_LEARNING=0 isn't just ignored

  # Create marker-based hook
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py" <<EOF
#!/usr/bin/env python3
import sys
import json
import time
import os

# Using TEMP_TEST_DIR for isolation
marker = os.path.join('${TEMP_TEST_DIR}', '.claude/logs/mode-test-marker.txt')
os.makedirs(os.path.dirname(marker), exist_ok=True)

# Write start time
with open(marker, 'w') as f:
    f.write(str(time.time()) + '\\n')

time.sleep(3)

result = {"continue": True, "systemMessage": "✅ Done"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  python3 -c "import os; f='${TEMP_TEST_DIR}/.claude/logs/mode-test-marker.txt'; os.path.exists(f) and os.remove(f)"

  # Test with ACE_ASYNC_LEARNING=0
  export ACE_ASYNC_LEARNING=0
  local start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" >/dev/null
  local sync_duration=$(timing_since "$start")

  # Should have blocked for 3+ seconds
  if [[ $sync_duration -lt 3000 ]]; then
    echo "REGRESSION: ACE_ASYNC_LEARNING=0 didn't block (${sync_duration}ms)" >&2
    return 1
  fi

  python3 -c "import os; f='${TEMP_TEST_DIR}/.claude/logs/mode-test-marker.txt'; os.path.exists(f) and os.remove(f)"

  # Now test with ACE_ASYNC_LEARNING=1
  export ACE_ASYNC_LEARNING=1
  start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" >/dev/null
  local async_duration=$(timing_since "$start")

  # Should have returned quickly
  if [[ $async_duration -ge 2000 ]]; then
    echo "REGRESSION: ACE_ASYNC_LEARNING=1 blocked (${async_duration}ms)" >&2
    return 1
  fi

  # The difference should be SIGNIFICANT (at least 2s)
  local difference=$((sync_duration - async_duration))
  [[ $difference -ge 2000 ]] || {
    echo "REGRESSION: No meaningful difference between sync (${sync_duration}ms) and async (${async_duration}ms)" >&2
    echo "Expected at least 2000ms difference, got ${difference}ms" >&2
    return 1
  }
}

@test "REGRESSION: async mode would fail if background spawn removed" {
  # This is a "canary" test - if someone removes the '&' from the hook script,
  # this test should catch it

  export ACE_ASYNC_LEARNING=1

  # Create a deliberately slow hook
  cat > "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py" <<'EOF'
#!/usr/bin/env python3
import sys
import json
import time

# This will take 8 seconds
time.sleep(8)

result = {"continue": True, "systemMessage": "✅ Finally done"}
print(json.dumps(result))
sys.exit(0)
EOF
  chmod +x "${TEMP_TEST_DIR}/shared-hooks/ace_after_task.py"

  # Measure how long the hook takes
  local start=$(timing_get_ms)
  create_hook_input "Stop" | bash "${TEMP_TEST_DIR}/ace_stop_wrapper.sh" >/dev/null
  local duration=$(timing_since "$start")

  # If this test PASSES (duration < 2000), async is working
  # If this test FAILS (duration >= 8000), someone broke async mode!
  if [[ $duration -ge 2000 ]]; then
    echo "🚨 CRITICAL REGRESSION DETECTED! 🚨" >&2
    echo "" >&2
    echo "Hook took ${duration}ms with ACE_ASYNC_LEARNING=1" >&2
    echo "This means the background spawn ('&') is missing or broken!" >&2
    echo "" >&2
    echo "Expected: <2000ms (background execution)" >&2
    echo "Got:      ${duration}ms (synchronous execution)" >&2
    echo "" >&2
    echo "Someone likely removed the '&' from line 136 in ace_stop_wrapper.sh" >&2
    echo "or broke the async execution logic in some other way." >&2
    return 1
  fi
}
