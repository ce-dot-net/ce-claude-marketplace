# Query Enhancement Decision: Server Team Feedback

## ❌ Original Proposal (WRONG)

**What I Proposed**:
```python
def enhance_query_for_search(user_prompt: str) -> str:
    """Add technical keywords for better semantic search"""
    enhancements = {
        'implement': 'implementation patterns code examples strategies',
        'fix': 'troubleshooting debugging solutions error handling',
        # ... etc
    }
    # Add generic keywords
    return f"{user_prompt} {context_words}"
```

**Why This Was Wrong**:
- ❌ Applied **keyword search optimization** to a **semantic search system**
- ❌ ACE uses embeddings (all-MiniLM-L6-v2), not keyword matching (BM25)
- ❌ Generic words like "patterns examples strategies" **DILUTE** the semantic signal

**Evidence** (from server team):
```python
# Embeddings make keyword stuffing IRRELEVANT:
original = "implement JWT auth"
embedding_original = [0.123, -0.456, 0.789, ...]  # 384 dimensions

enhanced = "implement JWT auth implementation patterns code examples"
embedding_enhanced = [0.125, -0.452, 0.791, ...]  # Nearly IDENTICAL!

# Result: No improvement, or worse!
```

**Research Evidence**:
- Natural language queries: 0.82 NDCG ✅
- Keyword-stuffed queries: 0.71 NDCG ❌ (worse!)

---

## ✅ Server Team Recommendations (IMPLEMENTED)

### 1. **Minimal Abbreviation Expansion Only**

```python
def expand_abbreviations(prompt: str) -> str:
    """Expand ONLY common abbreviations. NO generic keywords!"""
    replacements = {
        ' JWT ': ' JSON Web Token ',
        ' API ': ' REST API ',
        ' DB ': ' database ',
        ' auth ': ' authentication ',
        # ... minimal set only
    }
    return apply_replacements(prompt)
```

**Why This Helps**:
- ✅ Clarifies abbreviations → better semantic understanding
- ✅ "JWT" → "JSON Web Token" = same concept, clearer signal
- ✅ NO noise added (unlike keyword stuffing)

**Example**:
- Input: `"implement JWT auth"`
- Output: `"implement JSON Web Token authentication"` ✓
- NOT: `"implement JWT auth implementation patterns code examples"` ✗

### 2. **Client-Side Quality Filtering**

```python
# Filter low-quality patterns if we have enough results
if len(pattern_list) > 5:
    high_quality = [p for p in pattern_list
                    if p.get('confidence', 0) >= 0.5
                    or p.get('helpful', 0) >= 2]
    if len(high_quality) >= 3:
        pattern_list = high_quality
```

**Why This Helps**:
- ✅ Removes low-confidence noise patterns
- ✅ Prioritizes proven helpful patterns (helpful >= 2)
- ✅ Only filters when we have surplus (keeps at least 3)

### 3. **What Server Team Should Do**

Plugin can't control these (server-side config):

1. ✅ **Lower threshold**: 0.3 (already done)
2. ✅ **Increase top_k**: 15-20 (vs default 10)
3. ✅ **Adaptive retry**: Try multiple thresholds (0.6 → 0.45 → 0.3)

---

## Key Learnings

### **Semantic Search ≠ Keyword Search**

| Approach | Keyword Search (BM25) | Semantic Search (Embeddings) |
|----------|----------------------|------------------------------|
| **Query expansion** | ✅ Helps (adds synonyms) | ❌ Hurts (adds noise) |
| **Keyword stuffing** | ✅ Improves recall | ❌ Dilutes signal |
| **Natural language** | ⚠️ Needs preprocessing | ✅ Works best as-is |
| **Abbreviations** | ⚠️ May miss matches | ✅ Should expand |

### **Research Evidence**

From embedding model papers:
- Embeddings capture **semantic meaning**, not word frequency
- Generic words like "patterns", "examples", "best practices" add **noise**
- Natural language queries perform **better** than keyword-stuffed ones

### **Mental Model**

**Wrong** (keyword search thinking):
```
"JWT auth" → lacks context → add keywords → "JWT auth patterns examples"
                                              ↓
                                         Better results ✗
```

**Correct** (semantic search thinking):
```
"JWT auth" → embedding captures semantic meaning → [0.123, -0.456, ...]
                                                     ↓
                                                Natural language works best ✓

"JWT auth patterns examples" → diluted meaning → [0.125, -0.452, ...]
                                                   ↓
                                              Same or worse results ✗
```

---

## Implementation Summary

**File**: `shared-hooks/ace_before_task.py`

**Changes**:
1. ✅ Added `expand_abbreviations()` - Minimal enhancement only
2. ✅ Added client-side quality filtering - Filter low-confidence patterns
3. ❌ **Did NOT add** keyword stuffing (would hurt results!)

**Example Workflow**:
```
User: "implement JWT auth"
  ↓
expand_abbreviations: "implement JSON Web Token authentication"
  ↓
run_search() → server uses embeddings
  ↓
Client-side filter: Keep confidence >= 0.5 OR helpful >= 2
  ↓
Return high-quality patterns to Claude
```

---

## Credit

**Server Team Feedback** (the experts who got it right):

> "We use semantic embeddings (all-MiniLM-L6-v2), not keyword search.
> Research shows embeddings work better with natural language, not keyword
> stuffing. Adding generic words like 'patterns examples strategies' actually
> dilutes the semantic signal and produces worse results."

**Thank you** to the server team for catching this before it shipped! 🎯

---

## References

- **ACE Server**: Uses `all-MiniLM-L6-v2` embeddings (384 dimensions)
- **Similarity**: Cosine similarity on embeddings (not keyword matching)
- **Research**: Embedding models perform better with natural language queries
- **Evidence**: 0.82 NDCG (natural) vs 0.71 NDCG (keyword-stuffed)
