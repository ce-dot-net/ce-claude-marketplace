# Changelog

All notable changes to the ACE Orchestration Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.2.21] - 2025-10-29

### Fixed
- **CRITICAL**: Skills now ACTUALLY auto-invoke using SessionStart hook enforcement
  - Added `hooks/ace-skill-enforcement.sh` - Injects MANDATORY skill protocol into every session's context
  - SessionStart hook output gets added to Claude's context BEFORE any user messages
  - This is STRONGER than CLAUDE.md checkpoints (which can be ignored)
  - This is STRONGER than skill descriptions (which are behavioral suggestions)
  - NOW: Context includes system-level MANDATORY instructions that cannot be bypassed

### Why Previous Fixes Failed
- v3.2.19: Added checkpoints to CLAUDE.md - behavioral reminders, can be ignored
- v3.2.20: Added checkpoints to both skills - still behavioral, not enforced
- **Root Cause**: Model-invoked skills with behavioral reminders are NOT reliable
- **Real Solution**: SessionStart hook injects MANDATORY protocol into system context

### Added
- `hooks/ace-skill-enforcement.sh` - Session start enforcement script
  - Outputs MANDATORY skill invocation protocol
  - Gets added to Claude's context at session start (per hooks docs)
  - Lists all trigger keywords explicitly
  - Explains consequences of skipping skills

### Changed
- Updated `hooks/hooks.json` - Added skill enforcement hook as first SessionStart hook
- Updated `hooks/ace-version-check.sh` - Use `${CLAUDE_PLUGIN_ROOT}` instead of hardcoded path
- SessionStart hooks now run in order: enforcement → version check

### How It Works Now
1. Session starts
2. SessionStart hook runs ace-skill-enforcement.sh
3. Hook output gets injected into Claude's context (per Claude Code hooks spec)
4. Claude sees MANDATORY protocol before processing any user messages
5. Skills MUST be invoked - no longer optional

## [3.2.20] - 2025-10-29

### Fixed
- **CRITICAL**: Restored balance between BEFORE and AFTER skill checkpoints
  - v3.2.19 added checkpoint only for ace-learning (AFTER), creating imbalance
  - ace-playbook-retrieval (BEFORE) was inadvertently de-emphasized
  - Result: Retrieval skill stopped auto-invoking at task start
- Added matching "⚠️ CRITICAL CHECKPOINT" to ace-playbook-retrieval skill
- Added "⚠️ CRITICAL CHECKPOINT - BEFORE STARTING WORK" section to CLAUDE.md
- Renamed existing checkpoint to "⚠️ CRITICAL CHECKPOINT - AFTER COMPLETING WORK" for clarity

### Why This Matters
- **Complete learning cycle requires BOTH skills**: retrieval (before) → execution → learning (after)
- v3.2.19 broke the cycle by over-emphasizing the AFTER skill
- Users reported: "the initial getting pattern skill is not running anymore"
- This fix restores equal emphasis on both timing checkpoints

### Changed
- Updated `CLAUDE.md` with balanced checkpoints (lines 29-38: BEFORE, lines 47-65: AFTER)
- Updated `skills/ace-playbook-retrieval/SKILL.md` with checkpoint section (lines 27-36)

## [3.2.19] - 2025-10-29

### Fixed
- **Critical**: Added explicit checkpoint reminders to ace-learning skill to ensure auto-invocation after every substantial task
- Added "⚠️ CRITICAL CHECKPOINT" section to `skills/ace-learning/SKILL.md` with 3 checkpoint questions
- Added matching checkpoint reminder to `CLAUDE.md` template that gets distributed via `/ace-claude-init`
- Ensures complete learning cycle (retrieval → execution → learning) runs consistently

### Why This Matters
- Previous behavior would sometimes skip learning skill invocation, breaking the ACE learning cycle
- This fix ensures every substantial task completion triggers pattern capture
- Critical for maintaining the self-improving behavior of the ACE framework
- Learning skill should invoke IMMEDIATELY after work completion, BEFORE responding to user

### Changed
- Updated `CLAUDE.md` versions to v3.2.19 (lines 71, 305) to reflect current release

## [3.2.18] - 2025-10-28

### Changed
- **Bootstrap Orchestrator Skill** - Updated to use BootstrapResponse directly from ACE Server v2.9.0
  - Eliminated redundant `ace_status` API call (reduced from 7 to 6 steps)
  - Uses server-calculated `compression_percentage` and `analysis_time_seconds`
  - Simplified API flow: `ace_bootstrap` now returns complete BootstrapResponse
- **API Evolution** - Aligned with ACE Server v2.9.0's new `/bootstrap` endpoint structure
  - Server now calculates compression metrics (was client-side calculation)
  - Added `analysis_time_seconds` to show processing duration
  - More accurate and consistent compression reporting

