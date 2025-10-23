# ACE Plugin Evolution: v3.2.8 → v3.2.10

**Period**: October 23, 2025  
**Major Changes**: Skill enforcement, version detection, trajectory format fix

---

## v3.2.8 - MANDATORY Skill Usage Rules

### Problem
Skills were **not auto-triggering** despite having model-invoked architecture:
- Passive language in descriptions: "Use when...", "Automatically after..."
- No explicit enforcement in project CLAUDE.md
- Claude's judgment alone wasn't sufficient

### Solution: Three-Layer Enforcement

**Layer 1: MANDATORY Section in CLAUDE.md** (lines 9-58)
```markdown
## 🚨 MANDATORY: ACE Skill Usage Rules

**YOU MUST FOLLOW THESE RULES FOR EVERY TASK:**

### Before ANY Implementation, Debugging, or Refactoring Task:

**ALWAYS invoke the ACE Playbook Retrieval skill FIRST:**
```
Skill: ace-orchestration:ace-playbook-retrieval
```

**Trigger keywords that require retrieval:**
- implement, build, create, add, develop
- debug, fix, troubleshoot, resolve, diagnose
- refactor, optimize, improve, restructure
- integrate, connect, setup, configure
- architect, design, plan

**You MUST call this skill BEFORE starting work when the user's request contains ANY of these keywords.**
```

**Layer 2: Aggressive Skill Descriptions**
- Changed from: "Use when you need to retrieve patterns..."
- Changed to: "PROACTIVELY use this skill BEFORE implementation tasks. YOU MUST retrieve playbook patterns when user says implement, build, debug..."

**Layer 3: Workflow Example**
```
User: "Implement JWT authentication"
    ↓
Step 1: Invoke ace-orchestration:ace-playbook-retrieval
Step 2: Review retrieved patterns
Step 3: Implement using learned patterns
Step 4: Invoke ace-orchestration:ace-learning
Step 5: Respond to user
```

### Files Changed
- `plugins/ace-orchestration/CLAUDE.md` - Added MANDATORY section (lines 9-58)
- `plugins/ace-orchestration/skills/ace-playbook-retrieval/SKILL.md` - Aggressive description
- `plugins/ace-orchestration/skills/ace-learning/SKILL.md` - Aggressive description

### Result
✅ Skills now auto-trigger consistently  
✅ Clear, explicit, non-negotiable instructions  
✅ "YOU MUST" language enforces behavior

---

## v3.2.9 - Version Detection & Auto-Update

### Problem
Users with old CLAUDE.md content (v3.2.6, v3.2.7) were missing new features:
- No MANDATORY section
- Outdated documentation
- Running `/ace-claude-init` again said "already initialized" and exited
- Manual editing required

### Solution: Smart Version Detection

**Step 3: Version Detection & Comparison** (in `/ace-claude-init`)

1. **Detect existing version** in project CLAUDE.md:
   - Pattern: `## 🔄 Complete Automatic Learning Cycle (vX.X.X)`
   - Extract version number

2. **Read plugin version** from installed plugin CLAUDE.md

3. **Compare versions:**
   - If match: "Already initialized with current version"
   - If outdated: "Your project has ACE v{old}, but plugin is v{new}. Would you like to update? (y/n)"

**Step 3a: Smart Update Process** (only if user says yes)

1. **Find ACE section boundaries**:
   - Start: `# ACE Orchestration Plugin - Automatic Learning Cycle`
   - End: Next `#` header at same level OR end of file

2. **Extract non-ACE content**:
   - Content BEFORE ACE section
   - Content AFTER ACE section

3. **Replace ACE section**:
   - Remove old ACE section completely
   - Insert new plugin CLAUDE.md content
   - Preserve all other content

4. **Write updated file**:
   - Reconstruct: `[before] + [new ACE] + [after]`

5. **Confirm update**:
   - Show: "ACE updated from v3.2.6 → v3.2.9"

### Files Changed
- `plugins/ace-orchestration/commands/ace-claude-init.md` - Enhanced with Steps 3 & 3a

