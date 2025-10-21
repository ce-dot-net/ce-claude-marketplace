# ACE Client Documentation Index

**Date**: 2025-10-20
**Architecture**: TypeScript MCP Client + Python FastAPI Server

---

## 📚 Documentation Files

### 🚀 Start Here (Copy/Paste for Client Claude)

**File**: `../COPY_PASTE_FOR_CLIENT_CLAUDE.md`

**What**: Quick summary for client-side Claude implementing the MCP client
**Contains**:
- TL;DR of what to implement
- Data model summary
- SQLite cache schema
- 3-tier cache strategy
- Implementation checklist
- Authentication setup

**Use this file**: Copy/paste to client-side Claude session

---

### 📖 Complete Guides

#### 1. Client Implementation Guide

**File**: `CLIENT_IMPLEMENTATION_GUIDE.md`

**What**: Comprehensive guide for implementing client-side TypeScript MCP client
**Contains**:
- What gets saved where (client vs server)
- Complete data models (PlaybookBullet, StructuredPlaybook, etc.)
- Client SQLite schema (playbook_bullets, embedding_cache, sync_state)
- Client-server sync flow (fresh start, cache hit, stale, offline)
- Implementation checklist (5 phases)
- Performance expectations (10-50x speedup)

**Use this file**: Reference while implementing LocalCacheService and ACEServerClient

---

#### 2. Authentication and Multi-Tenancy Guide

**File**: `AUTHENTICATION_AND_MULTI_TENANCY.md`

**What**: How to implement multi-tenant authentication in the client
**Contains**:
- Required headers for EVERY request (Authorization, X-ACE-Project)
- Multi-tenant data isolation (org → project → collection)
- Authentication flow (client → server validation)
- Server tenant management API (create org, create project)
- Common client mistakes (hardcoding, missing headers)
- Testing authentication (curl examples)

**Use this file**: Implement ACEServerClient.request() method with auth headers

---

#### 3. Server vs Client Responsibilities

**File**: `SERVER_VS_CLIENT_RESPONSIBILITIES.md`

**What**: Complete breakdown of what client does vs what server does
**Contains**:
- Client responsibilities (intelligence, local cache)
- Server responsibilities (storage, embeddings, multi-tenancy)
- What client saves locally (playbook cache, embedding cache)
- What server saves permanently (ChromaDB, SQLite tenants.db)
- Authentication flow with code examples
- Pattern discovery, reflection, curation examples

**Use this file**: Understand the complete architecture before implementing

---

### 📋 Reference Documents

#### 4. READ_ME_FIRST.md

**File**: `../READ_ME_FIRST.md`

**What**: Critical warnings and common mistakes to avoid
**Contains**:
- Critical mistakes to avoid (v2 files, standalone client, GPU claims)
- What you need to implement (types, server-client, reflector, curator)
- Environment variables required
- Server endpoints that ALREADY exist
- Quick start checklist

**Use this file**: Read before starting implementation (avoid known mistakes)

---

#### 5. WHY_CLIENT_SIDE.md

**File**: `../WHY_CLIENT_SIDE.md`

**What**: Rationale for client-side intelligence architecture
**Contains**:
- 10 key reasons for client-side intelligence
- No API key needed (uses MCP Sampling)
- Privacy (code never leaves client)
- Cost efficiency (no per-request charges)
- Offline capability
- ACE Paper compliance

**Use this file**: Understand architectural decisions

---

## 🏗️ Server Documentation (Reference Only)

