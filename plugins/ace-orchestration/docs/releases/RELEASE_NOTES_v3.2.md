# ACE Orchestration Plugin v3.2.1 - Server-Side Intelligence Architecture

**Release Date**: 2025-10-22
**MCP Client Version**: v3.2.2
**Plugin Version**: v3.2.1

## 🎯 Major Architecture Change

This release implements the **ACE framework's server-side intelligence architecture**, moving Reflector and Curator agents from the client to the server for universal MCP compatibility.

## 🏗️ Architecture Overview

### Before (v3.1.x): Client-Side Intelligence
```
Claude Code → MCP Client (with LLM calls) → ACE Server (storage only)
                ├─ Reflector (Sonnet 4)
                └─ Curator (Haiku 4.5)
```
**Problem**: MCP clients cannot call LLMs directly, breaking compatibility with tools like Cursor, Cline, and other MCP clients.

### After (v3.2.x): Server-Side Intelligence
```
Claude Code → MCP Client (HTTP only) → ACE Server (full intelligence)
                                         ├─ Reflector (Sonnet 4)
                                         ├─ Curator (Haiku 4.5)
                                         └─ Merge Algorithm
```
**Benefits**:
- ✅ Universal MCP compatibility (works with ANY MCP client)
- ✅ Cost optimized (60% savings using Haiku for Curator)
- ✅ Server-side analysis with transparent logging
- ✅ No LLM calls from client = simpler, faster client

## 📋 What Changed

### 1. MCP Client Changes (`@ce-dot-net/ace-client@3.2.2`)

**New Tool Added**: `ace_init`
- Initialize playbook from git history (server-side analysis)
- Analyzes commit patterns, file co-changes, common fixes
- Parameters:
  - `repo_path`: Path to git repository (defaults to cwd)
  - `commit_limit`: Number of commits to analyze (default: 100)
  - `days_back`: Days of history to analyze (default: 30)
  - `merge_with_existing`: Merge with existing playbook (default: true)

**Architecture Changes**:
- Removed client-side Reflector/Curator LLM calls
- Simple HTTP POST to `/traces` endpoint
- Server handles all intelligence autonomously
- Client now just posts trace data and retrieves results

**Key Methods** (`src/services/server-client.ts`):
```typescript
// POST trace → server runs Reflector + Curator automatically
async storeExecutionTrace(trace: any): Promise<any> {
  return this.request('/traces', 'POST', trace);
}

// POST git analysis → server performs offline learning
async initializeFromRepo(params: {...}): Promise<any> {
  return this.request('/init', 'POST', params);
}

// GET playbook with 3-tier cache (RAM → SQLite → Server)
async getPlaybook(): Promise<any> {
  // Cache logic...
  return this.request('/playbook', 'GET');
}
```

### 2. Plugin Configuration Updates

**`.mcp.json`**:
```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": ["--yes", "@ce-dot-net/ace-client@3.2.2"]
    }
  }
}
```

**`plugin.json`**: Updated to v3.2.1

### 3. MCP Tool Prefix Corrections

**Correct Prefix**: `mcp__ace-pattern-learning__`
**Wrong Prefix**: `mcp__plugin_ace-orchestration_ace-pattern-learning__`

**Files Fixed**:
- `CLAUDE.md` (lines 43, 103)
- `commands/ace-test.md` (lines 53, 135-140, 146)
- `.claude/settings.local.json` (lines 44-45)

**Available Tools**:
```
mcp__ace-pattern-learning__ace_learn        - Core learning function
mcp__ace-pattern-learning__ace_status       - Get playbook stats
mcp__ace-pattern-learning__ace_get_playbook - View full playbook
mcp__ace-pattern-learning__ace_clear        - Clear playbook
mcp__ace-pattern-learning__ace_init         - Initialize from git (NEW!)
mcp__ace-pattern-learning__ace_save_config  - Save configuration
```

## 🔬 ACE Framework Architecture

This release fully implements the ACE framework architecture:

### Three-Agent Architecture

1. **Generator** (Main Claude Instance)
   - Executes coding tasks
   - Produces reasoning trajectories
   - Collects execution feedback

