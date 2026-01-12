#!/usr/bin/env bash
# hook_simulator.sh - Integration test harness that simulates Claude Code's hook execution
set -euo pipefail

# ============================================================================
# Hook Simulator - Mimics Claude Code's hook trigger mechanism
# ============================================================================

simulate_hook_trigger() {
  local hook_name="$1"
  local hook_script="$2"
  local context_json="${3:-{}}"
  local stdin_json="${4:-}"

  # Validate hook script exists
  if [[ ! -f "$hook_script" ]]; then
    echo "{\"error\": \"Hook script not found: $hook_script\"}" | jq -c
    return 1
  fi

  # Set up environment like Claude Code does
  export CLAUDE_SESSION_ID="${CLAUDE_SESSION_ID:-sim-$(uuidgen | tr -d '-')}"
  export CLAUDE_PROJECT_ROOT="${CLAUDE_PROJECT_ROOT:-$(pwd)}"
  export SESSION_ID="$CLAUDE_SESSION_ID"

  # Load context variables from JSON
  if [[ -n "$context_json" ]] && [[ "$context_json" != "{}" ]]; then
    # Validate JSON first
    if echo "$context_json" | jq -e . >/dev/null 2>&1; then
      eval "$(echo "$context_json" | jq -r 'to_entries | .[] | "export \(.key)=\(.value)"')"
    else
      echo "[WARN] Invalid context JSON, skipping: $context_json" >&2
    fi
  fi

  # Prepare stdin
  local hook_input
  if [[ -n "$stdin_json" ]]; then
    hook_input="$stdin_json"
  else
    # Generate default input based on hook type
    hook_input=$(cat <<EOF
{
  "hook_event_name": "${hook_name}",
  "cwd": "${CLAUDE_PROJECT_ROOT}",
  "session_id": "${CLAUDE_SESSION_ID}",
  "transcript_path": "${CLAUDE_PROJECT_ROOT}/.claude/data/transcript-${CLAUDE_SESSION_ID}.jsonl"
}
EOF
)
  fi

  # Execute hook and capture metrics
  local temp_output=$(mktemp)
  local temp_error=$(mktemp)

  local start_ns=$(python3 -c 'import time; print(int(time.time() * 1000000000))')

  set +e
  echo "$hook_input" | bash "$hook_script" >"$temp_output" 2>"$temp_error"
  local exit_code=$?
  set -e

  local end_ns=$(python3 -c 'import time; print(int(time.time() * 1000000000))')
  local duration_ms=$(( (end_ns - start_ns) / 1000000 ))

  # Read outputs
  local stdout_content=$(cat "$temp_output")
  local stderr_content=$(cat "$temp_error")

  # Clean up
  rm -f "$temp_output" "$temp_error"

  # Return results as JSON
  jq -n \
    --arg hook_name "$hook_name" \
    --arg hook_script "$hook_script" \
    --arg stdout "$stdout_content" \
    --arg stderr "$stderr_content" \
    --argjson exit_code "$exit_code" \
    --argjson duration_ms "$duration_ms" \
    --arg session_id "$CLAUDE_SESSION_ID" \
    '{
      hook_name: $hook_name,
      hook_script: $hook_script,
      session_id: $session_id,
      exit_code: $exit_code,
      duration_ms: $duration_ms,
      stdout: $stdout,
      stderr: $stderr,
      success: ($exit_code == 0)
    }'
}

# ============================================================================
# Batch Hook Simulation
# ============================================================================

simulate_hook_sequence() {
  local hooks_json="$1"  # Array of {hook_name, hook_script, context}

  local results=()
  while IFS= read -r hook_spec; do
    local hook_name=$(echo "$hook_spec" | jq -r '.hook_name')
    local hook_script=$(echo "$hook_spec" | jq -r '.hook_script')
    local context=$(echo "$hook_spec" | jq -c '.context // {}')

    local result=$(simulate_hook_trigger "$hook_name" "$hook_script" "$context")
    results+=("$result")
  done < <(echo "$hooks_json" | jq -c '.[]')

  # Combine results
  printf '%s\n' "${results[@]}" | jq -s '.'
}

# ============================================================================
# Claude Code Session Simulator (Simplified)
# ============================================================================

