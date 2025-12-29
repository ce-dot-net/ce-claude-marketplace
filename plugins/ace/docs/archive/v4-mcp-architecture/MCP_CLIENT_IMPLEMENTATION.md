# ACE MCP Client Implementation Guide

**Version**: 3.3.2
**Target**: `@ce-dot-net/ace-client@3.3.2`
**Date**: 2025-11-01

## Overview

This document specifies the changes required for the ACE MCP client to support the new configuration architecture and version checking system.

---

## 1. Configuration Discovery

### Global Configuration: `~/.ace/config.json`

**Location**: User's home directory
**Purpose**: Org-level settings (serverUrl, apiToken, cache settings, auto-update preferences)

**Schema**:
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxx",
  "cacheTtlMinutes": 360,
  "autoUpdateEnabled": true
}
```

**Fields**:
- `serverUrl` (string, required): ACE server endpoint
- `apiToken` (string, required): API token for authentication
- `cacheTtlMinutes` (number, optional, default: 360): Cache TTL in minutes (6 hours)
- `autoUpdateEnabled` (boolean, optional, default: false): Enable automatic CLAUDE.md updates

**MCP Client Must**:
1. Read `~/.ace/config.json` on startup
2. Expand `~` to actual home directory path (OS-specific)
3. Handle missing file gracefully (return error with setup instructions)
4. Validate JSON schema
5. Use these values for ALL ACE API calls

### Project Configuration: `.claude/settings.local.json`

**Location**: Project root `.claude/` directory
**Purpose**: Project-specific MCP server definition with projectId

**Schema**:
```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": [
        "--yes",
        "@ce-dot-net/ace-client@3.3.2",
        "--project-id",
        "prj_xxxxx"
      ]
    }
  }
}
```

**MCP Client Must**:
1. Read `--project-id` from command-line args
2. This is passed by Claude Code when invoking the MCP server
3. Combine with global config to construct full ACE client context

---

## 2. Version Checking System

### Two Independent Version Checks

The MCP client must perform TWO separate version checks on startup:

#### Check 1: Plugin Version (GitHub Releases API)

**Purpose**: Detect if ACE Orchestration Plugin has a newer release

**Implementation**:
```typescript
async function checkPluginVersion(): Promise<PluginVersionStatus> {
  const response = await fetch(
    'https://api.github.com/repos/ce-dot-net/ce-claude-marketplace/releases/latest',
    {
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'ACE-MCP-Client/3.3.2'
      }
    }
  );

  const data = await response.json();
  const latestVersion = data.tag_name; // e.g., "v3.3.2"
  const currentVersion = "v3.3.1"; // From package.json or embedded

  return {
    updateAvailable: compareVersions(currentVersion, latestVersion) < 0,
    currentVersion,
    latestVersion,
    releaseUrl: data.html_url
  };
}
```

**Error Handling**:
- Network timeout: Return `{ updateAvailable: false, error: "timeout" }`
- Rate limit: Cache last known version, return cached result
- Invalid response: Log warning, continue without version check

#### Check 2: CLAUDE.md Template Version (GitHub Raw Content)

**Purpose**: Detect if ACE plugin instructions in project's CLAUDE.md are outdated

**Template Source**:
```
https://raw.githubusercontent.com/ce-dot-net/ce-claude-marketplace/main/plugins/ace-orchestration/CLAUDE.md
```

**Implementation**:
```typescript
async function checkClaudeMdVersion(projectRoot: string): Promise<ClaudeMdVersionStatus> {
  // 1. Fetch template from GitHub
  const templateResponse = await fetch(
    'https://raw.githubusercontent.com/ce-dot-net/ce-claude-marketplace/main/plugins/ace-orchestration/CLAUDE.md'
  );
  const templateContent = await templateResponse.text();

  // 2. Extract version from template
  const templateVersionMatch = templateContent.match(/<!-- ACE_SECTION_START v([\d.]+) -->/);
  const templateVersion = templateVersionMatch?.[1]; // e.g., "3.3.2"

  // 3. Read user's project CLAUDE.md
  const projectClaudeMdPath = path.join(projectRoot, 'CLAUDE.md');
  let projectVersion: string | null = null;

  if (fs.existsSync(projectClaudeMdPath)) {
    const projectContent = fs.readFileSync(projectClaudeMdPath, 'utf8');
    const projectVersionMatch = projectContent.match(/<!-- ACE_SECTION_START v([\d.]+) -->/);
    projectVersion = projectVersionMatch?.[1];
  }

  // 4. Compare versions
  return {
    updateAvailable: projectVersion !== null && compareVersions(projectVersion, templateVersion) < 0,
    projectVersion,
    templateVersion,
    claudeMdExists: fs.existsSync(projectClaudeMdPath),
    hasAceSection: projectVersion !== null
  };
}
```

**Version Marker Format**:
```html
<!-- ACE_SECTION_START v3.3.2 -->
...ACE plugin instructions...
<!-- ACE_SECTION_END v3.3.2 -->
```

**Extraction Logic**:
- Use regex: `/<!-- ACE_SECTION_START v([\d.]+) -->/`
- Capture group 1 contains version string (e.g., "3.3.2")
- Compare as semver (parse major.minor.patch)

**Edge Cases**:
- **No CLAUDE.md exists**: `claudeMdExists: false`, suggest running `/ace-orchestration:ace-claude-init`
- **CLAUDE.md exists but no ACE section**: `hasAceSection: false`, suggest running `/ace-orchestration:ace-claude-init`
- **Project version > template version**: User may have custom/beta version, don't warn
- **Network failure fetching template**: Cache last known template version, use cached

---

## 3. Startup Initialization Response

### New Initialization Protocol

When MCP client starts (first tool call), it must return version status as part of response metadata.

**Implementation**:
```typescript
interface InitializationResponse {
  // Existing fields
  capabilities: string[];

