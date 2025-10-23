---
description: Add ACE plugin instructions to project CLAUDE.md (one-time setup)
---

# ACE Claude Init

Initialize ACE plugin instructions in your project's CLAUDE.md file.

## What This Does

Copies the full ACE plugin instructions inline into your project's CLAUDE.md. This ensures Claude always has access to ACE architecture instructions for the automatic learning cycle.

## Instructions for Claude

When the user runs `/ace-claude-init`, follow these steps:

### Step 1: Read Plugin CLAUDE.md

Read the full ACE plugin CLAUDE.md file:
```
~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md
```

This file contains ~289 lines of ACE architecture documentation.

### Step 2: Check for Project CLAUDE.md

Check if CLAUDE.md exists in the project root:
- If it exists, read it first to check for existing ACE content
- If it doesn't exist, you'll create it

### Step 3: Check if ACE Already Added

Look for the ACE content marker in the project's CLAUDE.md:
```markdown
# ACE Orchestration Plugin - Automatic Learning Cycle
```

If this header already exists:
- Tell the user ACE is already initialized
- Show them where it's located in CLAUDE.md
- Exit successfully (no changes needed)

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
- Copy all ~289 lines of content from the plugin file

### Step 5: Confirm Success

After adding:
- Read the updated CLAUDE.md to verify
- Show the user a confirmation message
- Confirm ACE instructions are now available inline
- Explain what this enables (automatic learning cycle)

## What Gets Added

The full ACE plugin CLAUDE.md content (~289 lines) is copied inline, which contains:

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

### ⚠️ One-Time Setup:
- Run once per project
- Safe to run multiple times (checks for existing reference)
- No manual editing needed

## After Running

Once initialized, every Claude session will have:
1. ✅ Your project-specific instructions (existing CLAUDE.md content)
2. ✅ ACE plugin instructions (copied inline, ~289 lines)
3. ✅ Skills available for automatic invocation

**Test it:**
- Try a coding task: "Implement JWT authentication"
- Watch for ACE Playbook Retrieval skill to auto-invoke
- Complete the task and watch ACE Learning skill capture feedback

## Complementary Commands

- `/ace-bootstrap` - Bootstrap playbook from git history (optional)
- `/ace-status` - Check playbook statistics
- `/ace-patterns` - View learned patterns
- `/ace-configure` - Set up ACE server connection

## Example Workflow

```bash
# 1. Install ACE plugin
# 2. Restart Claude Code

# 3. Initialize ACE in project (one-time)
/ace-claude-init

# 4. Optionally bootstrap from git history
/ace-bootstrap --commits 100 --days 30

# 5. Start coding - ACE learns automatically!
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

### Idempotent:
- ✅ Safe to run multiple times
- ✅ Detects existing reference
- ✅ No duplicate entries

### Transparent:
- ✅ Shows what was added
- ✅ Explains why it's needed
- ✅ User can inspect/remove manually if desired

## Manual Removal (if needed)

If the user wants to remove ACE instructions:

1. Open CLAUDE.md in the project root
2. Find the section starting with: `# ACE Orchestration Plugin - Automatic Learning Cycle`
3. Delete all ACE content (~289 lines)

ACE skills will still work, but won't have the always-on architectural context.

## See Also

- Project CLAUDE.md documentation: https://docs.claude.com/en/docs/claude-code/memory
- ACE plugin README: `~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/README.md`
- Skills guide: https://docs.claude.com/en/docs/claude-code/skills
