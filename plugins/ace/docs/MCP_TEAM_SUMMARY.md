# ACE MCP Client v3.3.2 - Implementation Summary

**Quick Reference for MCP Client Team**

## What Changed

### Configuration Architecture (BREAKING CHANGE)

**Old (v3.3.1)**:
- `.ace/config.json` in project root (serverUrl, apiToken, projectId)
- `.mcp.json` in plugin directory (MCP server definition)

**New (v3.3.2)**:
- `~/.ace/config.json` in home directory (serverUrl, apiToken, cacheTtlMinutes=360, autoUpdateEnabled)
- `.claude/settings.local.json` in project root (MCP server definition + projectId as args)

### Why This Change?

1. ✅ **No duplication**: Global org config (URL + token) shared across all projects
2. ✅ **Claude Code native**: Uses standard `.claude/` directory pattern
3. ✅ **Clear separation**: Org settings vs project settings
4. ✅ **Versioning**: MCP client version pinned in project config (no more @latest caching issues)

## Critical Implementation Tasks

### 1. Configuration Discovery (HIGH PRIORITY)

**Read global config on startup**:
```typescript
// ~/.ace/config.json
const homedir = require('os').homedir();
const globalConfigPath = path.join(homedir, '.ace', 'config.json');
const globalConfig = JSON.parse(fs.readFileSync(globalConfigPath, 'utf8'));

// Extract values
const { serverUrl, apiToken, cacheTtlMinutes, autoUpdateEnabled } = globalConfig;
```

**Read project ID from command args**:
```typescript
// Passed via .claude/settings.local.json
// Example: ["--yes", "@ce-dot-net/ace-client@3.3.2", "--project-id", "prj_xxxxx"]
const projectIdArg = process.argv.find(arg => arg.startsWith('--project-id'));
const projectId = process.argv[process.argv.indexOf(projectIdArg) + 1];
```

**Error handling**:
- If `~/.ace/config.json` not found → Return error with setup instructions
- If `--project-id` not provided → Return error with project setup instructions

### 2. Version Checking (HIGH PRIORITY)

**Two independent checks on startup**:

**Check 1: Plugin Version (GitHub Releases API)**
```typescript
const response = await fetch(
  'https://api.github.com/repos/ce-dot-net/ce-claude-marketplace/releases/latest'
);
const { tag_name } = await response.json();
// Compare with current version from package.json
```

**Check 2: CLAUDE.md Template Version (GitHub Raw Content)**
```typescript
// Fetch template
const templateUrl = 'https://raw.githubusercontent.com/ce-dot-net/ce-claude-marketplace/main/plugins/ace-orchestration/CLAUDE.md';
const template = await fetch(templateUrl).then(r => r.text());

// Extract version from template
const templateVersionMatch = template.match(/<!-- ACE_SECTION_START v([\d.]+) -->/);
const templateVersion = templateVersionMatch?.[1]; // e.g., "3.3.2"

// Extract version from user's project CLAUDE.md
const projectClaudeMd = fs.readFileSync(path.join(projectRoot, 'CLAUDE.md'), 'utf8');
const projectVersionMatch = projectClaudeMd.match(/<!-- ACE_SECTION_START v([\d.]+) -->/);
const projectVersion = projectVersionMatch?.[1];

// Compare
const claudeMdUpdateAvailable = projectVersion !== templateVersion;
```

**Return version status in initialization response**:
```typescript
{
  versionStatus: {
    plugin: {
      updateAvailable: true,
      currentVersion: "v3.3.1",
      latestVersion: "v3.3.2"
    },
    claudeMd: {
      updateAvailable: true,
      projectVersion: "3.3.1",
      templateVersion: "3.3.2",
      claudeMdExists: true,
      hasAceSection: true
    },
    autoUpdateEnabled: true
  }
}
```

### 3. Cache TTL Update (MEDIUM PRIORITY)

**Change default TTL**:
```typescript
// Old: 5 minutes
// New: 360 minutes (6 hours)
const DEFAULT_CACHE_TTL = 360;
```

