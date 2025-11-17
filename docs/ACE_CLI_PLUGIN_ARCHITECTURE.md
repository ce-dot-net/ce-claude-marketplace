# ACE CLI-Based Plugin Architecture

**Date:** 2025-11-16
**Version:** 5.0.0-alpha (Proposed)
**Current Version:** 4.2.6 (MCP-based)

## Executive Summary

This document proposes a **CLI-based architecture** for the ACE Orchestration plugin as an alternative to the current **MCP-based architecture**. The CLI approach would use a standalone `ce-ace` binary/script instead of MCP tools.

### Key Differences

| Aspect | MCP Architecture (v4.2.6) | CLI Architecture (v5.0.0) |
|--------|---------------------------|---------------------------|
| **Integration** | MCP server + tools | Standalone CLI binary |
| **Communication** | JSON-RPC over stdio | Process execution + stdio |
| **Caching** | MCP client (3-tier) | CLI-managed (3-tier) |
| **Parallelism** | MCP server singleton | Process-per-invocation |
| **Hooks** | Python scripts call MCP tools | Bash scripts call CLI |
| **Slash Commands** | Call MCP tools directly | Wrap CLI commands |
| **Deployment** | Plugin + MCP server config | Plugin + CLI binary |
| **Dependencies** | Node.js MCP client | Bash + CLI binary |

---

## Full Plugin Architecture

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code CLI (Main Process)                              │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ ACE Orchestration Plugin                           │    │
│  │                                                      │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │    │
│  │  │ Hooks        │  │ Commands     │  │ Agents   │ │    │
│  │  │ (Bash)       │  │ (Bash)       │  │ (MD)     │ │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────┘ │    │
│  │         │                  │                         │    │
│  │         └──────────┬───────┘                         │    │
│  │                    │                                 │    │
│  │         ┌──────────▼───────────┐                    │    │
│  │         │ CLI Abstraction      │                    │    │
│  │         │ Layer (lib/ace.sh)   │                    │    │
│  │         └──────────┬───────────┘                    │    │
│  └────────────────────┼────────────────────────────────┘    │
└────────────────────────┼─────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ ce-ace CLI Binary    │
              │ (Standalone)         │
              │                      │
              │ • search             │
              │ • learn              │
              │ • get-playbook       │
              │ • status             │
              │ • bootstrap          │
              │ • config             │
              │ • clear              │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ Local Cache          │
              │ ~/.ace-cache/        │
              │ {org}_{project}.db   │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │ ACE Server           │
              │ (HTTP API)           │
              │                      │
              │ • Reflector (Sonnet) │
              │ • Curator (Haiku)    │
              │ • Merge Algorithm    │
              └──────────────────────┘
```

---

## Folder Structure

```
plugins/ace-orchestration/
├── .claude-plugin/
│   ├── plugin.json                    # Plugin manifest
│   └── plugin.template.json           # Template for marketplace
├── bin/
│   └── ce-ace                         # Standalone CLI binary (or symlink)
├── lib/
│   ├── ace.sh                         # Bash abstraction layer
│   ├── context.sh                     # Context resolution (orgId, projectId)
│   ├── error-handler.sh               # Error handling and retry logic
│   └── security.sh                    # Token management, redaction
├── hooks/
│   ├── hooks.json                     # Hook configuration
│   ├── before-task.sh                 # UserPromptSubmit → ace search
│   └── after-task.sh                  # PreCompact → ace learn
├── commands/
│   ├── ace-search.md                  # /ace-search wrapper
│   ├── ace-learn.md                   # /ace-learn wrapper
│   ├── ace-patterns.md                # /ace-patterns wrapper
│   ├── ace-status.md                  # /ace-status wrapper
│   ├── ace-bootstrap.md               # /ace-bootstrap wrapper
│   ├── ace-configure.md               # /ace-configure wizard
│   └── ace-clear.md                   # /ace-clear wrapper
├── agents/
│   ├── ace-retrieval.md               # Retrieval subagent (calls lib/ace.sh)
│   └── ace-learning.md                # Learning subagent (calls lib/ace.sh)
├── scripts/
│   └── ace-claude-init.sh             # Project CLAUDE.md updater
├── tests/
│   ├── test-search.sh                 # Integration tests
│   ├── test-learn.sh
│   └── test-parallel.sh               # Parallel execution tests
├── CLAUDE.md                          # Plugin documentation template
├── README.md                          # User documentation
├── CHANGELOG.md                       # Version history
└── marketplace.json                   # Marketplace metadata
```

---

## Hook Definitions

### hooks.json

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "implement|build|create|add|develop|write|update|modify|change|edit|fix|debug|troubleshoot|refactor|optimize|integrate|setup|configure|architect|design|test|deploy",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}\"/hooks/before-task.sh"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}\"/hooks/after-task.sh"
          }
        ]
      }
    ]
  }
}
```

