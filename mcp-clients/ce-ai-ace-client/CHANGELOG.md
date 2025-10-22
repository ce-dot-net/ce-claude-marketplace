# Changelog

All notable changes to @ce-dot-net/ace-client will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[3.2.3]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/ace-client-v3.2.2...ace-client-v3.2.3
[3.2.2]: https://github.com/ce-dot-net/ce-claude-marketplace/compare/ace-client-v3.2.1...ace-client-v3.2.2
[3.2.1]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/ace-client-v3.2.1
