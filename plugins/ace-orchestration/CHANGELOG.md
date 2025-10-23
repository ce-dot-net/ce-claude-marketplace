# Changelog

All notable changes to the ACE Orchestration Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[3.2.4]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.3...v3.2.4
[3.2.3]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.2...v3.2.3
[3.2.2]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/v3.2.1...v3.2.2
[3.2.1]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v3.2.1
