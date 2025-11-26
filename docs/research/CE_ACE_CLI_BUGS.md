# ce-ace CLI Bugs Report

**Date**: 2025-11-18
**Plugin Version**: v5.1.1
**CLI Version**: Tested with ce-ace@1.0.4

## Bug 1: Plain Text Output Shows 0 Bullets When Data Exists

**Severity**: HIGH - Makes `ce-ace status` unusable

**Reproduction**:
```bash
# Setup: Project has 70 patterns confirmed via API
export ACE_ORG_ID="org_34fYIlitYk4nyFuTvtsAzA6uUJF"
export ACE_PROJECT_ID="prj_d3a244129d62c198"

# BUG: Plain text shows 0
ce-ace status
# Output: Total Bullets: 0 ❌

# WORKS: JSON shows correct count
ce-ace status --json
# Output: "total_patterns": 70 ✅
```

**Expected**: Both outputs should show 70 patterns
**Actual**: Plain text formatter shows 0, JSON works correctly

**Impact**: Users see empty playbook despite having data

---

## Bug 2: --org and --project Flags Don't Work

**Severity**: HIGH - Documented flags are non-functional

**Reproduction**:
```bash
# These flags are documented in help/docs but don't work
ce-ace --org "org_34fYIlitYk4nyFuTvtsAzA6uUJF" --project "prj_d3a244129d62c198" status
# Output: Total Bullets: 0 ❌

# Without flags (using env vars) works
export ACE_ORG_ID="org_34fYIlitYk4nyFuTvtsAzA6uUJF"
export ACE_PROJECT_ID="prj_d3a244129d62c198"
ce-ace status --json
# Output: "total_patterns": 70 ✅
```

**Expected**: Flags should override environment variables
**Actual**: Flags appear to be ignored or cause wrong project lookup

**Impact**: Cannot use CLI flags for project selection

---

## Bug 3: --server-url Flag Doesn't Work in `config validate`

**Severity**: MEDIUM - Workaround available via env vars

**Reproduction**:
```bash
ce-ace config validate \
  --server-url "https://ace-api.code-engine.app" \
  --api-token "ace_xxxxx"

# Output: Error: Server URL required. Use --server-url or set ACE_SERVER_URL ❌
```

**Workaround**:
```bash
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_xxxxx"
ce-ace config validate --json
# Works ✅
```

**Expected**: Flags should work as documented
**Actual**: CLI ignores --server-url flag, requires env vars

**Impact**: Configuration workflow requires env vars instead of flags

---

## Current Workaround in Plugin

ACE plugin v5.1.1 uses `ce-ace status --json` and outputs raw JSON.
We will NOT implement parsing workarounds - CLI team must fix output formatting.

---

## Outdated Documentation References

The **ce-ace-cli integration guide** needs updates to reflect these bugs:

### ❌ Section: "Context Resolution (4-Tier Precedence)"

**Currently Documents**:
```
Tier 1 (Highest Priority):
  CLI Flags: --org <org_id> --project <project_id>
    ↓
Tier 2:
  Environment Variables: ACE_ORG_ID, ACE_PROJECT_ID
```

**Reality**: Tier 1 (CLI flags) is BROKEN. Only Tier 2 (env vars) works.

**Fix Needed**: Document that `--org` and `--project` flags don't work, use env vars or .claude/settings.json instead.

---

### ❌ Section: "Complete Command Reference"

**Currently Documents**:
```bash
ce-ace status [--json]                 # Show playbook statistics
```

**Reality**: Plain text mode shows 0 bullets, only `--json` works.

**Fix Needed**: Change to:
```bash
ce-ace status --json                   # Show playbook statistics (JSON only - plain text broken)
```

---

### ❌ Section: "Configuration & Diagnostics"

**Currently Documents**:
```bash
ce-ace config validate --server-url <url> --api-token <token>
```

**Reality**: `--server-url` flag is ignored, must use env vars.

**Fix Needed**: Document workaround:
```bash
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_xxxxx"
ce-ace config validate --json
```

---

### ❌ All Code Examples Using --org and --project

**Examples to Remove/Fix**:
- Any use of `--org` and `--project` flags
- Any Tier 1 precedence references
- Any examples showing plain text output (non-JSON)

**Replacement Pattern**:
- Document env vars (ACE_ORG_ID, ACE_PROJECT_ID) as primary method
- Document .claude/settings.json as preferred for plugins
- Always use `--json` flag for programmatic access

---

## Next Steps

1. **CLI Team**: Fix plain text formatter in `ce-ace status`
2. **CLI Team**: Fix --org and --project flag handling
3. **CLI Team**: Fix --server-url flag in `config validate`
4. **CLI Team**: Add integration tests for all output formats
5. **Docs Team**: Update integration guide to remove broken flag references
6. **Docs Team**: Add "Known Issues" section to guide
7. **Plugin Team**: Continue using `--json` + env vars (no workarounds)
