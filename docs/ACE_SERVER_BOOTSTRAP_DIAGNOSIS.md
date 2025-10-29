# ACE Server Bootstrap Pattern Extraction - Critical Diagnostic

## 🚨 PROBLEM STATEMENT

Bootstrap extracted **158 domain-specific patterns** from the Recrible codebase but the playbook only shows **14 generic meta-patterns** about the bootstrap process itself.

### Expected Patterns (158 total):
- **27 strategies**: Stripe billing flows, Auth.js v5 multi-tenant, Firebase security rules
- **49 code snippets**: Concrete implementations of Stripe webhooks, Auth.js adapters, Firebase queries
- **17 troubleshooting**: Known issues with Stripe signature verification, Auth.js session handling, Firebase permissions
- **65 APIs**: Stripe API usage, Auth.js v5 configuration, Firebase Admin SDK patterns, German VAT compliance

### Actual Patterns in Playbook (14 total):
- **5 strategies**: "When bootstrapping ACE playbooks...", "Bootstrap pattern extraction should..."
- **3 snippets**: Generic bootstrap code snippets (not domain-specific)
- **3 troubleshooting**: Meta-patterns about bootstrap troubleshooting
- **3 APIs**: Generic guidance about API extraction

### Evidence from MCP Client:
```json
{
  "mode": "BOTH",
  "sources_analyzed": {
    "git_history": {
      "commits_analyzed": 108,
      "patterns_extracted": 70
    },
    "local_files": {
      "files_scanned": 92,
      "patterns_extracted": 88,
      "linguist_result": {
        "TypeScript": "50.08%",
        "TSX": "37.77%",
        "JavaScript": "10.46%",
        "JSON": "0.72%",
        "SCSS": "0.49%"
      }
    }
  },
  "total_patterns": 158,
  "sent_to_server": true
}
```

---

## 📖 ACE RESEARCH PAPER ARCHITECTURE (Validation)

From the ACE research paper (`2510.04618v1.pdf`):

### Three-Agent Architecture:

```
Query → Generator → Trajectory → Reflector → Insights → Curator → Delta Context Items
         ↑                                                            ↓
    Context Playbook ←────────────── Update ─────────────────────────┘
```

### Expected Behavior:

1. **Reflector Role**:
   > "distills concrete insights from successes and errors"

   **Expectation**: Extract domain-specific patterns like:
   - "Stripe webhook signature verification requires express.raw() middleware"
   - "Auth.js v5 JWT sessions need custom adapter for multi-tenant architecture"
   - "Firebase security rules must scope by orgId for tenant isolation"

2. **Curator Role**:
   > "synthesizes these lessons into compact delta entries, which are merged **deterministically**
   > into the existing context by **lightweight, non-LLM logic**"

   **Expectation**:
   - ⚠️ **CRITICAL**: Curator should NOT use LLM
   - Should use deterministic merge algorithm
   - Should preserve domain-specific details from Reflector

3. **Anti-Pattern Prevention**:
   > Paper discusses avoiding "context collapse" and "brevity bias"

   **Current Issue**: 158 specific patterns collapsed into 14 generic meta-patterns = context collapse

---

## 🔍 WHAT TO INVESTIGATE

### 1. LLM-Based Domain Discovery

**Question**: You mentioned there's an LLM-based domain discovery on the server.

**Check**:
- Where is this domain discovery in the bootstrap flow?
- Is it analyzing the extracted patterns OR the source code?
- Is it creating meta-patterns about the process instead of extracting code patterns?

**Expected**: Domain discovery should identify domains like:
- ✅ "Stripe billing integration"
- ✅ "Auth.js v5 authentication"
- ✅ "Firebase multi-tenant architecture"

**Not Expected**: Domain discovery should NOT create:
- ❌ "Bootstrap process patterns"
- ❌ "Pattern extraction methodology"
- ❌ "ACE playbook initialization"

### 2. Reflector Implementation

**File to Check**: `server/services/reflector.py` (or equivalent)

**Questions**:
1. What prompt is the Reflector using for bootstrap patterns?
2. Is it analyzing the **code patterns** OR the **extraction process**?
3. Is it preserving concrete technical details (API names, code snippets, error messages)?

**Expected Reflector Output Example**:
```json
{
  "section": "apis_to_use",
  "insight": "Stripe webhook signature verification",
  "details": "express.raw() middleware required for bodyParser to preserve raw body for signature verification",
  "code_reference": "app.post('/api/webhooks/stripe', express.raw({type: 'application/json'}), handler)",
  "domain": "stripe-billing"
}
```

