# Changelog

All notable changes to the CE Claude Marketplace project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.1.2] - 2025-10-21

### 🏗️ Configuration Update - Project-Local Config Storage

**Configuration now saves to project directory by default!**

### Changed

#### Configuration Storage Location
- **NEW**: Configuration saves to `./.ace/config.json` (project root) by default
- Global fallback: `~/.ace/config.json` (home directory)
- **Priority**: Environment variables → Project-local → Global → Defaults
- Git repository detection: Uses `git rev-parse --show-toplevel` to find project root
- Falls back to current working directory if not in a git repository

### Benefits
- ✅ Each project can have its own ACE server and credentials
- ✅ Configuration travels with the project for team collaboration
- ✅ Environment-specific configurations (dev, staging, prod)
- ✅ Global fallback still available for personal default settings

### Configuration Priority (Updated)
1. **Environment variables** (highest priority)
2. **`./.ace/config.json`** (project-local, NEW default)
3. **`~/.ace/config.json`** (global fallback)
4. **Default values** (lowest priority)

### Migration
- **Automatic** - Existing global configs (`~/.ace/config.json`) still work
- New configs created with `/ace-configure` will save to project directory
- To migrate: Run `/ace-configure` in your project directory

---

## [3.1.1] - 2025-10-21

### 🔄 Plugin Update - npm Package Integration

**Claude Code Plugin now uses published npm package!**

### Changed

#### Distribution Method
- **Switched from bundled MCP server to npm download**
- Plugin now uses: `npx --yes @ce-dot-net/ace-client@3.1.0`
- Downloads latest MCP client from public npm registry
- No bundled dependencies - smaller plugin size
- Zero authentication required
- Users can easily update: `npm install -g @ce-dot-net/ace-client@latest`

### Benefits
- ✅ Always gets latest MCP client with bug fixes
- ✅ Smaller plugin installation size
- ✅ Easy updates without reinstalling plugin
- ✅ Same npm package works standalone or with plugin

### Migration
- **Automatic** - Just update the plugin and restart Claude Code
- Plugin will download MCP client from npm on first run

---

## [3.1.0] - 2025-10-21

### 🎉 Major Release - Code Engine ACE Public Launch

**First public release on npm!** Now available at: https://www.npmjs.com/package/@ce-dot-net/ace-client

### ✨ New Features

#### Interactive Configuration Wizard
- **NEW MCP Tool**: `ace_save_config` for saving credentials
- **Enhanced `/ace-configure` command**: Interactive prompts for server URL, API token, and project ID
- Automatic configuration storage to `~/.ace/config.json`
- Multi-source configuration support:
  1. Environment variables (highest priority)
  2. `~/.ace/config.json` file
  3. Default values (localhost:9000)

#### Simplified Installation
- **Zero authentication required** - Published to public npm registry
- **One-command install**: `npm install @ce-dot-net/ace-client` or `npx @ce-dot-net/ace-client`
- **Bundled MCP server option** - Works offline with no downloads
- Universal compatibility: Claude Code, Claude Desktop, Cursor, and any MCP-compatible client

### 🔄 Changes

#### Rebranding
- **Name**: "ACE Pattern Learning" → **"Code Engine ACE"**
- **Focus**: Research implementation → Production-ready code intelligence
- Removed all academic paper references (arXiv, Stanford, SambaNova, UC Berkeley)
- Updated descriptions across all packages and plugins
- New tagline: "Intelligent pattern learning and code generation for AI assistants"

#### Security & Privacy
- **Removed all real credentials** from documentation and examples
- Using placeholder values: `ace_your_api_token_here`, `prj_your_project_id`
- `.env` file properly gitignored and excluded from npm package
- Package only ships: `dist/`, `README.md`, `LICENSE`

#### Package Distribution
- **Published to npm public registry** (npmjs.org) instead of GitHub Packages
- No authentication required for installation
- Available for standalone use in any Node.js project
- Keywords updated: `code-engine`, `ai-assistant`, `pattern-learning`

### 🐛 Bug Fixes
- Fixed `/ace-configure` command - now actually saves configuration via MCP tool
- Fixed startup message to show correct version number
- Removed references to non-existent research papers in production code

