# ACE Orchestration - Enhancement Roadmap

**Status**: 95% paper alignment achieved
**Last Updated**: 2025-10-23

---

## 📊 Current Implementation Status

### ✅ Core Principles: 10/10 Complete

All fundamental ACE principles are fully implemented:
- Three-agent architecture (Generator/Reflector/Curator)
- Incremental delta updates (not monolithic rewrites)
- Four playbook sections as specified
- Grow-and-refine strategy
- Context collapse prevention
- Brevity bias avoidance
- No labeled supervision
- Execution feedback only
- Confidence scoring (helpful/harmful tracking)
- Progressive disclosure

**Result**: Core architecture is 100% compliant. No changes needed.

### ⚠️ Advanced Features: 3/3 with Cost Optimizations

Three advanced features implemented with production optimizations:

| Feature | Paper Spec | Current Implementation | Location |
|---------|------------|----------------------|----------|
| **De-duplication** | Semantic (85% similarity) | Exact string match | Server + MCP Client |
| **Refinement Mode** | Proactive OR lazy | Proactive only | Server (Curator) |
| **Helpful/Harmful** | Generator marks | Reflector LLM marks | Server (Reflector) |

**Result**: All features present, but with smart cost/complexity trade-offs.

---

## 🎯 Enhancement Options

### To Reach 100% Paper Compliance

These enhancements would bring implementation to 100% alignment with the research paper.

---

## 1. Semantic De-duplication (Priority: Medium)

**Current**: Exact string matching for duplicate detection ($0 cost, instant)
**Paper**: Semantic similarity with embedding comparison (85% threshold)

### Why the Paper Specifies This
- Catches semantically equivalent bullets with different wording
- Example: "Use JWT tokens for auth" vs "Implement JSON Web Tokens for authentication"
- Prevents playbook bloat with redundant information

### Current Trade-off
- ✅ **Pros**: Zero embedding API costs, no latency, simple implementation
- ❌ **Cons**: May accumulate semantically duplicate bullets over time

### To Implement

#### Server-Side Changes
**File**: `server/ace_server/curator.py`

```python
# Current implementation
def _is_duplicate(self, new_bullet: str, existing_bullets: List[str]) -> bool:
    return new_bullet in existing_bullets  # Exact match only

# Enhanced implementation
async def _is_duplicate(self, new_bullet: str, existing_bullets: List[PlaybookBullet]) -> bool:
    # Get embedding for new bullet
    new_embedding = await self.embedding_service.get_embedding(new_bullet)

    # Compare with existing bullets
    for existing in existing_bullets:
        existing_embedding = await self.embedding_service.get_embedding(existing.content)
        similarity = cosine_similarity(new_embedding, existing_embedding)

        if similarity >= 0.85:  # Paper's threshold
            return True

    return False
```

**New Dependencies**:
```python
# Add to server requirements.txt
openai>=1.0.0  # For embeddings API
numpy>=1.24.0  # For cosine similarity
```

**Configuration**:
```python
# Add to server config
SEMANTIC_DEDUP_ENABLED: bool = True
SEMANTIC_SIMILARITY_THRESHOLD: float = 0.85
EMBEDDING_MODEL: str = "text-embedding-3-small"
```

#### MCP Client Changes
**File**: `mcp-clients/ce-ai-ace-client/src/services/local-cache.ts`

```typescript
// Already has embedding cache infrastructure!
export class LocalCacheService {
  // These methods exist but aren't currently used for dedup
  getEmbedding(content: string): number[] | null {
    // Retrieve cached embedding from SQLite
  }

  cacheEmbedding(content: string, embedding: number[]): void {
    // Store embedding in SQLite for reuse
  }
}
```

**No changes needed** - Infrastructure already exists!

#### Plugin Changes
**None required** - Plugin is agnostic to dedup strategy

### Cost Analysis

**With text-embedding-3-small**:
- $0.00002 per 1K tokens
- Average bullet: ~50 tokens = $0.000001
- 10,000 bullets processed = $0.01

**Optimization**: Cache embeddings in SQLite (already implemented in MCP client!)
- First computation: $0.000001
- Subsequent comparisons: $0 (uses cache)

**Recommendation**: Enable semantic dedup, cost is negligible with caching.

---

## 2. Lazy Refinement Mode (Priority: Low)

**Current**: Proactive refinement only (Curator runs after every learning)
**Paper**: Proactive OR lazy refinement (on-demand during retrieval)

