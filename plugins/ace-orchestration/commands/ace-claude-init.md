---
description: Add ACE plugin instructions to project CLAUDE.md (one-time setup)
---

# ACE Claude Init

Initialize ACE plugin instructions in your project's CLAUDE.md file.

## What This Does

Copies the full ACE plugin instructions inline into your project's CLAUDE.md. This ensures Claude always has access to ACE architecture instructions for the automatic learning cycle.

## Instructions for Claude

When the user runs `/ace-claude-init`, follow these steps:

### Step 0: Try Script-Based Initialization (Fast Path)

**NEW in v3.2.36+:** Try the shell script first for token-free, instant execution.

1. **Execute the script:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/ace-claude-init.sh
   ```

2. **Check exit code:**
   - **Exit 0:** Success! Script handled initialization/update
     - Show success message from script output
     - Skip to "Confirm Success" section
     - **Stop here - do NOT proceed to Step 1**

   - **Exit 2:** Fallback needed (file has no HTML markers or complex structure)
     - Continue to Step 1 (LLM-based approach)
     - This is expected for first-time runs on projects without markers

   - **Exit 1:** Error occurred
     - Continue to Step 1 (LLM-based approach as fallback)

3. **When script succeeds (exit 0):**
   - Token usage: **0 tokens** (pure shell script)
   - Execution time: **< 1 second**
   - No further action needed

4. **When script exits with code 2:**
   - This means: File exists but has no HTML markers
   - Fall through to Step 1 for LLM-based handling
   - Token usage: Normal LLM path (~17,000 tokens)

**Script Capabilities:**
- ✅ Creates new CLAUDE.md files (instant)
- ✅ Appends to existing CLAUDE.md without ACE content
- ✅ Updates marker-based ACE sections (v3.2.36+)
- ❌ Cannot handle: Files without HTML markers (uses LLM fallback)

### Step 0a: Interactive Update Menu (NEW in v4.1.14)

**When:** Script exits with code 2 AND output contains JSON with `"status":"update_available"`.

**What to do:**

1. **Parse version info from script output:**
   - Look for JSON output: `{"status":"update_available","current_version":"X.X.X","plugin_version":"Y.Y.Y"}`
   - Extract: `current_version` and `plugin_version`

2. **Show interactive menu using AskUserQuestion:**
   ```javascript
   AskUserQuestion({
     questions: [{
       question: `Your project has ACE v${current_version}, but plugin is v${plugin_version}. Would you like to update?`,
       header: "ACE Update",
       multiSelect: false,
       options: [
         {
           label: "Yes, update now",
           description: `Update to v${plugin_version} (recommended)`
         },
         {
           label: "Show what changed",
           description: "View changelog before deciding"
         },
         {
           label: "No, keep current version",
           description: `Stay on v${current_version}`
         }
       ]
     }]
   })
   ```

3. **Handle user selection:**

   **User selected "Yes, update now":**
   - Run: `${CLAUDE_PLUGIN_ROOT}/scripts/ace-claude-init.sh --update`
   - Display update result
   - Exit successfully

   **User selected "Show what changed":**
   - Run: `${CLAUDE_PLUGIN_ROOT}/scripts/ace-claude-init.sh --show-changes`
   - Display changelog output
   - **Re-show the interactive menu** (same 3 options)
   - User can now choose "Yes" or "No" with full context

   **User selected "No, keep current version":**
   - Tell user: "Keeping ACE v${current_version}. Run `/ace-claude-init` again if you change your mind."
   - Exit successfully

**Benefits:**
- ✅ Token-free changelog preview (~50 tokens vs ~17k)
- ✅ User-friendly interactive workflow
- ✅ Informed decision-making
- ✅ No manual flag typing

**Example Flow:**
```
User runs: /ace-orchestration:ace-claude-init
    ↓
Script detects: v4.1.12 → v4.1.14
Script outputs: {"status":"update_available","current_version":"4.1.12","plugin_version":"4.1.14"}
Script exits: code 2
    ↓
Claude shows menu:
  [1] Yes, update now
  [2] Show what changed  ← User selects this
  [3] No, keep current
    ↓
Claude runs: --show-changes
Claude displays:
  ## [4.1.14] - 2025-01-06
  ### Fixed
  - Missing interactive menu features...
    ↓
