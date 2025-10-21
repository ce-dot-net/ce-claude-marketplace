# ACE Client Implementation Guide (TypeScript MCP)

**Date**: 2025-10-20
**For**: Client-side Claude implementing the MCP client
**Architecture**: Client-Side Intelligence + Local SQLite Cache + Remote Server Storage

---

## 🚨 CRITICAL: What Gets Saved Where

Based on ACE Paper (arXiv:2510.04618) + Architecture Design:

### CLIENT-SIDE Storage (Your Responsibility)

**Location**: `~/.ace-cache/{org_id}_{project_id}.db` (SQLite)

**What to Save Locally**:

1. **Playbook Bullets** (cached from server)
   - Full playbook snapshot for offline work
   - Survives Claude Code/Desktop restarts
   - Syncs with server when online
   - TTL: 5 minutes (configurable)

2. **Embedding Cache** (performance optimization)
   - Content hash → embedding vector mapping
   - Avoids re-computing same text embeddings
   - Persists across sessions

3. **Sync State** (metadata)
   - Last sync timestamp
   - Server version/checksum
   - Dirty flags for offline changes

**What NOT to Save Locally**:
- ❌ Organization/Project metadata (server manages)
- ❌ API tokens (from environment variables only)
- ❌ Execution traces (send directly to server)
- ❌ Pattern discovery results (send directly to server)

---

### SERVER-SIDE Storage (Python FastAPI)

**Location**:
- ChromaDB: `~/.ace-memory/chroma/{org_id}_{project_id}`
- SQLite: `~/.ace-memory/tenants.db`

**What Server Saves** (Source of Truth):

1. **Playbook Bullets** (ChromaDB collection)
   ```python
   {
     "id": "ctx-1729500000-abc12",
     "section": "strategies_and_hard_rules",
     "content": "Always validate JWT before processing requests",
     "helpful": 8,        # Counter: incremented by client
     "harmful": 2,        # Counter: incremented by client
     "confidence": 0.80,  # Calculated: helpful / (helpful + harmful)
     "observations": 10,  # Total times bullet was used
     "evidence": ["auth.py:45", "middleware.py:12"],
     "created_at": "2025-10-20T10:30:00Z",
     "last_used": "2025-10-20T12:45:00Z"
   }
   ```

2. **Embeddings** (ChromaDB, stored with bullets)
   - Model: `all-MiniLM-L6-v2` (384 dimensions)
   - Computed on server (CPU-based)
   - Used for similarity search (0.85 threshold)

3. **Execution Traces** (ChromaDB collection `{org_id}_{project_id}_traces`)
   ```python
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
     "playbook_used": ["ctx-001", "ctx-002"],  # Bullets consulted
     "timestamp": "2025-10-20T12:45:00Z"
   }
   ```

4. **Organizations & Projects** (SQLite `tenants.db`)
   - Organizations table (org_id, api_token)
   - Projects table (project_id, org_id, collection_name)
   - Multi-tenant isolation

---

## 📊 Complete Data Model

### 1. Playbook Bullet (Core Unit)

**ACE Paper**: "Collection of structured, itemized bullets with unique identifiers and counters"

```typescript
interface PlaybookBullet {
  id: string;                    // Format: ctx-{timestamp}-{random5}
  section: BulletSection;        // Where this bullet lives
  content: string;               // The actual knowledge/strategy
  helpful: number;               // Counter: how many times helpful
  harmful: number;               // Counter: how many times harmful
  confidence: number;            // Derived: helpful / (helpful + harmful)
  observations: number;          // Total times bullet was consulted
  evidence: string[];            // File paths, error messages, line numbers
  created_at: string;            // ISO timestamp
  last_used: string;             // ISO timestamp
}

type BulletSection =
  | 'strategies_and_hard_rules'
  | 'useful_code_snippets'
  | 'troubleshooting_and_pitfalls'
  | 'apis_to_use';
```

**Where Saved**:
- ✅ **Server (ChromaDB)**: Source of truth, permanent
- ✅ **Client (SQLite)**: Cached copy, synced every 5 min
- ✅ **Client (RAM)**: In-memory for fast access during MCP session

---

### 2. Structured Playbook (Container)

**ACE Paper**: "Comprehensive playbook organized by sections" (Figure 3)

