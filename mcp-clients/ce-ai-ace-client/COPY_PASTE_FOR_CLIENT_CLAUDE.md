# 📋 COPY/PASTE THIS TO CLIENT-SIDE CLAUDE

**Date**: 2025-10-20
**Your Task**: Implement client-side SQLite cache for ACE MCP client

---

## ⚡ TL;DR - What You Need to Do

You're working on the **TypeScript MCP client** for ACE (Agentic Context Engineering).

**Problem**: Currently, every MCP tool call fetches playbook from server → slow, network-dependent, doesn't survive restarts.

**Solution**: Add **client-side SQLite cache** at `~/.ace-cache/{org}_{project}.db`

**Benefits**: 10-50x faster, survives restarts, offline work, 90% fewer network calls.

---

## 📊 What Gets Saved Where (Complete Breakdown)

### CLIENT (Your Responsibility)

#### In-Memory Cache (RAM)
- **Playbook snapshot** (fast access, lost on restart)
- **Analysis results** (temporary)
- **Purpose**: Speed during MCP session

#### SQLite Cache (`~/.ace-cache/{org}_{project}.db`) ⚠️ **YOU NEED TO IMPLEMENT THIS**
```sql
-- Table: playbook_bullets (cached from server)
CREATE TABLE playbook_bullets (
  id TEXT PRIMARY KEY,                  -- ctx-xxx
  section TEXT NOT NULL,                -- strategies_and_hard_rules, etc.
  content TEXT NOT NULL,
  helpful INTEGER DEFAULT 0,
  harmful INTEGER DEFAULT 0,
  confidence REAL DEFAULT 0.5,
  observations INTEGER DEFAULT 0,
  evidence TEXT,                        -- JSON array
  created_at TEXT NOT NULL,
  last_used TEXT NOT NULL,
  synced_at TEXT                        -- Last sync with server
);

-- Table: embedding_cache (avoid re-computing)
CREATE TABLE embedding_cache (
  content_hash TEXT PRIMARY KEY,        -- SHA256(content)
  embedding BLOB NOT NULL,              -- Float32Array
  created_at TEXT NOT NULL
);

-- Table: sync_state (metadata)
CREATE TABLE sync_state (
  key TEXT PRIMARY KEY,                 -- 'last_sync', 'server_version'
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

**What to Cache**:
- ✅ Playbook bullets (snapshot from server)
- ✅ Embeddings (avoid re-computing same text)
- ✅ Sync state (last sync timestamp)

**What NOT to Cache**:
- ❌ Source code (never leaves client)
- ❌ Execution traces (send directly to server)
- ❌ Organizations/Projects (server manages)

**TTL**: 5 minutes (configurable)

---

### SERVER (Python FastAPI - Already Implemented)

#### ChromaDB Storage (`~/.ace-memory/chroma/`)
```
org_abc123_prj_xyz789/              # Playbook bullets collection
org_abc123_prj_xyz789_traces/       # Execution traces collection
```

**What Server Saves**:
- ✅ **Playbook bullets** (permanent, with embeddings)
- ✅ **Execution traces** (learning data)
- ✅ **Embeddings** (all-MiniLM-L6-v2, 384 dimensions)

#### SQLite Storage (`~/.ace-memory/tenants.db`)
- ✅ **Organizations** (org_id, api_token)
- ✅ **Projects** (project_id, org_id, collection_name)

---

## 📚 Key Data Structures (ACE Paper)

### 1. Playbook Bullet (Core Unit)

**ACE Paper**: *"Collection of structured, itemized bullets with unique identifiers and counters"*

```typescript
interface PlaybookBullet {
  id: string;                    // ctx-{timestamp}-{random}
  section: BulletSection;        // Which section
  content: string;               // The knowledge
  helpful: number;               // Counter: how many times helpful
  harmful: number;               // Counter: how many times harmful
  confidence: number;            // helpful / (helpful + harmful)
  observations: number;          // Total times consulted
  evidence: string[];            // File paths, errors, line numbers
  created_at: string;
  last_used: string;
}

type BulletSection =
  | 'strategies_and_hard_rules'
  | 'useful_code_snippets'
  | 'troubleshooting_and_pitfalls'
  | 'apis_to_use';
