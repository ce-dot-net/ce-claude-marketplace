# Server vs Client: Clear Separation of Responsibilities

**Date**: 2025-10-20
**Architecture**: TypeScript MCP Client + Python FastAPI Server

---

## ⚠️ CRITICAL: Multi-Tenant Authentication Required

**The client CANNOT run standalone!**

The TypeScript MCP client **MUST** authenticate with the Python FastAPI server using:
- ✅ **API Token** (`ACE_API_TOKEN=ace_xxx`) - Identifies organization
- ✅ **Project ID** (`ACE_PROJECT_ID=prj_xxx`) - Identifies project within organization
- ✅ **Server URL** (`ACE_SERVER_URL=http://localhost:9000`) - Server endpoint

**Without these, the client will fail!**

---

## ⚡ PERFORMANCE: Client-Side SQLite Cache

**The client SHOULD cache playbook locally for performance!**

**Location**: `~/.ace-cache/{org_id}_{project_id}.db` (SQLite)

**What Gets Cached Locally**:
- ✅ **Playbook snapshot** (survives restarts, TTL: 5 minutes)
- ✅ **Embedding cache** (avoids re-computing same embeddings)
- ✅ **Sync state** (last sync timestamp, server version)

**Benefits**:
- 🚀 **10-50x faster** playbook access (5-10ms vs 100-500ms)
- 💾 **Survives restarts** (close/reopen Claude Code, cache intact)
- 🔌 **Offline work** (use stale cache when network unavailable)
- 📊 **Reduced network calls** (90% cache hit rate)

**ACE Paper Quote**: *"cached locally or remotely, avoiding repetitive and expensive prefill operations"*

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  CLIENT (TypeScript MCP)                                │
│  Location: ce-ai-ace-client/                            │
│  Language: TypeScript                                   │
│  Runs: Inside Claude Code/Desktop via MCP               │
│                                                          │
│  Responsibilities:                                       │
│  - Pattern discovery (uses YOUR Claude via MCP Sampling)│
│  - Reflection analysis (uses YOUR Claude)               │
│  - Curation logic (0.85/0.30 thresholds)                │
│  - Domain taxonomy generation                           │
│  - Delta operation generation                           │
│                                                          │
│  Does NOT Store:                                        │
│  ❌ Patterns (sends to server)                          │
│  ❌ Embeddings (computed on server)                     │
│  ❌ Execution traces (sends to server)                  │
│  ❌ Organization/Project data (server manages)          │
│                                                          │
│  Authentication:                                        │
│  ✅ MUST provide ACE_API_TOKEN                          │
│  ✅ MUST provide ACE_PROJECT_ID                         │
│  ✅ MUST provide ACE_SERVER_URL                         │
└─────────────────────────────────────────────────────────┘
                         ↓ HTTP REST API
                         ↓ (Bearer token auth)
┌─────────────────────────────────────────────────────────┐
│  SERVER (Python FastAPI)                                │
│  Location: ce-ai-ace/server/                            │
│  Language: Python                                       │
│  Runs: Standalone process (python -m ace_server)        │
│                                                          │
│  Responsibilities:                                       │
│  - Pattern storage (ChromaDB)                           │
│  - Embedding computation (all-MiniLM-L6-v2, CPU)        │
│  - Execution trace storage                              │
│  - Multi-tenant isolation                               │
│  - Organization/Project management                      │
│  - API token validation                                 │
│                                                          │
│  Stores (Persistent):                                   │
│  ✅ Patterns (ChromaDB collections)                     │
│  ✅ Embeddings (with patterns)                          │
│  ✅ Execution traces (separate collections)             │
│  ✅ Organizations (SQLite tenants.db)                   │
│  ✅ Projects (SQLite tenants.db)                        │
│  ✅ API tokens (SQLite tenants.db)                      │
│                                                          │
│  Does NOT Do:                                           │
│  ❌ Pattern discovery (client does this)                │
│  ❌ LLM calls (client uses MCP Sampling)                │
│  ❌ Reflection analysis (client does this)              │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 What Gets Saved Where

### CLIENT (TypeScript) - Temporary Processing Only

