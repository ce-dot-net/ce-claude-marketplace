# Changelog

All notable changes to the ACE Orchestration Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.1.1] - 2025-11-04

### 🐛 Bug Fix: Single-Org Interactive Menu

**Fixed**: Missing interactive menu when running `/ace-configure` with existing single-org configuration.

#### The Issue
- Users upgrading from v4.0.x to v4.1.0 had existing single-org configs
- Running `/ace-configure` detected the config but showed no menu
- Command had menus for fresh install and multi-org mode, but not single-org mode

#### The Fix
Added "Single-Org Mode Decision" menu with 4 options:
1. **Keep current config** - No changes
2. **Update settings** - Modify server URL, token, cache TTL, auto-update
3. **Add another organization** - Convert to multi-org mode
4. **Reconfigure from scratch** - Replace entire configuration

#### Files Changed
- `commands/ace-configure.md` - Added single-org menu flow in Step 4

#### Impact
- ✅ Users can now interact with `/ace-configure` when single-org config exists
- ✅ Smooth upgrade path from v4.0.x to v4.1.x
- ✅ Provides option to convert to multi-org mode

## [4.1.0] - 2025-11-04

### 🌐 NEW FEATURE: Multi-Organization Support

**Manage multiple organizations in a single configuration!**

#### Added

- **Multi-Org Configuration**: New `orgs` object in global config for managing multiple organizations
- **Automatic Org Resolution**: MCP Client auto-resolves organization from project ID
- **Verification Endpoint Integration**: `/api/v1/config/verify` auto-populates org_id, org_name, and projects
- **Multi-Org Flows in `/ace-configure`**:
  - Detect and manage multi-org mode
  - Add new organizations with token verification
  - Validate projects belong to configured organizations
  - Enhanced summary display with org info
- **CLI Argument**: `--org-id` parameter in `.mcp.json` for explicit org selection
- **Helper Functions**:
  - `verify_token()` - Verify API token and fetch org info from server
  - `validate_project_in_orgs()` - Validate project belongs to an organization

#### Changed

- **MCP Client Version**: Updated from v3.8.0 → v3.8.1 (includes multi-org support)
- **Plugin Descriptions**: Updated to mention multi-org support and backward compatibility
- **Configuration Summary**: Shows multi-org status when detected

#### Enhanced

- **🔍 Subagent Visibility**: Added emoji headers for better visual feedback
  - ACE Retrieval: `🔍 [ACE Retrieval] Searching playbook for patterns...`
  - ACE Learning: `📚 [ACE Learning] Analyzing completed work...`
  - Updated all subagent instructions to ALWAYS output these headers
  - Provides colored-background feeling users expect from subagents

#### Documentation

- **README.md**: New "Multi-Organization Support" section with examples
- **ace-configure.md**: Comprehensive multi-org flows and examples
- **CLAUDE.md**: Version markers updated to v4.1.0

#### Backward Compatibility

- ✅ **100% backward compatible** - Single-org configs (v4.0.x and earlier) work unchanged
- ✅ **Zero migration required** - Both single-org and multi-org formats work simultaneously
- ✅ **Fallback token** - Projects not in any org use root-level `apiToken`

#### Requirements

- **MCP Client**: v3.8.1+ (includes `--org-id` support and org auto-resolution)
- **Server API**: `/api/v1/config/verify` endpoint for token verification

#### Use Cases

Perfect for:
- 🧑‍💼 Consultants working with multiple clients
- 🏢 Developers switching between company and personal projects
- 👥 Teams managing multiple organizational accounts

### Files Changed

**Core Configuration**:
- `.mcp.json` - Added `--org-id` CLI argument for v3.8.1 client

**Commands**:
- `commands/ace-configure.md` - Multi-org detection, verification, validation flows

**Subagents** (Visibility Enhancement):
- `agents/ace-retrieval.md` - Added mandatory emoji header `🔍 [ACE Retrieval]`
- `agents/ace-learning.md` - Added mandatory emoji header `📚 [ACE Learning]`

**Version Files**:
- `.claude-plugin/plugin.json` - v4.1.0
- `.claude-plugin/plugin.template.json` - v4.1.0
- `../../.claude-plugin/marketplace.json` - v4.1.0

**Documentation**:
- `README.md` - Multi-org documentation section
- `CLAUDE.md` - Version markers v4.1.0
- `CHANGELOG.md` - This file

## [4.0.0] - 2025-11-04

### 🚀 MAJOR ARCHITECTURAL REFACTORING - Subagent Architecture

**Complete replacement of hooks + skills with Claude Code CLI subagents.**

This is a **BREAKING CHANGE** release that fundamentally restructures how ACE works.

### 🔍 Why This Refactoring?

**Problems Solved**:

1. **Hook Storm Bug (Issue #3523)**
   - Progressive hook duplication: 1x → 2x → 4x → 8x
   - Caused session crashes and resource exhaustion
   - Affected v3.3.11 (SubagentStop hook) and v3.3.12 (Bash logging hook)
   - **Solution**: Complete removal of ALL hooks

2. **Skill Blocking Problem**
   - ACE skills with 35+ trigger keywords monopolized Claude's attention
   - Prevented other user plugins/skills from executing
   - User report: "When ACE skills trigger, other skills don't run"
   - **Solution**: Subagents run in separate contexts (no blocking)

3. **Prescriptive vs Educational**
   - CLAUDE.md was 436 lines of "MANDATORY", "CRITICAL", "DO NOT SKIP" commands
   - Did not align with ACE Research Paper (describes ACE as "optional enhancement")
   - Created tunnel vision and aggressive triggering (80-90% of requests)
   - **Solution**: Educational 149-line CLAUDE.md, transparent operation

### ✅ New Architecture: Subagents

**Replaced**:
- ❌ 6 hooks (SessionStart, UserPromptSubmit, PostToolUse matchers)
- ❌ 2 skills (ace-playbook-retrieval, ace-learning)
- ❌ 6 hook scripts (session-start, user-prompt-trigger, inject-retrieval, remind-learning, ensure-gitignore, check-ace-version)

**With**:
- ✅ 2 subagents in `agents/` directory:
  - `ace-retrieval.md` - Retrieves patterns before work (calls ace_get_playbook, ace_search)
  - `ace-learning.md` - Captures patterns after work (calls ace_learn)

### 🎯 Benefits

1. **No More Hook Storms**
   - Zero hooks = Issue #3523 cannot occur
   - No progressive duplication
   - No session crashes from resource exhaustion

2. **No More Skill Blocking**
   - Subagents run in separate context windows
   - Other user plugins/skills work normally
   - Claude Code documentation confirms: "separate context windows prevent conversation pollution"

3. **Transparent Operation**
   - Users see: `[ACE Retrieval] Searching playbook...`
   - Users see: `[ACE Learning] Captured 3 new patterns`
   - Clear understanding of what ACE is doing

4. **User Controllable**
   - Easy to disable: Delete agent files or tell Claude "Don't use ACE subagents"
   - No hidden mandatory triggering
   - Optional, not forced

5. **Simplified Codebase**
   - CLAUDE.md: 436 lines → 149 lines (66% reduction)
   - Removed entire `hooks/` and `scripts/` directories
   - Removed entire `skills/` directory
   - 2 subagent files vs 6 hooks + 2 skills + 7 scripts

### 📋 Breaking Changes

**⚠️ IMPORTANT**: Users upgrading from v3.x **MUST** re-initialize their projects.

**Removed**:
- All hooks (hooks.json and hooks/ directory deleted)
- All skills (skills/ directory deleted)
- Hook scripts (6 scripts deleted from scripts/ directory)
- Infrastructure automation:
  - Auto .gitignore management (was in SessionStart hook)
  - Auto version checking (was in SessionStart hook)
  - Auto-update feature (removed entirely - manual only)

**Kept**:
- `/ace-claude-init` command still works (uses scripts/ace-claude-init.sh)
- All slash commands unchanged (view, configure, bootstrap, etc.)

**Migration Steps**:
1. Disable old plugin version: `/plugin disable ace-orchestration`
2. Update marketplace: `git pull` (or re-install from marketplace)
3. Enable new version: `/plugin enable ace-orchestration`
4. Re-run in projects: `/ace-orchestration:ace-claude-init` (updates CLAUDE.md to v4.0.0)
5. Bootstrap patterns (optional): `/ace-orchestration:ace-bootstrap --mode hybrid --thoroughness deep`

### 📁 Changed Files

**Deleted**:
- `hooks/hooks.json` (all 6 hooks removed)
- `hooks/` directory (entire directory removed)
- `skills/` directory (both skills removed)
- Hook scripts: `session-start-ace-context.sh`, `user-prompt-ace-trigger-check.sh`, `inject-ace-retrieval-context.sh`, `remind-ace-learning-after-edit.sh`, `ensure-gitignore.sh`, `check-ace-version.sh`

**Kept (still needed by commands)**:
- `scripts/ace-claude-init.sh` (used by `/ace-claude-init` command)
- `scripts/lib/section-parser.sh` (library for ace-claude-init.sh)

**Created**:
- `agents/ace-retrieval.md` - Subagent for pattern retrieval
- `agents/ace-learning.md` - Subagent for pattern capture

**Modified**:
- `CLAUDE.md` - Rewritten from 436→149 lines, educational (not prescriptive)
- `.claude-plugin/plugin.json` - Bumped to v4.0.0, removed hooks field, updated description
- `.claude-plugin/marketplace.json` - Bumped to v4.0.0, updated description
- `CHANGELOG.md` - Added v4.0.0 entry (this)

**To Be Updated**:
- `README.md` - Architecture documentation updates
- `/ace-doctor` command - Health checks for subagent architecture

### 🔧 Technical Details

**Subagent Invocation**:
- Automatic: Claude recognizes task patterns from subagent `description` field
- Triggers: implement, build, create, fix, debug, refactor, optimize, integrate, architect, test, deploy, etc.
- Same keywords as v3.x skills, but in separate contexts (no blocking)

**MCP Tool Compatibility**:
- Subagents call same MCP tools: ace_get_playbook, ace_search, ace_learn, etc.
- MCP client version unchanged (@ce-dot-net/ace-client@3.8.0)
- Server-side architecture unchanged (Reflector → Curator → Merge)

**Precedence**:
- Project-level agents (.claude/agents/) override plugin agents
- Users can customize subagent behavior by creating project-level overrides

### 📚 Documentation

**Updated**:
- CLAUDE.md now explains subagents as "optional and controllable"
- Removed "MANDATORY", "CRITICAL", "DO NOT SKIP" language
- Added "Disabling ACE" section with clear instructions
- Added example workflow showing transparent operation

**See Also**:
- README.md for complete architecture documentation
- `/ace-orchestration:ace-doctor` for health diagnostics
- Claude Code docs: https://docs.claude.com/en/docs/claude-code/sub-agents

### 🙏 Credits

**User Feedback**:
- Report: "When ACE skills trigger based on our list of triggers, other skills (that the user might have) are not running"
- Request: "Refactoring is okay! Let's not be stubborn and stay on what we have currently implemented!"

**Research**:
- ACE Research Paper (arXiv:2510.04618v1): Describes ACE as optional enhancement, not mandatory system
- Claude Code Issue #3523: Progressive hook duplication bug
- Claude Code CLI Subagents documentation: Confirmed subagents can call MCP tools

---

## [3.3.12] - 2025-11-04

### 🚨 CRITICAL BUG FIX - Second Hook Storm Resolved

**Issue**: Bash logging hook caused session crashes on both auto-approve and manual approve operations.

### 🔍 Root Cause Analysis

**The Problem**:
- PostToolUse (Bash) hook logged every Bash command to `~/.ace/execution_log.jsonl`
- When user approves multiple operations (auto or manual), many Bash commands execute rapidly
- Claude Code Issue #3523 (progressive hook duplication) causes hooks to multiply: 1x → 2x → 4x → 8x
- Execution log bloated to **6,146 entries (396KB)** in single session
- Session crashes from resource exhaustion

**Evidence from Live Session**:
- SessionStart hook fired **8 times** (should be 1x)
- Same pattern affects ALL hooks (SessionStart, UserPromptSubmit, PostToolUse)
- Bash hook multiplied 4-8x per command = thousands of log writes
- Crashes on both auto-approve AND manual approve

### ✅ Solution: Remove Bash Logging Hook

**Why Remove**:
1. ✅ **Debug-Only Purpose**: Hook was only for debugging, not critical functionality
2. ✅ **Same Pattern as v3.3.11**: Hook duplication bug (#3523) affects ALL PostToolUse hooks
3. ✅ **User Impact**: Crashes on approve operations unacceptable
4. ✅ **Alternative**: Users can check command history via Claude Code's built-in transcript

### 📋 Changes

**Removed**:
- PostToolUse (Bash) hook from `hooks/hooks.json` (lines 60-68)
- Execution log accumulation mechanism

**Modified Files**:
- `hooks/hooks.json` - Removed Bash logging hook
- `README.md` - Removed Bash hook documentation
- `CHANGELOG.md` - Added v3.3.12 entry

**Version Updates**:
- All metadata files bumped to v3.3.12

### 🎯 Remaining Hooks (4 Active)

**Before Work (ace-playbook-retrieval)**:
1. ✅ SessionStart Hook
2. ✅ UserPromptSubmit Hook
3. ✅ PostToolUse (ExitPlanMode) Hook

**After Work (ace-learning)**:
4. ✅ PostToolUse (Edit|Write) Hook

**Note**: While Claude Code v2.0.32 fixes some hook issues, Issue #3523 (progressive duplication) still exists. We minimize risk by keeping only essential hooks.

### 📊 Impact

| Metric | Before v3.3.12 | After v3.3.12 |
|--------|----------------|---------------|
| Bash hook fires | 100s-1000s/session | 0 (removed) |
| Execution log bloat | 396KB, 6,146 entries | None |
| Crashes on approve | Frequent | Fixed |
| Hook storm risk | HIGH | Minimal |

### 🔗 References

- **Claude Code Issue #3523**: Progressive hook duplication bug (observed live: SessionStart fired 8x)
- **Claude Code v2.0.32**: Fixes some hook issues but #3523 persists
- **v3.3.11 Fix**: SubagentStop hook removal (same root cause)

---