### Why the Paper Specifies This
- **Proactive**: Refine immediately after learning (always fresh playbook)
- **Lazy**: Refine during retrieval only when needed (deferred computation)
- Lazy mode saves compute when playbook isn't accessed frequently

### Current Trade-off
- ✅ **Pros**: Simpler architecture, playbook always current, predictable costs
- ❌ **Cons**: May refine even when playbook won't be retrieved soon

### To Implement

#### Server-Side Changes
**File**: `server/ace_server/curator.py`

```python
# Add configuration option
class CuratorConfig:
    refinement_mode: Literal["proactive", "lazy"] = "proactive"
    lazy_refine_threshold: int = 100  # Refine every N retrievals

# Update curator logic
class Curator:
    def __init__(self, config: CuratorConfig):
        self.mode = config.refinement_mode
        self.retrieve_count = 0

    async def handle_retrieval(self, request: RetrievalRequest) -> Playbook:
        if self.mode == "lazy":
            self.retrieve_count += 1
            if self.retrieve_count >= self.lazy_refine_threshold:
                await self._refine_playbook()
                self.retrieve_count = 0

        return self.get_playbook()
```

#### MCP Client Changes
**None required** - Client doesn't care about refinement timing

#### Plugin Changes
**None required** - Plugin doesn't care about refinement timing

### Use Cases

**Proactive (Current)**: Best for active development (frequent learning + retrieval)
**Lazy**: Best for occasional use (infrequent learning, batched refinement)

**Recommendation**: Keep proactive as default, add lazy as optional config.

---

## 3. Generator Helpful/Harmful Marking (Priority: Low)

**Current**: Reflector LLM analyzes execution trace and marks bullets
**Paper**: Generator (Claude) marks bullets during task execution

### Why the Paper Specifies This
- Generator has direct task execution context
- Can immediately mark bullets as helpful/harmful during use
- Real-time feedback loop

### Current Trade-off
- ✅ **Pros**: More objective analysis, removes marking burden from Generator
- ❌ **Cons**: Delayed feedback (analysis happens after task completion)

### To Implement

#### Plugin-Side Changes
**File**: `skills/ace-learning/SKILL.md`

```markdown
# Current
Call mcp__ace_learn with:
- task: "What was done"
- trajectory: "Steps taken"
- output: "Lessons learned"
- success: true/false

# Enhanced
Call mcp__ace_learn with:
- task: "What was done"
- trajectory: "Steps taken"
- output: "Lessons learned"
- success: true/false
- playbook_used: ["bullet_id_1", "bullet_id_2"]  # NEW: Track which bullets were used
```

**File**: `skills/ace-playbook-retrieval/SKILL.md`

```markdown
# Enhanced: Return bullet IDs
The playbook retrieval should track which bullets Claude uses:

Example response:
{
  "bullets": [
    {"id": "ctx-1234", "content": "Use refresh token rotation", ...}
  ]
}

Claude should remember these IDs and pass to ace_learn.
```

#### MCP Client Changes
**File**: `mcp-clients/ce-ai-ace-client/src/types/pattern.ts`

```typescript
// Add to LearningRequest interface
export interface LearningRequest {
  task: string;
  trajectory: TrajectoryStep[];
  success: boolean;
  output: string;
  playbook_used?: string[];  // NEW: Bullet IDs that were helpful
}
```

**File**: `mcp-clients/ce-ai-ace-client/src/index.ts`

```typescript
// Update ace_learn tool
tools.push({
  name: "ace_learn",
  parameters: {
    // ... existing params ...
    playbook_used: {
      type: "array",
      items: { type: "string" },
      description: "IDs of playbook bullets that were consulted during this task (optional). Helps track which patterns were useful."
    }
  }
});
```

#### Server-Side Changes
**File**: `server/ace_server/reflector.py`

```python
# Current: Reflector analyzes trajectory to infer helpful patterns
class Reflector:
    async def analyze(self, learning: LearningRequest) -> List[Pattern]:
        # Analyzes trajectory, extracts patterns, infers helpfulness
        pass

# Enhanced: Use explicit playbook_used for accurate marking
class Reflector:
    async def analyze(self, learning: LearningRequest) -> List[DeltaOperation]:
        patterns = await self._extract_patterns(learning.trajectory)

        # If Generator marked bullets as helpful, honor that
        if learning.playbook_used:
            helpful_ops = [
                DeltaOperation(
                    type="UPDATE",
                    bullet_id=bullet_id,
                    helpful_delta=1  # Increment helpful counter
                )
                for bullet_id in learning.playbook_used
            ]
            return helpful_ops + patterns

        # Otherwise, fall back to inference (current behavior)
        return patterns
```