  // NEW: Version status
  versionStatus: {
    plugin: {
      updateAvailable: boolean;
      currentVersion: string;
      latestVersion: string;
      releaseUrl?: string;
    };
    claudeMd: {
      updateAvailable: boolean;
      projectVersion: string | null;
      templateVersion: string;
      claudeMdExists: boolean;
      hasAceSection: boolean;
    };
    autoUpdateEnabled: boolean; // From ~/.ace/config.json
  };

  // NEW: Config status
  configStatus: {
    globalConfigFound: boolean;
    projectIdProvided: boolean;
    cacheEnabled: boolean;
    cacheTtlMinutes: number;
  };
}
```

**Example Response**:
```json
{
  "capabilities": ["ace_get_playbook", "ace_learn", "ace_status", "..."],
  "versionStatus": {
    "plugin": {
      "updateAvailable": true,
      "currentVersion": "v3.3.1",
      "latestVersion": "v3.3.2",
      "releaseUrl": "https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v3.3.2"
    },
    "claudeMd": {
      "updateAvailable": true,
      "projectVersion": "3.3.1",
      "templateVersion": "3.3.2",
      "claudeMdExists": true,
      "hasAceSection": true
    },
    "autoUpdateEnabled": true
  },
  "configStatus": {
    "globalConfigFound": true,
    "projectIdProvided": true,
    "cacheEnabled": true,
    "cacheTtlMinutes": 360
  }
}
```

---

## 4. Version Comparison Algorithm

### Semantic Versioning Comparison

**Implementation**:
```typescript
function compareVersions(v1: string, v2: string): number {
  // Remove 'v' prefix if present
  const clean1 = v1.replace(/^v/, '');
  const clean2 = v2.replace(/^v/, '');

  const parts1 = clean1.split('.').map(Number);
  const parts2 = clean2.split('.').map(Number);

  for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
    const p1 = parts1[i] || 0;
    const p2 = parts2[i] || 0;

    if (p1 > p2) return 1;
    if (p1 < p2) return -1;
  }

  return 0; // Equal
}
```

**Usage**:
```typescript
// Returns: -1 (v1 < v2), 0 (equal), 1 (v1 > v2)
compareVersions("3.3.1", "3.3.2"); // -1 (update available)
compareVersions("3.3.2", "3.3.2"); // 0 (up to date)
compareVersions("3.3.3", "3.3.2"); // 1 (ahead, no update)
```

---

## 5. Caching Architecture

### Three-Tier Cache System

**Unchanged from v3.3.1**, but TTL updated to 360 minutes (6 hours).

**Cache Layers**:
1. **RAM Cache**: In-memory, session-scoped
2. **SQLite Cache**: `~/.ace-cache/{org}_{project}.db`, 360-minute TTL
3. **Server Fetch**: Only when cache stale or empty

**SQLite Schema**:
```sql
CREATE TABLE playbook_cache (
  project_id TEXT PRIMARY KEY,
  playbook_json TEXT NOT NULL,
  cached_at INTEGER NOT NULL
);

