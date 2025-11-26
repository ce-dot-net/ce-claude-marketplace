# ACE Integration Walkthrough

This document verifies the installation and functionality of the Native ACE Pack enhancements.

## 1. Installation Verification
- [x] **Adapter Script**: `.agent/ace/adapter.py` exists and is executable.
- [x] **Configuration**: `.antigravity/ace.json` is configured.
- [x] **Workflows**: All workflows are present in `.agent/workflows/`.

## 2. Command Verification
### Basic Commands
- `search`: Verified via `adapter.py search "test"`
- `learn`: Verified via `adapter.py learn ...`
- `status`: Verified via `adapter.py status`

### Advanced Commands
- `tune`: Verified. (Usage: `adapter.py tune show`)
- `clear`: Verified. (Usage: `adapter.py clear`)
- `top`: Verified. (Usage: `adapter.py top <limit>`)
- `delta`: Verified. (Usage: `adapter.py delta [add|update|remove] ...`)
- `export`: Verified. (Usage: `adapter.py export --output <path>`)
- `import`: Verified. (Usage: `adapter.py import --file <path>`)

## 3. Health Check
Run `.agent/ace/adapter.py doctor` to verify overall system health.
- Result: **HEALTHY**
