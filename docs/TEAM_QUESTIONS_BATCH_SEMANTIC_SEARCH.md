# ACE Plugin - Batch & Semantic Search Optimization
## Multi-Team Questions Document

**Context**: Investigating whether batch endpoints (`ace_batch_get`) and semantic search (`ace_search`) are being used optimally across the ACE system to achieve 50-80% token reduction.

**Date**: 2025-11-02
**Plugin Version**: v3.3.6
**MCP Client Version**: v3.7.3

---

## Team 1: Claude Code CLI Plugin Team (Us)

**Responsibility**: Plugin structure, skills, commands, hooks, documentation

### Q1.1: What retrieval methods does our plugin expose to users?

**Answer**: We expose 3 methods via slash commands:

1. **`/ace-search <query>`** (commands/ace-search.md)
   - Uses: `mcp__plugin_ace-orchestration_ace-pattern-learning__ace_search`
   - Purpose: Semantic search with natural language queries
   - Parameters: query, section (optional), top_k (default: 10), threshold (default: 0.7)
   - Claims: 50-80% token reduction vs full playbook

2. **`/ace-patterns [section]`** (commands/ace-patterns.md)
   - Uses: `mcp__plugin_ace-orchestration_ace-pattern-learning__ace_get_playbook`
   - Purpose: Full playbook or section retrieval
   - Parameters: section (optional), min_helpful (optional)

3. **`/ace-top [section] [limit]`** (commands/ace-top.md)
   - Uses: `mcp__plugin_ace-orchestration_ace-pattern-learning__ace_top_patterns`
   - Purpose: Highest-rated patterns by helpful score
   - Parameters: section (optional), limit (default: 10), min_helpful (optional)

**Note**: No explicit `/ace-batch-get` command - batch retrieval is documented only in skills.

---

### Q1.2: Do our skills implement intelligent retrieval strategy selection?

**Answer**: YES, documented in `skills/ace-playbook-retrieval/SKILL.md`

**Decision Logic** (lines 39-77):
```markdown
Default Strategy: Try ace_search first for specific requests,
fall back to ace_get_playbook only if query is too broad.
```

**When to use `ace_search`** (PREFERRED):
- ✅ User mentions specific technology (JWT, Stripe, React)
- ✅ Narrow domain focus (auth, error handling, API integration)
- ✅ Can formulate natural language query
- ✅ Want 50-80% token reduction

**When to use `ace_get_playbook`**:
- ✅ Complex multi-domain task
- ✅ Architectural decisions requiring broad context
- ✅ No clear narrow query to formulate

**When to use `ace_batch_get`** (lines 66-75):
- ✅ Have pattern IDs from previous search results
- ✅ Need full details of specific patterns
- ✅ Following up on references
- ✅ Claims: 10x-50x faster than sequential fetches

---

### Q1.3: Is the skill's decision logic enforced or just recommended?

**Answer**: **RECOMMENDED ONLY** - not enforced

**Evidence**:
- Line 77: "Default Strategy: **Try** `ace_search` first" (suggestion language)
- No mandatory checks or validation
- Claude (the model) decides whether to follow the guidance
- No tracking of which method was actually used

**Risk**: Claude may default to familiar `ace_get_playbook()` and miss token savings.

---

### Q1.4: Do our skills actually use `ace_batch_get`?

**Answer**: **DOCUMENTED BUT NO EXAMPLES IN ACTUAL SKILL FLOW**

**Evidence**:
- Skill describes `ace_batch_get` (lines 66-75)
- Example 5 shows search → batch workflow (lines 210-224)
- BUT: No step-by-step instruction like "After ace_search, extract IDs and call ace_batch_get"
- Workflow is: `ace_search` returns results → Claude uses them directly

**Question for implementation**: Does `ace_search` return:
- (A) Full pattern details (no need for batch fetch)?
- (B) Abbreviated results requiring `ace_batch_get` for full details?

**This needs Server Team answer** (see Q2.6 below)

---

### Q1.5: What token savings are claimed in plugin documentation?

**Answer**: Claims documented but not measured empirically

**Token Savings Claims**:

1. **ace-search.md** (lines 88-97):
   ```
   Before (full playbook): 10,000-15,000 tokens
   After (semantic search): 2,000-3,000 tokens
   Token reduction: 80%
   ```