**Wrong Reflector Output** (what's happening now):
```json
{
  "section": "strategies_and_hard_rules",
  "insight": "Bootstrap pattern extraction methodology",
  "details": "When bootstrapping ACE playbooks from existing codebases...",
  "code_reference": null,
  "domain": "ace-bootstrap"
}
```

### 3. Curator Implementation

**File to Check**: `server/services/curator.py` (or equivalent)

**CRITICAL QUESTIONS**:
1. ⚠️ **Is the Curator using an LLM?** (It shouldn't according to the research paper!)
2. Is it using deterministic merge logic? (It should!)
3. Is it compressing/summarizing the Reflector's insights? (It shouldn't!)

**Expected Curator Behavior** (from research paper):
```python
def curator_merge(existing_playbook, reflector_insights):
    """
    Deterministic, non-LLM merge algorithm
    Preserves all domain-specific details from Reflector
    """
    for insight in reflector_insights:
        section = insight['section']

        # Simple deterministic merge (no LLM!)
        if not is_duplicate(existing_playbook[section], insight):
            existing_playbook[section].append({
                'bullet': insight['details'],
                'code': insight.get('code_reference'),
                'domain': insight['domain'],
                'confidence': insight.get('confidence', 0.5),
                'helpful_count': 0,
                'harmful_count': 0
            })

    return existing_playbook
```

**Wrong Curator Behavior** (if using LLM):
```python
def curator_merge(existing_playbook, reflector_insights):
    """
    ❌ ANTI-PATTERN: Using LLM to "synthesize" insights
    This causes context collapse and brevity bias
    """
    # Send to LLM
    prompt = f"Synthesize these insights: {reflector_insights}"
    llm_response = claude_api.call(prompt)

    # ❌ Result: Generic meta-patterns instead of specific code patterns
    return llm_response
```

### 4. Bootstrap Endpoint

**File to Check**: `server/routes/playbook.py` (or equivalent) - `/api/playbook/bootstrap` endpoint

**Questions**:
1. What parameters are passed to the Reflector?
2. Is the raw pattern data (158 patterns) being passed correctly?
3. Is there a step that filters or summarizes before Reflector?

**Expected Flow**:
```python
@router.post("/api/playbook/bootstrap")
async def bootstrap(patterns: List[Pattern]):
    # Step 1: Domain discovery (LLM can be used here)
    domains = await domain_discovery(patterns)  # ✅ OK to use LLM

    # Step 2: Reflector extracts concrete insights
    insights = await reflector.extract_insights(patterns, domains)
    # ✅ Should get 158 concrete insights from 158 patterns

    # Step 3: Curator merges deterministically
    updated_playbook = curator.merge(existing_playbook, insights)
    # ⚠️ Should NOT use LLM here!
    # ⚠️ Should preserve all 158 insights!

    return updated_playbook
```

---

## 🧪 DIAGNOSTIC TESTS

### Test 1: Check Reflector Output

```python
# In your server code, add logging:
@router.post("/api/playbook/bootstrap")
async def bootstrap(patterns: List[Pattern]):
    logger.info(f"📥 Received {len(patterns)} patterns")

    insights = await reflector.extract_insights(patterns, domains)
    logger.info(f"🔍 Reflector extracted {len(insights)} insights")
    logger.info(f"📊 Sample insights: {insights[:3]}")

    # Check: Should be ~158 insights, not 14!
```

### Test 2: Check Curator Behavior

```python
# Check if Curator is using LLM:
def curator_merge(existing_playbook, reflector_insights):
    logger.info(f"📝 Curator received {len(reflector_insights)} insights")

    # ⚠️ IS THERE AN LLM CALL HERE?
    # Search for: anthropic.messages.create, openai.ChatCompletion.create, etc.

    result = merge_logic(existing_playbook, reflector_insights)
    logger.info(f"✅ Curator produced {len(result)} final patterns")

    # Check: Should be ~158 patterns, not 14!
```

### Test 3: Check Domain Discovery

```python
# Check what domains are discovered:
domains = await domain_discovery(patterns)
logger.info(f"🌍 Discovered domains: {domains}")

# Expected: ['stripe-billing', 'auth-js-v5', 'firebase-multi-tenant', ...]
# Not Expected: ['ace-bootstrap', 'pattern-extraction-methodology', ...]
```

---

## 🎯 EXPECTED FIX

Based on the research paper architecture:

### 1. Domain Discovery (✅ CAN use LLM)
```python
async def domain_discovery(patterns: List[Pattern]) -> List[str]:
    """
    Use LLM to identify technical domains in the codebase
    This is BEFORE Reflector, so it's OK to use LLM
    """
    prompt = f"""
    Analyze these code patterns and identify technical domains:
    {patterns}

    Return domains like: "stripe-billing", "auth-js-authentication",
    "firebase-database", NOT "bootstrap-process" or "pattern-extraction"
    """
    return await llm_call(prompt)
```

### 2. Reflector (✅ CAN use LLM)
```python
async def extract_insights(patterns: List[Pattern], domains: List[str]) -> List[Insight]:
    """
    Use LLM to extract concrete, domain-specific insights
    Focus on CODE PATTERNS, not PROCESS PATTERNS
    """
    prompt = f"""
    Extract concrete code patterns from these {len(patterns)} patterns.

    Domains identified: {domains}

    For each pattern, extract:
    - Specific API usage (e.g., "Stripe webhook signature verification")
    - Code snippets (e.g., "express.raw() middleware configuration")
    - Error messages and solutions
    - Configuration requirements

    DO NOT create meta-patterns about the extraction process itself!
    """
    return await llm_call(prompt)
```

### 3. Curator (⚠️ MUST NOT use LLM)
```python
def merge(existing_playbook: Playbook, insights: List[Insight]) -> Playbook:
    """
    Deterministic merge - NO LLM!
    Preserve ALL insights from Reflector
    """
    for insight in insights:
        section = insight.section

        # Simple duplicate detection (no LLM)
        if not any(is_similar(bullet, insight) for bullet in existing_playbook[section]):
            existing_playbook[section].append({
                'bullet': insight.details,
                'code': insight.code_reference,
                'domain': insight.domain,
                'helpful_count': 0,
                'harmful_count': 0
            })

    return existing_playbook
```

---

## 📋 CHECKLIST FOR ACE SERVER TEAM

- [ ] **Step 1**: Check domain discovery - is it creating "bootstrap" domain or "stripe/auth/firebase" domains?
- [ ] **Step 2**: Check Reflector prompt - is it analyzing code patterns or extraction process?
- [ ] **Step 3**: Check Reflector output - are we getting ~158 insights or ~14 insights?
- [ ] **Step 4**: Check Curator - is it using an LLM? (It shouldn't!)
- [ ] **Step 5**: Check Curator - is it compressing insights? (It shouldn't!)
- [ ] **Step 6**: Check final playbook - are domain-specific patterns preserved?

---

## 🔧 FILES TO INVESTIGATE

Based on typical ACE server architecture:

```
server/
├── services/
│   ├── reflector.py              ← Check Reflector prompt and logic
│   ├── curator.py                ← ⚠️ Check if using LLM (shouldn't!)
│   └── domain_discovery.py       ← Check domain identification
├── routes/
│   └── playbook.py               ← Check /api/playbook/bootstrap endpoint
├── models/
│   └── pattern.py                ← Check Pattern schema
└── utils/
    └── merge.py                  ← Check merge algorithm (should be deterministic)
```

---

## 💡 SUMMARY

**The Problem**: 158 domain-specific patterns → 14 generic meta-patterns

**Root Cause Hypothesis**:
1. **Domain discovery** creating wrong domains ("bootstrap" instead of "stripe/auth/firebase")
2. **Reflector prompt** analyzing the extraction process instead of code patterns
3. **Curator using LLM** to compress insights (violates research paper architecture)

**Research Paper Validation**:
- ✅ Reflector should extract "concrete insights" (domain-specific)
- ✅ Curator should use "lightweight, non-LLM logic" (deterministic)
- ❌ Current behavior shows context collapse (158 → 14)

**Next Steps**:
1. Add logging to see where patterns are lost (Reflector output vs Curator output)
2. Check if Curator is using LLM (it shouldn't according to paper)
3. Fix Reflector prompt to focus on code patterns not extraction process
4. Fix domain discovery to identify technical domains not meta-domains

---

**Evidence Trail**:
- MCP Client v3.2.14: ✅ Extracted 158 patterns, sent to server
- ACE Server: ❌ Produced 14 meta-patterns instead of 158 domain patterns
- Research Paper: Confirms Curator should be deterministic, not LLM-based