**What Client Creates** (but doesn't persist):
1. **Pattern Discovery Results** → Sent to server via `POST /patterns`
2. **Reflection Analysis** → Generates DeltaOperations, sent via `POST /delta`
3. **Curation Decisions** → Applied locally, final patterns sent to server
4. **Domain Taxonomy** → Sent to server as pattern metadata

**Client Memory** (temporary):
- Current conversation context (RAM, lost on restart)
- Temporary analysis results (RAM, lost on restart)
- MCP Sampling responses from Claude (RAM, lost on restart)

**Client DOES cache to disk** (performance optimization):
- ✅ Playbook snapshot in SQLite (`~/.ace-cache/{org}_{project}.db`)
- ✅ Embedding cache in SQLite (avoid re-computing)
- ✅ Sync state metadata (last sync timestamp)
- **Purpose**: Survive restarts, offline work, reduce network calls
- **TTL**: 5 minutes (configurable)
- **NOT source of truth**: Server ChromaDB is canonical

**Client NEVER stores source code or execution traces to disk**!

---

### SERVER (Python) - Persistent Storage

**What Server Stores** (permanent):

#### 1. **ChromaDB Collections** (`~/.ace-memory/chroma/`)

**Pattern Collections** (format: `{org_id}_{project_id}`):
```python
# Example: org_abc123_prj_xyz789
{
  "id": "pattern_abc123",
  "name": "Always validate JWT tokens",
  "domain": "authentication",
  "content": "Before processing requests, validate JWT expiration",
  "confidence": 0.95,
  "observations": 10,
  "helpful": 8,      # ← Server tracks this
  "harmful": 2,      # ← Server tracks this
  "section": "strategies_and_hard_rules",
  "evidence": ["auth.py:45", "middleware.py:12"],
  "created_at": "2025-10-20T...",
  "updated_at": "2025-10-20T..."
}
```

**Execution Trace Collections** (format: `{org_id}_{project_id}_traces`):
```python
# Example: org_abc123_prj_xyz789_traces
{
  "task": "Create user authentication endpoint",
  "trajectory": [
    {"step": 1, "action": "write_file", "args": {"path": "auth.py"}},
    {"step": 2, "action": "run_tests", "args": {}}
  ],
  "result": {
    "success": true,
    "output": "All tests passed",
    "error": null
  },
  "playbook_used": ["ctx-001", "ctx-002"],
  "timestamp": "2025-10-20T..."
}
```

#### 2. **SQLite Database** (`~/.ace-memory/tenants.db`)

**Organizations Table**:
```sql
CREATE TABLE organizations (
  org_id TEXT PRIMARY KEY,          -- e.g., "org_abc123"
  org_name TEXT NOT NULL,
  api_token TEXT UNIQUE NOT NULL,   -- e.g., "ace_sZlqtF9-jY8M_..."
  created_at TEXT NOT NULL
);
```

**Projects Table**:
```sql
CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,               -- e.g., "prj_6bba0d15c5a6abc1"
  org_id TEXT NOT NULL,                      -- Foreign key to organizations
  project_name TEXT NOT NULL,
  chromadb_collection_name TEXT UNIQUE,      -- e.g., "org_abc123_prj_xyz789"
  created_at TEXT NOT NULL,
  settings_json TEXT,
  FOREIGN KEY (org_id) REFERENCES organizations(org_id)
);
```

---

## 🔐 Authentication Flow (Client → Server)

### Step 1: Client Configuration (TypeScript)

**File**: `~/.config/claude-code/mcp-server-config.json` (or Claude Desktop config)

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "node",
      "args": ["/path/to/ce-ai-ace-client/dist/index.js"],
      "env": {
        "ACE_SERVER_URL": "http://localhost:9000",
        "ACE_API_TOKEN": "ace_sZlqtF9-jY8M_4dXXRWMu4e0MyMcyAzargm_TK21YSs",
        "ACE_PROJECT_ID": "prj_6bba0d15c5a6abc1"
      }
    }
  }
}
```

### Step 2: Client Connects to Server (TypeScript)

**File**: `ce-ai-ace-client/src/services/server-client.ts`

```typescript
export class ACEServerClient {
  private serverUrl: string;
  private apiToken: string;
  private projectId: string;

  constructor() {
    // CRITICAL: These MUST be set or client fails!
    this.serverUrl = process.env.ACE_SERVER_URL || 'http://localhost:9000';
    this.apiToken = process.env.ACE_API_TOKEN!;
    this.projectId = process.env.ACE_PROJECT_ID!;

    if (!this.apiToken || !this.projectId) {
      throw new Error('ACE_API_TOKEN and ACE_PROJECT_ID are required!');
    }
  }

