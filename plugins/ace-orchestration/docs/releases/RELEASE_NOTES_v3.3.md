# ACE Orchestration Plugin v3.3.0 - Release Notes

**Release Date**: October 31, 2025
**Version**: 3.3.0
**MCP Client**: @ce-dot-net/ace-client@3.6.0+
**ACE Server**: v3.1.0+ (https://ace-api.code-engine.app)

---

## 🔍 MAJOR FEATURES: Semantic Search & Delta Operations

This release brings **50-80% token reduction** through semantic pattern search and introduces complete ACE Paper Section 3.3 implementation with delta operations.

### Key Highlights

✅ **Semantic Pattern Search** - Natural language queries with 50-80% token savings
✅ **Runtime Configuration** - Adjust server settings without code changes
✅ **Manual Pattern Management** - Direct playbook manipulation via delta operations
✅ **Batch Retrieval** - 10x-50x faster bulk pattern fetching
✅ **Intelligent Tool Selection** - Skills automatically choose optimal retrieval method

---

## 🎯 What's New

### 1. Semantic Pattern Search

**Command**: `/ace-search <query>`

**What it does**:
- Searches playbook using natural language queries
- Returns only relevant patterns matching query intent
- Reduces context usage by **50-80%** vs full playbook retrieval
- Powered by ChromaDB semantic search (all-MiniLM-L6-v2 embeddings)

**Example**:
```bash
/ace-search "JWT authentication patterns"
# Returns: Top 10 patterns about JWT auth
# Tokens: ~2,500 vs ~12,000 for full section (80% savings!)
```

**Use cases**:
- Specific technology/pattern queries
- Narrow domain focus (authentication, error handling, API integration)
- When you can formulate the query as a natural language question

**MCP Tool**: `mcp__ace_search(query, threshold=0.7, top_k=10)`

---

### 2. Top Patterns Retrieval

**Command**: `/ace-top <section> [limit]`

**What it does**:
- Retrieves highest-rated patterns by helpful score
- Filters by section and minimum helpful threshold
- Perfect for "best practices" queries

**Example**:
```bash
/ace-top troubleshooting_and_pitfalls 5
# Returns: Top 5 debugging patterns by quality score
```

**Use cases**:
- Getting proven, battle-tested patterns
- Finding best practices in a specific domain
- Quality-first retrieval

**MCP Tool**: `mcp__ace_top_patterns(section, limit=10, min_helpful=0)`

---

### 3. Runtime Configuration Management

**Command**: `/ace-config [action] [params]`

**What it does**:
- View and update server configuration dynamically
- Adjust thresholds, enable token budget, configure deduplication
- Changes persist across sessions, cached for 5 minutes on client

**Examples**:
```bash
/ace-config show                        # View current settings
/ace-config token-budget 50000          # Enable auto-pruning at 50k tokens
/ace-config search-threshold 0.8        # Stricter semantic matching
/ace-config dedup-threshold 0.9         # Configure duplicate detection
```

**Use cases**:
- Dynamic threshold adjustment without code changes
- Testing different search sensitivities
- Managing playbook size with token budget

**MCP Tools**:
- `mcp__ace_get_config()` - Fetch configuration
- `mcp__ace_set_config(...)` - Update configuration

---

### 4. Manual Pattern Management (Delta Operations)

**Command**: `/ace-delta [operation] [pattern]`

**What it does**:
- Add, update, or remove patterns manually (bypasses automatic learning)
- Implements ACE Paper Section 3.3 delta operations
- Direct playbook manipulation for manual curation

**Examples**:
```bash
/ace-delta add "Always use HttpOnly cookies for auth tokens" strategies_and_hard_rules
/ace-delta update ctx-abc-123 helpful=5 harmful=0
/ace-delta remove ctx-xyz-789
```

**Use cases**:
- Quick fixes to playbook
- Manual curation of patterns
- Administrative corrections

**⚠️ Note**: Prefer automatic learning (via ACE Learning skill) over manual delta operations for 99% of cases. Use sparingly.

**MCP Tool**: `mcp__ace_delta(operation="add|update|remove", bullets=[...])`

---

### 5. Batch Retrieval

**What it does**:
- Fetch multiple patterns by ID in single request
- **10x-50x faster** than sequential retrieval
- Max 50 patterns per batch

**Example**:
```bash
# Stage 1: Search for relevant patterns
results = ace_search("authentication patterns")
pattern_ids = [p.id for p in results]

# Stage 2: Fetch full details in bulk (10x-50x faster!)
full_patterns = ace_batch_get(pattern_ids)
```

**Performance**:
- 50 patterns: 1 request (~200ms) vs 50 requests (~10 seconds)
- Perfect for follow-up queries after semantic search

**MCP Tool**: `mcp__ace_batch_get(pattern_ids=[...])`

---

## 🧠 Intelligent Tool Selection

**Updated**: `skills/ace-playbook-retrieval/SKILL.md`

The playbook retrieval skill now includes decision logic for choosing the optimal retrieval method:

### Decision Logic

**Use `ace_search`** (PREFERRED for specific queries):
- ✅ User mentions specific technology/pattern (e.g., "JWT auth", "Stripe webhooks")
- ✅ Narrow domain focus
- ✅ Want 50-80% token reduction

**Use `ace_get_playbook`** (for comprehensive needs):
- ✅ Complex multi-domain task (touches auth + database + API)
- ✅ Architectural decisions requiring broad context
- ✅ No clear narrow query to formulate

**Use `ace_batch_get`** (for follow-up retrieval):
- ✅ Have pattern IDs from previous search
- ✅ Need full details of specific patterns

**Default Strategy**: Try `ace_search` first for specific requests, fall back to `ace_get_playbook` only if query is too broad.

### Updated Examples

All 5 examples in the skill now demonstrate intelligent tool selection:
- Examples 1-3: Use `ace_search` for specific queries (JWT auth, async debugging, Stripe webhooks)
- Example 4: Uses `ace_get_playbook` for complex multi-domain task
- Example 5: Uses `ace_batch_get` for follow-up retrieval

---

## 📦 New Files

### Slash Commands
- `commands/ace-search.md` - Semantic search command with examples
- `commands/ace-top.md` - Top patterns command with usage guide
- `commands/ace-config.md` - Runtime configuration management
- `commands/ace-delta.md` - Manual pattern operations (ADD/UPDATE/REMOVE)

### Updated Skills
- `skills/ace-playbook-retrieval/SKILL.md` - **MAJOR UPDATE: Intelligent tool selection**
  - Decision logic for choosing between tools
  - Default strategy: Try ace_search first
  - 5 updated examples showing real-world scenarios
  - Advanced usage patterns (two-stage retrieval)

### Updated Templates
- `CLAUDE.md` - Slimmed down to essential instructions
  - Removed verbose MCP tool examples
  - Added semantic search commands section (v3.3.0+)
  - Brief tool list with reference to detailed docs

---

## 🚀 Performance Improvements

### Token Reduction

**Before v3.3.0**:
```bash
ace_get_playbook(section="strategies_and_hard_rules")
→ Returns ALL 50 patterns (~12,000 tokens)
```

**After v3.3.0**:
```bash
ace_search(query="authentication patterns", top_k=10)
→ Returns 10 relevant patterns (~2,500 tokens)
→ 80% reduction! 🚀
```

### Retrieval Speed

**Sequential Retrieval**:
```bash
# Fetch 50 patterns individually
for pattern_id in pattern_ids:
    fetch_pattern(pattern_id)  # ~200ms each
# Total: ~10 seconds
```

**Batch Retrieval**:
```bash
# Fetch 50 patterns in bulk
ace_batch_get(pattern_ids)  # ~200ms total
# Total: ~200ms (50x faster!)
```

---

## 📋 Dependencies

### Required

- **ACE MCP Client**: @ce-dot-net/ace-client@**3.6.0+** (published 2025-10-31)
- **ACE Server**: v3.1.0+ (already deployed at https://ace-api.code-engine.app)
- **Claude Code**: Latest version

### New Server Endpoints

- `POST /patterns/search` - Semantic search with embeddings
- `GET /patterns/top` - Top patterns by helpful score
- `POST /patterns/batch` - Bulk pattern retrieval
- `GET /api/v1/config` - Server configuration retrieval
- `PUT /api/v1/config` - Server configuration updates
- `POST /delta` - Delta operations for incremental updates

---

## 📖 Migration Guide

### Upgrading from v3.2.x

**Step 1**: Automatic MCP Update
- MCP client will auto-update to v3.6.0 on next session
- No manual intervention required

**Step 2**: New Features Available
- Try `/ace-search "your query"` for targeted retrieval
- Use `/ace-top` for best practices
- Explore `/ace-config` for runtime configuration

**Step 3**: Recommendation
- Use semantic search for specific tasks to reduce token usage
- Skills will automatically choose optimal retrieval method

### Backward Compatibility

✅ `/ace-patterns` still works (full playbook retrieval)
✅ Existing skill behavior unchanged (now uses semantic search when appropriate)
✅ All previous commands remain functional
✅ **No breaking changes**

---

## ✨ Why This Matters

### User Impact

- **80% less context** for targeted pattern retrieval
- **Faster responses** with smaller playbook fetches
- **Better accuracy** with semantic matching
- **Quality filtering** via top patterns command
- **More control** over server behavior

### Developer Impact

- Completes ACE Paper Section 3.3 implementation (delta operations)
- Enables incremental playbook updates
- Provides fine-grained control over pattern retrieval
- Supports context budget constraints
- Optimizes token usage for cost-sensitive applications

---

## 🔧 Technical Details

### MCP Tools (v3.6.0+)

All new tools are available via the ACE MCP client:

```typescript
// Semantic search
mcp__ace_search(query: string, threshold?: number, top_k?: number)

// Top patterns
mcp__ace_top_patterns(section?: string, limit?: number, min_helpful?: number)

// Batch retrieval
mcp__ace_batch_get(pattern_ids: string[])

// Configuration
mcp__ace_get_config()
mcp__ace_set_config(token_budget_enforcement?: boolean, max_playbook_tokens?: number, ...)

// Delta operations
mcp__ace_delta(operation: "add"|"update"|"remove", bullets: Bullet[])

// Cache management
mcp__ace_cache_clear(cache_type?: "ram"|"sqlite"|"all")
```

### Caching Architecture

ACE uses a 3-tier caching system:

1. **RAM Cache**: In-memory, session-scoped (instant access)
2. **SQLite Cache**: `~/.ace-cache/{org}_{project}.db`, 5-minute TTL (milliseconds)
3. **Server Fetch**: Only when cache is stale or empty (seconds)

**New in v3.6.0**: Server configuration also cached for 5 minutes.

---

## 📁 Files Changed

**Plugin Configuration**:
- `plugin.PRODUCTION.json` - Version bump to 3.3.0
- `plugin.local.json` - Version bump to 3.3.0

**Documentation**:
- `CLAUDE.md` - Slimmed down, v3.3.0 marker, semantic search section
- `README.md` - Updated with v3.3.0 features
- `CHANGELOG.md` - Comprehensive v3.3.0 release notes
- `docs/releases/RELEASE_NOTES_v3.3.md` - This file

**Skills**:
- `skills/ace-playbook-retrieval/SKILL.md` - **MAJOR UPDATE: Intelligent tool selection**

**Commands**:
- `commands/ace-search.md` - NEW semantic search command
- `commands/ace-top.md` - NEW top patterns command
- `commands/ace-config.md` - NEW runtime configuration command
- `commands/ace-delta.md` - NEW manual pattern management command

**Total**: 13 files changed, 9 new/updated files

---

## 🎉 Summary

**This is a performance and intelligence-focused release:**

- ✅ **Skills now intelligently choose tools** (ace_search preferred for specific queries)
- ✅ **Massive token savings** (50-80% reduction with semantic search)
- ✅ **Full backward compatibility** (all existing commands still work)
- ✅ **Enhanced control** (runtime config, manual pattern management)
- ✅ **Faster operations** (batch retrieval 10x-50x faster)

**v3.3.0 completes the ACE Paper implementation** with full delta operations support and introduces semantic search for optimal token efficiency.

---

## 📚 Additional Resources

- **CHANGELOG**: [CHANGELOG.md](../../CHANGELOG.md)
- **Installation Guide**: [docs/guides/INSTALL.md](../guides/INSTALL.md)
- **Configuration Guide**: [docs/guides/CONFIGURATION.md](../guides/CONFIGURATION.md)
- **Architecture**: [docs/technical/ARCHITECTURE.md](../technical/ARCHITECTURE.md)
- **GitHub Release**: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v3.3.0

---

**Questions or Issues?**
- GitHub Issues: https://github.com/ce-dot-net/ce-claude-marketplace/issues
- Documentation: https://github.com/ce-dot-net/ce-claude-marketplace/tree/main/plugins/ace-orchestration