**Read from config**:
```typescript
const cacheTtlMinutes = globalConfig.cacheTtlMinutes || 360;
```

### 4. Migration Logic (MEDIUM PRIORITY)

**Auto-migrate old configs on first run**:
```typescript
// Check for old project config
const oldProjectConfig = path.join(projectRoot, '.ace', 'config.json');
if (fs.existsSync(oldProjectConfig) && !fs.existsSync(globalConfigPath)) {
  const oldData = JSON.parse(fs.readFileSync(oldProjectConfig, 'utf8'));

  // Create ~/.ace/config.json
  fs.mkdirSync(path.dirname(globalConfigPath), { recursive: true });
  fs.writeFileSync(globalConfigPath, JSON.stringify({
    serverUrl: oldData.serverUrl,
    apiToken: oldData.apiToken,
    cacheTtlMinutes: 360,
    autoUpdateEnabled: false
  }, null, 2));

  // Create .claude/settings.local.json
  const settingsPath = path.join(projectRoot, '.claude', 'settings.local.json');
  fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
  fs.writeFileSync(settingsPath, JSON.stringify({
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

## Testing Checklist

- [ ] Config discovery: Read `~/.ace/config.json`
- [ ] Config discovery: Read `--project-id` from args
- [ ] Config discovery: Handle missing global config (error message)
- [ ] Config discovery: Handle missing project ID (error message)
- [ ] Version check: Fetch plugin version from GitHub Releases
- [ ] Version check: Fetch CLAUDE.md template from GitHub raw
- [ ] Version check: Extract versions using regex `/<!-- ACE_SECTION_START v([\d.]+) -->/`
- [ ] Version check: Compare versions semantically
- [ ] Version check: Return status in initialization response
- [ ] Cache TTL: Default to 360 minutes
- [ ] Cache TTL: Read from config
- [ ] Migration: Detect old `.ace/config.json` in project
- [ ] Migration: Create new `~/.ace/config.json`
- [ ] Migration: Create `.claude/settings.local.json`

## Timeline

**Target Release**: v3.3.2
**Breaking Changes**: Yes (config file locations changed)
**Migration**: Automatic on first run
**Backwards Compatibility**: Migration handles v3.3.1 → v3.3.2

## Files Changed

### New Files
- `~/.ace/config.json` - Global org config (created by /ace-orchestration:ace-configure)
- `.claude/settings.local.json` - Project MCP server definition (created by /ace-orchestration:ace-configure)

### Removed Files
- `.ace/config.json` in project root - **MIGRATED** to `~/.ace/config.json`
- `.mcp.json` in plugin directory - **REPLACED** by `.claude/settings.local.json`

## Questions?

See full implementation guide: `docs/MCP_CLIENT_IMPLEMENTATION.md`

## Example Flow

```
User runs: /ace-orchestration:ace-configure
    ↓
Creates: ~/.ace/config.json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_xxxxx",
  "cacheTtlMinutes": 360,
  "autoUpdateEnabled": true
}
    ↓
Creates: .claude/settings.local.json
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
  - Checks plugin version (GitHub Releases API) ✅
  - Checks CLAUDE.md version (GitHub raw content) ✅
  - Returns initialization response with versionStatus ✅
    ↓
SessionStart hook receives versionStatus:
  - If autoUpdateEnabled + updates available → Run ace-claude-init.sh --auto-update
  - Else → Show notification to user
```

## API Changes

### New Initialization Response

```typescript
interface InitializationResponse {
  capabilities: string[];

  // NEW in v3.3.2
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
    autoUpdateEnabled: boolean;
  };

  configStatus: {
    globalConfigFound: boolean;
    projectIdProvided: boolean;
    cacheEnabled: boolean;
    cacheTtlMinutes: number;
  };
}
```

## Performance Requirements

- Config read: < 10ms (synchronous)
- Plugin version check: < 500ms (GitHub API)
- CLAUDE.md version check: < 500ms (GitHub raw)
- Total startup overhead: < 1500ms (parallel checks)

---

**Ready to implement? See `MCP_CLIENT_IMPLEMENTATION.md` for complete details.**
