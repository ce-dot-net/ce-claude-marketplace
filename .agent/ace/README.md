# Native ACE Adapter

This adapter provides a bridge between Antigravity and the ACE CLI (`ce-ace`).

## Configuration
Configuration is stored in `.antigravity/ace.json`.
Legacy configuration in `.claude/settings.json` is supported as a fallback.

## Usage

### Basic Commands
- **Search**: `adapter.py search <query>`
- **Learn**: `adapter.py learn <task> <trajectory> <success>`
- **Status**: `adapter.py status`
- **Patterns**: `adapter.py patterns`
- **Doctor**: `adapter.py doctor`

### Advanced Commands
- **Tune**: `adapter.py tune [args]` - Adjust project configuration.
- **Clear**: `adapter.py clear` - Reset the project playbook (Delete all patterns).
- **Top**: `adapter.py top <limit>` - View top-rated patterns.
- **Delta**: `adapter.py delta` - Show changes since last sync.
- **Export**: `adapter.py export --file <path>` - Export patterns to a JSON file.
- **Import**: `adapter.py import --file <path>` - Import patterns from a JSON file.

## Workflows
Workflows are available in `.agent/workflows/` for all major commands.