2. **skills/ace-playbook-retrieval/SKILL.md**:
   - Line 52: "Want 50-80% token reduction"
   - Example 1 (line 156): "80% token reduction vs full playbook!"

**Issue**: These are estimates, not measured from actual usage.

---

### Q1.6: Do we track which retrieval method is used?

**Answer**: **NO** - no usage tracking implemented

**Current Tracking**:
- `hooks/hooks.json` logs Bash tool executions to `~/.ace/execution_log.jsonl`
- Does NOT log MCP tool calls (ace_search, ace_get_playbook, ace_batch_get)
- No analytics on which method is used or token savings achieved

**What we'd need**:
- MCP client to log tool calls (ace_search vs ace_get_playbook vs ace_batch_get)
- Response size tracking (tokens retrieved)
- Cache hit/miss tracking
- Query patterns analysis

**This requires MCP Client Team implementation** (see Q3.4 below)

---

### Q1.7: Should we make semantic search more prominent in skill instructions?

**Answer**: **POSSIBLY** - depends on Server Team answers

**Current State**:
- Skill YAML description (line 3): "Retrieves learned patterns from ACE playbook BEFORE starting work"
- Does NOT mention semantic search or token savings
- Instructions are buried in Step 1 (lines 39-77)

**Potential Improvements** (IF semantic search quality is high):
1. Update YAML description: "ALWAYS try semantic search (ace_search) first for token efficiency"
2. Make it a MANDATORY step, not optional
3. Add token savings to YAML description
4. Show examples directly in description

**Blockers**: Need Server Team to confirm:
- Semantic search quality is production-ready
- Token savings are real (not just estimates)
- Coverage is complete (all patterns indexed)

---

### Q1.8: Can we add per-project API token support for multi-org users?

**Answer**: **NOT YET** - identified in this session as a future feature

**Current State**:
- Only ONE global API token: `~/.config/ace/config.json`
- Project config only has `ACE_PROJECT_ID`: `.claude/settings.json`
- Multi-org users must manually switch global config

**Proposed Solution** (Option 1 from earlier analysis):
```json
// .claude/settings.json
{
  "env": {
    "ACE_PROJECT_ID": "prj_d3a244129d62c198",
    "ACE_API_TOKEN": "ace_xxxxx"  // NEW - project override
  }
}
```

**Requires**:
- MCP Client v3.7.4 update: Check `ACE_API_TOKEN` env var before global config
- Plugin docs update: Document multi-org setup
- ace-configure command: Add `--project-token` flag

**This requires MCP Client Team implementation** (see Q3.7 below)

---

### Q1.9: Plugin Team Summary - What We Control

**What we CAN do**:
- ✅ Update skill instructions (emphasize semantic search)
- ✅ Add examples and guidance
- ✅ Create new slash commands
- ✅ Update documentation (README, CLAUDE.md)
- ✅ Add hooks for local tracking (if MCP client provides data)

**What we CANNOT do**:
- ❌ Enforce which MCP tool Claude calls (model decides)
- ❌ Implement MCP tool tracking (requires MCP client)
- ❌ Change semantic search quality (requires server)
- ❌ Modify caching behavior (requires MCP client)
- ❌ Implement batch retrieval logic (requires MCP client + server)

**Recommendation**: Focus on improving skill instructions AFTER getting Server Team answers about semantic search quality.

---

## Team 2: ACE Server Team

**Responsibility**: Server endpoints, semantic search, embeddings, pattern storage, ChromaDB

### Q2.1: What retrieval endpoints does the ACE server provide?

**Context**: We need to understand the full API surface to optimize plugin behavior.

**Request**: Please document all playbook retrieval endpoints with:
- Endpoint path (e.g., `GET /api/projects/{projectId}/playbook`)
- HTTP method
- Request parameters (required vs optional)
- Response format
- Response size (typical token count)

**Expected endpoints** (based on MCP tool names):
1. Full playbook retrieval
2. Semantic search
3. Batch retrieval by pattern IDs
4. Top patterns by helpful score

**Follow-up**: Are there any other retrieval endpoints we're not using?

---

### Q2.2: Is semantic search production-ready?