CREATE TABLE version_cache (
  cache_key TEXT PRIMARY KEY, -- "plugin_version" or "claudemd_version"
  version TEXT NOT NULL,
  cached_at INTEGER NOT NULL
);
```

**Cache Invalidation**:
- TTL-based: 360 minutes (6 hours) from `cached_at`
- Manual: `/ace-orchestration:ace-clear-cache` command
- Automatic: On major version updates (3.x.x → 4.x.x)

---

## 6. Error Handling

### Configuration Errors

**Error 1: Global Config Missing**
```json
{
  "error": "CONFIG_NOT_FOUND",
  "message": "ACE global configuration not found at ~/.ace/config.json. Run /ace-orchestration:ace-configure to set up.",
  "recoverable": true,
  "setupCommand": "/ace-orchestration:ace-configure"
}
```

**Error 2: Invalid Project ID**
```json
{
  "error": "PROJECT_ID_MISSING",
  "message": "Project ID not provided. Ensure .claude/settings.local.json contains --project-id argument.",
  "recoverable": true,
  "setupCommand": "/ace-orchestration:ace-configure --project"
}
```

**Error 3: Network Timeout**
```json
{
  "error": "NETWORK_TIMEOUT",
  "message": "Failed to check for updates (network timeout). Using cached version info.",
  "recoverable": true,
  "fallback": "cached"
}
```

### Version Check Errors

**Error 4: GitHub API Rate Limit**
```json
{
  "error": "RATE_LIMIT",
  "message": "GitHub API rate limit exceeded. Version check will retry in 1 hour.",
  "recoverable": true,
  "retryAfter": 3600
}
```

**Error 5: CLAUDE.md Parse Error**
```json
{
  "error": "CLAUDEMD_PARSE_ERROR",
  "message": "Failed to extract version from CLAUDE.md. File may be corrupted.",
  "recoverable": true,
  "suggestion": "Run /ace-orchestration:ace-claude-init to repair"
}
```

---

## 7. Implementation Checklist

### Phase 1: Configuration Discovery (v3.3.2)
- [ ] Implement `~/.ace/config.json` reader
- [ ] Handle OS-specific home directory expansion
- [ ] Validate JSON schema on load
- [ ] Read `--project-id` from command args
- [ ] Combine global + project config
- [ ] Return config status in initialization response

### Phase 2: Version Checking (v3.3.2)
- [ ] Implement GitHub Releases API check (plugin version)
- [ ] Implement GitHub Raw content fetch (CLAUDE.md template)
- [ ] Extract version from template using regex
- [ ] Read project `CLAUDE.md` and extract version
- [ ] Implement semantic version comparison
- [ ] Cache version check results (360-minute TTL)
- [ ] Return version status in initialization response

### Phase 3: Error Handling (v3.3.2)
- [ ] Handle missing `~/.ace/config.json`
- [ ] Handle missing project ID
- [ ] Handle network timeouts (version checks)
- [ ] Handle GitHub API rate limits
- [ ] Handle CLAUDE.md parse errors
- [ ] Provide recovery suggestions for all errors

### Phase 4: Testing (v3.3.2)
- [ ] Test with `~/.ace/config.json` present
- [ ] Test with `~/.ace/config.json` missing
- [ ] Test with various TTL values (0, 360, 1440)
- [ ] Test plugin version check (outdated, current, ahead)
- [ ] Test CLAUDE.md version check (no file, no section, outdated, current)
- [ ] Test network failures (timeout, rate limit)
- [ ] Test cross-platform (macOS, Linux, Windows)

---

## 8. Breaking Changes from v3.3.1

### Removed
- ❌ `.mcp.json` in plugin directory (replaced by `.claude/settings.local.json`)
- ❌ `.ace/config.json` in project root (moved to `~/.ace/config.json`)
- ❌ Environment variables for config (not supported for end users)

### Changed
- ⚠️ Config discovery: Now reads `~/.ace/config.json` + args from `.claude/settings.local.json`
- ⚠️ Cache TTL: Default changed from 5 minutes to 360 minutes (6 hours)
- ⚠️ Initialization: Now returns `versionStatus` and `configStatus` metadata

### Added
- ✅ Plugin version checking via GitHub Releases API
- ✅ CLAUDE.md template version checking via GitHub raw content
- ✅ Automatic version comparison (plugin vs template independently)
- ✅ Auto-update flag in `~/.ace/config.json`
- ✅ Comprehensive error recovery suggestions

---

## 9. Example Flows

### Flow 1: Fresh Installation

```
User runs: /ace-orchestration:ace-configure
    ↓
Plugin creates: ~/.ace/config.json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxx",
  "cacheTtlMinutes": 360,
  "autoUpdateEnabled": false
}
    ↓
Plugin creates: .claude/settings.local.json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": ["--yes", "@ce-dot-net/ace-client@3.3.2", "--project-id", "prj_xxxxx"]
    }
  }
}
    ↓
MCP client starts:
  - Reads ~/.ace/config.json ✅
  - Reads --project-id from args ✅
  - Checks plugin version: v3.3.2 (latest) ✅
  - Checks CLAUDE.md: Not found ⚠️
    ↓
Returns initialization response:
{
  "versionStatus": {
    "plugin": { "updateAvailable": false, ... },
    "claudeMd": {
      "updateAvailable": false,
      "claudeMdExists": false,
      "hasAceSection": false
    }
  }
}
    ↓
