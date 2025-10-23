---
description: Add ACE plugin instructions to project CLAUDE.md (one-time setup)
---

# ACE Claude Init

Initialize ACE plugin instructions in your project's CLAUDE.md file.

## What This Does

Adds a reference to the ACE plugin's CLAUDE.md file in your project's CLAUDE.md. This ensures Claude always has access to ACE architecture instructions for the automatic learning cycle.

## Instructions for Claude

When the user runs `/ace-claude-init`, follow these steps:

### Step 1: Check for CLAUDE.md

Check if CLAUDE.md exists in the project root:
- If it exists, read it first
- If it doesn't exist, you'll create it

### Step 2: Check if ACE Already Added

Look for the marker comment in CLAUDE.md:
```markdown
## ACE Plugin Instructions
@~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md
```

If this reference already exists:
- Tell the user ACE is already initialized
- Show them where it's located in CLAUDE.md
- Exit successfully (no changes needed)

### Step 3: Add ACE Reference Safely

If ACE reference is NOT present:

**If CLAUDE.md exists:**
- Append to the END of the file (preserve all existing content)
- Add two blank lines first for spacing
- Add the section:

```markdown

## ACE Plugin Instructions
@~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md
```

**If CLAUDE.md doesn't exist:**
- Create it with a basic header plus ACE reference:

```markdown
# Project Instructions

## ACE Plugin Instructions
@~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md
```

### Step 4: Confirm Success

After adding:
- Read the updated CLAUDE.md to verify
- Show the user the last ~10 lines of CLAUDE.md
- Confirm ACE instructions are now available
- Explain what this enables (automatic learning cycle)

## What Gets Added

The `@` syntax tells Claude to include the ACE plugin's CLAUDE.md file, which contains:

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

**Solution:** Adding ACE CLAUDE.md reference provides:
- ✅ Always-on context about the ACE system
- ✅ Clear trigger words for skills (implement, debug, refactor)
- ✅ Complete understanding of the automatic learning cycle
- ✅ Complementary to skills (general context + specific tools)

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
2. ✅ ACE plugin instructions (via @ reference)
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

```markdown
# Open CLAUDE.md and delete these lines:

## ACE Plugin Instructions
@~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md
```

ACE skills will still work, but won't have the always-on architectural context.

## See Also

- Project CLAUDE.md documentation: https://docs.claude.com/en/docs/claude-code/memory
- ACE plugin README: `~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/README.md`
- Skills guide: https://docs.claude.com/en/docs/claude-code/skills
