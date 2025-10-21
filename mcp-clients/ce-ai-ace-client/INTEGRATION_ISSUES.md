# ACE Client Integration Issues

**Date**: 2025-01-20
**Status**: ❌ BLOCKED - Client cannot work with current setup

## Critical Issues

### 1. Plugin MCP Configuration (BLOCKING)

**Location**: `/plugins/ace-orchestration/plugin.json`

**Current**:
```json
"mcpServers": {
  "ace-pattern-learning": {
    "command": "python",
    "args": ["-m", "ace_client"],  // ← Python module DELETED
```

**Problem**: Points to deleted Python client

**Fix Required**:
```json
"mcpServers": {
  "ace-pattern-learning": {
    "command": "node",
    "args": ["${CLAUDE_PLUGIN_ROOT}/../../mcp-clients/ce-ai-ace-client/dist/index.js"],
    "env": {
      "ACE_SERVER_URL": "http://localhost:8000",
      "ACE_API_TOKEN": "ace_sZlqtF9-jY8M_4dXXRWMu4e0MyMcyAzargm_TK21YSs",
      "ACE_PROJECT_ID": "prj_6bba0d15c5a6abc1"
    }
  }
}
```

### 2. Server API Endpoints (BLOCKING)

**Client calls** (TypeScript src/services/server-client.ts):
- `POST /playbook` → save StructuredPlaybook
- `GET /playbook` → get StructuredPlaybook
- `DELETE /playbook?confirm=true` → clear playbook
- `POST /embeddings` → compute embeddings ✅
- `GET /analytics` → get stats ✅

**Server has** (Python ace_server/api_server.py):
- `POST /patterns` → save Pattern[]
- `GET /patterns` → get Pattern[]
- `DELETE /patterns?confirm=true` → clear patterns
- `POST /embeddings` → compute embeddings ✅
- `GET /analytics` → get stats ✅

**Result**: Client will get **404 Not Found** errors!

**Fix Required**: Update server endpoints to match client

### 3. Server Type Definitions (BLOCKING)

**Client expects** (src/types/pattern.ts):
```typescript
interface StructuredPlaybook {
  strategies_and_hard_rules: PlaybookBullet[];
  useful_code_snippets: PlaybookBullet[];
  troubleshooting_and_pitfalls: PlaybookBullet[];
  apis_to_use: PlaybookBullet[];
}

interface PlaybookBullet {
  id: string;  // ctx-{timestamp}-{random}
  section: BulletSection;
  content: string;
  helpful: number;  // Counter
  harmful: number;  // Counter
  confidence: number;  // 0.0-1.0
  evidence: string[];
  observations: number;
  created_at: string;
  last_used: string;
}
```

**Server returns** (ace_server/types.py):
```python
class Pattern(BaseModel):
    id: str
    name: str
    domain: str
    content: str
    confidence: float
    observations: int
    harmful: int  # Single counter, not helpful/harmful
    created_at: str
    updated_at: str
    evidence: list[str]
```

**Result**: Client cannot parse server responses!

**Fix Required**: Update server types to ACE paper models

## Resolution Plan

### Step 1: Update Plugin Configuration (THIS REPO)

File: `/plugins/ace-orchestration/plugin.json`

Change MCP server command from Python to Node.js TypeScript client.

### Step 2: Update Server (DIFFERENT REPO: ce-ai-ace)

**Location**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server/`

**Files to update**:
1. `ace_server/types.py` → Add StructuredPlaybook, PlaybookBullet models
2. `ace_server/storage.py` → Store StructuredPlaybook instead of Pattern[]
3. `ace_server/api_server.py` → Change endpoints:
   - `POST /patterns` → `POST /playbook`
   - `GET /patterns` → `GET /playbook`
   - `DELETE /patterns` → `DELETE /playbook`

### Step 3: Test Integration

1. Start server: `python -m ace_server --port 8000`
2. Test client: Call `ace_status` tool from Claude Code
3. Test learning: Call `ace_learn` with execution trace
4. Verify playbook updates

## Current State

✅ **Client (TypeScript)**: Fully refactored to ACE paper (v1.0.0)
❌ **Plugin**: Points to deleted Python client
❌ **Server**: Still using old Pattern-based APIs
❌ **Integration**: Will fail with 404 errors

## Next Steps

1. Fix plugin.json MCP configuration (5 minutes)
2. Update server types, storage, and endpoints (30 minutes)
3. Test end-to-end (10 minutes)