Claude re-shows menu:
  [1] Yes, update now  ← User selects this
  [2] Show what changed
  [3] No, keep current
    ↓
Claude runs: --update
Claude shows: ✅ Updated to v4.1.14
```

### Step 1: Read Plugin CLAUDE.md (LLM Fallback Path)

Read the full ACE plugin CLAUDE.md file:
```
~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md
```

This file contains ~344 lines of ACE architecture documentation (includes v3.2.8 MANDATORY section + trajectory format fix).

### Step 2: Check for Project CLAUDE.md

Check if CLAUDE.md exists in the project root:
- If it exists, read it first to check for existing ACE content
- If it doesn't exist, you'll create it

### Step 3: Check if ACE Already Added & Version Detection

Look for the ACE content marker in the project's CLAUDE.md:
```markdown
# ACE Orchestration Plugin - Automatic Learning Cycle
```

**If this header already exists:**

1. **Detect existing version** by searching for version pattern in project CLAUDE.md:
   - **Optimized:** Check line 93 specifically: `## 🔄 Complete Automatic Learning Cycle (v3.2.36)`
   - Extract version using pattern: `v([0-9]+\.[0-9]+\.[0-9]+)`
   - Fallback: Search entire file if not found on line 93

2. **Read plugin version** from the plugin CLAUDE.md file:
   - **Optimized:** Check line 93 of plugin template (same location)
   - Fallback: Search entire plugin file if structure differs

3. **Compare versions:**

   **If versions match (up-to-date):**
   - Tell the user ACE is already initialized with current version
   - Show them where it's located in CLAUDE.md
   - Exit successfully (no changes needed)

   **If project version is older than plugin version:**
   - Tell the user ACE content is outdated
   - Show current version vs. plugin version
   - Ask if they want to update: "Your project has ACE v{old}, but plugin is v{new}. Would you like to update? (y/n)"
   - If user says yes → proceed to Step 3a (Update existing ACE content)
   - If user says no → exit successfully

### Step 3a: Update Existing ACE Content (Only if outdated)

If user confirmed they want to update outdated ACE content:

1. **Find ACE section boundaries** in project CLAUDE.md:
   - **Check for HTML markers first:** `<!-- ACE_SECTION_START -->` and `<!-- ACE_SECTION_END -->`
   - If markers present: Use them for exact boundaries (fast, accurate)
   - If markers absent: Use header-based detection:
     - Start: Line with `# ACE Orchestration Plugin - Automatic Learning Cycle`
     - End: Next `#` header at the same level (pattern: `^# [^#]`) OR end of file

2. **Extract non-ACE content:**
   - Content BEFORE the ACE section (if any)
   - Content AFTER the ACE section (if any)

3. **Replace ACE section:**
   - Remove old ACE section completely
   - Insert new plugin CLAUDE.md content at same location
   - Preserve all other content (before and after)

4. **Write updated file:**
   - Reconstruct: `[content before] + [new ACE content] + [content after]`
   - Save to project CLAUDE.md

5. **Confirm update:**
   - Tell user ACE updated from vX.X.X → vY.Y.Y
   - Show what's new in the update
   - Proceed to Step 5 (Confirm Success)

### Step 4: Copy ACE Instructions Inline

If ACE content is NOT present:

**If CLAUDE.md exists:**
- Append to the END of the file (preserve all existing content)
- Add two blank lines first for spacing
- Copy the FULL content of the plugin CLAUDE.md file inline
- DO NOT use `@` reference syntax
- The content should start with: `# ACE Orchestration Plugin - Automatic Learning Cycle`

**If CLAUDE.md doesn't exist:**
- Create it with the full ACE plugin CLAUDE.md content
- Copy all ~344 lines of content from the plugin file (includes MANDATORY section + trajectory format fix)

### Step 5: Confirm Success

After adding:
- Read the updated CLAUDE.md to verify
- Show the user a confirmation message
- Confirm ACE instructions are now available inline
- Explain what this enables (automatic learning cycle)

## What Gets Added

The full ACE plugin CLAUDE.md content (~344 lines) is copied inline, which contains:

- 🚨 **MANDATORY: ACE Skill Usage Rules** (v3.2.8+) - Explicit, non-negotiable skill invocation instructions
- 🔄 **Complete automatic learning cycle** explanation
- 🤖 **How skills work** (retrieval before tasks, learning after tasks)
- 🎯 **When to trigger** ACE features (implement, debug, refactor, etc.)
- 📊 **Architecture overview** (Generator → Reflector → Curator → Playbook)
- 🔧 **MCP tools reference** for manual control
- 📁 **Playbook structure** (4 sections: strategies, snippets, troubleshooting, APIs)

## Why This is Needed

**Problem:** Skills are model-invoked and load instructions ONLY when triggered. This means:
- ❌ Claude doesn't know about the ACE cycle until a skill activates
- ❌ No standing context about when to use ACE features
- ❌ Missing architecture overview

**Solution:** Copying ACE instructions inline into project CLAUDE.md provides:
- ✅ Always-on context about the ACE system
- ✅ Clear trigger words for skills (implement, debug, refactor)
- ✅ Complete understanding of the automatic learning cycle
- ✅ Complementary to skills (general context + specific tools)
- ✅ Full content always available (no reference dependency)

## When to Use

### ✅ Required For:
- **Full ACE cycle** - Retrieval + Learning working together
- **Optimal skill triggering** - Claude knows when to invoke skills
- **Architecture awareness** - Claude understands the system

### ⚠️ One-Time Setup (With Version Updates):
- Run once per project for initial setup
- Safe to run multiple times (checks for existing content)
- **Auto-detects version** - offers to update if outdated
- Run again after plugin updates to get new features
- No manual editing needed

## After Running

Once initialized, every Claude session will have:
1. ✅ Your project-specific instructions (existing CLAUDE.md content)
2. ✅ ACE plugin instructions (copied inline, ~344 lines with MANDATORY section + trajectory format fix)
3. ✅ Skills available for automatic invocation
4. ✅ Explicit skill invocation rules (YOU MUST use skills for qualifying tasks)

**Test it:**
- Try a coding task: "Implement JWT authentication"
- Watch for ACE Playbook Retrieval skill to auto-invoke
- Complete the task and watch ACE Learning skill capture feedback

## Complementary Commands

- `/ace-orchestration:ace-configure` - Set up ACE server connection (REQUIRED FIRST!)
- `/ace-orchestration:ace-status` - Check playbook statistics
- `/ace-orchestration:ace-bootstrap` - Bootstrap playbook from git history (optional)
- `/ace-orchestration:ace-patterns` - View learned patterns

## Example Workflow

```bash
# 1. Install ACE plugin
# 2. Restart Claude Code

# 3. Configure ACE server connection (REQUIRED!)
/ace-orchestration:ace-configure

# 4. Initialize ACE in project (one-time)
/ace-orchestration:ace-claude-init

# 5. Optionally bootstrap from git history
/ace-orchestration:ace-bootstrap --commits 100 --days 30

# 6. Verify setup
/ace-orchestration:ace-status

# 7. Start coding - ACE learns automatically!
# "Implement user authentication"
# → ACE Playbook Retrieval skill auto-invokes
# → Claude implements with learned patterns
# → ACE Learning skill captures new insights
```

## Safety Features

### Non-Destructive:
- ✅ Never overwrites existing content
- ✅ Always appends to end of file
- ✅ Checks for duplicates before adding
- ✅ Preserves all user customizations

### Idempotent & Version-Aware:
- ✅ Safe to run multiple times
- ✅ Detects existing ACE content
- ✅ Compares versions automatically
- ✅ Offers to update when outdated
- ✅ No duplicate entries

### Transparent:
- ✅ Shows what was added
- ✅ Explains why it's needed
- ✅ User can inspect/remove manually if desired

## Manual Removal (if needed)

If the user wants to remove ACE instructions:

1. Open CLAUDE.md in the project root
2. Find the section starting with: `# ACE Orchestration Plugin - Automatic Learning Cycle`
3. Delete all ACE content (~344 lines)

ACE skills will still work, but won't have the always-on architectural context.

## See Also

- Project CLAUDE.md documentation: https://docs.claude.com/en/docs/claude-code/memory
- ACE plugin README: `~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/README.md`
- Skills guide: https://docs.claude.com/en/docs/claude-code/skills
