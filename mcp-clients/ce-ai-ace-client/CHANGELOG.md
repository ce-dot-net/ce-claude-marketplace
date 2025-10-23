# Changelog

All notable changes to @ce-dot-net/ace-client will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.2.6] - 2025-10-23

### Added
- **Local file analysis** - NEW: `ace_bootstrap` tool now analyzes current project files (committed or uncommitted!)
  - Extracts imports and dependencies from TypeScript/JavaScript/Python files
  - Discovers error handling patterns (try-catch, error logging)
  - Captures what libraries are ACTUALLY being used NOW
  - Includes work-in-progress and prototype code (uncommitted changes)
  - Client-side analysis (fast, no git operations needed)
- **Multi-mode bootstrap** - Three analysis modes for flexibility:
  - `local-files`: Analyze current codebase files only
  - `git-history`: Analyze git commits only (existing behavior)
  - `both`: Combined analysis (default, recommended)
- **Configurable file extensions** - Customize which file types to analyze (default: `.ts`, `.js`, `.py`, `.go`, `.java`, `.rb`)
- **Max files limit** - Control analysis scope with `max_files` parameter (default: 1000)

### Changed
- **Renamed `ace_init` to `ace_bootstrap`** - More accurate name for bootstrapping playbook
  - Tool name: `ace_init` → `ace_bootstrap`
  - Description updated to reflect multi-mode capabilities
  - Server endpoint unchanged (`POST /init`)
- **Enhanced pattern extraction** - Smarter analysis of current codebase:
  - Import/require statements → APIs section
  - Error handling patterns → Troubleshooting section
  - File type statistics for visibility
- **Updated version** - Bumped from 3.2.5 to 3.2.6 to align with plugin

### Technical Details
- Added `analyzeLocalFiles()` function for client-side file scanning
- Recursive directory traversal with common ignore patterns (node_modules, dist, __pycache__)
- Regex-based pattern extraction for imports and error handling
- Sends extracted patterns to server via `ace_learn` execution trace
- TypeScript compilation successful with no errors

## [3.2.5] - 2025-10-23

### Fixed
- **Plugin integration** - Fixed SessionStart hook structure in ACE Orchestration Plugin that prevented auto-injection script from running
  - No changes to MCP client itself, version bumped to maintain parity with plugin version

## [3.2.4] - 2025-10-23

### Changed
- **Updated .mcp.json and .mcp.template.json** - Changed from hardcoded versions to `@latest` for automatic npm package updates
- **Improved caching documentation** - Clarified 3-tier cache architecture (RAM → SQLite → Server)

### Removed
- **Cleaned up 10 outdated documentation files** from MCP client directory
  - API_ENDPOINT_FIXES.md
  - COPY_PASTE_FOR_CLIENT_CLAUDE.md
  - DISCOVERED_PATTERNS.md
  - FRESH_START_COMPLETE.md
  - INTEGRATION_ISSUES.md
  - READ_ME_FIRST.md
  - SERVER_READY_INSTRUCTIONS.md
  - TEST_RESULTS.md
  - VERIFICATION_COMPLETE.md
  - WHAT_TO_TEST_NOW.md

### Documentation
- Updated inline comments for clarity on caching behavior
- Simplified tool descriptions to focus on automatic invocation patterns

## [3.2.3] - 2025-10-23

### Changed
- **MAJOR: Improved `ace_learn` tool description** - Dramatically enhanced tool description following Anthropic's best practices for automatic invocation
  - Added clear use cases with bullet points (Problem-solving, Implementation, API Integration, etc.)
  - Added explicit "WHEN TO USE" and "SKIP FOR" sections
  - Added 4 real-world examples for pattern matching
  - Enhanced parameter descriptions with concrete examples
  - Added contextual keywords Claude recognizes
- **Upgraded MCP SDK** from 0.6.1 to 1.20.1 (latest stable)
  - Zero breaking changes - perfect backwards compatibility
  - Gained notification debouncing for performance
  - Better authentication handling
  - Protocol spec compliance (2025-06-18)
  - 71 new dependencies (HTTP transport support, unused but available)

### Removed
- Cleaned up abandoned event-driven SQLite approach
  - Removed `execution_events` table from local-cache.ts
  - Removed unused `chokidar` dependency
  - Deleted unused hook scripts

### Fixed
- All integration tests passing with SDK 1.20.1
- Build successful with updated dependencies

### Documentation
- Added `IMPROVEMENTS.md` - Detailed analysis of tool description improvements
- Added `SDK_UPGRADE.md` - Comprehensive MCP SDK upgrade analysis
- Updated inline comments for clarity

## [3.2.2] - 2025-10-22

### Added
- Server-side architecture with Reflector + Curator autonomous processing
- Delta merge algorithm for incremental playbook updates

### Changed
- MCP client simplified to HTTP interface only
- Reflector (Sonnet 4) and Curator (Haiku 4.5) moved to server-side
- Updated to align with ACE research paper architecture

## [3.2.1] - 2025-10-21

### Added
- Initial release with offline learning from git history
- Local SQLite cache for playbook
- Basic MCP tools (ace_learn, ace_get_playbook, ace_status, ace_clear, ace_init)

[3.2.5]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/ace-client-v3.2.4...ace-client-v3.2.5
[3.2.4]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/ace-client-v3.2.3...ace-client-v3.2.4
[3.2.3]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/ace-client-v3.2.2...ace-client-v3.2.3
[3.2.2]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/ace-client-v3.2.1...ace-client-v3.2.2
[3.2.1]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/ace-client-v3.2.1