**Note:** PostToolUse hooks removed due to Claude Code bug #4809, #11504.

---

### hooks/before-task.sh

```bash
#!/usr/bin/env bash
# Before-task hook: Search ACE playbook for relevant patterns

set -euo pipefail

# Source abstraction layer
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
source "${PLUGIN_ROOT}/lib/ace.sh"
source "${PLUGIN_ROOT}/lib/context.sh"
source "${PLUGIN_ROOT}/lib/error-handler.sh"

# Read user message from stdin
USER_MESSAGE=$(cat)

# Resolve context from .claude/settings.json
resolve_context || {
  echo "⚠️ Could not resolve project context - skipping ACE search"
  exit 0
}

# Search for relevant patterns
PATTERNS=$(ace_search "$USER_MESSAGE" --threshold 0.85 --limit 5) || {
  handle_search_error $?
  exit 0  # Fallback gracefully
}

# Inject patterns as hidden context (for Claude)
echo "<ace-patterns>"
echo "$PATTERNS"
echo "</ace-patterns>"

# Show summary to user (visible)
PATTERN_COUNT=$(echo "$PATTERNS" | jq '.patterns | length')
if [ "$PATTERN_COUNT" -gt 0 ]; then
  echo ""
  echo "🔍 [ACE] Found $PATTERN_COUNT relevant patterns:"
  echo "$PATTERNS" | jq -r '.patterns[] | "• \(.content | .[0:80])... (+\(.helpful) helpful)"'
  echo ""
fi

exit 0
```

---

### hooks/after-task.sh

```bash
#!/usr/bin/env bash
# After-task hook: Capture learning from completed work

set -euo pipefail

# Source abstraction layer
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
source "${PLUGIN_ROOT}/lib/ace.sh"
source "${PLUGIN_ROOT}/lib/context.sh"
source "${PLUGIN_ROOT}/lib/error-handler.sh"

# Resolve context
resolve_context || {
  echo "⚠️ Could not resolve project context - skipping ACE learning"
  exit 0
}

# Check if substantial work was done (heuristic)
# TODO: Implement transcript analysis to detect:
# - 3+ file edits
# - Problem-solving activity
# - API integration
# - Architecture decisions

# For now, just remind user
echo ""
echo "📚 [ACE] Reminder: If you completed substantial work, run:"
echo "   /ace-learn"
echo ""

exit 0
```

**Note:** Full automatic learning requires transcript analysis, which may not be feasible in hooks due to Claude Code limitations.

---

## Slash Command Definitions

### commands/ace-search.md

````markdown
---
description: Search ACE playbook for relevant patterns
format: /ace-search <query>
---

# Search ACE Playbook

Search for patterns relevant to your current task.

## Usage

```bash
/ace-search <query>
```

## Examples

```bash
/ace-search authentication patterns
/ace-search debugging async tests
/ace-search Stripe webhook integration
```

## Script

```bash
#!/usr/bin/env bash
set -euo pipefail

QUERY="$*"
source "${CLAUDE_PLUGIN_ROOT}/lib/ace.sh"
source "${CLAUDE_PLUGIN_ROOT}/lib/context.sh"

resolve_context || {
  echo "❌ Could not resolve project context"
  exit 1
}

PATTERNS=$(ace_search "$QUERY" --threshold 0.85 --limit 10 --format table) || {
  echo "❌ Search failed - check /ace-status"
  exit 1
}

echo "$PATTERNS"
```
````

---

### commands/ace-learn.md

````markdown
---
description: Capture learning from completed work
format: /ace-learn
---

# Capture Learning

Manually capture patterns and lessons learned from your recent work.

## Usage

```bash
/ace-learn
```

