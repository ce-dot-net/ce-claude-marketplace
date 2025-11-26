# ACE Plugin Architecture Analysis: Is It Over-Engineered?

**Date**: 2025-11-18  
**Version**: v5.1.1  
**Status**: Architecture Review

---

## Executive Summary

The ACE plugin architecture uses a **3-layer chain** (Bash wrapper → Python hook → CLI subprocess). This analysis examines whether this is over-engineered or appropriately designed.

**TL;DR**: The architecture is **NOT over-engineered**. Each layer has a distinct purpose and provides real value. The design follows the recommended boilerplate pattern and is actually quite elegant.

---

## Architecture Overview

### Current Chain

```
Claude Code hooks.json
    ↓
Bash Wrapper (ace_before_task_wrapper.sh)
    ↓
Python Hook (ace_before_task.py)
    ↓
Subprocess (ce-ace search --stdin)
    ↓
ACE Server
```

### Files Involved

**Hook Configuration:**
- `/plugins/ace/hooks/hooks.json` - Declares hook events and wrapper scripts

**Bash Wrappers (3 files):**
- `/plugins/ace/scripts/ace_before_task_wrapper.sh` (UserPromptSubmit)
- `/plugins/ace/scripts/ace_after_task_wrapper.sh` (PreCompact, Stop)
- `/plugins/ace/scripts/ace_task_complete_wrapper.sh` (PostToolUse)

**Python Hooks (3 files):**
- `/shared-hooks/ace_before_task.py` - Pattern retrieval
- `/shared-hooks/ace_after_task.py` - Learning capture (backup)
- `/shared-hooks/ace_task_complete.py` - Learning capture (per-task)

**Python Utilities:**
- `/shared-hooks/utils/ace_context.py` - Reads `.claude/settings.json`
- `/shared-hooks/utils/ace_cli.py` - Subprocess wrappers for ce-ace CLI

**Slash Commands (13 files):**
- `/plugins/ace/commands/*.md` - All call ce-ace CLI directly

---

## Layer-by-Layer Analysis

### Layer 1: Bash Wrappers (Plugin-Specific)

**Location**: `/plugins/ace/scripts/ace_*_wrapper.sh`

**What they do:**
```bash
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/ace_before_task.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_before_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

exec uv run "${HOOK_SCRIPT}" "$@"
```

**Value provided:**
- ✅ **Plugin isolation**: Each plugin has its own wrappers in its own directory
- ✅ **Path resolution**: Finds shared hooks relative to marketplace root
- ✅ **Error handling**: Fails gracefully if Python script missing
- ✅ **Environment setup**: Ensures `uv run` is used (Python dependency management)
- ✅ **Non-blocking exit**: Uses `exec` to replace shell process (no extra process)

**Is this necessary?** YES.
- Claude Code hooks.json expects executable scripts in plugin directory
- Needs path resolution to find shared hooks
- Error checking prevents silent failures