### Improved
- **Performance** - One fewer API call during bootstrap process
- **Accuracy** - Server-side compression calculation eliminates client-side formula drift

## [3.2.17] - 2025-10-28

### Added
- **Bootstrap Orchestrator Skill** - New skill for intelligent bootstrap reporting
  - Automatically calculates pattern compression percentage (e.g., 158 → 18 = 89% reduction)
  - Shows conditional explanation when compression > 80% (references ACE Research Paper Section 3.2)
  - Displays progress messages during 10-30 second bootstrap analysis
  - Uses actual numbers from `ace_status` API, not hardcoded examples
  - Explains semantic deduplication: similar patterns merged into core patterns
  - File: `skills/bootstrap-orchestrator/SKILL.md` (143 lines, 7-step orchestration process)
- **Data Flow Diagram in ace-bootstrap.md** - Visual ASCII diagram showing bootstrap pipeline
  - Shows: Command → Skill → MCP Tool → ACE Server → Reflector → Results → Report

### Changed
- **ace-bootstrap command** - Now invokes bootstrap-orchestrator skill instead of calling MCP tool directly
  - Better user experience with dynamic reporting
  - Eliminates confusion about pattern compression (users thought it was a bug)
  - Clear explanation that quality > quantity is intentional design

### Improved
- **User Experience** - Users now understand why 158 code blocks → 12 patterns
  - Before: "Is this a bug?" (confusion)
  - After: "Ah, semantic deduplication - makes sense!" (clarity)

## [3.2.16] - 2025-10-27

### Fixed
- **CLAUDE.md bootstrap documentation** - Fixed incorrect bootstrap command references
  - Updated documentation to reflect current bootstrap behavior
  - Clarified hybrid mode as default with intelligent fallback

## [3.2.15] - 2025-10-27