This opens an interactive session to capture:
- Task description
- Key steps taken (trajectory)
- Success/failure status
- Lessons learned
- Pattern IDs used

## Script

```bash
#!/usr/bin/env bash
set -euo pipefail

source "${CLAUDE_PLUGIN_ROOT}/lib/ace.sh"
source "${CLAUDE_PLUGIN_ROOT}/lib/context.sh"

resolve_context || {
  echo "❌ Could not resolve project context"
  exit 1
}

# Interactive prompts
echo "📚 [ACE Learning] Capturing patterns from your work"
echo ""

read -p "Task description (1-2 sentences): " TASK
read -p "Success? (y/n): " SUCCESS_INPUT
SUCCESS=$([ "$SUCCESS_INPUT" = "y" ] && echo "true" || echo "false")

echo "Key steps taken (one per line, Ctrl+D when done):"
TRAJECTORY=$(cat)

echo "Lessons learned (one per line, Ctrl+D when done):"
OUTPUT=$(cat)

echo "Pattern IDs used (space-separated, or empty):"
read PATTERN_IDS

# Call CLI
ace_learn \
  --task "$TASK" \
  --success "$SUCCESS" \
  --trajectory "$TRAJECTORY" \
  --output "$OUTPUT" \
  --patterns "$PATTERN_IDS" || {
  echo "❌ Learning capture failed"
  exit 1
}

echo "✅ Learning captured successfully"
```
````

---

### commands/ace-patterns.md

````markdown
---
description: View ACE playbook organized by section
format: /ace-patterns [section] [min-helpful]
---

# View ACE Playbook

View learned patterns organized by section.

## Usage

```bash
/ace-patterns [section] [min-helpful]
```

## Sections

- `strategies` - Architectural patterns, coding principles
- `snippets` - Reusable code patterns
- `troubleshooting` - Known issues, gotchas, solutions
- `apis` - Recommended libraries, frameworks

## Examples

```bash
/ace-patterns                     # View all sections
/ace-patterns strategies          # View only strategies
/ace-patterns troubleshooting 5   # Min helpful score = 5
```

## Script

```bash
#!/usr/bin/env bash
set -euo pipefail

SECTION="${1:-}"
MIN_HELPFUL="${2:-0}"

source "${CLAUDE_PLUGIN_ROOT}/lib/ace.sh"
source "${CLAUDE_PLUGIN_ROOT}/lib/context.sh"

resolve_context || {
  echo "❌ Could not resolve project context"
  exit 1
}

PLAYBOOK=$(ace_get_playbook --section "$SECTION" --min-helpful "$MIN_HELPFUL" --format table) || {
  echo "❌ Failed to retrieve playbook"
  exit 1
}

echo "$PLAYBOOK"
```
````

---

### commands/ace-status.md

````markdown
---
description: Show ACE playbook statistics and health check
format: /ace-status
---

# ACE Status

Show playbook statistics, server connection, and health check.

## Usage

```bash
/ace-status
```

## Script

```bash
#!/usr/bin/env bash
set -euo pipefail

source "${CLAUDE_PLUGIN_ROOT}/lib/ace.sh"
source "${CLAUDE_PLUGIN_ROOT}/lib/context.sh"

resolve_context || {
  echo "❌ Could not resolve project context"
  exit 1
}

STATUS=$(ace_status --format table) || {
  echo "❌ Failed to check status"
  exit 1
}

echo "$STATUS"
```
````

---

## Integration Calls for Each CLI Command

### lib/ace.sh (Abstraction Layer)