**Context**: Plugin skill recommends `ace_search` as the primary method, claiming 50-80% token reduction. Before we make it mandatory, we need to confirm quality.

**Questions**:
- What's the current quality/accuracy of semantic search?
- Are all patterns indexed with embeddings?
- What embedding model is used? (e.g., text-embedding-ada-002, text-embedding-3-small)
- What's the embedding dimension?
- Does search cover all 4 sections equally? (strategies, snippets, troubleshooting, APIs)
- What threshold should we recommend as default? (currently 0.7)
- Are there edge cases where semantic search fails?

**Why this matters**: If search quality is excellent, we should make it the default. If it's experimental, we keep full playbook as fallback.

---

### Q2.3: What are the actual token savings from semantic search?

**Context**: Plugin docs claim "50-80% token reduction" but these are estimates, not measured.

**Request**: Please provide real measurements:

**Scenario 1**: User request: "Implement JWT authentication"
```
ace_get_playbook():
  - Total patterns returned: 17
  - Response size: ~12,000 tokens
  - Relevant patterns: 3 out of 17
  - Relevance ratio: 18%

ace_search(query="JWT authentication", threshold=0.7, top_k=10):
  - Patterns returned: 3
  - Response size: ~2,000 tokens
  - Token savings: 83% reduction
  - Relevance: High (semantic match)
```

**Scenario 2**: User request: "Fix intermittent async test failures"
```
ace_get_playbook():
  - Total patterns: 17
  - Response size: ~12,000 tokens
  - Relevant patterns: 2

ace_search(query="async test failures intermittent"):
  - Patterns returned: 2
  - Response size: ~1,500 tokens
  - Token savings: 88% reduction
```

**Request**: Can you provide 5-10 real-world examples with measurements?

**Follow-up**: Can the server include token estimates in response metadata?
```json
{
  "patterns": [...],
  "metadata": {
    "tokens_in_response": 2000,
    "tokens_saved_vs_full_playbook": 10000,
    "efficiency_gain": "83%"
  }
}
```

---

### Q2.4: How does `ace_search` response format work?

**Context**: We need to know if search returns full patterns or abbreviated results.

**Question**: Does `ace_search` return:

**Option A**: Full pattern details (no further fetch needed)
```json
{
  "patterns": [
    {
      "id": "ctx-001",
      "content": "Full pattern description with all context...",
      "helpful": 8,
      "harmful": 0,
      "confidence": 0.92,
      "section": "strategies_and_hard_rules",
      "similarity": 0.87,
      "evidence": "Full evidence text...",
      "observations": "Full observations...",
      "created_at": "2025-10-15T10:30:00Z"
    }
  ]
}
```

**Option B**: Abbreviated results requiring `ace_batch_get` for full details
```json
{
  "patterns": [
    {
      "id": "ctx-001",
      "content_preview": "Refresh token rotation prevents...",  // First 100 chars
      "helpful": 8,
      "harmful": 0,
      "confidence": 0.92,
      "section": "strategies_and_hard_rules",
      "similarity": 0.87
    }
  ]
}
```

**Why this matters**: If Option B, we need to update skill to include `ace_batch_get` step. If Option A, batch retrieval is only for follow-up queries.

---

### Q2.5: What's the performance benefit of `ace_batch_get`?

**Context**: Plugin docs claim "10x-50x faster than sequential fetches" but this is not measured.

**Request**: Please provide performance benchmarks:

**Scenario**: Fetch 5 patterns by ID

**Sequential (5 individual calls)**:
```
GET /api/projects/{id}/patterns/ctx-001  → 150ms
GET /api/projects/{id}/patterns/ctx-002  → 150ms
GET /api/projects/{id}/patterns/ctx-003  → 150ms
GET /api/projects/{id}/patterns/ctx-004  → 150ms
GET /api/projects/{id}/patterns/ctx-005  → 150ms
---
Total: 750ms
HTTP overhead: 5 round-trips
```

**Batch (1 call with 5 IDs)**:
```
POST /api/projects/{id}/patterns/batch
Body: {"pattern_ids": ["ctx-001", "ctx-002", "ctx-003", "ctx-004", "ctx-005"]}
---
Total: ~200ms (estimate?)
HTTP overhead: 1 round-trip
Performance gain: 3.75x faster (estimate?)
```