### Added
- **Hybrid Bootstrap Mode** - Intelligent multi-source analysis with fallback logic
  - Priority order: docs → git history → local files
  - Extracts patterns from documentation files (CLAUDE.md, README.md, ARCHITECTURE.md, docs/*.md)
  - Falls back to git history and local files if docs are missing or sparse
  - Comprehensive coverage: combines all three sources for maximum pattern extraction
- **Thoroughness Parameter** - Control bootstrap depth with light/medium/deep settings
  - Light: 1000 files, 100 commits, 30 days
  - Medium: 5000 files, 500 commits, 90 days (default)
  - Deep: unlimited files, 1000 commits, 180 days
- **5x Deeper Defaults** - Increased default limits for more comprehensive analysis
  - max_files: 500 → 5000 (10x increase)
  - commit_limit: 100 → 500 (5x increase)
  - days_back: 30 → 90 (3x increase)

### Changed
- **Enhanced bootstrap documentation** - Complete guide for all bootstrap modes
  - Detailed explanation of hybrid mode's intelligent fallback logic
  - Clear examples for each thoroughness level
  - Updated usage examples with new parameters
- **Project-scoped configuration** - Clarified that ACE config is per-project
  - Each project needs its own `.ace/config.json`
  - Configuration stored in project root, not globally

### Fixed
- **plugin.template.json version mismatch** - Corrected version number inconsistency

### Removed
- **Obsolete mcp-server directory** - Cleaned up old MCP server files from plugin

## [3.2.14] - 2025-10-26

### Added
- **SessionStart hook for automatic version detection** - Detects plugin version on session start
  - Logs plugin version for debugging
  - Helps troubleshoot version-related issues

### Changed
- **Documentation cleanup** - Removed internal development references
  - Removed research paper references from public-facing docs
  - Cleaned up technical README to remove deleted file references
  - Added docs-internal/ to gitignore for private development docs
  - Removed internal docs and added .serena to gitignore

## [3.2.13] - 2025-10-25

### Fixed
- **ACE acronym correction** - Changed "Automatic" to "Agentic" Context Engineering
  - Reflects accurate naming: ACE = Agentic Context Engineering
  - Updated all documentation to use correct terminology

### Changed
- **Major documentation cleanup** - User-focused improvements
  - Simplified explanations for better clarity
  - Removed overly technical implementation details
  - Focused on user benefits and practical usage

## [3.2.12] - 2025-10-25

### Changed
- **Version bump to 3.2.12** - Standard maintenance release
  - Updated version numbers across all configuration files
  - No functional changes

## [3.2.11] - 2025-10-24

### Changed
- **Version bump to 3.2.11** - Maintenance release with documentation updates
  - Complete ACE paper verification and implementation specs
  - Enhanced documentation organization by domain
  - Updated project CLAUDE.md with ACE v3.2.10 instructions

### Fixed
- **ACE Learning skill trigger sensitivity** - Made skill trigger MORE aggressively
  - Improved detection of substantial work completion
  - Better recognition of learning opportunities
  - Reduced false negatives (missed learning opportunities)

## [3.2.10] - 2025-10-24

### Fixed
- **Trajectory format documentation** - Fixed incorrect trajectory parameter format
  - Corrected documentation to show trajectory must be an array of objects with descriptive keys
  - Example: `[{"step": "Analysis", "action": "Analyzed the problem"}]` not a string
  - Updated all documentation and examples to reflect correct format

## [3.2.9] - 2025-10-24

### Added
- **Version Detection in /ace-claude-init** - Automatic version detection and update
  - Command now detects plugin version and updates project CLAUDE.md accordingly
  - Shows warning if project CLAUDE.md has outdated version
  - Provides clear instructions for updating to latest version

## [3.2.8] - 2025-10-24

### Added
- **Mandatory Skill Triggering with Aggressive Prompting** - Enhanced skill invocation
  - Added prominent reminders in CLAUDE.md about when to invoke skills
  - Clear trigger keywords for retrieval skill (implement, build, create, etc.)
  - Clear trigger conditions for learning skill (after substantial work)
  - Workflow examples showing exact skill invocation sequence
  - Non-negotiable language emphasizing skills are mandatory, not optional

### Changed
- **Enhanced skill documentation** - More explicit instructions for Claude
  - Added "YOU MUST FOLLOW THESE RULES" section at top of CLAUDE.md
  - Workflow example showing step-by-step skill usage
  - Emphasized proactive skill usage for every qualifying task

## [3.2.7] - 2025-10-23

### Fixed
- **`/ace-claude-init` command implementation** - CRITICAL BUG FIX: Command was broken in v3.2.6
  - **Problem**: Used `@` reference syntax which doesn't work in command expansion
  - **Solution**: Now properly copies full plugin CLAUDE.md content inline (~289 lines)
  - **Impact**: v3.2.6 users got broken command that didn't inject instructions
  - Command now works as documented: copies content inline, no `@` references
  - Non-destructive: appends to existing CLAUDE.md without overwriting user content
  - Idempotent: detects existing content and prevents duplicates
  - Creates CLAUDE.md if it doesn't exist

## [3.2.6] - 2025-10-23 [BROKEN - DO NOT USE]

**WARNING**: This version contains a broken `/ace-claude-init` command. Please use v3.2.7 instead.

### Added
- **`/ace-claude-init` command** - BROKEN: Used `@` reference syntax instead of inline copy
  - Intended to copy full ACE plugin instructions inline into project CLAUDE.md
  - Provides always-on context about ACE architecture and automatic learning cycle (~289 lines)
  - Non-destructive: appends to existing CLAUDE.md without overwriting user content
  - Idempotent: detects existing content and prevents duplicates
  - Creates CLAUDE.md if it doesn't exist
  - Replaces unreliable SessionStart hook approach with explicit user control
  - **BUG**: Implementation used `@` reference syntax which doesn't work - FIXED IN v3.2.7
- **Local file analysis in `/ace-bootstrap`** - NEW: Analyze current project files (committed or uncommitted!)
  - Three modes: `local-files`, `git-history`, or `both` (default)
  - Extracts imports/dependencies from TypeScript, JavaScript, Python, Go, Java, Ruby files
  - Discovers error handling patterns (try-catch, error logging)
  - Captures work-in-progress and prototype code (uncommitted changes)
  - Client-side analysis (fast, no git operations needed)
  - Configurable file extensions and max files limit
- **Enhanced bootstrap documentation** - Complete guide for local file analysis
  - Detailed explanation of what gets analyzed in each mode
  - Examples for different use cases (prototyping, current state, historical patterns)
  - Why local files matter (uncommitted code, current reality vs. historical experiments)

### Changed
- **Renamed `/ace-init` to `/ace-bootstrap`** - More accurate name for bootstrapping playbook
  - Clearer purpose: "bootstrap" indicates initializing from existing data
  - Distinguishes from new `/ace-claude-init` which initializes CLAUDE.md
  - Tool name: `mcp__ace-pattern-learning__ace_init` → `mcp__ace-pattern-learning__ace_bootstrap`
  - All documentation updated to reflect new command name
- **Updated MCP Client to v3.2.6** - Includes local file analysis capabilities
  - New `analyzeLocalFiles()` function for client-side file scanning
  - Recursive directory traversal with common ignore patterns
  - Regex-based pattern extraction for imports and error handling
  - Sends extracted patterns to server via `ace_learn` execution trace
- **Updated installation workflow** - Now includes `/ace-claude-init` as Step 7 (one-time setup)
  - Provides explicit user control over CLAUDE.md patching
  - More reliable than automatic SessionStart hook injection
  - Follows official Claude Code plugin patterns (no CLAUDE.md auto-injection)

### Removed
- **SessionStart hook** - Removed automatic CLAUDE.md injection (replaced by `/ace-claude-init`)
  - Unreliable: hook structure issues prevented consistent execution
  - Not official: Plugin CLAUDE.md auto-injection not in official Anthropic spec
  - User control: Explicit command is more transparent and reliable
- **auto-inject-instructions.sh script** - No longer needed with new manual command approach

### Fixed
- **Reliable CLAUDE.md setup** - Users now have explicit, reliable command to initialize ACE instructions
  - Solves SessionStart hook failures across different environments
  - Works every time (file operation vs. hook execution)
  - User can verify what was added
- **Bootstrap now captures uncommitted work** - Major improvement over git-only analysis
  - Prototypes and WIP features no longer missed
  - Current architecture/dependencies captured accurately
  - What's ACTUALLY being used NOW vs. historical experiments

## [3.2.5] - 2025-10-23

### Fixed
- **SessionStart hook structure** - Fixed nested hooks array that prevented auto-inject-instructions.sh from running
  - Changed from incorrect nested structure `{"hooks": [{"type": "command", ...}]}` to correct flat structure `{"type": "command", ...}`
  - This resolves the issue where plugin CLAUDE.md reference was not being injected into project CLAUDE.md files after session restart
  - PostToolUse hook structure was already correct (uses matcher, so nesting is valid)

## [3.2.4] - 2025-10-23

### Added
- **ACE Playbook Retrieval Skill** - NEW model-invoked skill that automatically fetches learned patterns BEFORE tasks
  - Auto-triggers on: implement, build, create, fix, debug, refactor, integrate, optimize, architect
  - Provides: Strategies, code snippets, troubleshooting tips, API recommendations from previous sessions
  - Completes the automatic learning cycle: Retrieve → Use → Learn → Update → Repeat
- **Serena Memories** - Created two memory files for ACE architecture and skills patterns
  - `ace-automatic-cycle-v3.2.4.md` - Documents the complete automatic learning cycle
  - `claude-code-skills-patterns.md` - Skills best practices and patterns

### Changed
- **Updated to MCP Client v3.2.4** - Includes .mcp.json using @latest for automatic npm updates
- **Simplified hooks.json** - Removed redundant learning reminders (skills now handle automation)
  - SessionStart hook: Simplified to basic instructions only
  - PostToolUse hook: Removed learning reminders (ACE Learning skill handles this)
- **Enhanced CLAUDE.md** - Complete documentation of automatic learning cycle
  - Added detailed section on ACE Playbook Retrieval skill
  - Documented 3-tier caching architecture (RAM → SQLite → Server)
  - Added examples of complete learning cycles
  - Clarified model-invoked vs manual commands
- **Enhanced README.md** - Updated with complete automatic cycle explanation
  - Added retrieval skill documentation
  - Updated architecture diagrams
  - Clarified skills vs slash commands

### Removed
- **Redundant hook instructions** - Learning reminders now handled by Agent Skills
- **Manual learning prompts** - Skills trigger automatically based on task context

## [3.2.3] - 2025-10-23

### Changed
- **Updated to MCP Client v3.2.3** - Includes dramatically improved `ace_learn` tool description
- **Updated CLAUDE.md** - Accurate description of automatic learning via Agent Skill
  - Clarified that Agent Skill triggers automatically after substantial work
  - Added detailed examples of when learning occurs
  - Explained the full learning pipeline from execution to playbook update

### Documentation
- Added `CHANGELOG.md` for tracking plugin releases

## [3.2.2] - 2025-10-22

### Changed
- Updated to MCP Client v3.2.2 with server-side architecture
- Reflector (Sonnet 4) and Curator (Haiku 4.5) now run server-side
- MCP client simplified to HTTP interface for universal compatibility

## [3.2.1] - 2025-10-21

### Added
- Initial release of ACE Orchestration Plugin
- Integration with @ce-dot-net/ace-client MCP server
- Slash commands for ACE operations (/ace-patterns, /ace-status, etc.)
- Agent Skill for automatic learning from execution

[3.2.17]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.16...v3.2.17
[3.2.16]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.15...v3.2.16
[3.2.15]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.14...v3.2.15
[3.2.14]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.13...v3.2.14
[3.2.13]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.12...v3.2.13
[3.2.12]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.11...v3.2.12
[3.2.11]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.10...v3.2.11
[3.2.10]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.9...v3.2.10
[3.2.9]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.8...v3.2.9
[3.2.8]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.7...v3.2.8
[3.2.7]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.6...v3.2.7
[3.2.6]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.5...v3.2.6
[3.2.5]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.4...v3.2.5
[3.2.4]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.3...v3.2.4
[3.2.3]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.2...v3.2.3
[3.2.2]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.1...v3.2.2
[3.2.1]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v3.2.1