```bash
#!/usr/bin/env bash
# ACE CLI abstraction layer

set -euo pipefail

# Paths
ACE_BIN="${CLAUDE_PLUGIN_ROOT}/bin/ce-ace"
ACE_CONFIG="${HOME}/.ace/config.json"
ACE_CACHE_DIR="${HOME}/.ace-cache"
ACE_LOGS_DIR="${HOME}/.ace-logs"

# Ensure CLI exists
if [ ! -x "$ACE_BIN" ]; then
  echo "❌ ACE CLI not found at $ACE_BIN"
  exit 1
fi

# Security: Load config and export ENV vars
load_config() {
  if [ ! -f "$ACE_CONFIG" ]; then
    echo "⚠️ ACE not configured - run /ace-configure"
    return 1
  fi

  export ACE_SERVER_URL=$(jq -r '.serverUrl' "$ACE_CONFIG")
  export ACE_API_TOKEN=$(jq -r '.apiToken' "$ACE_CONFIG")
  export ACE_ORG_ID=$(jq -r '.orgId' "$ACE_CONFIG")
  export ACE_PROJECT_ID=$(jq -r '.projectId' "$ACE_CONFIG")
}

# ace_search <query> [--threshold N] [--limit N] [--format json|table]
ace_search() {
  load_config || return 1

  local query="$1"
  shift

  "$ACE_BIN" search \
    --org "$ACE_ORG_ID" \
    --project "$ACE_PROJECT_ID" \
    --query "$query" \
    "$@" 2>&1 || return $?
}

# ace_learn --task <task> --success <bool> --trajectory <text> --output <text> [--patterns <ids>]
ace_learn() {
  load_config || return 1

  "$ACE_BIN" learn \
    --org "$ACE_ORG_ID" \
    --project "$ACE_PROJECT_ID" \
    "$@" 2>&1 || return $?
}

# ace_get_playbook [--section <section>] [--min-helpful N] [--format json|table]
ace_get_playbook() {
  load_config || return 1

  "$ACE_BIN" get-playbook \
    --org "$ACE_ORG_ID" \
    --project "$ACE_PROJECT_ID" \
    "$@" 2>&1 || return $?
}

# ace_status [--format json|table]
ace_status() {
  load_config || return 1

  "$ACE_BIN" status \
    --org "$ACE_ORG_ID" \
    --project "$ACE_PROJECT_ID" \
    "$@" 2>&1 || return $?
}

# ace_bootstrap [--mode hybrid|git-history|local-files|docs-only] [--thoroughness light|medium|deep]
ace_bootstrap() {
  load_config || return 1

  "$ACE_BIN" bootstrap \
    --org "$ACE_ORG_ID" \
    --project "$ACE_PROJECT_ID" \
    "$@" 2>&1 || return $?
}

# ace_config [--server-url URL] [--api-token TOKEN] [--org-id ID] [--project-id ID]
ace_config() {
  "$ACE_BIN" config "$@" 2>&1 || return $?
}

# ace_clear --confirm
ace_clear() {
  load_config || return 1

  "$ACE_BIN" clear \
    --org "$ACE_ORG_ID" \
    --project "$ACE_PROJECT_ID" \
    "$@" 2>&1 || return $?
}
```

---

### lib/context.sh (Context Resolution)

```bash
#!/usr/bin/env bash
# Context resolution: Extract orgId, projectId from .claude/settings.json

resolve_context() {
  local SETTINGS_FILE=".claude/settings.json"

  if [ ! -f "$SETTINGS_FILE" ]; then
    echo "⚠️ No .claude/settings.json found - not in Claude project?"
    return 1
  fi

  # Override from .claude/settings.json if available
  local ORG_ID=$(jq -r '.orgId // empty' "$SETTINGS_FILE")
  local PROJECT_ID=$(jq -r '.projectId // empty' "$SETTINGS_FILE")

  if [ -n "$ORG_ID" ]; then
    export ACE_ORG_ID="$ORG_ID"
  fi

  if [ -n "$PROJECT_ID" ]; then
    export ACE_PROJECT_ID="$PROJECT_ID"
  fi

  return 0
}
```

---

### lib/error-handler.sh (Error Handling)

```bash
#!/usr/bin/env bash
# Error handling and retry logic

handle_search_error() {
  local exit_code=$1

  case $exit_code in
    0)
      # Success
      return 0
      ;;
    401)
      # Authentication failed
      echo "❌ ACE authentication failed - run /ace-configure to update token"
      return 1
      ;;
    404)
      # Playbook empty
      echo "⚠️ ACE playbook empty - run /ace-bootstrap to initialize"
      return 0
      ;;
    *)
      # Other error - retry once
      echo "⚠️ ACE search failed (exit code $exit_code) - retrying..."
      sleep 1
      return 2  # Signal retry needed
      ;;
  esac
}

handle_learn_error() {
  local exit_code=$1

  case $exit_code in
    0)
      return 0
      ;;
    401)
      echo "❌ ACE authentication failed - run /ace-configure"
      return 1
      ;;
    *)
      echo "⚠️ ACE learning failed (exit code $exit_code)"
      return 0  # Don't block user
      ;;
  esac
}
```