  private async fetch(endpoint: string, options?: RequestInit): Promise<any> {
    const url = `${this.serverUrl}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiToken}`,      // ← Server validates this
        'X-ACE-Project': this.projectId,                 // ← Server uses this
        ...options?.headers
      }
    });

    if (!response.ok) {
      throw new Error(`Server error: ${response.statusText}`);
    }

    return response.json();
  }

  // Example: Save patterns to server
  async savePatterns(patterns: Pattern[]): Promise<void> {
    await this.fetch('/patterns', {
      method: 'POST',
      body: JSON.stringify({ patterns: patterns.map(p => p.toJSON()) })
    });
  }

  // Example: Get structured playbook from server
  async getStructuredPlaybook(): Promise<StructuredPlaybook> {
    const response = await this.fetch('/playbook');
    return response.playbook;
  }
}
```

### Step 3: Server Validates (Python)

**File**: `ce-ai-ace/server/ace_server/api_server.py`

```python
async def verify_auth(
    authorization: Optional[str] = Header(None),
    x_ace_project: Optional[str] = Header(None)
) -> dict:
    """
    Verify Bearer token and project access

    Returns dict with org_id, project_id, collection_name
    """
    # Extract Bearer token
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")

    # Validate token → Get org_id
    org_id = tenant_manager.validate_token(token)
    if not org_id:
        raise HTTPException(status_code=401, detail="Invalid API token")

    # Get project ID from header
    project_id = x_ace_project

    # Verify project belongs to org
    project = tenant_manager.get_project(project_id)
    if not project or project.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "org_id": org_id,
        "project_id": project_id,
        "collection_name": project.chromadb_collection_name  # ← Used for ChromaDB
    }