### 📚 Documentation
- Updated `INSTALL.md` with simplified 3-step installation
- Rewrote `/ace-configure` command documentation with example interactions
- Added configuration priority documentation
- Removed GitHub Packages authentication instructions (no longer needed)

### 🔧 Technical Details

**MCP Client (`@ce-dot-net/ace-client@3.1.0`)**
- New tool: `ace_save_config(serverUrl, apiToken, projectId)`
- Startup message: "🚀 Code Engine ACE - MCP Client v3.1.0"
- Description: "Code Engine ACE - TypeScript MCP Client for intelligent pattern learning and code generation"
- Keywords: `code-engine`, `ai-assistant`, `mcp`, `claude-code`, `pattern-learning`

**Claude Code Plugin (`ace-orchestration@3.1.0`)**
- Description: "Code Engine ACE - Intelligent pattern learning and code generation"
- Bundled MCP server with all dependencies included
- Interactive `/ace-configure` command using `ace_save_config` tool
- Works offline - no external downloads required

### 📦 Installation

**For npm users (standalone):**
```bash
npm install -g @ce-dot-net/ace-client
ace-client
```

**For Claude Code users:**
```bash
# Clone and install plugin
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace/plugins/ace-orchestration
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration

# Restart Claude Code, then configure:
/ace-configure
```

### 🙏 Migration Guide

**From v3.0.x:**
- Update package: `npm install @ce-dot-net/ace-client@3.1.0`
- Run `/ace-configure` to set up credentials
- No breaking changes - existing configurations still work

### 🔗 Links
- **npm Package**: https://www.npmjs.com/package/@ce-dot-net/ace-client
- **Documentation**: https://github.com/ce-dot-net/ce-claude-marketplace
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

---

## [3.0.3] - 2025-10-21

### 🚀 Production Release - GitHub Packages Deployment

Complete TypeScript MCP client published to GitHub Packages with automated installation workflow.

### Added