---

## Fallback Logic

### Search Fallback

```bash
# In hooks/before-task.sh
PATTERNS=$(ace_search "$USER_MESSAGE" --threshold 0.85 --limit 5) || {
  exit_code=$?

  if [ $exit_code -eq 2 ]; then
    # Retry signal
    sleep 1
    PATTERNS=$(ace_search "$USER_MESSAGE" --threshold 0.85 --limit 5) || {
      echo "⚠️ ACE search failed after retry - continuing without patterns"
      exit 0
    }
  else
    handle_search_error $exit_code
    exit 0
  fi
}
```

### Learn Fallback

```bash
# In hooks/after-task.sh
ace_learn --task "$TASK" --success "$SUCCESS" --trajectory "$TRAJECTORY" --output "$OUTPUT" || {
  exit_code=$?
  handle_learn_error $exit_code
  exit 0  # Don't block compaction
}
```

### Config Fallback

```bash
# In lib/ace.sh load_config()
load_config() {
  if [ ! -f "$ACE_CONFIG" ]; then
    echo "⚠️ ACE not configured - run /ace-configure"
    echo "Using default server URL: https://ace.yourdomain.com"
    export ACE_SERVER_URL="https://ace.yourdomain.com"
    export ACE_API_TOKEN=""
    export ACE_ORG_ID="${ACE_ORG_ID:-unknown}"
    export ACE_PROJECT_ID="${ACE_PROJECT_ID:-unknown}"
    return 1
  fi

  # Load from config
  export ACE_SERVER_URL=$(jq -r '.serverUrl // "https://ace.yourdomain.com"' "$ACE_CONFIG")
  export ACE_API_TOKEN=$(jq -r '.apiToken // ""' "$ACE_CONFIG")
  export ACE_ORG_ID=$(jq -r '.orgId // "unknown"' "$ACE_CONFIG")
  export ACE_PROJECT_ID=$(jq -r '.projectId // "unknown"' "$ACE_CONFIG")
}
```

---

## Migration Path from Legacy MCP Plugin

### Step 1: Detect Legacy Plugin

```bash
# In scripts/ace-claude-init.sh or during plugin enable

LEGACY_MCP_CONFIG="${HOME}/.claude/mcp/config.json"
LEGACY_PLUGIN_DIR="${HOME}/.claude/plugins/ace-orchestration-mcp"

if [ -f "$LEGACY_MCP_CONFIG" ]; then
  if grep -q "ace-pattern-learning" "$LEGACY_MCP_CONFIG" 2>/dev/null; then
    echo "⚠️ Legacy ACE MCP plugin detected"
    echo ""
    echo "Migration required:"
    echo "1. Disable old plugin: /plugin disable ace-orchestration-mcp"
    echo "2. Remove MCP config: rm ~/.claude/mcp/config.json (or edit to remove ace-pattern-learning)"
    echo "3. Enable new plugin: /plugin enable ace-orchestration"
    echo ""
    read -p "Proceed with automatic migration? (y/n) " MIGRATE

    if [ "$MIGRATE" = "y" ]; then
      migrate_from_mcp
    else
      echo "❌ Migration cancelled - please migrate manually"
      exit 1
    fi
  fi
fi
```

---

### Step 2: Migrate Configuration