### Benefits
✅ Easy updates: Just run `/ace-claude-init` again  
✅ Safe: Asks confirmation before changes  
✅ Smart: Only updates ACE section  
✅ Non-destructive: Preserves user customizations

---

## v3.2.10 - Trajectory Format Documentation Fix

### Problem
ACE Learning skill documentation showed **incorrect trajectory format**:

**❌ Documented (Wrong)**:
```json
{
  "trajectory": "1. Step one\n2. Step two\n3. Step three"
}
```

**✅ Server Requires**:
```json
{
  "trajectory": [
    {"step": "Analysis", "action": "Analyzed the problem"},
    {"step": "Implementation", "action": "Implemented the solution"}
  ]
}
```

**Result**: Users got **422 validation errors** when following docs

### Solution: Fix All Trajectory Examples

**Updated Files**:

1. **`skills/ace-learning/SKILL.md`** (3 examples fixed)
   - Line 83: Added **"IMPORTANT: Must be an array of objects"**
   - Example 1: JWT auth (5-step array)
   - Example 2: Debugging (6-step array)
   - Example 3: Stripe webhooks (6-step array)

2. **`CLAUDE.md`** (manual tool usage example)
   - Lines 272-283: Fixed trajectory format
   - Added IMPORTANT note (line 283)

3. **`commands/ace-claude-init.md`** (line counts)
   - Updated: 340 → 344 lines
   - Added note about trajectory fix

### Version Header Update
- **CLAUDE.md line 60**: Changed `v3.2.6` → `v3.2.10`
- **Reason**: `/ace-claude-init` uses this for version detection
- **Pattern**: `## 🔄 Complete Automatic Learning Cycle (v3.2.10)`

### Correct Format Examples

**Example 1: Successful Implementation**
```json
{
  "task": "Implemented user authentication with JWT tokens and refresh token rotation",
  "success": true,
  "trajectory": [
    {"step": "Analysis", "action": "Analyzed security requirements and token expiration needs"},
    {"step": "Library Selection", "action": "Chose JWT library (jsonwebtoken) for token generation"},
    {"step": "Token Strategy", "action": "Implemented access token (15min) + refresh token (7 days) pattern"},
    {"step": "Rotation Logic", "action": "Added token rotation logic in refresh endpoint"},
    {"step": "Security", "action": "Secured endpoints with authentication middleware"}
  ],
  "feedback": "Successfully implemented secure auth flow. Key insights: ..."
}
```

**Example 2: Debugging**
```json
{
  "task": "Debugged intermittent test failures in async database operations",
  "success": true,
  "trajectory": [
    {"step": "Observation", "action": "Observed random test failures in CI/CD pipeline"},
    {"step": "Hypothesis", "action": "Suspected race condition in database cleanup"},
    {"step": "First Attempt", "action": "Added transaction isolation and explicit wait for cleanup"},
    {"step": "Continued Failure", "action": "Tests still failed intermittently"},
    {"step": "Root Cause", "action": "Discovered missing await on database.close()"},
    {"step": "Solution", "action": "Added proper async/await chain to all cleanup operations"}
  ],
  "feedback": "Root cause: Forgot await on database.close() causing connection pool exhaustion..."
}
```

### Files Changed
- `plugins/ace-orchestration/skills/ace-learning/SKILL.md` - All 3 examples fixed
- `plugins/ace-orchestration/CLAUDE.md` - Manual tool usage example fixed (lines 272-283)
- `plugins/ace-orchestration/commands/ace-claude-init.md` - Line counts updated
- Version bumps: `plugin.json`, `marketplace.json`, `package.json` → 3.2.10

### Benefits
✅ No more 422 validation errors  
✅ Clear array of objects format  
✅ IMPORTANT warning prevents confusion  
✅ All examples consistent

---

## Summary Table

| Version | Date | Focus | Key Files |
|---------|------|-------|-----------|
| v3.2.8 | 2025-10-23 | Skill enforcement | CLAUDE.md (MANDATORY section), SKILL.md descriptions |
| v3.2.9 | 2025-10-23 | Version detection | ace-claude-init.md (Steps 3 & 3a) |
| v3.2.10 | 2025-10-23 | Trajectory format fix | ace-learning/SKILL.md (3 examples), CLAUDE.md (line 272-283) |