2. **Reflector** (Server-Side, Sonnet 4)
   - Analyzes execution traces
   - Distills high-level insights
   - Identifies patterns and anti-patterns
   - Output: Structured analysis with confidence scores

3. **Curator** (Server-Side, Haiku 4.5)
   - Processes Reflector insights
   - Creates incremental delta updates
   - Prevents "brevity bias" and "context collapse"
   - Output: Surgical JSON patches to playbook

### Delta Update Mechanism

**Key Innovation**: Incremental updates instead of monolithic rewrites
```
Reflector Output → Curator → Delta JSON Patches → Merge Algorithm → Updated Playbook
```

**Benefits**:
- Prevents information loss ("context collapse")
- Grows and refines playbook over time
- Surgical updates to specific sections
- Preserves high-confidence existing patterns

### Offline Learning (Bonus Feature)

The `/ace-init` command enables **offline learning from git history**:
```
Git Commits → Server-Side Analysis → Pattern Extraction → Playbook Bootstrap
```

Discovers:
- Common bug patterns and fixes
- File co-change patterns
- API usage patterns
- Troubleshooting steps

## 📊 Performance & Cost

ACE Framework Results:
- **Significant** improvement on agentic tasks
- **Improved** performance on domain-specific tasks
- **60% cost savings** using Haiku 4.5 for Curator vs Sonnet 4

## 🚀 Getting Started

### First Time Setup

1. **Install/Update Plugin**:
   ```bash
   # Plugin auto-installs MCP client via npx
   # Restart Claude Code to pick up v3.2.2
   ```

2. **Configure Connection**:
   ```bash
   /ace-configure
   ```

3. **Bootstrap from Git History** (Optional):
   ```bash
   /ace-init --commits 100 --days 30
   ```

4. **Verify Setup**:
   ```bash
   /ace-test
   ```

### Automatic Learning

The Agent Skill (`ace-orchestration:ace-learning`) triggers automatically after:
- Problem-solving & debugging
- Code implementation & refactoring
- API & tool integration
- Learning from failures
- Substantial multi-step tasks

**Learning Pipeline**:
```
Work Completed → Agent Skill Triggers → ace_learn Called →
MCP Client POSTs to /traces → Server Runs Reflector + Curator →
Delta Updates Applied → Playbook Enhanced!
```

## 🔧 Troubleshooting

### `/ace-init` not available

**Symptom**: Tool not found error
**Cause**: Running old MCP client version
**Fix**: Restart Claude Code to load v3.2.2

### MCP tool prefix errors

**Symptom**: `mcp__plugin_ace-orchestration_ace-pattern-learning__*` not found
**Cause**: Wrong tool prefix in older versions
**Fix**: This release fixes all prefixes to `mcp__ace-pattern-learning__*`

### Server connection issues

**Symptom**: Connection refused or timeout
**Cause**: ACE server not running or wrong URL
**Fix**: Run `/ace-configure` to set correct server URL

## 📚 Commands Reference

- `/ace-test` - Verify setup and show diagnostics
- `/ace-status` - View playbook statistics
- `/ace-patterns [section]` - View learned patterns
- `/ace-init` - Initialize from git history (NEW!)
- `/ace-clear` - Clear playbook
- `/ace-configure` - Configure server connection
- `/ace-export-patterns` - Export playbook to JSON
- `/ace-import-patterns` - Import playbook from JSON

## 🔗 Links

- **Repository**: https://github.com/ce-dot-net/ce-ai-ace
- **MCP Client**: [@ce-dot-net/ace-client@3.2.2](https://www.npmjs.com/package/@ce-dot-net/ace-client)

## 🎉 Result

**Significant performance improvement on agentic tasks through fully automatic pattern learning!**

The ACE architecture enables Claude Code to learn from every execution, continuously improving performance on complex coding tasks through intelligent pattern recognition and context engineering.

---

**Technical Note**: This architecture enables universal MCP compatibility by moving all LLM calls to the server. Any MCP-compatible tool (Claude Code, Cursor, Cline, etc.) can now benefit from ACE's automatic learning without requiring sampling or direct LLM access.
