# Changelog

All notable changes to the CE Claude Marketplace project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [Unreleased]

### Planned Features
- Web dashboard for pattern visualization
- Pattern sharing across projects
- Team collaboration features
- Advanced playbook customization
- Multi-language support expansion

---

[0.1.0]: https://github.com/ce-dot-net/ce-claude-marketplace/releases/tag/v0.1.0