---

## File Locations (Quick Reference)

```
plugins/ace-orchestration/
├── CLAUDE.md (344 lines, v3.2.10)
│   ├── Lines 9-58: MANDATORY section (v3.2.8)
│   ├── Line 60: Version header (v3.2.10)
│   └── Lines 272-283: Trajectory example (v3.2.10)
├── skills/
│   ├── ace-playbook-retrieval/SKILL.md (aggressive description, v3.2.8)
│   └── ace-learning/SKILL.md (trajectory examples fixed, v3.2.10)
├── commands/
│   └── ace-claude-init.md (version detection, v3.2.9; line counts, v3.2.10)
└── plugin.json (version: 3.2.10)

.claude-plugin/marketplace.json (version: 3.2.10)
mcp-clients/ce-ai-ace-client/package.json (version: 3.2.10)
```

---

## Testing the Changes

### Test v3.2.8 (MANDATORY enforcement)
```bash
# Request with trigger word
User: "Implement JWT authentication"

# Expected:
✅ ace-playbook-retrieval skill auto-invokes BEFORE implementation
✅ Implementation uses retrieved patterns
✅ ace-learning skill auto-invokes AFTER completion
```

### Test v3.2.9 (Version detection)
```bash
# In project with old ACE content (v3.2.6, v3.2.7)
/ace-claude-init

# Expected:
✅ Detects: "Your project has ACE v3.2.6, but plugin is v3.2.10"
✅ Asks: "Would you like to update? (y/n)"
✅ If yes: Replaces only ACE section, preserves other content
✅ Confirms: "ACE updated from v3.2.6 → v3.2.10"
```

### Test v3.2.10 (Trajectory format)
```bash
# Use correct trajectory format
mcp__ace-pattern-learning__ace_learn(
  task="Implemented error handler",
  success=true,
  trajectory=[
    {"step": "Retrieval", "action": "Retrieved ACE patterns"},
    {"step": "Design", "action": "Designed error class hierarchy"}
  ],
  output="Successfully implemented..."
)

# Expected:
✅ No 422 validation errors
✅ Server accepts trajectory
✅ Execution trace stored successfully
```

---

## Common Issues & Solutions

### Issue: Skills still not triggering (after v3.2.8)
**Check**:
- User must have run `/ace-claude-init` to get MANDATORY section
- Task must contain trigger words (implement, debug, etc.)
- Task must be substantial (not trivial Q&A)

### Issue: /ace-claude-init says "already initialized" (after v3.2.9)
**Check**:
- Look for version in output: "already initialized with v3.2.10"
- If version matches, it's correct behavior
- If no version mentioned, there may be content mismatch

### Issue: 422 trajectory validation error (after v3.2.10)
**Check**:
- Trajectory must be **array of objects**, not string
- Each object needs descriptive keys (e.g., `{"step": "...", "action": "..."}`)
- See examples in ace-learning/SKILL.md

---

## Upgrade Path for Users

**Step 1: Update Plugin**
```bash
claude plugin update ace-orchestration
```

**Step 2: Update Project CLAUDE.md**
```bash
/ace-claude-init
# Will detect outdated version and offer to update
```

**Step 3: Verify**
```bash
/ace-status
# Try a task: "Implement user authentication"
# Skills should auto-trigger
```

---

## Key Learnings

1. **Explicit > Implicit**: MANDATORY section was needed despite model-invoked architecture
2. **Progressive Enhancement**: Version detection enables safe, non-destructive updates
3. **Documentation Accuracy**: Even small format mismatches cause user friction
4. **Testing Matters**: Discovered trajectory format issue through actual usage
5. **Iteration Works**: v3.2.8 → v3.2.9 → v3.2.10 in rapid succession = responsive improvements

---

**Last Updated**: 2025-10-23  
**Current Version**: v3.2.10  
**Status**: All features tested and working ✅