**Questions**:
- What's the real latency for batch retrieval?
- Is there a limit on batch size? (e.g., max 50 patterns per request)
- What's the server-side optimization? (single DB query vs 5 queries?)

---

### Q2.6: Is the intended workflow `ace_search` → `ace_batch_get`?

**Context**: Plugin skill documents this as "Two-Stage Retrieval" but we're not sure if it's actually implemented or recommended.

**Workflow**:
```
Step 1: ace_search(query="JWT authentication", threshold=0.7)
  Response: [
    {id: "ctx-001", content_preview: "Refresh token rotation...", score: 0.89},
    {id: "ctx-002", content_preview: "Short-lived access tokens...", score: 0.85},
    {id: "ctx-003", content_preview: "HttpOnly cookies...", score: 0.78}
  ]

Step 2: ace_batch_get(pattern_ids=["ctx-001", "ctx-002", "ctx-003"])
  Response: [Full pattern details with evidence, observations, timestamps]
```

**Questions**:
- Is this the intended workflow?
- Does `ace_search` return abbreviated results that require batch fetch?
- Or does `ace_search` return full details already?
- When should we recommend `ace_batch_get` vs just using `ace_search` results directly?

---

### Q2.7: How do search results interact with the 3-tier caching system?

**Context**: MCP client implements RAM → SQLite → Server caching with 5-minute TTL.

**Questions**:
- Are search results cached separately from full playbook?
- Cache key structure: `{org}_{project}_search_{query_hash}`?
- If user searches "JWT auth" twice in 5 minutes, is it instant (cached)?
- Does searching populate the full playbook cache?
- What's the cache invalidation strategy for searches?
- Do different thresholds create different cache entries?

**Why this matters**: If searches are cached independently, repeated similar queries get instant responses. If not, we might want to guide users toward batch retrieval instead of multiple searches.

---

### Q2.8: Does the server track which endpoints are being used?

**Context**: We want to know if semantic search is being underutilized.

**Request**: Do you have analytics on:
- Tool usage distribution:
  - ace_search: X% of calls
  - ace_get_playbook: Y% of calls
  - ace_batch_get: Z% of calls
- Search query patterns (what are users searching for?)
- Token efficiency metrics (avg tokens saved per search)
- Cache hit rates per tool
- Search quality metrics (patterns clicked/used after search)

**Why this matters**: Server-side analytics would show if semantic search is underutilized and help us optimize plugin skill behavior.

---

### Q2.9: Should we deprecate full playbook retrieval in favor of semantic search?

**Context**: If semantic search quality is excellent, we could guide users more strongly.

**Proposal**: "Semantic-First Mode"
- Make `ace_search` the primary interface
- `ace_get_playbook` returns deprecation warning or encourages semantic search
- Forces users to formulate specific queries (better for learning)

**Trade-offs**:
- ✅ Encourages token-efficient behavior
- ✅ Improves query formulation skills
- ✅ Reduces server load (smaller responses)
- ❌ Requires excellent semantic search quality
- ❌ May frustrate users with broad queries
- ❌ Breaking change for existing workflows

**Question**: Is semantic search quality good enough for this? What's your recommendation?

---

### Q2.10: Can you provide semantic search test cases?

**Context**: We want to test and document semantic search behavior.

**Request**: Please provide 10 test cases with:
- Query string
- Expected top 3 pattern IDs
- Similarity scores
- Why these patterns matched

**Example**:
```
Query: "JWT authentication with refresh tokens"
Expected results:
  1. ctx-045 (similarity: 0.92) - "Refresh token rotation prevents theft attacks"
  2. ctx-023 (similarity: 0.87) - "Short-lived access tokens balance security and UX"
  3. ctx-067 (similarity: 0.81) - "HttpOnly cookies for refresh tokens prevent XSS"
```

**Why this matters**: We can use these to create better examples in plugin documentation and skill instructions.

---

### Q2.11: Server Team Summary - What We Need

**Critical Information**:
1. ✅ Semantic search quality confirmation (production-ready?)
2. ✅ Real token savings measurements (50-80% claim validated?)
3. ✅ `ace_search` response format (full details or abbreviated?)
4. ✅ Batch retrieval performance (10x-50x claim validated?)