simulate_session() {
  local session_config="$1"  # {hooks: [...], context: {...}}

  local session_id="sim-$(uuidgen | tr -d '-')"
  export CLAUDE_SESSION_ID="$session_id"
  export SESSION_ID="$session_id"

  echo "🚀 Starting simulated session: $session_id" >&2

  # Extract hooks to trigger
  local hooks=$(echo "$session_config" | jq -c '.hooks')
  local global_context=$(echo "$session_config" | jq -c '.context // {}')

  # Simulate hook sequence
  local results=$(simulate_hook_sequence "$hooks")

  # Calculate session metrics
  local total_duration=$(echo "$results" | jq '[.[].duration_ms] | add')
  local failed_count=$(echo "$results" | jq '[.[] | select(.success == false)] | length')
  local success=$(echo "$results" | jq 'all(.success)')

  echo "✅ Session complete: $session_id" >&2
  echo "   Duration: ${total_duration}ms, Failed: $failed_count" >&2

  # Return session results
  jq -n \
    --arg session_id "$session_id" \
    --argjson total_duration "$total_duration" \
    --argjson failed_count "$failed_count" \
    --argjson success "$success" \
    --argjson hooks "$results" \
    '{
      session_id: $session_id,
      total_duration_ms: $total_duration,
      failed_hooks: $failed_count,
      success: $success,
      hooks: $hooks
    }'
}

# ============================================================================
# Performance Benchmarking
# ============================================================================

benchmark_hook() {
  local hook_script="$1"
  local iterations="${2:-10}"
  local context="${3:-{}}"

  echo "📊 Benchmarking: $hook_script ($iterations iterations)" >&2

  local durations=()
  for ((i=1; i<=iterations; i++)); do
    local result=$(simulate_hook_trigger "Benchmark" "$hook_script" "$context")
    local duration=$(echo "$result" | jq -r '.duration_ms')
    durations+=("$duration")
    echo "   Iteration $i: ${duration}ms" >&2
  done

  # Calculate statistics
  local json_array=$(printf '%s\n' "${durations[@]}" | jq -s '.')
  local min=$(echo "$json_array" | jq 'min')
  local max=$(echo "$json_array" | jq 'max')
  local avg=$(echo "$json_array" | jq 'add / length')
  local median=$(echo "$json_array" | jq 'sort | if length % 2 == 0 then (.[length/2-1] + .[length/2])/2 else .[length/2] end')

  echo "📈 Results:" >&2
  echo "   Min: ${min}ms, Max: ${max}ms, Avg: ${avg}ms, Median: ${median}ms" >&2

  jq -n \
    --arg hook_script "$hook_script" \
    --argjson iterations "$iterations" \
    --argjson min "$min" \
    --argjson max "$max" \
    --argjson avg "$avg" \
    --argjson median "$median" \
    --argjson durations "$json_array" \
    '{
      hook_script: $hook_script,
      iterations: $iterations,
      min_ms: $min,
      max_ms: $max,
      avg_ms: $avg,
      median_ms: $median,
      durations: $durations
    }'
}

# ============================================================================
# Main CLI
# ============================================================================

show_usage() {
  cat <<EOF
Hook Simulator - Integration testing harness for Claude Code hooks

USAGE:
  $(basename "$0") trigger <hook_name> <hook_script> [context_json]
  $(basename "$0") sequence <hooks_json_file>
  $(basename "$0") session <session_config_json>
  $(basename "$0") benchmark <hook_script> [iterations]

EXAMPLES:
  # Trigger single hook
  $(basename "$0") trigger Stop plugins/ace/scripts/ace_stop_wrapper.sh '{"ACE_ASYNC_LEARNING":"1"}'

  # Run hook sequence
  $(basename "$0") sequence tests/fixtures/hook-sequence.json

  # Simulate full session
  $(basename "$0") session tests/fixtures/session-config.json

  # Benchmark hook performance
  $(basename "$0") benchmark plugins/ace/scripts/ace_stop_wrapper.sh 100

EOF
}

main() {
  local command="${1:-}"

  case "$command" in
    trigger)
      shift
      simulate_hook_trigger "$@"
      ;;
    sequence)
      shift
      local hooks_file="$1"
      simulate_hook_sequence "$(cat "$hooks_file")"
      ;;
    session)
      shift
      local session_file="$1"
      simulate_session "$(cat "$session_file")"
      ;;
    benchmark)
      shift
      benchmark_hook "$@"
      ;;
    help|--help|-h)
      show_usage
      ;;
    *)
      echo "Error: Unknown command '$command'" >&2
      echo "" >&2
      show_usage
      exit 1
      ;;
  esac
}

# Run main if executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