#### MCP Client Package (@ce-dot-net/ace-client)
- **Published to GitHub Packages** (npm.pkg.github.com)
  - Package: `@ce-dot-net/ace-client@3.0.3`
  - Full deletion control (unlike npm's 72-hour limit)
  - Scoped package with authentication support
  - Working npx execution: `npx --package=@ce-dot-net/ace-client ace-client`

#### Automated Installation System
- **Installation Scripts**
  - `plugins/ace-orchestration/scripts/install.sh` - Bash version
  - `plugins/ace-orchestration/scripts/setup.js` - Node.js version
  - Auto-loads `GITHUB_TOKEN` from `.env` file
  - Creates `.npmrc` at marketplace root with authentication
  - Validates environment variables (ACE_SERVER_URL, ACE_API_TOKEN, ACE_PROJECT_ID)
  - Checks plugin configuration files

#### Plugin Configuration
- **Updated Plugin Templates**
  - `plugin.template.json` - Production config with npx
  - Uses `npx --package=@ce-dot-net/ace-client ace-client` syntax
  - Environment variables via `${env:VAR_NAME}` pattern
  - Auto-downloads MCP client on first use

#### Security & Configuration
- **Token Management**
  - `.env` file for GITHUB_TOKEN storage (gitignored)
  - Auto-generated `.npmrc` with auth token (gitignored)
  - Safe template files with placeholders (committed)
- **Updated .gitignore**
  - Added `.npmrc` (contains auth token)
  - Added `.env` (contains secrets)
  - Added `plugins/*/plugin.json` (user configs)

### Changed

#### Package Configuration
- **Removed `prepare` script** from package.json
  - Fixed npm install failures (no source files in published package)
  - Only `prepack` script remains for building
- **Fixed npx execution**
  - Updated from `npx @ce-dot-net/ace-client` (failed)
  - To: `npx --package=@ce-dot-net/ace-client ace-client` (works)
  - Addresses scoped package bin resolution issues

#### Version Synchronization
- All versions updated to 3.0.3:
  - `mcp-clients/ce-ai-ace-client/package.json`: 3.0.3
  - `plugins/ace-orchestration/plugin.template.json`: 3.0.3
  - `.claude-plugin/marketplace.json`: 3.0.3

### Fixed

- **NPM Package Installation**
  - Removed `prepare` script that caused install failures
  - Fixed: "Cannot find module 'dist/tests/integration-test.js'" error
- **NPX Execution**
  - Fixed scoped package bin command resolution
  - Now works: `npx --yes --package=@ce-dot-net/ace-client ace-client`
- **Authentication Flow**
  - Fixed npm registry authentication for GitHub Packages
  - Auto-loads token from `.env` via install script
  - Creates proper `.npmrc` with auth configuration

### Documentation

#### Installation Guides
- **INSTALL.md** (plugins/ace-orchestration/)
  - Automated installation steps
  - Manual installation fallback
  - Troubleshooting section
- **PUBLISH_NOW.md** (project root)
  - Step-by-step publishing guide
  - GitHub token creation
  - Package verification steps
- **GITHUB_PACKAGES_SETUP.md** (project root)
  - Complete GitHub Packages guide
  - Deletion commands
  - Comparison with npm

### Technical Details

#### Published Versions History
- v3.0.0 - Initial GitHub Packages publish (had `prepare` script issue)
- v3.0.1 - Removed `prepare` script
- v3.0.2 - First fully working version
- v3.0.3 - Final release with updated version display

#### Installation Workflow
```bash
# 1. Clone repo
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace

# 2. Run installation script (auto-configures .npmrc)
cd plugins/ace-orchestration
./scripts/install.sh

# 3. Set environment variables
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="your-token"
export ACE_PROJECT_ID="your-project"

# 4. Install plugin in Claude Code
cp plugin.template.json plugin.json
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration
```

#### MCP Server Configuration
```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": ["--package=@ce-dot-net/ace-client", "ace-client"],
      "env": {
        "ACE_SERVER_URL": "${env:ACE_SERVER_URL}",
        "ACE_API_TOKEN": "${env:ACE_API_TOKEN}",
        "ACE_PROJECT_ID": "${env:ACE_PROJECT_ID}"
      }
    }
  }
}
```

### Breaking Changes

- **Package Location**: Now on GitHub Packages (npm.pkg.github.com), not npm
- **Installation**: Requires `.npmrc` configuration for scoped registry
- **NPX Syntax**: Must use `--package` flag for execution

### Migration Guide

**From v3.0.0 or earlier:**
1. Delete old `.npmrc` files (home and project)
2. Run `plugins/ace-orchestration/scripts/install.sh`
3. Update `plugin.json` with new npx syntax from template
4. Restart Claude Code

## [0.1.0] - 2025-01-19

### 🎉 Initial Release

First public release of CE Claude Marketplace with ACE Orchestration plugin and MCP client.

### Added

#### Marketplace Infrastructure
- **Marketplace Configuration** (`.claude-plugin/marketplace.json`)
  - Full marketplace setup for Claude Code CLI 2.0+
  - Plugin discovery and installation support
  - Metadata for `ce-dot-net-marketplace` catalog

#### ACE Orchestration Plugin (v2.5.0)
- **Plugin Manifest** (`plugins/ace-orchestration/plugin.json`)
  - Local testing configuration with localhost MCP server
  - Production template (`plugin.PRODUCTION.json`) for PyPI deployment
  - Complete plugin metadata and component definitions

- **Slash Commands** (8 commands)
  - `/ace-status` - View pattern database statistics
  - `/ace-patterns` - List learned patterns with filtering
  - `/ace-train-offline` - Train on git history
  - `/ace-force-reflect` - Manual pattern reflection
  - `/ace-clear` - Reset pattern database
  - `/ace-export-patterns` - Export patterns to JSON
  - `/ace-import-patterns` - Import patterns from JSON
  - `/ace-export-speckit` - Export specification kit

- **Specialized Agents** (3 agents)
  - Reflector - Discovers coding patterns from code
  - Domain Discoverer - Bottom-up taxonomy discovery
  - Reflector Prompt - Iterative pattern refinement

- **Event Hooks**
  - PostToolUse - Automatic pattern reflection on Edit/Write
  - PostTaskCompletion - Task completion processing
  - Configurable hook matchers and actions

#### MCP Client (v2.5.0)
- **FastMCP-based Client** (`mcp-clients/ce-ai-ace-client/`)
  - Thin proxy to remote ACE server
  - 6 MCP tools exposed (reflect, train, patterns, playbook, status, clear)
  - HTTP transport with bearer token authentication
  - Python 3.10+ support

- **PyPI Package Configuration**
  - `pyproject.toml` with full metadata
  - Entry point: `ce-ai-ace-client`
  - Dependencies: fastmcp>=2.4.0, httpx>=0.27.0, pydantic>=2.0.0

#### Documentation
- **Comprehensive README.md**
  - Installation instructions (local and production)
  - Plugin and MCP client overview
  - Configuration examples
  - Usage guidelines

- **Setup Documentation** (`docs/SETUP_INSTRUCTIONS.md`)
  - Original setup guide from initial implementation

- **Quick Reference** (`docs/QUICK_REFERENCE.md`)
  - Command reference
  - Configuration snippets

- **Local Testing Guide** (`docs/LOCAL_TESTING.md`)
  - Complete step-by-step local testing workflow
  - Troubleshooting section with common issues
  - Production transition guide
  - Environment variable reference
  - Debug mode instructions

- **Testing Checklist** (`docs/TESTING_CHECKLIST.md`)
  - Pre-testing setup checklist
  - Command testing scenarios
  - Hook and MCP tool verification
  - Production readiness checklist
  - Quick troubleshooting fixes

#### Configuration Files
- **Claude Code Settings** (`.claude/settings.local.json`)
  - Local development configuration
  - Marketplace and plugin settings

### Technical Details

#### Architecture
- **Plugin System**: Claude Code CLI 2.0 plugin architecture
- **MCP Integration**: Model Context Protocol for tool exposure
- **FastMCP**: Modern Python MCP server framework
- **Research-Based**: Implements Stanford/SambaNova/UC Berkeley ACE paper (arXiv:2510.04618v1)

#### Local Testing Mode
- Python module invocation (`python -m ace_client`)
- Localhost MCP server connection (`http://localhost:8000/mcp`)
- Development token authentication
- Editable pip installation support

#### Production Mode (Template)
- PyPI package installation (`uvx ce-ai-ace-client`)
- Remote server connection (configurable URL)
- Environment variable token management
- Pattern storage in plugin directory

### Installation

#### Local Testing
```bash
# Install MCP client
cd mcp-clients/ce-ai-ace-client
pip install -e .

# Add marketplace
/plugin marketplace add /path/to/ce-claude-marketplace

# Install plugin
/plugin install ace-orchestration@ce-dot-net-marketplace
```

#### Production (After PyPI Publish)
```bash
# Add marketplace from GitHub
/plugin marketplace add ce-dot-net/ce-claude-marketplace

# Install plugin
/plugin install ace-orchestration@ce-dot-net-marketplace
```

### Research Foundation

Based on **Agentic Context Engineering (ACE)** research:
- Paper: [arXiv:2510.04618v1](https://arxiv.org/abs/2510.04618)
- Institutions: Stanford University, SambaNova Systems, UC Berkeley
- Features: Pattern learning, offline training, playbook generation, domain discovery

### Repository Structure

```
ce-claude-marketplace/
├── .claude-plugin/
│   └── marketplace.json          # Marketplace configuration
├── plugins/
│   └── ace-orchestration/        # ACE plugin
│       ├── plugin.json           # Local config
│       ├── plugin.PRODUCTION.json # Production config
│       ├── commands/             # 8 slash commands
│       ├── agents/               # 3 specialized agents
│       └── hooks/                # Event hooks
├── mcp-clients/
│   └── ce-ai-ace-client/         # FastMCP client
│       ├── pyproject.toml        # Package config
│       └── ace_client/           # Client implementation
└── docs/
    ├── LOCAL_TESTING.md          # Testing guide
    ├── TESTING_CHECKLIST.md      # Quick checklist
    ├── SETUP_INSTRUCTIONS.md     # Setup guide
    └── QUICK_REFERENCE.md        # Quick reference
```

### Next Steps

- [ ] Publish `ce-ai-ace-client` to PyPI
- [ ] Deploy ACE MCP server to production
- [ ] Update `plugin.json` with production configuration
- [ ] Test GitHub marketplace installation
- [ ] Community feedback and improvements

### License

MIT License

### Authors

- ACE Team <ace@ce-dot-net.com>

---

## [3.0.0] - 2025-01-21

### 🚀 Major Release: TypeScript MCP Client Production Ready

Complete rewrite from Python to TypeScript with 3-tier caching, comprehensive testing, and production-ready architecture.

### Breaking Changes

- **MCP Client**: Complete rewrite in TypeScript (Python client deprecated)
- **Installation**: Now requires Node.js 18+ (no Python dependency for client)
- **Package Name**: `@ce-dot-net/ace-client` (npm) instead of `ce-ai-ace-client` (PyPI)
- **MCP Tools**: 5 tools (was 6) - consolidated functionality

### Added

#### TypeScript MCP Client (v3.0.0)
- **Native TypeScript Implementation**
  - Full MCP SDK 0.6.0 integration
  - ESM modules throughout
  - Type-safe design with TypeScript 5.7.2
  - No Python dependency

- **3-Tier Cache Architecture**
  - Layer 1: RAM cache (0ms, instant)
  - Layer 2: SQLite cache (4ms, `.ace-cache/` in project)
  - Layer 3: Remote server (50-200ms, ChromaDB)
  - Performance: 50-200x speedup on cache hits
  - Embedding cache: 133x speedup

- **5 MCP Tools**
  - `ace_init` - Initialize from codebase (offline learning)
  - `ace_reflect` - Learn from execution (online learning)
  - `ace_get_playbook` - Retrieve structured playbook
  - `ace_status` - System statistics
  - `ace_clear` - Clear all patterns

#### Testing & Quality (10/10 PASSING ✅)
- **Comprehensive Integration Tests** (`tests/integration-test.ts`)
  - Server connectivity and authentication
  - Local cache creation and performance
  - Offline initialization (discovers 30-40 patterns)
  - Remote save/retrieve operations
  - Embedding cache performance
  - Cache invalidation
  - Full workflow cycle
  - Total runtime: ~2.4 seconds

- **Fresh Start Completed**
  - Cleared 8 test patterns with simulated metrics
  - Discovered 37 real patterns from codebase analysis
  - Ready for authentic helpful/harmful tracking

#### Pattern Database
- **37 Real Patterns Discovered**
  - 2 strategies (async/await, ORM usage)
  - 28 code snippets (imports, dependencies)
  - 0 troubleshooting (will emerge from bugs)
  - 7 APIs (npm packages, libraries)
  - All patterns: helpful=0, harmful=0 (authentic tracking ready)

#### Security & Configuration
- **Environment Variable Support**
  - `plugin.template.json` with `${env:*}` placeholders
  - `.env.example` for configuration guidance
  - `CONFIGURATION.md` - Complete setup guide
  - `SECURITY.md` - Security best practices

- **Safety Improvements**
  - No hardcoded credentials in templates
  - `.gitignore` prevents credential commits
  - Token management guide
  - Multi-project support

#### Documentation
- **Client Documentation**
  - `README.md` - Complete user guide
  - `tests/README.md` - Testing documentation
  - `PUBLISHING.md` - npm publication guide
  - `FRESH_START_COMPLETE.md` - Fresh start results
  - `DISCOVERED_PATTERNS.md` - Pattern analysis
  - `API_ENDPOINT_FIXES.md` - Endpoint corrections
  - `CONFIGURATION.md` - Setup instructions
  - `SECURITY.md` - Security practices

- **Memory Bank Updates**
  - `ace_client_final_status.md` - Updated with v3.0 status
  - `ace_plugin_setup.md` - Current configuration
  - `project-progress.md` - Complete timeline

### Changed

- **API Endpoints** (Corrected to match server)
  - `POST /patterns` (was `/playbook`)
  - `DELETE /patterns` (was `/playbook`)
  - All endpoints now working correctly

- **Cache Location**
  - Now: `./.ace-cache/` (project directory)
  - Was: `~/.ace-cache/` (home directory)
  - Benefit: Project-specific caching

- **Package Metadata**
  - Version: 3.0.0 (SemVer major bump)
  - License: MIT
  - Homepage: GitHub repository
  - Keywords: Updated for better discovery

### Fixed

- **SQLite Schema** - NOT NULL constraint on `last_used` field
  - Added DEFAULT CURRENT_TIMESTAMP
  - Added fallback values in insert statements

- **Server Communication** - API endpoint mismatches
  - POST /playbook → POST /patterns ✅
  - DELETE /playbook → DELETE /patterns ✅

- **Test Data Cleanup**
  - Removed 8 simulated test patterns
  - Saved 37 real patterns from code analysis
  - Authentic foundation for learning

### Removed

- **Python Client** (Deprecated)
  - ❌ `ace_client/` directory
  - ❌ Python test files
  - ❌ `.venv/` and virtual environment
  - ❌ `pyproject.toml` (Python packaging)
  - ❌ FastMCP dependency

### Performance

- **Cache Performance**
  - Get Playbook: 150-200ms → 4ms (37-50x speedup)
  - Get Embeddings: 133ms → 0ms (133x speedup)
  - Pattern Lookup: 100-150ms → 2-4ms (25-75x speedup)

- **Test Performance**
  - 10 integration tests: ~2.4 seconds total
  - Average per test: ~240ms

### Technical Details

#### Migration Path

**From Python (v0.2.0)**:
```bash
# Old (deprecated)
pip install ce-ai-ace-client
uvx ce-ai-ace-client
```

**To TypeScript (v3.0.0)**:
```bash
# New (current)
npm install @ce-dot-net/ace-client
npx @ce-dot-net/ace-client
```

#### Plugin Configuration

**Published Package** (production):
```json
{
  "command": "npx",
  "args": ["@ce-dot-net/ace-client"],
  "env": {
    "ACE_SERVER_URL": "${env:ACE_SERVER_URL}",
    "ACE_API_TOKEN": "${env:ACE_API_TOKEN}",
    "ACE_PROJECT_ID": "${env:ACE_PROJECT_ID}"
  }
}
```

**Local Development**:
```json
{
  "command": "node",
  "args": ["${CLAUDE_PLUGIN_ROOT}/../../mcp-clients/ce-ai-ace-client/dist/index.js"],
  "env": { "..." }
}
```

### Installation

#### For Users (After npm Publish)

```bash
# 1. Install plugin
ln -s /path/to/ce-claude-marketplace/plugins/ace-orchestration \
  ~/.config/claude-code/plugins/ace-orchestration

# 2. Configure environment variables
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="your-token-here"
export ACE_PROJECT_ID="your-project-id"

# 3. Restart Claude Code

# 4. Test installation
/ace-status
```

#### For Developers

```bash
# 1. Clone repository
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace

# 2. Build MCP client
cd mcp-clients/ce-ai-ace-client
npm install && npm run build

# 3. Run tests
npm test

# 4. Expected: 10/10 tests passing
```

### Upgrade Guide

**If you're using v0.1.0 or v0.2.0 (Python)**:

1. **Uninstall Python client**:
   ```bash
   pip uninstall ce-ai-ace-client
   ```

2. **Install Node.js 18+** (if not installed)

3. **Build TypeScript client**:
   ```bash
   cd mcp-clients/ce-ai-ace-client
   npm install && npm run build
   ```

4. **Update plugin configuration**:
   - Copy `plugin.template.json` to `plugin.json`
   - Set environment variables
   - Update command to use `npx @ce-dot-net/ace-client`

5. **Clear old cache** (optional):
   ```bash
   rm -rf ~/.ace-cache/
   ```

6. **Restart Claude Code**

7. **Verify installation**:
   ```bash
   /ace-status
   ```

### Success Criteria Met ✅

- [x] TypeScript client fully functional
- [x] 3-tier cache working correctly
- [x] All API endpoints corrected
- [x] Integration tests passing (10/10)
- [x] Fresh start completed with real patterns
- [x] Documentation comprehensive
- [x] Memory banks updated
- [x] Cache performance verified (50-200x speedup)
- [x] Local testing working
- [x] Production-ready architecture
- [x] Security best practices implemented

### Links

- npm Package: https://www.npmjs.com/package/@ce-dot-net/ace-client
- GitHub Release: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v3.0.0
- Documentation: https://github.com/ce-dot-net/ce-claude-marketplace/tree/main/mcp-clients/ce-ai-ace-client

---

## [Unreleased]

### Planned Features
- Monitor pattern evolution in production
- Web dashboard for pattern visualization
- Pattern sharing across projects
- Team collaboration features
- Advanced playbook customization
- Multi-language support expansion

---

[3.0.0]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v3.0.0
[0.1.0]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v0.1.0