**Does it duplicate logic?** NO.
- Only does path resolution and delegation
- No org/project context logic (that's in Python)
- No CLI calls (that's in Python)

---

### Layer 2: Python Hooks (Shared Implementation)

**Location**: `/shared-hooks/ace_*.py`

**What they do:**
1. Read hook event JSON from stdin
2. Parse user prompt or event metadata
3. Call `get_context()` to read `.claude/settings.json`
4. Call `run_search()` or `run_learn()` to execute ce-ace CLI
5. Parse CLI JSON response
6. Print formatted output (emoji-marked, visible to user)

**Value provided:**
- ✅ **Event parsing**: JSON deserialization from Claude Code
- ✅ **Context resolution**: Reads org/project from `.claude/settings.json`
- ✅ **CLI orchestration**: Builds subprocess commands
- ✅ **Output formatting**: Emoji-marked, user-friendly messages
- ✅ **Error handling**: Graceful failures, never blocks workflow
- ✅ **Code reuse**: Shared across multiple hooks

**Is this necessary?** YES.
- Hooks need to parse JSON events from Claude Code
- Python is better than Bash for JSON parsing
- Shared code across 3 hooks (before/after/complete)
- Complex output formatting (domains, bullet points, etc.)

**Does it duplicate logic?** NO.
- CLI calls are delegated to `ace_cli.py` utilities
- Context logic is delegated to `ace_context.py`
- Each hook has distinct trigger logic (substantial task detection, etc.)

---

### Layer 3: ce-ace CLI (Subprocess)

**Location**: External Node.js CLI (`@ce-dot-net/ce-ace-cli`)

**What it does:**
1. Reads global config from `~/.config/ace/config.json`
2. Resolves org/project from environment or config
3. Calls ACE Server API (HTTP)
4. Returns JSON response

**Value provided:**
- ✅ **Configuration management**: Single source of truth for API tokens
- ✅ **Server communication**: HTTP client, retry logic, error handling
- ✅ **Caching**: 3-tier cache (RAM → SQLite → Server)
- ✅ **Reusability**: Used by both hooks AND slash commands
- ✅ **Standalone tool**: Can be used outside Claude Code

**Is this necessary?** YES.
- Separates concerns: hooks don't need to know HTTP details
- Standalone CLI is useful for testing/debugging
- Shared by both hooks and commands

**Does it duplicate logic?** NO.
- Only place that calls ACE Server
- Only place with API token management
- Only place with caching logic

---

## Context Management: Where Does It Happen?

This is a critical question. Let's trace org/project ID flow:

### Pattern 1: Hooks (Automatic Triggers)

```
hooks.json (UserPromptSubmit)
    ↓
ace_before_task_wrapper.sh
    - No context logic (just delegation)
    ↓
ace_before_task.py
    - Calls: get_context() → Reads .claude/settings.json
    - Extracts: org_id, project_id
    - Sets: Environment variables (ACE_ORG_ID, ACE_PROJECT_ID)
    ↓
ce-ace search --stdin
    - Reads: Environment variables OR global config
    - Uses: Org/project for API call
```

### Pattern 2: Slash Commands (Manual Invocations)

```
/ace-search <query>
    ↓
ace-search.md (command definition)
    - Bash script reads .claude/settings.json directly
    - Extracts: org_id, project_id
    - Calls: ce-ace --org "$ORG_ID" --project "$PROJECT_ID" search "$QUERY"
    ↓
ce-ace CLI
    - Uses: --org/--project flags (explicit)
```

### Who Sets Context?

| Layer | Hooks | Slash Commands |
|-------|-------|----------------|
| **Bash wrapper** | No (just delegation) | **YES (reads settings.json)** |
| **Python hook** | **YES (sets env vars)** | N/A |
| **ce-ace CLI** | Reads env vars | Reads flags |

**Is this duplication?** NO.
- Hooks set environment variables (Python is better for JSON parsing)
- Commands set CLI flags (Bash is simpler for one-liners)
- Both read from `.claude/settings.json` but in different ways

**Could this be unified?** Possibly, but not worth it.
- Hooks need Python for event parsing anyway
- Commands are simpler as Bash one-liners
- Both patterns are idiomatic for their use case

---

## Comparison to Boilerplate Pattern

### cc-boilerplate-v2 Hook Pattern

From `HOOK_VISIBILITY_RESEARCH.md`:

```bash
# /plugins/core/scripts/session_start_wrapper.sh
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/session_start.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] session_start.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

exec uv run "${HOOK_SCRIPT}" "$@"
```

### ACE Hook Pattern

```bash
# /plugins/ace/scripts/ace_before_task_wrapper.sh
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOOK_SCRIPT="${MARKETPLACE_ROOT}/shared-hooks/ace_before_task.py"

[[ -f "${HOOK_SCRIPT}" ]] || {
  echo "[ERROR] ace_before_task.py not found: ${HOOK_SCRIPT}" >&2
  exit 1
}

exec uv run "${HOOK_SCRIPT}" "$@"
```

### Analysis

**Are they identical?** YES.
- ACE follows the EXACT same pattern as boilerplate
- Only differences: script names, error messages

**Is ACE consistent with best practices?** YES.
- Uses recommended wrapper → Python pattern
- Proper error handling
- Clean delegation with `exec`

---

## Is Environment Variable Setting in Python Correct?

### Current Implementation

```python
# /shared-hooks/utils/ace_cli.py
def run_search(query: str) -> Optional[Dict[str, Any]]:
    """
    Call ce-ace search --stdin
    
    Note:
        CLI handles configuration automatically:
        - Reads org/project from ~/.config/ace/config.json
        - Fetches server config (search_top_k, constitution_threshold)
        - Uses server settings as defaults
        
        No need to pass --org, --project, --top-k, or --threshold!
    """
    try:
        result = subprocess.run(
            ['ce-ace', 'search', '--stdin', '--json'],
            input=query.encode('utf-8'),
            capture_output=True,
            timeout=10
        )
```

Wait, this is interesting. The Python utility does NOT set environment variables. Let me check the actual hooks:

```python
# /shared-hooks/ace_before_task.py
context = get_context()  # Returns {'org': ..., 'project': ...}
if not context:
    print("⚠️ [ACE] No project context found - skipping search")
    sys.exit(0)

# Call ce-ace search --stdin
# CLI handles org/project/top_k/threshold from its own config
patterns_response = run_search(query=user_prompt)
```

### Revelation: Context is NOT Passed to CLI!

The Python hooks:
1. Call `get_context()` to check if `.claude/settings.json` exists
2. If no context, skip the hook (early exit)
3. If context exists, proceed
4. **But don't pass context to CLI!**

The CLI:
1. Reads org/project from `~/.config/ace/config.json` (global config)
2. Falls back to environment variables if multi-org mode

### Is This a Bug?

Looking at `/ace-configure` command:

```bash
# Global config: ~/.config/ace/config.json
ce-ace config \
  --server-url "$SERVER_URL" \
  --api-token "$API_TOKEN" \
  --project-id "$PROJECT_ID" \
  --json

# Project config: .claude/settings.json
cat > "$PROJECT_CONFIG" <<EOF
{
  "env": {
    "ACE_ORG_ID": "$ORG_ID",
    "ACE_PROJECT_ID": "$PROJECT_ID"
  }
}
EOF
```

So `.claude/settings.json` sets environment variables, but **the hooks don't use them!**

### Analysis: Is This Intentional?

Looking at `ace_context.py`:

```python
def get_context() -> Optional[Dict[str, str]]:
    """
    Read orgId and projectId from .claude/settings.json
    
    Supports two formats:
    1. Direct: {"orgId": "...", "projectId": "..."}
    2. Env wrapper: {"env": {"ACE_ORG_ID": "...", "ACE_PROJECT_ID": "..."}}
    
    Returns:
        Dict with 'org' and 'project' keys, or None if not found
    """
```

**This function reads the values but doesn't SET environment variables!**

### The Problem

Current flow:
1. Python hook reads `.claude/settings.json` → gets org/project
2. Python hook **discards** org/project (doesn't set env vars)
3. Python hook calls `ce-ace search --stdin` (no org/project flags)
4. CLI reads from global config `~/.config/ace/config.json`
5. **Project-specific config is ignored!**

### The Fix

The hooks should either:

**Option A: Set environment variables before subprocess**
```python
# In ace_cli.py
def run_search(query: str, org: str = None, project: str = None):
    env = os.environ.copy()
    if org:
        env['ACE_ORG_ID'] = org
    if project:
        env['ACE_PROJECT_ID'] = project
    
    result = subprocess.run(
        ['ce-ace', 'search', '--stdin', '--json'],
        input=query.encode('utf-8'),
        capture_output=True,
        timeout=10,
        env=env  # ← Pass modified environment
    )
```

**Option B: Pass flags explicitly**
```python
# In ace_cli.py
def run_search(query: str, org: str = None, project: str = None):
    cmd = ['ce-ace']
    if org:
        cmd.extend(['--org', org])
    if project:
        cmd.extend(['--project', project])
    cmd.extend(['search', '--stdin', '--json'])
    
    result = subprocess.run(
        cmd,
        input=query.encode('utf-8'),
        capture_output=True,
        timeout=10
    )
```

**Which is better?** Option A (environment variables).
- Matches the pattern used by slash commands
- CLI already supports reading from environment
- Simpler subprocess call

---

## Does the Wrapper Architecture Add Value?

### Value Proposition

**Bash wrapper layer:**
- ✅ Plugin isolation (each plugin owns its wrappers)
- ✅ Path resolution (finds shared hooks)
- ✅ Error handling (graceful failures)
- ✅ Python environment setup (uv run)

**Python hook layer:**
- ✅ JSON event parsing (from Claude Code)
- ✅ Context resolution (from `.claude/settings.json`)
- ✅ CLI orchestration (subprocess management)
- ✅ Output formatting (emoji, domains, bullets)
- ✅ Code reuse (3 hooks share utilities)

**CLI subprocess layer:**
- ✅ Configuration management (global config)
- ✅ Server communication (HTTP, caching)
- ✅ Reusability (hooks + commands)
- ✅ Standalone tool (testing/debugging)

### Could Layers Be Combined?

**Option: Bash wrapper calls CLI directly (skip Python)**

```bash
#!/usr/bin/env bash
# Read .claude/settings.json
ORG_ID=$(jq -r '.env.ACE_ORG_ID' .claude/settings.json)
PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID' .claude/settings.json)

# Read hook event from stdin
PROMPT=$(jq -r '.prompt' /dev/stdin)

# Call CLI
ce-ace --org "$ORG_ID" --project "$PROJECT_ID" search "$PROMPT" --json
```

**Problems:**
- ❌ Bash is bad at JSON parsing (requires jq)
- ❌ No error handling for malformed JSON
- ❌ No output formatting (domains, bullets, emoji)
- ❌ No code reuse across hooks
- ❌ No trigger logic (substantial task detection)
- ❌ Duplicates logic across 3 wrapper scripts

**Option: Python hook calls server directly (skip CLI)**

```python
import httpx

def search_patterns(query: str, org: str, project: str):
    response = httpx.post(
        "https://ace-api.code-engine.app/search",
        json={"query": query, "org": org, "project": project},
        headers={"Authorization": f"Bearer {api_token}"}
    )
    return response.json()
```

**Problems:**
- ❌ Duplicates HTTP client logic (CLI already has this)
- ❌ No caching (CLI has 3-tier cache)
- ❌ No retry logic
- ❌ Slash commands still need CLI (code duplication)
- ❌ No standalone tool for testing

**Conclusion:** Current 3-layer architecture is optimal.

---

## Where Should Org/Project Be Set?

### Current Situation

**Hooks:**
- Bash wrapper: No context logic ✅ (just delegation)
- Python hook: Reads context but doesn't pass it ❌ (BUG)
- CLI: Reads global config (wrong source) ❌

**Slash Commands:**
- Bash script: Reads `.claude/settings.json` and passes flags ✅
- CLI: Uses flags ✅

### Recommended Fix

**Hooks should match slash commands pattern:**

```python
# /shared-hooks/ace_before_task.py
context = get_context()
if not context:
    sys.exit(0)

# Pass context to CLI via environment variables
patterns_response = run_search(
    query=user_prompt,
    org=context['org'],
    project=context['project']
)
```

```python
# /shared-hooks/utils/ace_cli.py
def run_search(query: str, org: str = None, project: str = None):
    env = os.environ.copy()
    if org:
        env['ACE_ORG_ID'] = org
    if project:
        env['ACE_PROJECT_ID'] = project
    
    result = subprocess.run(
        ['ce-ace', 'search', '--stdin', '--json'],
        input=query.encode('utf-8'),
        capture_output=True,
        timeout=10,
        env=env  # ← Pass context via environment
    )
```

**Why environment variables instead of flags?**
- CLI already supports reading from environment
- Avoids modifying command line (cleaner for --stdin pattern)
- Matches the pattern that `.claude/settings.json` uses

---

## Summary of Findings

### Architecture Assessment

| Layer | Purpose | Is Necessary? | Adds Value? | Has Bugs? |
|-------|---------|---------------|-------------|-----------|
| Bash wrapper | Plugin delegation | ✅ YES | ✅ YES | ❌ NO |
| Python hook | Event parsing, context | ✅ YES | ✅ YES | ⚠️ YES (context not passed) |
| CLI subprocess | Server communication | ✅ YES | ✅ YES | ❌ NO |

**Overall verdict:** Architecture is **well-designed, NOT over-engineered**.

### Issues Found

**Bug 1: Context Not Passed to CLI in Hooks**
- **Severity**: Medium
- **Impact**: Hooks use global config instead of project-specific config
- **Fix**: Pass org/project via environment variables in subprocess call
- **Location**: `/shared-hooks/utils/ace_cli.py`

**Bug 2: Settings.json Format Inconsistency**
- **Severity**: Low (already documented in v5.0.3 changelog)
- **Impact**: Supports both `{orgId, projectId}` and `{env: {ACE_ORG_ID, ACE_PROJECT_ID}}` formats
- **Status**: Working as intended (dual format support)
- **Location**: `/shared-hooks/utils/ace_context.py`

### Recommendations

1. ✅ **Keep the 3-layer architecture** - Each layer has distinct value
2. ⚠️ **Fix context passing bug** - Hooks should use project-specific config
3. ✅ **Continue using direct stdout** - Emoji-marked output is user-friendly
4. ✅ **Follow boilerplate pattern** - Current wrapper design is correct
5. ✅ **Keep utilities separate** - `ace_context.py` and `ace_cli.py` promote code reuse

---

## Code Example: Correct Implementation

### Fixed ace_cli.py

```python
#!/usr/bin/env python3
"""ACE CLI Subprocess Wrapper - Calls ce-ace with context"""

import subprocess
import json
import os
from typing import Optional, Dict, Any


def run_search(query: str, org: str = None, project: str = None) -> Optional[Dict[str, Any]]:
    """
    Call ce-ace search --stdin with project context
    
    Args:
        query: Search query text
        org: Organization ID (optional, for multi-org mode)
        project: Project ID (required)
    
    Returns:
        Parsed JSON response or None on failure
    """
    try:
        # Build environment with project context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project
        
        result = subprocess.run(
            ['ce-ace', 'search', '--stdin', '--json'],
            input=query.encode('utf-8'),
            capture_output=True,
            timeout=10,
            env=env  # ← Pass context via environment
        )
        
        if result.returncode != 0:
            return None
        
        return json.loads(result.stdout)
    
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def run_learn(task: str, trajectory: str, success: bool, 
              org: str = None, project: str = None,
              patterns_used: Optional[list] = None) -> bool:
    """
    Call ce-ace learn --stdin with project context
    
    Args:
        task: Task description
        trajectory: Execution steps taken
        success: Whether task succeeded
        org: Organization ID (optional)
        project: Project ID (required)
        patterns_used: Optional list of pattern IDs used
    
    Returns:
        True if learning succeeded, False otherwise
    """
    try:
        payload = {
            'task': task,
            'trajectory': trajectory,
            'success': success
        }
        
        if patterns_used:
            payload['patterns_used'] = patterns_used
        
        # Build environment with project context
        env = os.environ.copy()
        if org:
            env['ACE_ORG_ID'] = org
        if project:
            env['ACE_PROJECT_ID'] = project
        
        result = subprocess.run(
            ['ce-ace', 'learn', '--stdin'],
            input=json.dumps(payload).encode('utf-8'),
            capture_output=True,
            timeout=10,
            env=env  # ← Pass context via environment
        )
        
        return result.returncode == 0
    
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
```

### Fixed ace_before_task.py

```python
#!/usr/bin/env -S uv run --script
# (script header unchanged)

from ace_cli import run_search
from ace_context import get_context

def main():
    try:
        event = json.load(sys.stdin)
        user_prompt = event.get('prompt', '')
        
        if not user_prompt:
            sys.exit(0)
        
        if user_prompt.strip().startswith('/'):
            sys.exit(0)
        
        # Get project context
        context = get_context()
        if not context:
            print("⚠️ [ACE] No project context found - skipping search")
            sys.exit(0)
        
        # Call ce-ace search --stdin WITH CONTEXT
        patterns_response = run_search(
            query=user_prompt,
            org=context['org'],      # ← Pass org
            project=context['project']  # ← Pass project
        )
        
        # ... rest unchanged
```

---

## Conclusion

### Is the ACE architecture over-engineered?

**NO.** The 3-layer architecture is:
- ✅ Well-designed and follows boilerplate pattern
- ✅ Each layer has distinct responsibilities
- ✅ No unnecessary duplication
- ✅ Easy to debug and maintain
- ✅ Reusable across hooks and commands

### What needs fixing?

**Context passing bug:**
- Hooks read `.claude/settings.json` but don't pass org/project to CLI
- Fix: Pass context via environment variables in subprocess calls
- Impact: Medium (hooks currently use wrong config)

### What's working well?

- ✅ Bash wrapper delegation pattern
- ✅ Python JSON parsing and output formatting
- ✅ CLI subprocess for server communication
- ✅ Direct stdout visibility with emoji markers
- ✅ Code reuse via utilities

### Final Recommendation

**Keep the architecture, fix the bug.** The design is sound; it just needs a small fix to properly propagate project context from `.claude/settings.json` to the CLI subprocess calls.
