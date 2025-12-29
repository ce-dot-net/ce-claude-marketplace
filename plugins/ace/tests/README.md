# ACE Orchestration Plugin - Tests

This directory contains unit and integration tests for the ACE Orchestration plugin v5.0.0.

## Test Structure

```
tests/
├── test_ace_context.py    # Context resolution tests
├── test_ace_cli.py         # CLI wrapper tests (mocked)
└── README.md               # This file
```

## Running Tests

### Unit Tests (No ace-cli required)

```bash
# Run all tests
python tests/test_ace_context.py
python tests/test_ace_cli.py

# Or use pytest
pytest tests/
```

### Integration Tests (Requires ace-cli)

Integration tests require the `ace-cli` CLI to be installed and configured:

```bash
npm install -g @ace-sdk/cli
ace-cli config  # Setup connection
```

Then run integration tests:

```bash
# TODO: Create integration_test.sh
./tests/integration_test.sh
```

## Test Coverage

### test_ace_context.py

Tests context resolution from `.claude/settings.json`:
- ✅ Successful context resolution (orgId, projectId)
- ✅ Missing settings file
- ✅ Missing required fields
- ✅ Invalid JSON handling

### test_ace_cli.py

Tests CLI subprocess wrapper (mocked):
- ✅ Successful search call
- ✅ Search failure (non-zero exit)
- ✅ Search timeout
- ✅ Invalid JSON response
- ✅ Successful learn call
- ✅ Learn failure
- ✅ Successful status call

## Adding Tests

### For Shared Hooks

Create test file in `tests/`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

# Add shared-hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'shared-hooks' / 'utils'))

from your_module import your_function

def test_your_function():
    result = your_function()
    assert result == expected
    print("✅ test passed")

if __name__ == '__main__':
    test_your_function()
```

### For Integration Tests

Create shell script to test full workflow:
```bash
#!/usr/bin/env bash
# Test hooks with real ace-cli

echo '{"prompt":"implement auth"}' | \
  ../scripts/ace_before_task_wrapper.sh

# Verify output contains patterns
```

## CI/CD

TODO: Add GitHub Actions workflow:
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install pytest
      - run: pytest tests/
```

## Dependencies

**Unit tests:** None (pure Python stdlib)
**Integration tests:** `ace-cli` CLI, configured ACE server

## Troubleshooting

### ImportError: No module named 'ace_context'

Make sure you're running tests from the project root or the imports adjust `sys.path` correctly.

### subprocess.FileNotFoundError: ace-cli

Install ace-cli: `npm install -g @ace-sdk/cli`

### Tests pass but hooks don't work

Integration tests needed - unit tests use mocks and don't test real CLI calls.