```bash
migrate_from_mcp() {
  echo "🔄 Migrating from MCP-based plugin to CLI-based plugin..."

  # Check if MCP config has ACE server settings
  if [ -f "$LEGACY_MCP_CONFIG" ]; then
    SERVER_URL=$(jq -r '.mcpServers["ace-pattern-learning"].env.ACE_SERVER_URL // empty' "$LEGACY_MCP_CONFIG")
    API_TOKEN=$(jq -r '.mcpServers["ace-pattern-learning"].env.ACE_API_TOKEN // empty' "$LEGACY_MCP_CONFIG")
    ORG_ID=$(jq -r '.mcpServers["ace-pattern-learning"].env.ACE_ORG_ID // empty' "$LEGACY_MCP_CONFIG")
    PROJECT_ID=$(jq -r '.mcpServers["ace-pattern-learning"].env.ACE_PROJECT_ID // empty' "$LEGACY_MCP_CONFIG")

    # Write to new config
    mkdir -p "${HOME}/.ace"
    cat > "${HOME}/.ace/config.json" <<EOF
{
  "serverUrl": "${SERVER_URL:-https://ace.yourdomain.com}",
  "apiToken": "${API_TOKEN}",
  "orgId": "${ORG_ID}",
  "projectId": "${PROJECT_ID}"
}
EOF
    chmod 0600 "${HOME}/.ace/config.json"

    echo "✅ Migrated configuration to ~/.ace/config.json"
  fi

  # Copy playbook cache if exists
  LEGACY_CACHE="${HOME}/.ace-cache-mcp"
  NEW_CACHE="${HOME}/.ace-cache"

  if [ -d "$LEGACY_CACHE" ]; then
    echo "🔄 Migrating playbook cache..."
    cp -r "$LEGACY_CACHE"/* "$NEW_CACHE"/ 2>/dev/null || true
    echo "✅ Cache migrated"
  fi

  # Remove MCP server entry
  if [ -f "$LEGACY_MCP_CONFIG" ]; then
    echo "🔄 Removing MCP server entry..."
    jq 'del(.mcpServers["ace-pattern-learning"])' "$LEGACY_MCP_CONFIG" > "${LEGACY_MCP_CONFIG}.tmp"
    mv "${LEGACY_MCP_CONFIG}.tmp" "$LEGACY_MCP_CONFIG"
    echo "✅ MCP config cleaned"
  fi

  echo ""
  echo "✅ Migration complete!"
  echo ""
  echo "Next steps:"
  echo "1. Test CLI: ce-ace status"
  echo "2. Bootstrap if needed: /ace-bootstrap"
  echo "3. Start using: /ace-search <query>"
}
```

---

### Step 3: Backward Compatibility Warnings

Add to `CLAUDE.md`:

```markdown
## Migration from v4.x (MCP-based)

**If upgrading from v4.2.6 or earlier:**

The v5.0.0 release changes from MCP-based architecture to CLI-based architecture.

### Breaking Changes
- MCP server `ace-pattern-learning` is NO LONGER USED
- Configuration moved from `~/.claude/mcp/config.json` to `~/.ace/config.json`
- Tools changed from `mcp__ace-pattern-learning__*` to `ce-ace <command>`

### Automatic Migration
Run `/ace-configure` and the plugin will detect legacy config and migrate automatically.

### Manual Migration
If automatic migration fails:
1. Copy settings from `~/.claude/mcp/config.json` → `~/.ace/config.json`
2. Remove `ace-pattern-learning` entry from MCP config
3. Restart Claude Code CLI
```

---

## Ready to Implement Summary

### ✅ Architecture Complete

**Component** | **Status** | **Details**
---|---|---
**CLI Binary** | ⏳ Need to build | Standalone `ce-ace` binary
**Abstraction Layer** | ✅ Designed | `lib/ace.sh`, `lib/context.sh`, `lib/error-handler.sh`
**Hooks** | ✅ Designed | `before-task.sh` (UserPromptSubmit), `after-task.sh` (PreCompact)
**Slash Commands** | ✅ Designed | 7 commands wrapping CLI
**Agents** | ✅ Existing | Reuse `ace-retrieval.md`, `ace-learning.md` (update to call lib/ace.sh)
**Error Handling** | ✅ Designed | Retry logic, fallbacks, graceful degradation
**Security** | ✅ Designed | Token management, redaction, permissions
**Parallelism** | ✅ Designed | Process isolation, project-scoped resources
**Migration** | ✅ Designed | Auto-detect legacy, migrate config/cache
**Tests** | ⏳ Need to write | Integration tests, parallel execution tests

---

### 🚧 Implementation Steps

#### Phase 1: CLI Binary (External)
1. Build standalone `ce-ace` CLI binary (separate repo/project)
   - Implements: search, learn, get-playbook, status, bootstrap, config, clear
   - Uses: 3-tier caching (RAM → SQLite → HTTP)
   - Outputs: JSON or table format
2. Test CLI independently (no plugin required)

#### Phase 2: Plugin Abstraction Layer
1. Create `lib/ace.sh` with wrapper functions
2. Create `lib/context.sh` for .claude/settings.json parsing
3. Create `lib/error-handler.sh` for retry/fallback logic
4. Create `lib/security.sh` for token management
5. Unit test each library function