```

**Where Saved**:
- ✅ Server (ChromaDB): Source of truth, permanent
- ✅ Client (SQLite): Cache, synced every 5 min ⚠️ **YOU IMPLEMENT**
- ✅ Client (RAM): Fast access during session

---

### 2. Structured Playbook (Container)

```typescript
interface StructuredPlaybook {
  strategies_and_hard_rules: PlaybookBullet[];
  useful_code_snippets: PlaybookBullet[];
  troubleshooting_and_pitfalls: PlaybookBullet[];
  apis_to_use: PlaybookBullet[];
}
```

**Where Saved**:
- ✅ Server (ChromaDB): All bullets, queryable by section
- ✅ Client (SQLite): Full snapshot ⚠️ **YOU IMPLEMENT**
- ✅ Client (RAM): Loaded on first call

---

### 3. Execution Trace

**ACE Paper**: *"Generator highlights which bullets were useful or misleading"*

```typescript
interface ExecutionTrace {
  task: string;
  trajectory: TrajectoryStep[];
  result: { success: boolean; output: string; error?: string };
  playbook_used: string[];       // Bullet IDs consulted
  timestamp: string;
}
```

**Where Saved**:
- ✅ Server (ChromaDB): Permanent
- ❌ Client: NOT saved (send immediately to server)

---

### 4. Delta Operations

**ACE Paper**: *"Incremental delta updates, not monolithic rewrites"*

```typescript
interface DeltaOperation {
  type: 'ADD' | 'UPDATE' | 'DELETE';

  // For ADD
  section?: BulletSection;
  content?: string;
  confidence?: number;
  evidence?: string[];

  // For UPDATE/DELETE
  bullet_id?: string;
  helpful_delta?: number;        // +1 if helpful, 0 otherwise
  harmful_delta?: number;        // +1 if harmful, 0 otherwise

  reason?: string;
}
```

**Where Saved**:
- ❌ Nowhere (ephemeral, generated → sent to server → discarded)

---

### 5. Domain Taxonomy (DEPRECATED)

**ACE Paper**: Bottom-up approach, domains emerge from bullets

**Status**: No longer used. Domains are emergent from:
- Bullet sections (4 categories)
- Bullet evidence (file paths, error types)
- Embeddings (similar bullets cluster)

**Where Saved**:
- ❌ Nowhere (not stored, emerges from metadata)

---

## 🔄 3-Tier Cache Strategy

```
MCP Tool Call
    ↓
┌─────────────────────┐
│ 1. Check RAM Cache  │  ← Fastest (5-10ms)
└─────────────────────┘
    ↓ (miss)
┌─────────────────────┐
│ 2. Check SQLite     │  ← Fast (20-50ms), survives restart
└─────────────────────┘
    ↓ (miss or stale)
┌─────────────────────┐
│ 3. Fetch from Server│  ← Slow (100-500ms), source of truth
└─────────────────────┘
    ↓
Update SQLite + RAM
```

---

## ✅ Implementation Checklist

### Step 1: Install Dependency
```bash
npm install better-sqlite3
npm install --save-dev @types/better-sqlite3
```

### Step 2: Create LocalCacheService
**File**: `src/services/local-cache.ts`

**Methods**:
- `initializeSchema()` - Create tables
- `getPlaybook()` - Read from SQLite
- `savePlaybook()` - Write to SQLite
- `getEmbedding()` - Check embedding cache
- `cacheEmbedding()` - Save embedding
- `needsSync()` - Check if cache stale (>5 min)
- `getSyncState()` / `setSyncState()`
- `clear()` - Wipe cache

### Step 3: Update ACEServerClient
**File**: `src/services/server-client.ts`

**Changes**:
```typescript
export class ACEServerClient {
  private localCache: LocalCacheService;
  private memoryCache?: StructuredPlaybook;

  constructor(config: ACEConfig) {
    this.localCache = new LocalCacheService(
      extractOrgId(config.apiToken),
      config.projectId
    );
  }

  async getPlaybook(forceRefresh = false): Promise<StructuredPlaybook> {
    // 1. RAM cache (fastest)
    if (!forceRefresh && this.memoryCache) {
      return this.memoryCache;
    }

    // 2. SQLite cache (if fresh)
    if (!forceRefresh && !this.localCache.needsSync()) {
      const cached = this.localCache.getPlaybook();
      if (cached) {
        this.memoryCache = cached;
        return cached;
      }
    }

    // 3. Fetch from server
    const result = await this.request('/playbook', 'GET');
    this.memoryCache = result.playbook;
    this.localCache.savePlaybook(result.playbook);
    return result.playbook;
  }

