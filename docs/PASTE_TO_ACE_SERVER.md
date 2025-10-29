# ACE Server Bootstrap Issue - Diagnostic Instructions

## 🚨 CRITICAL ISSUE: Pattern Loss in Bootstrap

**Problem**: Bootstrap sent 158 domain-specific patterns to server, but only 14 generic meta-patterns appear in playbook.

**Your Task**: Diagnose where patterns are being lost and why meta-patterns are being created instead of code patterns.

---

## 📊 EVIDENCE FROM CLIENT SIDE

### Patterns Sent to Server (158 total):
```json
{
  "mode": "BOTH",
  "git_history": { "commits_analyzed": 108, "patterns_extracted": 70 },
  "local_files": { "files_scanned": 92, "patterns_extracted": 88 },
  "total_patterns": 158,
  "domains": ["stripe-billing", "auth-js-v5", "firebase-multi-tenant", "german-vat-compliance"],
  "sent_to_server": true
}
```

### Expected Pattern Examples:
- **Strategies**: "Stripe webhook signature verification requires express.raw() middleware"
- **Snippets**: `app.post('/api/webhooks/stripe', express.raw({type: 'application/json'}), handler)`
- **Troubleshooting**: "Stripe signature verification fails if bodyParser processes request first"
- **APIs**: "Stripe SDK v14.x stripe.webhooks.constructEvent() for webhook validation"

### Actual Patterns in Playbook (14 total):
- **Strategies**: "When bootstrapping ACE playbooks from existing codebases..."
- **Snippets**: Generic bootstrap code (not domain-specific)
- **Troubleshooting**: "Bootstrap pattern extraction should consider..."
- **APIs**: "Pattern extraction methodologies..."

**❌ These are meta-patterns ABOUT bootstrap, not patterns FROM the codebase!**

---

## 📖 RESEARCH PAPER ARCHITECTURE (Your Implementation Guide)

From ACE research paper `2510.04618v1.pdf`:

### Three-Agent Architecture:
```
Patterns → Reflector → Insights → Curator → Delta → Playbook
           (LLM ✅)    (LLM ✅)   (NO LLM ❌)
```

### Key Quotes:

1. **Reflector**:
   > "distills **concrete insights** from successes and errors"

   **Meaning**: Extract SPECIFIC code patterns (API usage, error handling, config), not abstract meta-patterns