```typescript
interface StructuredPlaybook {
  strategies_and_hard_rules: PlaybookBullet[];      // Core principles
  useful_code_snippets: PlaybookBullet[];           // Reusable code
  troubleshooting_and_pitfalls: PlaybookBullet[];   // Error patterns
  apis_to_use: PlaybookBullet[];                    // Libraries/APIs
}
```

**Where Saved**:
- ✅ **Server (ChromaDB)**: All bullets in collection, queryable by section
- ✅ **Client (SQLite)**: Full playbook snapshot, indexed by section
- ✅ **Client (RAM)**: Loaded on first MCP tool call

---

### 3. Execution Trace (Learning Data)

**ACE Paper**: "Generator highlights which bullets were useful or misleading"

```typescript
interface ExecutionTrace {
  task: string;                  // What user asked for
  trajectory: TrajectoryStep[];  // Steps taken (tool calls)
  result: {
    success: boolean;
    output: string;
    error?: string;
  };
  playbook_used: string[];       // Bullet IDs consulted
  timestamp: string;
}

interface TrajectoryStep {
  step: number;
  action: string;                // Tool name (e.g., "write_file")
  args: Record<string, any>;
  result?: any;
}
```

**Where Saved**:
- ✅ **Server (ChromaDB)**: Permanent trace collection
- ❌ **Client**: NOT saved locally (send to server immediately)

---

### 4. Delta Operations (Updates)

**ACE Paper**: "Incremental delta updates... localized edits" (not monolithic rewrites)

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

  reason?: string;               // Why this operation
}
```

**Where Saved**:
- ✅ **Server**: Applied to ChromaDB bullets
- ❌ **Client**: NOT saved (generated on-the-fly, sent to server)

---

### 5. Domain Taxonomy (DEPRECATED)

**ACE Paper**: Bottom-up approach (emergent from bullets, not pre-defined)

**Status**: We no longer use explicit domain taxonomy. Domains emerge from:
- Bullet sections (4 categories)
- Bullet content (analyzed by embeddings)
- Evidence patterns (file paths, error types)

**Where Saved**:
- ❌ **Nowhere**: Not stored explicitly, emerges from bullet metadata

---

## 🏗️ Client SQLite Schema

**File**: `~/.ace-cache/{org_id}_{project_id}.db`

```sql
-- Cached playbook bullets (synced from server)
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

-- Embedding cache (avoid re-computing)
CREATE TABLE embedding_cache (
  content_hash TEXT PRIMARY KEY,        -- SHA256 of bullet content
  embedding BLOB NOT NULL,              -- Float32Array serialized
  created_at TEXT NOT NULL
);