  async computeEmbeddings(texts: string[]): Promise<number[][]> {
    // Check SQLite cache first, compute only uncached
    // ... (see full implementation in CLIENT_IMPLEMENTATION_GUIDE.md)
  }
}
```

### Step 4: Invalidate Cache After Deltas
**File**: `src/services/curator.ts`

```typescript
async applyDeltaOperations(playbook, reflection) {
  // Apply operations...

  // Invalidate cache (force refresh on next call)
  this.serverClient.invalidateCache();

  return updated;
}
```

---

## 🎯 Testing

### Test 1: Cache Survives Restart
1. Start Claude Code, call `ace_status`
2. Check SQLite file created: `~/.ace-cache/{org}_{project}.db`
3. Close Claude Code
4. Reopen Claude Code, call `ace_status` again
5. Verify cache hit (no network call, <20ms)

### Test 2: Cache Staleness
1. Call `ace_status` → cache fresh
2. Wait 6 minutes
3. Call `ace_status` again
4. Verify cache refresh (network call)

### Test 3: Embedding Cache
1. Call `ace_learn` twice with same text
2. Verify embedding cache hit (no server call)

---

## 📖 Full Documentation

**Complete guide**: `docs/CLIENT_IMPLEMENTATION_GUIDE.md` (348 lines)
**Server architecture**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server/docs/STORAGE_ARCHITECTURE.md`

---

## 🔑 Multi-Tenant Authentication (CRITICAL!)

**EVERY HTTP request to server MUST include these headers**:

```typescript
headers: {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${process.env.ACE_API_TOKEN}`,  // Organization identity
  'X-ACE-Project': process.env.ACE_PROJECT_ID              // Project identity
}
```

**Without these headers, ALL requests will fail with 401 Unauthorized!**

### Environment Variables (REQUIRED)

**File**: `~/.config/claude-code/mcp-server-config.json`

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "node",
      "args": ["/path/to/ce-ai-ace-client/dist/index.js"],
      "env": {
        "ACE_SERVER_URL": "http://localhost:9000",
        "ACE_API_TOKEN": "ace_sZlqtF9-jY8M_...",
        "ACE_PROJECT_ID": "prj_6bba0d15c5a6abc1"
      }
    }
  }
}
```

### Client Implementation (src/services/server-client.ts)

```typescript
export class ACEServerClient {
  private apiToken: string;
  private projectId: string;

  constructor(config: ACEConfig) {
    this.apiToken = process.env.ACE_API_TOKEN!;
    this.projectId = process.env.ACE_PROJECT_ID!;

    // CRITICAL: Fail fast if missing
    if (!this.apiToken || !this.projectId) {
      throw new Error('ACE_API_TOKEN and ACE_PROJECT_ID are required!');
    }
  }

  private async request(endpoint: string, method: string, body?: any) {
    const response = await fetch(`${this.serverUrl}${endpoint}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiToken}`,  // ← CRITICAL
        'X-ACE-Project': this.projectId              // ← CRITICAL
      },
      body: body ? JSON.stringify(body) : undefined
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Authentication failed! Check API token and project ID.');
      }
      if (response.status === 403) {
        throw new Error('Access denied! Project does not belong to your organization.');
      }
      throw new Error(`Server error: ${response.status}`);
    }

    return response.json();
  }
}
```

**See full guide**: `docs/AUTHENTICATION_AND_MULTI_TENANCY.md`

---

## ⚠️ Critical Reminders

1. **Server = Source of Truth**: ChromaDB is canonical, SQLite is cache
2. **TTL = 5 minutes**: Cache expires, fetches fresh from server
3. **Bullets, not Patterns**: Use "bullet" terminology (ACE Paper)
4. **No Domain Taxonomy**: Deprecated, domains are emergent
5. **Privacy**: Source code never leaves client, never cached
6. **ACE Paper Quote**: *"cached locally or remotely, avoiding repetitive and expensive prefill operations"*

---

**Good luck implementing the cache layer!** 🚀

If you have questions, refer to:
- `docs/CLIENT_IMPLEMENTATION_GUIDE.md`
- `docs/SERVER_VS_CLIENT_RESPONSIBILITIES.md`
- ACE Paper: https://arxiv.org/abs/2510.04618
