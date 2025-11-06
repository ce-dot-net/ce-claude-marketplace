# Changelog

All notable changes to the ACE Orchestration Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.1.10] - 2025-11-06

### Fixed
- Removed `agents` field from plugin.json to prevent duplicate agent registration
  - Root cause: agents/ directory is auto-discovered, explicit field caused duplicates
  - Impact: Each agent now appears once in /agents list
  - Impact: Hook now fires once instead of twice per trigger
- Removed `agents` field from plugin.template.json for consistency
- Updated ace-retrieval.md and ace-learning.md agent instructions
  - Clarified agents are manually invoked by main Claude (not automatic)
  - Added workflow explanation: hook reminder → manual Task tool invocation
  - Reflects reality: Auto-invoke unreliable in Claude Code per community feedback

### Technical Details
- Claude Code auto-discovers agents/ directory (no plugin.json field needed)
- Per docs: "Custom paths supplement default directories" = duplicates if both exist
- Manual invocation via Task tool works reliably when hook reminds main Claude

## [4.1.7] - 2025-11-05

### ✨ Feature: JSON Hook Output + SubagentStop Hook

**Added**: JSON-based hook output format and SubagentStop hook for complete ACE workflow coverage.

#### Problems Solved

1. **Hook Output Visibility (GitHub Issue #4084)**
   - **Problem**: v4.1.6 hooks used printf but output wasn't visible in Claude Code UI
   - **Root cause**: Plain stdout doesn't display properly (Claude Code expects JSON)
   - **Solution**: JSON output with systemMessage (visible to user) + additionalContext (injected into Claude's context)

2. **No Reminder After Subagent Completion**
   - **Problem**: Users forgot to invoke ACE Learning after subagent work completed
   - **Solution**: SubagentStop hook fires after ANY subagent completes

#### Changes

**New Files**:
- `hooks/user-prompt-reminder.py` - UserPromptSubmit hook with JSON output (commit f540dd9)
- `hooks/subagent-stop-reminder.py` - SubagentStop hook with JSON output (commit 690cfc0)

**Modified Files**:
- `hooks/hooks.json` - Configured both hooks with ${CLAUDE_PLUGIN_ROOT} variable
  - UserPromptSubmit: Triggers on 45+ action keywords (implement, build, create, fix, debug, etc.)
  - SubagentStop: Triggers after any subagent completion

**Hook Output Format**:
```json
{
  "systemMessage": "🔍 ACE: Use Retrieval → Work → Learning",
  "additionalContext": "REMINDER: Before starting implementation..."
}
```

**Benefits**:
- `systemMessage`: Visible to user in Claude Code UI
- `additionalContext`: Injected into Claude's context (actual reminder)
- Clean separation of user-facing vs Claude-facing content

#### Workflow Coverage

**Complete ACE Workflow**:
1. **UserPromptSubmit**: "🔍 ACE: Use Retrieval → Work → Learning workflow"
2. User does work (may invoke ACE Retrieval subagent)
3. **SubagentStop**: "📚 ACE Learning: Capture lessons after subagent completion"
4. User invokes ACE Learning subagent

**Result**: Complete before + after coverage for ACE workflow!

#### Testing

✅ Both Python scripts output valid JSON
✅ UserPromptSubmit tested with 45+ trigger words
✅ SubagentStop tested with mock subagent input
✅ hooks.json is valid JSON
✅ systemMessage visible in transcript mode (Ctrl-R)

#### Migration

- **From v4.1.6**: Automatic - restart Claude Code or reload plugin
- **Impact**: Hooks now properly display in UI and inject context
- **Breaking Changes**: None

#### Technical Notes

**Why Python instead of Bash?**
- Bash string escaping is error-prone (see v4.1.5, v4.1.6 issues)
- Python json.dumps() ensures valid JSON
- Easier to maintain and extend

**Hook Variables**:
- `${CLAUDE_PLUGIN_ROOT}`: Absolute path to plugin directory
- Allows hooks to work regardless of where Claude Code is run

**Hook Safety**:
- Single non-cascading hooks (learned from v3.x Hook Storm Bug #3523)
- UserPromptSubmit triggers once per user prompt
- SubagentStop triggers once per subagent completion

---

## [4.1.6] - 2025-11-05

### 🐛 Hotfix: UserPromptSubmit Hook Output Fix

**Critical Bug**: UserPromptSubmit hook was not outputting properly, preventing workflow reminders from appearing in Claude's context.

#### The Problem
- Hook used `echo '...\n...'` with single quotes
- Single quotes in shell don't interpret escape sequences
- Hook was outputting literal backslash-n characters: `\n`
- Result: No formatted output, no context injection

#### The Solution
Changed from `echo` to `printf` with properly escaped newlines:
- Before: `echo '\n🔍 ACE...'` (outputs literal `\n`)
- After: `printf '\\n🔍 ACE...'` (outputs actual newlines)

#### Changed
- **Fixed**: `hooks/hooks.json` - Replaced echo with printf (commit 9b0c5a0)

#### Testing
- ✅ Command executes without errors
- ✅ Newlines render correctly
- ✅ Output properly formatted

#### Migration
- **From v4.1.5**: Automatic - restart Claude Code or reload plugin
- **Impact**: Hook now properly injects workflow reminders into Claude's context
- **Breaking Changes**: None

---

## [4.1.5] - 2025-11-05

### ✨ Feature: UserPromptSubmit Hook for ACE Workflow Reminders

**Added**: Lightweight UserPromptSubmit hook that reminds Claude to use ACE subagents when trigger words are detected.

#### The Problem
- **Issue**: ACE subagents (Retrieval & Learning) were not triggering reliably despite strong CLAUDE.md documentation
- **Root cause**: CLAUDE.md guidance is passive - can be ignored without consequence
- **Community feedback**: Multiple reports of subagents not auto-triggering (Reddit, GitHub)

#### The Solution
Introduced a single, minimal UserPromptSubmit hook that:
- ✅ Fires when user message contains trigger words (check, verify, implement, build, fix, debug, refactor, etc.)
- ✅ Shows reminder about ACE sequential workflow: Retrieval → Work → Learning
- ✅ Non-cascading design (single hook, no exponential multiplication)
- ✅ Task-based (fires once per user message, not per tool)
- ✅ Optional (users can delete hooks/ directory if desired)

#### Changed
- **Added**: `hooks/hooks.json` with UserPromptSubmit configuration
- **Updated**: `plugin.json` - Added hooks field pointing to `./hooks/hooks.json`
- **Updated**: `plugin.template.json` - Added hooks field
- **Updated**: Description mentions "Lightweight hook for workflow reminders"

#### Trigger Words (Broad Matching)
**Planning/Investigation**: check, verify, validate, review, analyze, investigate, inspect, examine, explore, assess, evaluate, understand
**Design**: plan, design, architect, outline, structure
**Implementation**: implement, build, create, add, develop, write, code
**Modification**: update, modify, change, edit, enhance, extend, revise, improve
**Debugging**: fix, debug, troubleshoot, resolve, diagnose, solve
**Refactoring**: refactor, optimize, restructure
**Integration**: integrate, connect, setup, configure, install, deploy
**Decision Making**: choose, decide, select, compare, consider

#### Why This Design is Safe
**Learned from v3.x Hook Storm Bug (Issue #3523)**:
- ❌ v3.x had multiple cascading hooks: SessionStart + PreToolUse + PostToolUse + UserPromptTrigger
- ❌ Hooks triggered other hooks → exponential multiplication → crash
- ✅ v4.1.5 has ONE hook: UserPromptSubmit only
- ✅ Fires once per user message (not per tool)
- ✅ Shows reminder (doesn't auto-invoke subagents which could cascade)
- ✅ Non-cascading by design

#### User Benefits
- ✅ **Enforcement**: Visible reminder when trigger words detected
- ✅ **Non-intrusive**: Brief one-liner, not blocking workflow
- ✅ **Asymmetric triggering**: Broad triggers for planning AND implementation
- ✅ **Sequential workflow**: Reminds about full cycle (Retrieval → Work → Learning)
- ✅ **Optional**: Delete `hooks/` directory to disable

#### Disabling the Hook
Users can disable by:
1. Delete `~/.claude/plugins/.../ace-orchestration/hooks/` directory
2. Or edit `hooks.json` to remove/modify matchers

#### Migration
- **From v4.1.4**: Automatic - hook activates on next session
- **No breaking changes**: 100% backward compatible
- **Opt-out available**: Users can delete hooks directory

---

## [4.1.4] - 2025-11-04

### ⬆️ Dependency Update: MCP Client v3.8.2

**Updated**: MCP client dependency from v3.8.1 → v3.8.2

#### Changed
- `.mcp.json` - Updated `@ce-dot-net/ace-client` from v3.8.1 to v3.8.2

#### Impact
✅ Latest MCP client with improvements and bug fixes
✅ No configuration changes required
✅ 100% backward compatible

---

## [4.1.3] - 2025-11-04

### 🐛 Bug Fix: Missing ACE_ORG_ID in Multi-Org Project Config

**Fixed**: `/ace-configure` command was not writing `ACE_ORG_ID` to project's `.claude/settings.json` file when configuring multi-org projects.

#### The Issue
When running `/ace-configure` in a project that belongs to a multi-org setup:
1. ✅ Command correctly verified token and found project in organization
2. ✅ Command correctly added organization to global config (`~/.config/ace/config.json`)
3. ❌ **Command forgot to write `ACE_ORG_ID` to project config** (`.claude/settings.json`)

**Result**: MCP client received undefined `${ACE_ORG_ID}` environment variable, causing org resolution to fail.

**Expected**:
```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_374e70fce04f703c",
    "ACE_ORG_ID": "org_34fYIlitYk4nyFuTvtsAzA6uUJF"
  }
}
```

**Actual** (before fix):
```json
{
  "env": {
    "ACE_PROJECT_ID": "prj_374e70fce04f703c"
  }
}
```

#### The Fix
Updated `commands/ace-configure.md` Step 5 (project config save logic):
- When `MATCHING_ORG` is found (project belongs to an org), write BOTH `ACE_PROJECT_ID` and `ACE_ORG_ID`
- When creating new settings file, conditionally include `ACE_ORG_ID` if multi-org
- When merging with existing settings, conditionally add `ACE_ORG_ID` if multi-org
- Updated misleading comment "auto-resolved" → "set automatically for multi-org projects"

#### Files Changed
- `commands/ace-configure.md` - Fixed project config save logic (lines 591-633)

#### Impact
✅ Multi-org projects now get proper `ACE_ORG_ID` in `.claude/settings.json`
✅ MCP client can correctly resolve organization from environment variable
✅ Single-org projects unaffected (only `ACE_PROJECT_ID` as before)
✅ 100% backward compatible

#### Testing
After updating, run `/ace-configure` in a multi-org project and verify `.claude/settings.json` contains both environment variables.

---

## [4.1.2] - 2025-11-04

### 📚 Enhanced Subagent Triggering Documentation

**Issue**: Community reports ACE subagents not auto-triggering as reliably as expected across different use cases.

**Solution**: Strengthened documentation and instructions without adding hooks (conservative approach to maintain v4.0.0 architecture).

#### Enhanced

- **CLAUDE.md Template**: Added explicit "🚨 ACE Subagent Workflow" section with:
  - Clear BEFORE/AFTER workflow reminders
  - Comprehensive trigger keyword lists for both subagents
  - Sequential workflow diagram showing Retrieval → Work → Learning cycle
  - Usage examples (e.g., "Before implementing JWT auth, invoke ACE Retrieval")
  - Proactive usage reminders

- **Subagent Descriptions**: Strengthened with "MUST BE USED" and "ALWAYS invoke" emphasis
  - `agents/ace-retrieval.md`: Enhanced description with "FIRST before beginning substantial work"
  - `agents/ace-learning.md`: Enhanced description with "LAST after finishing implementation"
  - Added specific task types in descriptions (implementation, debugging, refactoring, architectural)

- **README.md**: New "🎯 Subagent Triggering Best Practices" section with:
  - Automatic vs explicit invocation patterns
  - When subagents should/shouldn't trigger (with ✅/❌ checklists)
  - Sequential workflow explanation (not parallel)
  - Troubleshooting guide for triggering issues
  - Links to detailed debugging steps

#### Rationale

Conservative approach to improve triggering through better documentation rather than re-introducing hooks (removed in v4.0.0 due to Issue #3523). Community evidence (Reddit, GitHub issues) shows subagents often don't auto-trigger, but we're testing if strengthened docs can solve this before adding hooks back.

**If v4.1.2 proves insufficient**, v4.2.0 may introduce lightweight reminder hooks based on community feedback.

#### Files Changed

- `CLAUDE.md` - Added "ACE Subagent Workflow" section (~40 lines), updated version markers
- `agents/ace-retrieval.md` - Enhanced description with stronger trigger language
- `agents/ace-learning.md` - Enhanced description with stronger trigger language
- `README.md` - Added "Subagent Triggering Best Practices" section (~100 lines)
- `CHANGELOG.md` - This entry

#### No Breaking Changes

✅ 100% backward compatible - documentation improvements only
✅ No code changes, no hooks, no architecture modifications
✅ Zero migration required

#### Testing Plan

After release, monitor:
1. User feedback on triggering reliability
2. ACE server metrics (ace_get_playbook and ace_learn call frequency)
3. Community response to documentation improvements

---

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