**Nice to Have**:
1. 📊 Usage analytics (which endpoints are used most?)
2. 📈 Cache behavior for searches
3. 🧪 Test cases for semantic search
4. 💡 Recommendation on semantic-first vs full playbook

**Timeline**: We'll update plugin skills and documentation based on your answers.

---

## Team 3: MCP Client Team

**Responsibility**: MCP client (`@ce-dot-net/ace-client`), caching, config discovery, HTTP requests to server

### Q3.1: What MCP tools does the client currently expose?

**Context**: We need to confirm the client implements all the tools the plugin expects.

**Expected Tools** (based on plugin skill documentation):
1. `ace_get_playbook` - Full playbook retrieval
2. `ace_search` - Semantic search
3. `ace_batch_get` - Batch retrieval by pattern IDs
4. `ace_top_patterns` - Top patterns by helpful score
5. `ace_learn` - Capture learning feedback
6. `ace_status` - Playbook statistics
7. `ace_clear` - Clear playbook
8. `ace_bootstrap` - Bootstrap from git/docs/code
9. `ace_delta` - Manual pattern management
10. `ace_get_config` / `ace_set_config` - Server configuration
11. `ace_cache_clear` - Clear local caches

**Question**: Are all of these implemented in MCP client v3.7.3?

---

### Q3.2: How does the 3-tier caching system work?

**Context**: Plugin docs say "3-tier caching (RAM → SQLite → Server) for optimal performance".

**Questions**:
- How is RAM cache implemented? (in-memory dictionary during MCP session?)
- How is SQLite cache structured? (`~/.ace-cache/{org}_{project}.db`)
  - Schema? (cache_key, value, timestamp, ttl?)
  - Cache key format for each tool?
- What's the TTL? (5 minutes mentioned in docs)
- When is cache invalidated?
- Does `ace_search` use the same cache as `ace_get_playbook` or separate?
- Are there separate caches for different search queries?

**Cache Key Examples**:
```
ace_get_playbook():
  Key: "{org}_{project}_playbook_full"

ace_get_playbook(section="strategies"):
  Key: "{org}_{project}_playbook_strategies"

ace_search(query="JWT auth", threshold=0.7):
  Key: "{org}_{project}_search_{hash(query)}_0.7"

ace_batch_get(["ctx-001", "ctx-002"]):
  Key: "{org}_{project}_batch_{hash(ids)}"
```

**Why this matters**: Understanding cache behavior helps us guide users toward cache-efficient patterns.

---

### Q3.3: What's the performance of each cache tier?

**Context**: Plugin docs claim "RAM is instant, SQLite is milliseconds, Server is seconds".

**Request**: Please provide benchmarks:

**Scenario**: Retrieve playbook with 17 patterns (~12k tokens)

```
RAM Cache Hit:
  - Latency: <1ms (instant)
  - Source: In-memory dictionary

SQLite Cache Hit:
  - Latency: ~10-50ms (estimate?)
  - Source: ~/.ace-cache/{org}_{project}.db
  - Overhead: Disk read + deserialization

Server Fetch (cache miss):
  - Latency: ~200-500ms (estimate?)
  - Source: HTTP request to ace-api.code-engine.app
  - Overhead: Network round-trip + server processing
```

**Questions**:
- What are the real latency numbers?
- How often do we hit each tier? (cache hit rate)
- Is SQLite cache shared across MCP sessions?

---

### Q3.4: Can we add MCP tool usage tracking?

**Context**: Plugin team wants to track which retrieval methods are used to measure optimization effectiveness.

**Proposal**: Log MCP tool calls to `~/.ace/mcp-usage-analytics.jsonl`

**Example entries**:
```jsonl
{"timestamp":"2025-11-02T22:00:00Z","tool":"ace_search","query":"JWT auth","threshold":0.7,"results":3,"tokens_estimate":2000,"cache":"miss"}
{"timestamp":"2025-11-02T22:05:00Z","tool":"ace_get_playbook","section":"all","tokens":12000,"cache":"hit:ram"}
{"timestamp":"2025-11-02T22:10:00Z","tool":"ace_batch_get","pattern_ids":["ctx-001","ctx-002"],"count":2,"cache":"hit:sqlite"}
```