Plugin suggests: "Run /ace-orchestration:ace-claude-init to add ACE instructions"
```

### Flow 2: Update Available

```
User starts session
    ↓
MCP client starts:
  - Reads ~/.ace/config.json ✅
  - Checks plugin version:
    - Current: v3.3.1
    - Latest: v3.3.2 (GitHub Releases API)
    - updateAvailable: true ⚠️
  - Checks CLAUDE.md:
    - Project version: 3.3.1 (from CLAUDE.md)
    - Template version: 3.3.2 (from GitHub raw)
    - updateAvailable: true ⚠️
    ↓
Returns initialization response with warnings
    ↓
SessionStart hook receives versionStatus
    ↓
IF autoUpdateEnabled == true:
  → Run ace-claude-init.sh --auto-update (silent)
ELSE:
  → Show notification:
    "🔔 ACE Plugin update available: v3.3.2
     🔔 CLAUDE.md template update available: v3.3.2
     Run /ace-orchestration:ace-claude-init to update"
```

---

## 10. Testing Scenarios

### Scenario 1: Normal Operation
- Global config exists: `~/.ace/config.json`
- Project config exists: `.claude/settings.local.json` with projectId
- Both plugin and CLAUDE.md up to date
- **Expected**: Clean initialization, no warnings

### Scenario 2: Missing Global Config
- No `~/.ace/config.json`
- **Expected**: Error with setup command suggestion

### Scenario 3: Missing Project ID
- Global config exists, but no `--project-id` in args
- **Expected**: Error with project setup command suggestion

### Scenario 4: Plugin Update Available
- Current: v3.3.1, Latest: v3.3.2
- **Expected**: Warning with release URL

### Scenario 5: CLAUDE.md Update Available
- Project CLAUDE.md: v3.3.1, Template: v3.3.2
- **Expected**: Warning with update command

### Scenario 6: No CLAUDE.md File
- Project has no `CLAUDE.md`
- **Expected**: Suggestion to run `/ace-orchestration:ace-claude-init`

### Scenario 7: Network Failure
- Cannot reach GitHub (timeout/offline)
- **Expected**: Use cached version info, warn about stale data

### Scenario 8: Rate Limited
- GitHub API returns 429
- **Expected**: Use cached data, log retry time

---

## 11. Performance Requirements

- **Config read**: < 10ms (synchronous file read)
- **Version check (plugin)**: < 500ms (GitHub API call)
- **Version check (CLAUDE.md)**: < 500ms (GitHub raw fetch)
- **Total startup overhead**: < 1500ms (parallel version checks)
- **Cache hit**: < 5ms (SQLite query)
- **Memory footprint**: < 5MB (RAM cache)

---

## 12. Security Considerations

- **API Token Storage**: Must be read from `~/.ace/config.json` with restricted permissions (chmod 600 recommended)
- **GitHub API**: Use rate-limited caching to avoid abuse
- **CLAUDE.md Content**: Validate content length (max 100KB) before parsing
- **Network Requests**: Set 5-second timeout for all external calls
- **Path Traversal**: Sanitize all file paths before reading

---

## 13. Migration Path (v3.3.1 → v3.3.2)

### Automatic Migration

When MCP client v3.3.2 starts and detects old config:

```typescript
// Check for old config locations
const oldProjectConfig = './.ace/config.json';
const oldMcpConfig = '~/.claude/plugins/.../ace-orchestration/.mcp.json';

if (fs.existsSync(oldProjectConfig) && !fs.existsSync('~/.ace/config.json')) {
  // Migrate to new location
  const oldData = JSON.parse(fs.readFileSync(oldProjectConfig, 'utf8'));

  fs.mkdirSync('~/.ace', { recursive: true });
  fs.writeFileSync('~/.ace/config.json', JSON.stringify({
    serverUrl: oldData.serverUrl,
    apiToken: oldData.apiToken,
    cacheTtlMinutes: 360, // NEW default
    autoUpdateEnabled: false // NEW field
  }, null, 2));

  // Create .claude/settings.local.json
  fs.writeFileSync('.claude/settings.local.json', JSON.stringify({
    mcpServers: {
      "ace-pattern-learning": {
        command: "npx",
        args: ["--yes", "@ce-dot-net/ace-client@3.3.2", "--project-id", oldData.projectId]
      }
    }
  }, null, 2));

  console.log('✅ Migrated config to v3.3.2 architecture');
}
```

---

## 14. Contact & Support

**Questions**: Open issue at https://github.com/ce-dot-net/ce-claude-marketplace/issues
**ACE SDK (MCP)**: https://github.com/ce-dot-net/ace-sdk
**Plugin Version**: v3.3.2
**Last Updated**: 2025-11-01