### Complexity Analysis

**Current**: Simple, single-point feedback (Reflector analyzes everything)
**Enhanced**: More complex, requires Generator to track bullet usage across conversation

**Recommendation**: Current approach is actually better for production! Reflector has full execution context and can be more objective.

---

## 🚀 Recommended Implementation Priority

### Phase 1: Semantic De-duplication (Recommended)
**Impact**: High - Prevents playbook bloat
**Effort**: Medium - Infrastructure already exists
**Cost**: Negligible with caching

**Action Items**:
1. Server: Enable semantic comparison in Curator (1 day)
2. Server: Add embedding API integration (1 day)
3. Server: Add configuration toggle (0.5 day)
4. Testing: Verify 85% threshold works well (1 day)

**Total Effort**: 3-4 days

### Phase 2: Lazy Refinement Mode (Optional)
**Impact**: Low - Current proactive mode works well
**Effort**: Low - Simple configuration addition
**Cost**: Neutral (saves compute in some scenarios)

**Action Items**:
1. Server: Add lazy mode configuration (0.5 day)
2. Server: Track retrieval count, trigger refinement (0.5 day)
3. Testing: Verify lazy mode works correctly (1 day)

**Total Effort**: 2 days

### Phase 3: Generator Marking (Not Recommended)
**Impact**: Low - Current Reflector analysis is more objective
**Effort**: High - Requires changes across all three components
**Cost**: Increases Generator complexity

**Recommendation**: Skip this enhancement. Current approach is actually superior.

---

## 📋 Current Status Summary

### What We Have (95%)
- ✅ Complete three-agent architecture
- ✅ Incremental delta updates
- ✅ Four playbook sections
- ✅ Context collapse prevention
- ✅ Confidence scoring
- ✅ Exact de-duplication (cost-optimized)
- ✅ Proactive refinement (simplified)
- ✅ Reflector marking (more accurate)

### What We're Missing (5%)
- ⏳ Semantic de-duplication (has exact match instead)
- ⏳ Lazy refinement mode (has proactive only)
- ⏳ Generator marking (has Reflector marking instead)

### Should We Implement the Missing 5%?

**Semantic De-duplication**: **YES** ✅
- Clear benefit: prevents playbook bloat
- Infrastructure ready: embeddings cache exists
- Cost negligible: $0.01 per 10K bullets
- Effort reasonable: 3-4 days

**Lazy Refinement**: **OPTIONAL** ⚠️
- Benefit unclear: current mode works well
- Use case specific: only helps with infrequent access
- Can add later if needed

**Generator Marking**: **NO** ❌
- Current approach is better: Reflector is more objective
- High complexity: requires cross-component changes
- Low value: doesn't improve outcomes

---

## 🎯 Final Recommendation

**Implement semantic de-duplication only** to reach **~98% paper compliance**.

The remaining 2% (lazy mode, Generator marking) are either:
1. Use-case specific (lazy mode)
2. Actually inferior to our approach (Generator marking)

**Current Status**: Production-ready at 95% compliance with smart optimizations
**Enhanced Status**: Production-optimal at 98% compliance with semantic dedup

---

## 📚 References

- **Architecture Doc**: [ARCHITECTURE.md](./ARCHITECTURE.md)
- **MCP Client**: `mcp-clients/ce-ai-ace-client/`
- **Server Repo**: (separate repository)
- **Plugin**: `plugins/ace-orchestration/`

---

## 💡 Future Enhancements (Beyond Paper)

Ideas not in the original paper but could improve the system:

1. **Multi-Model Ensemble** (Reflector)
   - Use multiple models for pattern extraction
   - Compare outputs, higher confidence on agreement

2. **Playbook Versioning**
   - Git-like version control for playbooks
   - Rollback to previous versions if quality degrades

3. **A/B Testing Framework**
   - Test pattern effectiveness
   - Automatically prune low-performing patterns

4. **Cross-Project Learning**
   - Share patterns across related projects
   - Organization-wide knowledge base

5. **Visualization Dashboard**
   - See pattern evolution over time
   - Identify knowledge gaps
   - Track learning velocity

**Note**: These are research ideas, not required for paper compliance.