2. **Curator**:
   > "synthesizes lessons into compact delta entries, which are merged **deterministically** into existing context by **lightweight, non-LLM logic**"

   **Meaning**:
   - ⚠️ **NO LLM in Curator!** Use deterministic algorithm
   - Preserve all Reflector insights (don't compress!)
   - Simple duplicate detection and merge

3. **Anti-Pattern**:
   > Paper warns against "context collapse" and "brevity bias"

   **Current Issue**: 158 specific patterns → 14 generic meta-patterns = context collapse!

---

## 🔍 DIAGNOSTIC CHECKLIST

### 1. Check Domain Discovery
**Where**: Likely in `services/domain_discovery.py` or similar

**Question**: What domains are being identified?

**Expected Output**:
```python
domains = [
    "stripe-billing",
    "auth-js-v5-authentication",
    "firebase-multi-tenant",
    "nextjs-15-app-router",
    "german-vat-compliance"
]
```

**Wrong Output** (if this is happening):
```python
domains = [
    "ace-bootstrap",
    "pattern-extraction-methodology",
    "playbook-initialization"
]
```

**Action**: Find domain discovery code, add logging, verify it's analyzing the CODE domains not the PROCESS.

---

### 2. Check Reflector Implementation
**Where**: Likely in `services/reflector.py` or similar

**Questions**:
- What's the Reflector prompt for bootstrap?
- Is it analyzing the 158 patterns OR the extraction process?
- How many insights does it output?

**Add This Logging**:
```python
async def extract_insights(patterns: List[Pattern], domains: List[str]):
    logger.info(f"🔍 Reflector INPUT: {len(patterns)} patterns")
    logger.info(f"🌍 Domains: {domains}")

    # Your Reflector logic here
    insights = await your_reflector_logic(patterns, domains)

    logger.info(f"✨ Reflector OUTPUT: {len(insights)} insights")
    logger.info(f"📝 Sample insights: {insights[:3]}")

    return insights
```

**Expected**: ~158 insights with domain-specific details
**Wrong**: ~14 insights about bootstrap process

**Example Good Insight**:
```python
{
    "section": "apis_to_use",
    "insight": "Stripe webhook signature verification",
    "details": "Use express.raw() middleware to preserve raw body for signature verification with stripe.webhooks.constructEvent()",
    "code": "app.post('/api/webhooks/stripe', express.raw({type: 'application/json'}), handler)",
    "domain": "stripe-billing"
}
```

**Example Bad Insight** (what's happening now):
```python
{
    "section": "strategies_and_hard_rules",
    "insight": "Bootstrap pattern extraction",
    "details": "When bootstrapping ACE playbooks from existing codebases, consider git history and local files",
    "code": null,
    "domain": "ace-bootstrap"
}
```

**Fix Reflector Prompt** (if needed):
```python
prompt = f"""
You are analyzing {len(patterns)} code patterns extracted from a codebase.

Domains identified: {domains}

YOUR TASK: Extract CONCRETE, DOMAIN-SPECIFIC insights about the CODE, such as:
- API usage patterns (e.g., "Stripe webhook signature verification requires...")
- Code implementation details (e.g., "express.raw() middleware for...")
- Error handling patterns (e.g., "Catch signature verification failures...")
- Configuration requirements (e.g., "Stripe webhook secret in .env...")

DO NOT create meta-patterns about:
- The bootstrap process itself
- Pattern extraction methodology
- ACE playbook initialization
- How patterns should be organized

Focus on WHAT THE CODE DOES, not how it was extracted.

Patterns to analyze:
{json.dumps(patterns, indent=2)}
"""
```

---

### 3. Check Curator Implementation ⚠️ CRITICAL
**Where**: Likely in `services/curator.py` or similar

**CRITICAL QUESTIONS**:

**Q1: Is the Curator using an LLM?**
```python
# Search for LLM calls in Curator:
# - anthropic.messages.create
# - openai.ChatCompletion.create
# - Any LLM API calls

# ❌ If you find LLM calls in Curator → THIS IS THE BUG!
```

**Q2: Is it compressing Reflector insights?**
```python
# Check if Curator is doing this:
def curator_merge(insights):
    # ❌ WRONG: Summarizing/compressing insights
    summary = llm_call(f"Summarize these insights: {insights}")
    return summary  # Results in 14 meta-patterns instead of 158 patterns!
```

**Research Paper Says**:
> "merged **deterministically** into existing context by **lightweight, non-LLM logic**"

**Expected Curator Implementation**:
```python
def curator_merge(existing_playbook: dict, reflector_insights: List[dict]) -> dict:
    """
    Deterministic merge - NO LLM!
    Preserve ALL insights from Reflector
    """
    logger.info(f"📝 Curator INPUT: {len(reflector_insights)} insights")

    for insight in reflector_insights:
        section = insight['section']

        # Simple duplicate detection (no LLM - use exact/fuzzy string matching)
        is_duplicate = any(
            is_similar_text(bullet['bullet'], insight['details'])
            for bullet in existing_playbook[section]
        )

        if not is_duplicate:
            existing_playbook[section].append({
                'bullet': insight['details'],
                'code': insight.get('code'),
                'domain': insight.get('domain'),
                'helpful_count': 0,
                'harmful_count': 0,
                'created_at': datetime.now().isoformat()
            })

    logger.info(f"✅ Curator OUTPUT: {sum(len(s) for s in existing_playbook.values())} total patterns")
    return existing_playbook

def is_similar_text(text1: str, text2: str, threshold: float = 0.85) -> bool:
    """Deterministic similarity check - NO LLM"""
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    return ratio >= threshold
```

**Add This Logging**:
```python
def curator_merge(existing_playbook, reflector_insights):
    logger.info(f"📝 Curator INPUT: {len(reflector_insights)} insights")

    # Check: Are you calling an LLM here?
    # ⚠️ YOU SHOULDN'T BE!

    result = your_merge_logic(existing_playbook, reflector_insights)

    total_patterns = sum(len(section) for section in result.values())
    logger.info(f"✅ Curator OUTPUT: {total_patterns} total patterns in playbook")

    # Expected: ~158 new patterns added
    # Wrong: ~14 patterns added

    return result
```

---

### 4. Check Bootstrap Endpoint
**Where**: Likely in `routes/playbook.py` - `/api/playbook/bootstrap`

**Add This Logging**:
```python
@router.post("/api/playbook/bootstrap")
async def bootstrap(request: BootstrapRequest):
    patterns = request.patterns
    logger.info(f"📥 Bootstrap received: {len(patterns)} patterns")

    # Step 1: Domain discovery
    domains = await domain_discovery(patterns)
    logger.info(f"🌍 Domains discovered: {domains}")
    # Check: Are domains correct? (stripe, auth-js, firebase) or wrong? (bootstrap, extraction)

    # Step 2: Reflector
    insights = await reflector.extract_insights(patterns, domains)
    logger.info(f"🔍 Reflector produced: {len(insights)} insights")
    # Check: Should be ~158, not ~14

    # Step 3: Curator
    updated_playbook = curator.merge(existing_playbook, insights)
    total = sum(len(section) for section in updated_playbook.values())
    logger.info(f"📚 Final playbook: {total} total patterns")
    # Check: Should be ~158 more than before

    return updated_playbook
```

---

## 🎯 EXPECTED BEHAVIOR

### Flow Diagram:
```
158 Patterns from Client
    ↓
Domain Discovery (LLM ✅)
    → ["stripe-billing", "auth-js-v5", "firebase-multi-tenant"]
    ↓
Reflector (LLM ✅)
    → 158 concrete insights about Stripe, Auth.js, Firebase code
    ↓
Curator (NO LLM ❌)
    → Deterministic merge: Add all 158 insights to playbook
    ↓
Playbook: 158 new domain-specific patterns ✅
```

### Current Broken Flow:
```
158 Patterns from Client
    ↓
Domain Discovery (LLM)
    → ❌ ["ace-bootstrap", "pattern-extraction"] (WRONG!)
    ↓
Reflector (LLM)
    → ❌ 14 meta-patterns about bootstrap process (WRONG!)
    ↓
Curator (LLM? ⚠️)
    → ❌ Compresses to 14 generic patterns (WRONG!)
    ↓
Playbook: 14 useless meta-patterns ❌
```

---

## 🔧 ACTION ITEMS

1. **Add logging** to all three components (domain discovery, Reflector, Curator)
2. **Run bootstrap again** and capture logs showing:
   - Input: 158 patterns
   - Domain discovery output: ??? domains
   - Reflector output: ??? insights
   - Curator output: ??? patterns in final playbook

3. **Identify the bottleneck**:
   - Is domain discovery creating wrong domains?
   - Is Reflector creating meta-patterns instead of code patterns?
   - Is Curator using LLM to compress? (It shouldn't!)

4. **Fix based on findings**:
   - Domain discovery: Focus on code domains not process domains
   - Reflector: Focus on code patterns not extraction patterns
   - Curator: Remove LLM, use deterministic merge

5. **Validate fix**:
   - Run bootstrap with same 158 patterns
   - Expect: ~158 domain-specific patterns in playbook
   - Domains should be: stripe, auth-js, firebase, etc.
   - Patterns should be: API usage, error handling, configs

---

## 📂 LIKELY FILES TO CHECK

```
server/
├── services/
│   ├── reflector.py              ← Check prompt and logic
│   ├── curator.py                ← ⚠️ Check for LLM usage (remove if found!)
│   └── domain_discovery.py       ← Check domain identification
├── routes/
│   └── playbook.py               ← Check /api/playbook/bootstrap endpoint
└── utils/
    └── merge.py                  ← Check merge algorithm
```

---

## ✅ SUCCESS CRITERIA

After the fix, running bootstrap should show:

```
📥 Bootstrap received: 158 patterns
🌍 Domains discovered: ['stripe-billing', 'auth-js-v5', 'firebase-multi-tenant', 'nextjs-15', 'german-vat']
🔍 Reflector produced: 158 insights (domain-specific)
📝 Curator merging: 158 insights (deterministic, no LLM)
✅ Final playbook: 158 new patterns added

Breakdown:
- strategies_and_hard_rules: 27 patterns (Stripe flows, Auth.js multi-tenant, Firebase security)
- useful_code_snippets: 49 patterns (Concrete implementations)
- troubleshooting_and_pitfalls: 17 patterns (Known issues and fixes)
- apis_to_use: 65 patterns (Stripe API, Auth.js v5, Firebase SDK)
```

---

**Reference**: ACE Research Paper validates this architecture - Curator must be deterministic (no LLM), Reflector must extract concrete insights (not meta-patterns).

**Client Status**: ✅ MCP Client v3.2.14 confirmed working - sent all 158 patterns to server correctly.

**Server Status**: ❌ Investigation needed - patterns being lost or transformed into meta-patterns.
