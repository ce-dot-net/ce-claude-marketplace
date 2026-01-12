# Hook Testing Infrastructure

Comprehensive testing framework for ACE plugin hooks using Bats (Bash Automated Testing System).

## 📁 Directory Structure

```
tests/
├── hooks/                      # Unit tests for individual hooks
│   └── ace_stop_wrapper.bats  # Stop hook async learning tests
├── integration/                # Integration tests
│   ├── hook_simulator.sh       # Hook execution simulator
│   └── ace_hooks_integration.bats
├── fixtures/                   # Test data and configurations
├── helpers/                    # Shared test utilities
│   ├── test_helper.bash        # Common test functions
│   └── install-bats.sh         # Bats installer script
├── package.json                # Test runner configuration
└── README.md                   # This file
```

## 🚀 Quick Start

### 1. Install Bats

```bash
cd tests
bun run install:bats
# or manually:
brew install bats-core bats-support bats-assert bats-file
```

### 2. Run Tests

```bash
# Run all tests
bun test

# Run specific test suite
bun test:unit        # Unit tests only
bun test:integration # Integration tests only

# Run single test file
bats tests/hooks/ace_stop_wrapper.bats

# Run with verbose output
bats -t tests/hooks/ace_stop_wrapper.bats
```

### 3. Watch Mode (Development)

```bash
bun test:watch
```

## 📊 Test Coverage

### Unit Tests: `tests/hooks/ace_stop_wrapper.bats`

**Async Mode (Issue #3 Regression Tests)**
- ✅ Returns in <2 seconds
- ✅ Creates background log files
- ✅ Returns immediate success message
- ✅ 10x faster than sync mode

**Sync Mode**
- ✅ Blocks until completion
- ✅ Returns actual task result

**Flag File Coordination (v5.4.7)**
- ✅ Exits silently when disabled flag exists
- ✅ Runs normally without flag

**CLI Detection**
- ✅ Exits silently when no CLI available
- ✅ Prefers `ace-cli` over `ce-ace`

**Config Validation**
- ✅ Exits gracefully without config
- ✅ Fails when logger missing
- ✅ Fails when hook script missing

**Working Directory Handling**
- ✅ Changes to directory from `cwd` field
- ✅ Falls back to inferring from `transcript_path`

**Argument Parsing**
- ✅ Accepts `--log`, `--no-log`, `--chat`, `--notify`

### Integration Tests: `tests/integration/ace_hooks_integration.bats`

**File Operations**
- ✅ Creates proper log files
- ✅ Propagates session ID correctly

**Hook Sequences**
- ✅ Simulates full hook lifecycle
- ✅ Runs multiple hooks concurrently

**Error Handling**
- ✅ Captures stderr properly
- ✅ Reports failure exit codes

## 🛠️ Hook Simulator

The hook simulator mimics Claude Code's hook execution environment for realistic integration testing.

### Usage

```bash
./tests/integration/hook_simulator.sh

# Trigger single hook
./tests/integration/hook_simulator.sh trigger \
  Stop \
  plugins/ace/scripts/ace_stop_wrapper.sh \
  '{"ACE_ASYNC_LEARNING":"1"}'

# Run hook sequence
./tests/integration/hook_simulator.sh sequence tests/fixtures/hook-sequence.json

# Benchmark performance
./tests/integration/hook_simulator.sh benchmark \
  plugins/ace/scripts/ace_stop_wrapper.sh \
  100
```

### Output Format

```json
{
  "hook_name": "Stop",
  "session_id": "sim-abc123",
  "exit_code": 0,
  "duration_ms": 245,
  "stdout": "{\"continue\": true}",
  "stderr": "",
  "success": true
}
```

## 🧪 Writing New Tests

### Unit Test Template

```bash
#!/usr/bin/env bats

load '../helpers/test_helper'

setup() {
  setup_test_env
  create_mock_ace_cli "success"
  create_mock_uv
  create_mock_python_hook "ace_after_task.py" "success"
}

teardown() {
  teardown_test_env
}

@test "my test description" {
  # Test code here
  run bash some_script.sh
  [ "$status" -eq 0 ]
  [[ "$output" =~ "expected output" ]]
}
```

### Integration Test Template

```bash
#!/usr/bin/env bats

load '../helpers/test_helper'

@test "integration test" {
  local result=$(bash "$SIMULATOR" trigger \
    "HookName" \
    "path/to/hook.sh" \
    '{"CONTEXT":"value"}')

  local exit_code=$(echo "$result" | jq -r '.exit_code')
  [[ $exit_code -eq 0 ]]
}
```

## 🎯 Testing Strategy

### Unit Tests (70% of test coverage)
- Test hook script logic in isolation
- Mock all external dependencies (ace-cli, Python scripts)
- Fast execution (<1s per test)
- Zero API costs

### Integration Tests (25% of test coverage)
- Test hook integration with file system
- Test hook sequences
- Test session ID propagation
- Still no LLM inference needed

### E2E Tests (5% of test coverage)
- Minimal full-stack validation
- Only for critical user journeys
- Expensive and slow - use sparingly

## 📈 Performance Benchmarks

Target metrics for ACE async learning hook (Issue #3):

| Metric | Target | Validated |
|--------|--------|-----------|
| Async return time | <2000ms | ✅ |
| Sync vs async speedup | >10x | ✅ |
| Background process spawns | 100% | ✅ |
| Log file creation | 100% | ✅ |

## 🔗 Resources

- [Bats Documentation](https://bats-core.readthedocs.io/)
- [Claude Code Hooks](https://github.com/anthropics/claude-code)

---

**Last Updated**: 2026-01-05
**Test Framework**: Bats 1.11+
**Coverage**: Unit (70%) + Integration (25%) + E2E (5%)