#### Phase 3: Hooks
1. Rewrite `hooks/before-task.sh` to call `lib/ace.sh`
2. Rewrite `hooks/after-task.sh` to call `lib/ace.sh`
3. Update `hooks.json` (remove PostToolUse if still present)
4. Test hooks in isolation (mock CLI responses)

#### Phase 4: Slash Commands
1. Convert each command from MCP tool calls to CLI wrappers
2. Update command documentation
3. Test each command independently

#### Phase 5: Agents
1. Update `ace-retrieval.md` to call `lib/ace.sh` instead of MCP tools
2. Update `ace-learning.md` to call `lib/ace.sh` instead of MCP tools
3. Test subagents with mocked CLI

#### Phase 6: Migration
1. Add detection logic for legacy MCP plugin
2. Implement config migration
3. Implement cache migration
4. Test migration path with v4.2.6 → v5.0.0

#### Phase 7: Integration Testing
1. Test full workflow: search → implement → learn
2. Test parallel execution (multiple projects)
3. Test error scenarios (invalid token, network failure, empty playbook)
4. Test migration from v4.2.6

#### Phase 8: Release
1. Update CHANGELOG.md with breaking changes
2. Update README.md with new architecture
3. Update marketplace.json
4. Tag v5.0.0-alpha
5. Release to marketplace

---

### 📊 Comparison: MCP vs CLI Architecture

**Criteria** | **MCP Architecture (v4.2.6)** | **CLI Architecture (v5.0.0)** | **Winner**
---|---|---|---
**Simplicity** | Requires MCP server config | Single binary, no server config | CLI
**Parallelism** | MCP server singleton, potential conflicts | Process-per-invocation, fully isolated | CLI
**Debugging** | MCP server logs + client logs | Single CLI logs | CLI
**Deployment** | Plugin + MCP server entry | Plugin + CLI binary | CLI
**Dependencies** | Node.js MCP runtime | Bash + CLI binary | CLI
**Caching** | MCP client (3-tier) | CLI-managed (3-tier) | Tie
**Error Handling** | MCP error codes + retry | CLI exit codes + retry | Tie
**Security** | ENV vars in MCP config | ENV vars in CLI wrapper | Tie
**Extensibility** | Add MCP tools | Add CLI commands | Tie
**Ecosystem** | MCP standard (Claude, Cursor, Cline) | Custom CLI (portable) | MCP
**Maintenance** | MCP client + server | Single CLI | CLI

**Recommendation:** CLI architecture is **simpler, more portable, easier to debug, and better for parallel execution**. However, MCP architecture has **ecosystem benefits** (standard protocol, works with all MCP clients).

**Trade-off:** If ACE is meant to work with multiple Claude clients (Claude Code, Cursor, Cline), **keep MCP**. If ACE is Claude Code-specific, **switch to CLI**.

---

### 🎯 Recommendation

**For v5.0.0:**

**Option A: Full CLI Migration** (Best for Claude Code-only)
- Build `ce-ace` CLI binary
- Migrate entire plugin to CLI architecture
- Deprecate MCP server
- **Pros:** Simpler, faster, easier to debug
- **Cons:** Breaks compatibility with other MCP clients

**Option B: Hybrid Approach** (Best for multi-client support)
- Keep MCP architecture for compatibility
- Add optional CLI mode for advanced users
- Plugin detects available backend (MCP or CLI) and uses appropriate one
- **Pros:** Maximum compatibility
- **Cons:** Maintains complexity

**Option C: Status Quo** (v4.2.6 is stable)
- Keep MCP architecture
- Focus on bug fixes and incremental improvements
- **Pros:** No migration risk, proven architecture
- **Cons:** Misses CLI simplicity benefits

---

**My Recommendation:** **Option C (Status Quo) for now**, with **Option A (CLI Migration) for v5.0.0** if/when a standalone CLI becomes available.

**Rationale:**
- v4.2.6 is stable and working
- No urgent need to migrate
- CLI would be simpler, but requires building standalone binary first
- MCP provides ecosystem compatibility

**Next Steps:**
1. Keep v4.2.6 as stable release
2. Build standalone `ce-ace` CLI (separate project)
3. Once CLI is proven, migrate to v5.0.0 with CLI architecture
4. Provide migration guide and tooling

---

**End of Architecture Document**