-- Sync metadata
CREATE TABLE sync_state (
  key TEXT PRIMARY KEY,                 -- 'last_sync', 'server_version'
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Performance indexes
CREATE INDEX idx_section ON playbook_bullets(section);
CREATE INDEX idx_confidence ON playbook_bullets(confidence);
CREATE INDEX idx_helpful ON playbook_bullets(helpful DESC);
```

---

## 🔄 Client-Server Sync Flow

### Scenario 1: Fresh Start (First MCP Tool Call)

```
Client:
1. Check local SQLite cache
2. Empty → Fetch from server GET /playbook
3. Save to SQLite + RAM cache
4. Use for MCP tool execution

Server:
1. Validate auth (Bearer token + X-ACE-Project)
2. Query ChromaDB collection {org_id}_{project_id}
3. Return structured playbook
```

### Scenario 2: Subsequent Calls (Cache Hit)

```
Client:
1. Check RAM cache (instant)
2. If fresh (<5 min) → Use cached playbook
3. No network call needed

Server:
(not contacted)
```

### Scenario 3: Cache Stale (After 5+ Minutes)

```
Client:
1. Check RAM cache → expired
2. Check SQLite cache → synced_at > 5 min ago
3. Fetch from server GET /playbook
4. Update SQLite + RAM cache

Server:
1. Return latest playbook from ChromaDB
```

### Scenario 4: Offline Work

```
Client:
1. Network unavailable
2. Use SQLite cache (stale but usable)
3. Queue delta operations for later sync
4. Continue working offline

Server:
(not contacted until online)
```

### Scenario 5: Learning from Execution

```
Client:
1. User completes task in Claude Code
2. Client captures execution trace
3. Send POST /traces (store trace)
4. Analyze with ReflectorService → DeltaOperation[]
5. Send POST /delta (apply operations)
6. Invalidate local cache (force refresh next call)

Server:
1. Store trace in {org_id}_{project_id}_traces collection
2. Apply delta operations to bullets:
   - ADD: Create new bullet with embedding
   - UPDATE: Increment helpful/harmful counters, recalc confidence
   - DELETE: Remove bullet from collection
3. Return success
```

---

## 🛠️ Implementation Checklist

### Phase 1: Local SQLite Cache (Priority 1)

- [ ] Install dependency: `better-sqlite3`
- [ ] Create `src/services/local-cache.ts`
- [ ] Implement `LocalCacheService` class
  - [ ] `initializeSchema()` - Create tables
  - [ ] `getPlaybook()` - Read from SQLite
  - [ ] `savePlaybook()` - Write to SQLite
  - [ ] `getEmbedding()` - Check embedding cache
  - [ ] `cacheEmbedding()` - Save embedding
  - [ ] `needsSync()` - Check if cache is stale
  - [ ] `getSyncState()` / `setSyncState()` - Metadata
  - [ ] `clear()` - Wipe cache

### Phase 2: Update ACEServerClient (Priority 1)

- [ ] Modify `src/services/server-client.ts`
- [ ] Add `localCache: LocalCacheService` property
- [ ] Update `getPlaybook()` - 3-tier cache (RAM → SQLite → Server)
- [ ] Update `computeEmbeddings()` - Check SQLite cache first
- [ ] Add `invalidateCache()` - Clear RAM, keep SQLite
- [ ] Add `extractOrgId()` - Parse org_id from token

### Phase 3: Update Services to Invalidate Cache (Priority 2)

- [ ] Modify `src/services/curator.ts`
  - [ ] Call `serverClient.invalidateCache()` after applying deltas
- [ ] Modify `src/services/reflector.ts`
  - [ ] No changes needed (read-only)
- [ ] Modify `src/services/initialization.ts`
  - [ ] Call `serverClient.invalidateCache()` after saving patterns

### Phase 4: Add package.json Dependency (Priority 1)

```json
{
  "dependencies": {
    "better-sqlite3": "^9.2.2"
  }
}
```

### Phase 5: Update Documentation (Priority 2)

- [ ] Update `README.md` - Mention local cache
- [ ] Update `SERVER_VS_CLIENT_RESPONSIBILITIES.md` - Add SQLite cache section
- [ ] Update `WHY_CLIENT_SIDE.md` - Add caching benefits

---

## 🔐 Environment Variables (REQUIRED)

**File**: `~/.config/claude-code/mcp-server-config.json` (or Claude Desktop)

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

**Without these, client will FAIL authentication!**

---

## 📈 Performance Expectations

### Without SQLite Cache (Current):
- ❌ Every MCP call = network request
- ❌ Restart = lost cache
- ❌ New chat = lost cache
- ❌ Embedding re-computation every time
- ⏱️ Latency: 100-500ms per call

### With SQLite Cache (After Implementation):
- ✅ 90% cache hit rate (no network)
- ✅ Survives restarts
- ✅ Survives new chat windows
- ✅ Embedding cache persists
- ⏱️ Latency: 5-10ms for cache hits

**Expected Speedup**: **10-50x faster** for cached playbook access!

---

## 🎯 Key Takeaways

1. **Server = Source of Truth**: ChromaDB stores all bullets permanently
2. **Client = Local Cache**: SQLite caches playbook for performance
3. **Client = Intelligence**: Pattern discovery, reflection, curation (uses YOUR Claude)
4. **Bullets = Core Unit**: Not patterns, not memories - bullets with counters
5. **Playbook = Structured**: 4 sections, sorted by helpfulness
6. **Domains = Emergent**: No explicit taxonomy, emerges from bullet metadata
7. **Traces = Server-Stored**: Execution traces saved to server immediately
8. **Delta Ops = Ephemeral**: Generated on-the-fly, applied to server, not cached

---

## 🚀 Start Implementation

1. Read this guide completely
2. Install `better-sqlite3` dependency
3. Create `LocalCacheService` class
4. Update `ACEServerClient` to use 3-tier cache
5. Test with existing MCP tools
6. Verify cache survives restarts
7. Measure performance improvement

**Good luck!** 🎉