```

---

## 🎯 Client Responsibilities (TypeScript)

### 1. **Pattern Discovery** (Client-Side Intelligence)

**File**: `ce-ai-ace-client/src/services/discovery.ts`

```typescript
async discoverPatterns(
  code: string,
  language: string,
  filePath: string,
  requestSampling: (messages: any[]) => Promise<any>  // ← Uses YOUR Claude
): Promise<Pattern[]> {
  // 1. Analyze code using MCP Sampling (YOUR Claude)
  const prompt = `Analyze this ${language} code and extract patterns...`;
  const response = await requestSampling([{ role: 'user', content: prompt }]);

  // 2. Parse response into patterns (client-side logic)
  const patterns = parsePatterns(response.content[0].text);

  // 3. Add metadata (client-side)
  patterns.forEach(p => {
    p.evidence = [filePath];
    p.created_at = new Date().toISOString();
  });

  // 4. Send to server for storage (server saves to ChromaDB)
  await serverClient.savePatterns(patterns);

  return patterns;
}
```

**What Client Does**:
- ✅ Calls YOUR Claude via MCP Sampling
- ✅ Parses LLM response into structured patterns
- ✅ Adds metadata (file paths, timestamps)
- ✅ **SENDS to server** (doesn't store locally)

**What Server Does**:
- ✅ Receives patterns via `POST /patterns`
- ✅ Computes embeddings (all-MiniLM-L6-v2)
- ✅ Stores in ChromaDB collection (multi-tenant)

---

### 2. **Reflection Analysis** (Client-Side Intelligence)

**File**: `ce-ai-ace-client/src/services/reflector.ts`

```typescript
async analyzeExecution(
  trace: ExecutionTrace,
  playbook: Pattern[],
  requestSampling: (messages: any[]) => Promise<any>  // ← Uses YOUR Claude
): Promise<Reflection> {
  // 1. Build prompt with execution data
  const prompt = `Analyze this execution and generate delta operations...`;

  // 2. Get analysis from YOUR Claude (client-side LLM call)
  const response = await requestSampling([{ role: 'user', content: prompt }]);

  // 3. Parse into delta operations (client-side logic)
  const reflection = JSON.parse(response.content[0].text);

  return reflection;  // DeltaOperation[]
}
```

**What Client Does**:
- ✅ Analyzes execution outcomes using YOUR Claude
- ✅ Generates delta operations (ADD/UPDATE/DELETE)
- ✅ **SENDS to server** via `POST /delta`

**What Server Does**:
- ✅ Receives delta operations via `POST /delta`
- ✅ Applies operations to ChromaDB (add patterns, update counters, delete patterns)
- ✅ Updates helpful/harmful counters
- ✅ Recalculates confidence scores

---

### 3. **Curation Logic** (Client-Side Intelligence)

**File**: `ce-ai-ace-client/src/services/curator.ts`

```typescript
async curatePatterns(
  newPatterns: Pattern[],
  requestSampling: (messages: any[]) => Promise<any>
): Promise<Pattern[]> {
  // 1. Get existing patterns from server
  const existingPatterns = await serverClient.getPatterns();

  // 2. Find similar patterns using server embeddings
  const similarPatterns = await serverClient.searchSimilar(newPatterns[0], 0.85);

  // 3. Apply curation logic (client-side thresholds)
  if (similarPatterns.length > 0) {
    // Merge similar patterns (client decides)
    const merged = mergePatterns(newPatterns[0], similarPatterns[0]);
    return [merged];
  } else {
    // Keep as new pattern
    return newPatterns;
  }
}
```

**What Client Does**:
- ✅ Fetches patterns from server via `GET /patterns`
- ✅ Applies 0.85 similarity threshold (client-side logic)
- ✅ Applies 0.30 confidence threshold (client-side logic)
- ✅ Decides merge/keep/prune (client-side logic)
- ✅ **SENDS final patterns to server** for storage

**What Server Does**:
- ✅ Provides similarity search via `POST /patterns/search`
- ✅ Computes embeddings for search
- ✅ Returns similar patterns
- ✅ Stores final curated patterns in ChromaDB

---

## 🚫 Common Misunderstandings (Client Claude's Mistakes)

### ❌ Mistake 1: "Client can run standalone"

**WRONG**: Client is just processing logic, it NEEDS the server for:
- Pattern storage (ChromaDB)
- Embedding computation
- Multi-tenant isolation
- Organization/Project management

**CORRECT**: Client MUST authenticate with server using API token + Project ID

---

### ❌ Mistake 2: "Client stores patterns locally"

**WRONG**: Client has NO persistent storage

**CORRECT**:
- Client discovers patterns → Sends to server
- Client curates patterns → Sends final result to server
- Client analyzes execution → Sends delta operations to server

---

### ❌ Mistake 3: "Server does LLM calls"

**WRONG**: Server has NO LLM access, no API keys

**CORRECT**:
- Client uses YOUR Claude via MCP Sampling
- Server only stores results
- Server never calls Anthropic API

---

### ❌ Mistake 4: "No authentication needed"

**WRONG**: Server is multi-tenant, REQUIRES authentication

**CORRECT**:
- Every request MUST include `Authorization: Bearer ace_xxx`
- Every request MUST include `X-ACE-Project: prj_xxx`
- Server validates token → org → project → collection

---

## 📝 Summary Table

| Responsibility | CLIENT (TypeScript) | SERVER (Python) |
|----------------|---------------------|-----------------|
| **Pattern Discovery** | ✅ Uses MCP Sampling | ❌ Not involved |
| **LLM Calls** | ✅ Via MCP Sampling | ❌ No LLM access |
| **Reflection Analysis** | ✅ Generates delta ops | ❌ Not involved |
| **Curation Logic** | ✅ Applies thresholds | ❌ Not involved |
| **Pattern Storage** | ❌ Sends to server | ✅ ChromaDB |
| **Embedding Computation** | ❌ Requests from server | ✅ all-MiniLM-L6-v2 |
| **Execution Trace Storage** | ❌ Sends to server | ✅ ChromaDB |
| **Multi-Tenant Isolation** | ❌ Just provides auth | ✅ Manages orgs/projects |
| **API Token Validation** | ❌ Just sends token | ✅ Validates token |
| **Helpful/Harmful Tracking** | ❌ Sends deltas | ✅ Updates counters |
| **Confidence Calculation** | ✅ Initial calculation | ✅ Recalculates from counters |

---

## 🔑 Required Environment Variables (Client)

**CRITICAL**: Client MUST have these set:

```bash
# Required
ACE_SERVER_URL=http://localhost:9000       # Server endpoint
ACE_API_TOKEN=ace_sZlqtF9-jY8M_...         # Organization API token
ACE_PROJECT_ID=prj_6bba0d15c5a6abc1       # Project ID

# Optional (for server setup only)
ANTHROPIC_API_KEY=sk-ant-...               # NOT used by client, only for server testing
```

**Without these, client will fail to start!**

---

## 🎯 Key Takeaway

**Client (TypeScript)**: INTELLIGENCE (pattern discovery, reflection, curation)
**Server (Python)**: STORAGE (ChromaDB, embeddings, multi-tenancy)

**Client CANNOT work without server!**
**Server CANNOT do intelligence without client!**

They are **symbiotic** - neither works alone! 🤝