**Questions**:
- Can this be implemented in MCP client?
- Should it be opt-in or always-on?
- Should it send anonymous analytics to server?
- What fields should we track?

**Why this matters**:
- Measures if semantic search is actually being used
- Quantifies token savings
- Helps identify optimization opportunities

---

### Q3.5: How does `ace_batch_get` work internally?

**Context**: Plugin claims "10x-50x faster than sequential fetches".

**Questions**:
- Does MCP client make a single HTTP request to server with all IDs?
- Or does it make parallel HTTP requests?
- Is there client-side batching logic? (collect IDs, batch, debounce?)
- What's the maximum batch size?
- How are errors handled? (if 1 out of 5 IDs fails, return partial results?)

**Example flows**:

**Option A**: Client makes single HTTP request
```
Claude calls: ace_batch_get(["ctx-001", "ctx-002", "ctx-003"])
  ↓
MCP Client: POST /api/projects/{id}/patterns/batch
            Body: {"pattern_ids": ["ctx-001", "ctx-002", "ctx-003"]}
  ↓
Server: Single DB query, returns all patterns
  ↓
MCP Client: Returns to Claude
```

**Option B**: Client makes parallel HTTP requests
```
Claude calls: ace_batch_get(["ctx-001", "ctx-002", "ctx-003"])
  ↓
MCP Client: 3 parallel requests:
            GET /patterns/ctx-001
            GET /patterns/ctx-002
            GET /patterns/ctx-003
  ↓
Server: 3 separate queries
  ↓
MCP Client: Aggregates responses, returns to Claude
```

**Which is it?** This affects our recommendations in plugin skills.

---

### Q3.6: What happens when semantic search returns pattern IDs?

**Context**: Plugin skill documents "Two-Stage Retrieval" (search → batch fetch), but we're not sure if it's necessary.

**Questions**:
- Does `ace_search` return full pattern details already?
- Or does it return IDs that require `ace_batch_get` for full details?
- Does MCP client automatically fetch full details after search?
- Or does Claude need to explicitly call `ace_batch_get`?

**Example**:

**Scenario A**: `ace_search` returns full details (no batch needed)
```
Claude: ace_search("JWT auth")
MCP Client → Server: POST /search
Server response: [Full pattern objects with all fields]
MCP Client → Claude: [Full patterns ready to use]
```

**Scenario B**: `ace_search` returns IDs (batch fetch required)
```
Claude: ace_search("JWT auth")
MCP Client → Server: POST /search
Server response: [Pattern IDs + previews]
MCP Client → Claude: [IDs only]

Claude: ace_batch_get(["ctx-001", "ctx-002"])
MCP Client → Server: POST /batch
Server response: [Full pattern objects]
MCP Client → Claude: [Full patterns]
```

**Which scenario is correct?** This determines how we instruct Claude in the skill.

---

### Q3.7: Can we support per-project API tokens for multi-org users?

**Context**: Identified in this session - users in multiple organizations need different tokens per project.

**Current Architecture**:
```
Global config (~/.config/ace/config.json):
  - serverUrl
  - apiToken (ONE token for all projects)
  - cacheTtlMinutes

Project config (.claude/settings.json):
  - ACE_PROJECT_ID (via environment variable)
```

**Proposed Architecture** (requires MCP client v3.7.4):
```
Global config (~/.config/ace/config.json):
  - serverUrl
  - apiToken (default/fallback token)
  - cacheTtlMinutes

Project config (.claude/settings.json):
  - ACE_PROJECT_ID
  - ACE_API_TOKEN (NEW - project override)
```

**MCP Client Change Required**:
```javascript
// Precedence order:
const apiToken =
  process.env.ACE_API_TOKEN ||           // 1. Project override
  config.apiToken ||                     // 2. Global config
  throwError("No API token configured");
```

**Questions**:
- Can this be implemented in MCP client v3.7.4?
- Should we support multiple profiles in global config instead?
- What's the recommended approach for multi-org support?

**Why this matters**: User encountered this today - had to manually switch global config between organizations.

---

### Q3.8: What config auto-discovery paths does the client check?