**Location**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server/docs/`

### Files:
- `STORAGE_ARCHITECTURE.md` - What server saves, API endpoints, data flows
- `SERVER_REFACTORED.md` - Server refactoring details
- `ACE_FULL_IMPLEMENTATION_ROADMAP.md` - Complete ACE Paper implementation plan

**Note**: Server is already fully implemented. These docs are for reference only.

---

## 🎯 Implementation Order

### Phase 1: Read Documentation (30 minutes)

1. Read `../COPY_PASTE_FOR_CLIENT_CLAUDE.md` (quick overview)
2. Read `AUTHENTICATION_AND_MULTI_TENANCY.md` (critical for ALL requests)
3. Read `CLIENT_IMPLEMENTATION_GUIDE.md` (detailed implementation steps)
4. Skim `SERVER_VS_CLIENT_RESPONSIBILITIES.md` (architecture overview)

### Phase 2: Environment Setup (10 minutes)

1. Create MCP server config with environment variables:
   ```json
   {
     "mcpServers": {
       "ace-pattern-learning": {
         "env": {
           "ACE_SERVER_URL": "http://localhost:9000",
           "ACE_API_TOKEN": "ace_xxx",
           "ACE_PROJECT_ID": "prj_xxx"
         }
       }
     }
   }
   ```

2. Start server:
   ```bash
   cd /Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server
   python3 -m ace_server --port 9000
   ```

### Phase 3: Install Dependencies (5 minutes)

```bash
npm install better-sqlite3
npm install --save-dev @types/better-sqlite3
```

### Phase 4: Implement Authentication (30 minutes)

**File**: `src/services/server-client.ts`

1. Add environment variable validation in constructor
2. Implement `request()` method with auth headers:
   - `Authorization: Bearer ${token}`
   - `X-ACE-Project: ${projectId}`
3. Add auth error handling (401, 403)

**Reference**: `AUTHENTICATION_AND_MULTI_TENANCY.md`

### Phase 5: Implement SQLite Cache (2 hours)

**File**: `src/services/local-cache.ts`

1. Create `LocalCacheService` class
2. Implement schema initialization (3 tables)
3. Implement cache methods (get/save playbook, embeddings, sync state)
4. Test cache survives restarts

**Reference**: `CLIENT_IMPLEMENTATION_GUIDE.md` sections on SQLite schema and LocalCacheService

### Phase 6: Update ACEServerClient (1 hour)

**File**: `src/services/server-client.ts`

1. Add `localCache: LocalCacheService` property
2. Update `getPlaybook()` to use 3-tier cache (RAM → SQLite → Server)
3. Update `computeEmbeddings()` to check SQLite cache first
4. Add `invalidateCache()` method

**Reference**: `CLIENT_IMPLEMENTATION_GUIDE.md` section on 3-tier cache

### Phase 7: Update Services to Invalidate Cache (30 minutes)

**Files**: `src/services/curator.ts`, `src/services/initialization.ts`

1. Call `serverClient.invalidateCache()` after applying deltas
2. Call `serverClient.invalidateCache()` after saving patterns

**Reference**: `CLIENT_IMPLEMENTATION_GUIDE.md` Phase 3

### Phase 8: Test (1 hour)

1. Test cache survives restart
2. Test cache staleness (>5 min)
3. Test embedding cache
4. Test authentication (401, 403 errors)
5. Measure performance improvement

**Reference**: `CLIENT_IMPLEMENTATION_GUIDE.md` section on Testing

---

## ⚠️ Critical Reminders

1. **Authentication**: EVERY request needs `Authorization: Bearer` + `X-ACE-Project` headers
2. **Server is Source of Truth**: ChromaDB is canonical, SQLite is cache
3. **Bullets, not Patterns**: Use ACE Paper terminology
4. **No Domain Taxonomy**: Deprecated, domains are emergent
5. **Privacy**: Source code never leaves client, never cached
6. **Cache TTL**: 5 minutes (configurable)

---

## 📖 External References

- **ACE Paper**: https://arxiv.org/abs/2510.04618
- **MCP Protocol**: https://modelcontextprotocol.io
- **Server Code**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server/`
- **Client Code**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-claude-marketplace/mcp-clients/ce-ai-ace-client/`

---

## 📊 Quick Reference

### Environment Variables
```bash
ACE_SERVER_URL=http://localhost:9000
ACE_API_TOKEN=ace_sZlqtF9-jY8M_...
ACE_PROJECT_ID=prj_6bba0d15c5a6abc1
```

### Auth Headers (EVERY request)
```typescript
headers: {
  'Authorization': `Bearer ${process.env.ACE_API_TOKEN}`,
  'X-ACE-Project': process.env.ACE_PROJECT_ID
}
```

### SQLite Cache Location
```
~/.ace-cache/{org_id}_{project_id}.db
```

### Server Endpoints
```
GET    /playbook                    - Get structured playbook
POST   /patterns                    - Save patterns
POST   /traces                      - Store execution trace
POST   /delta                       - Apply delta operation
PATCH  /patterns/{id}/counters      - Update helpful/harmful
POST   /embeddings                  - Compute embeddings
GET    /analytics                   - Statistics
```

---

**Total Implementation Time: ~5-6 hours** (including testing)

**Start with**: `../COPY_PASTE_FOR_CLIENT_CLAUDE.md`
