# ACE Client Integration Tests

Comprehensive test suite for ACE v3.0 TypeScript MCP client.

## 📋 What Gets Tested

### 1. **Server Connectivity**
- Direct HTTP connection to ACE server
- Authentication (Bearer token + X-ACE-Project header)
- Health check endpoint

### 2. **Local Cache (SQLite)**
- Cache file creation at `~/.ace-cache/{org}_{project}.db`
- 3 tables: playbook_bullets, embedding_cache, sync_state
- TTL management (5-minute freshness)
- Cache persistence across restarts

### 3. **3-Tier Cache Performance**
- RAM cache (5-10ms)
- SQLite cache (20-50ms)
- Server fetch (100-500ms)
- Speedup measurements

### 4. **Remote Server Storage**
- Save playbook to server
- Retrieve playbook from server
- Verify data persistence
- Multi-tenant isolation

### 5. **All 5 MCP Tools**
- `ace_status` - Get playbook statistics
- `ace_init` - Offline learning from codebase
- `ace_get_playbook` - Retrieve structured playbook
- `ace_learn` - Online learning from execution (conceptual test)
- `ace_clear` - Clear playbook

### 6. **Embedding Cache**
- Compute embeddings (384 dimensions)
- Cache to SQLite
- Reuse cached embeddings
- Performance comparison

### 7. **Cache Invalidation**
- Invalidate after mutations
- Force refresh from server
- Verify cache cleared

## 🚀 Running Tests

### Prerequisites

**1. Start ACE Server**
```bash
# In server repo
cd ~/repos/github_com/ce-dot-net/ce-ai-ace/server
python3 ace_server/api_server.py
# Server should be running on http://localhost:9000
```

**2. Set Environment Variables** (optional, uses defaults)
```bash
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"
```

### Run Tests

```bash
# Build and run tests
npm test

# Or run directly (faster, for development)
npm run test:integration:dev
```

## 📊 Test Output

```
████████████████████████████████████████████████████████████
🚀 ACE CLIENT INTEGRATION TEST SUITE
████████████████████████████████████████████████████████████

Configuration:
  - Server: http://localhost:9000
  - Project: prj_5bc0b560221052c1
  - Token: ace_wFIuXzQvaR5IV...
  - Cache: ~/.ace-cache/wFIuXzQv_prj_5bc0b560221052c1.db

============================================================
🧪 TEST: 1. Server Health Check
============================================================
ℹ️  Testing direct server connection...
✅ Server responding: 200 OK
ℹ️  Playbook sections: 4
✅ Test passed (123ms)

============================================================
🧪 TEST: 2. ace_status (GET playbook)
============================================================
ℹ️  Testing ace_status (playbook retrieval)...
✅ Retrieved playbook with 0 bullets
ℹ️    - Strategies: 0
ℹ️    - Snippets: 0
ℹ️    - Troubleshooting: 0
ℹ️    - APIs: 0
✅ Test passed (89ms)

... [more tests] ...

████████████████████████████████████████████████████████████
📊 TEST SUMMARY
████████████████████████████████████████████████████████████

Results: 10/10 passed, 0 failed
Total time: 3456ms

Detailed Results:
  ✅ Test 1: Server Health Check (123ms)
  ✅ Test 2: ace_status (GET playbook) (89ms)
  ✅ Test 3: Local Cache Creation (45ms)
  ✅ Test 4: Cache Hit Performance (234ms)
  ✅ Test 5: ace_init (Offline Learning) (890ms)
  ✅ Test 6: Remote Save Verification (67ms)
  ✅ Test 7: Embedding Cache (345ms)
  ✅ Test 8: Cache Invalidation (34ms)
  ✅ Test 9: ace_clear (Playbook Deletion) (56ms)
  ✅ Test 10: Full Cycle Test (1573ms)

📁 Cache File Stats:
   Path: ~/.ace-cache/wFIuXzQv_prj_5bc0b560221052c1.db
   Size: 16384 bytes
   Modified: 2025-01-20T15:30:45.123Z

✅ All tests passed!
```

## 🧪 What Each Test Does

### Test 1: Server Health Check
- Direct `curl`-like fetch to server
- Verifies authentication headers work
- Confirms server is responding

### Test 2: ace_status (GET playbook)
- Calls `serverClient.getPlaybook()`
- Tests 3-tier cache
- Counts bullets by section

### Test 3: Local Cache Creation
- Forces server fetch
- Verifies `~/.ace-cache/{org}_{project}.db` exists
- Checks file size and modification time

### Test 4: Cache Hit Performance
- Measures cold fetch (server)
- Measures RAM cache hit
- Measures SQLite cache hit
- Reports speedup (e.g., 50x faster)

### Test 5: ace_init (Offline Learning)
- Analyzes current repository
- Discovers patterns from git + local files
- Builds initial playbook
- Saves to server

### Test 6: Remote Save Verification
- Clears local cache
- Fetches from server
- Verifies bullets were saved remotely

### Test 7: Embedding Cache
- Computes embeddings for 3 texts (one duplicate)
- First call: Cold computation from server
- Second call: All cached (instant)
- Reports speedup

### Test 8: Cache Invalidation
- Gets playbook (cached)
- Calls `invalidateCache()`
- Gets playbook again (refetched)
- Verifies cache was cleared

### Test 9: ace_clear (Playbook Deletion)
- Calls `serverClient.clearPlaybook()`
- Verifies server returns empty playbook
- Confirms remote deletion worked

### Test 10: Full Cycle Test
- Clear → Init → Save → Retrieve → Verify → Clear
- End-to-end test of complete ACE workflow
- Verifies saved count matches retrieved count

## 🔍 Verifying Local Storage

**Check cache file manually:**
```bash
# Find cache file
ls -lh ~/.ace-cache/

# View SQLite schema
sqlite3 ~/.ace-cache/wFIuXzQv_prj_5bc0b560221052c1.db ".schema"

# Count cached bullets
sqlite3 ~/.ace-cache/wFIuXzQv_prj_5bc0b560221052c1.db \
  "SELECT COUNT(*) FROM playbook_bullets;"

# View sync state
sqlite3 ~/.ace-cache/wFIuXzQv_prj_5bc0b560221052c1.db \
  "SELECT * FROM sync_state;"
```

## 🐛 Troubleshooting

### Server Not Responding
```
❌ Test failed: Server error (ERR_FETCH_FAILED)
```
**Fix:** Ensure ACE server is running on port 9000:
```bash
curl http://localhost:9000/health
```

### Authentication Failed
```
❌ Test failed: Server error (401)
```
**Fix:** Check API token and project ID:
```bash
echo $ACE_API_TOKEN
echo $ACE_PROJECT_ID
```

### Cache File Not Created
```
❌ Test failed: Cache file not created at ~/.ace-cache/...
```
**Fix:** Check permissions:
```bash
mkdir -p ~/.ace-cache
chmod 755 ~/.ace-cache
```

### Import Errors
```
Error: Cannot find module '../src/services/server-client.js'
```
**Fix:** Build the project first:
```bash
npm run build
```

## 📚 Related Documentation

- `../INTEGRATION_READY.md` - Integration status
- `../IMPLEMENTATION_COMPLETE.md` - Implementation details
- `../docs/CLIENT_IMPLEMENTATION_GUIDE.md` - Architecture guide
- `../docs/AUTHENTICATION_AND_MULTI_TENANCY.md` - Auth details