**Context**: v3.3.6 removed `--config` parameter to work around Claude Code variable expansion bug.

**Current Documented Behavior** (v3.7.3):
```javascript
// Auto-discovery order:
1. ACE_CONFIG_PATH environment variable (highest priority)
2. ~/.config/ace/config.json (XDG standard)
3. ~/.ace/config.json (legacy v3.3.2 compatibility)
```

**Questions**:
- Is this implemented in v3.7.3?
- What happens if none of these exist? (clear error message?)
- Does the client log which config path it found?
- Can users verify which config is being used?

---

### Q3.9: How does the client handle errors from the server?

**Context**: We encountered 403 errors during multi-org token troubleshooting.

**Questions**:
- What error handling exists for common cases?
  - 401 Unauthorized (wrong API token)
  - 403 Forbidden (project doesn't belong to org)
  - 404 Not Found (project doesn't exist)
  - 500 Server Error
- Does the client provide helpful error messages?
- Are errors logged to console/file?
- Can we add better diagnostics for troubleshooting?

**Example of good error message**:
```
Error: Project 'prj_xxx' does not belong to organization 'org_yyy'

Possible causes:
1. Wrong API token (token is for different org)
2. Wrong project ID (project doesn't exist or belongs to different org)

To fix:
- Check your API token: ~/.config/ace/config.json
- Check your project ID: .claude/settings.json
- Run: /ace-orchestration:ace-configure to reconfigure

Debug info:
- Server: https://ace-api.code-engine.app
- Org from token: org_yyy
- Project requested: prj_xxx
```

---

### Q3.10: Can the client provide token usage estimates?

**Context**: We claim "50-80% token reduction" but can't measure it.

**Proposal**: Add token estimates to MCP tool responses

**Example**:
```json
{
  "patterns": [...],
  "metadata": {
    "tool": "ace_search",
    "query": "JWT authentication",
    "results_count": 3,
    "tokens_in_response": 2000,
    "tokens_saved_vs_full_playbook": 10000,
    "efficiency_gain": "83%",
    "cache_tier": "sqlite"
  }
}
```

**Questions**:
- Can the client calculate token estimates? (simple character count × 0.75?)
- Should this come from server or client?
- Should it be included in every response or only when requested?

**Why this matters**: Allows us to validate plugin claims and educate users on token efficiency.

---

### Q3.11: MCP Client Team Summary - What We Need

**Critical Features**:
1. ✅ Confirm all MCP tools are implemented (ace_search, ace_batch_get, etc.)
2. ✅ Document cache behavior (keys, TTL, invalidation)
3. ✅ Clarify batch retrieval implementation (single request vs parallel)
4. ✅ Explain search → batch workflow (is batch fetch needed?)

**Enhancement Requests**:
1. 📊 Add usage tracking (which tools are called, token savings)
2. 🔧 Support per-project API tokens (multi-org use case)
3. 💡 Provide token usage estimates in responses
4. 🐛 Improve error messages for troubleshooting

**Timeline**: We'll update plugin skills based on your architecture explanations.

---

## Next Steps

### For Plugin Team (Us):
1. **Wait for Server Team answers** about semantic search quality
2. **Wait for MCP Client Team answers** about caching and batch behavior
3. **Update skill instructions** based on answers:
   - Make semantic search more prominent if quality is high
   - Add two-stage retrieval (search → batch) if needed
   - Update token savings claims with real measurements
4. **Add usage tracking** to plugin hooks (if MCP client provides data)
5. **Document multi-org setup** once per-project tokens are supported

### For Server Team:
- Please answer Q2.1 through Q2.11
- Priority: Q2.2 (semantic search quality), Q2.3 (token savings), Q2.4 (response format)

### For MCP Client Team:
- Please answer Q3.1 through Q3.11
- Priority: Q3.1 (tool availability), Q3.2 (cache behavior), Q3.6 (search → batch workflow)

---

## Document Metadata

**Created**: 2025-11-02
**Created By**: Claude Code CLI Plugin Team
**Purpose**: Optimize batch & semantic search usage across ACE system
**Expected Impact**: 50-80% token reduction if semantic search is used optimally

**Contact**:
- Plugin Team: (we're here!)
- Server Team: (your contact)
- MCP Client Team: (your contact)
