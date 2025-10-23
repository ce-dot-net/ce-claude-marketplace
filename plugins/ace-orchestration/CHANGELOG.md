# Changelog

All notable changes to the ACE Orchestration Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[3.2.7]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.6...v3.2.7
[3.2.6]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.5...v3.2.6
[3.2.5]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.4...v3.2.5
[3.2.4]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.3...v3.2.4
[3.2.3]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.2...v3.2.3
[3.2.2]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.1...v3.2.2
[3.2.1]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v3.2.1
