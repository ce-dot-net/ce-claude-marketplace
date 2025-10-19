# CE Claude Marketplace - Architecture & Progress

## Project Overview

**Purpose**: Public marketplace for Claude Code plugins and MCP clients, starting with ACE Orchestration plugin.

**Repository**: `ce-dot-net/ce-claude-marketplace`

**Version**: v0.1.0 (Initial Release)

**Tech Stack**:
- Claude Code CLI 2.0+ plugin system
- FastMCP (Python MCP framework)
- Model Context Protocol (MCP)
- Python 3.10+

## Architecture

### Marketplace Structure

```
ce-claude-marketplace/
├── .claude-plugin/
│   └── marketplace.json          # Marketplace catalog
├── plugins/
│   └── ace-orchestration/        # ACE plugin
├── mcp-clients/
│   └── ce-ai-ace-client/         # FastMCP thin client
└── docs/                         # Documentation
```

### Plugin: ACE Orchestration (v2.5.0)

**Purpose**: Self-improving Claude Code plugin based on Stanford research

**Components**:
1. **Slash Commands** (8): status, patterns, train, reflect, clear, export, import
2. **Agents** (3): Reflector, Domain Discoverer, Reflector Prompt
3. **Hooks**: PostToolUse (auto-reflection), PostTaskCompletion
4. **MCP Server**: Connects to ACE pattern learning server

**Configuration Modes**:
- **Local Testing**: `plugin.json` - Uses `python -m ace_client`, localhost:8000
- **Production**: `plugin.PRODUCTION.json` - Uses `uvx ce-ai-ace-client`, remote URL

### MCP Client: ce-ai-ace-client (v2.5.0)

**Purpose**: Thin proxy that forwards requests to remote ACE server

**Architecture**:
- FastMCP-based Python server
- HTTP transport with bearer token auth
- 6 MCP tools: reflect, train, patterns, playbook, status, clear
- Zero business logic (all in remote server)

**Deployment Modes**:
- **Local Dev**: Editable pip install (`pip install -e .`)
- **Production**: PyPI package (`uvx ce-ai-ace-client`)

## Configuration Domains

### 1. Marketplace Configuration

**File**: `.claude-plugin/marketplace.json`

**Key Settings**:
- Name: `ce-dot-net-marketplace`
- Plugin root: `./plugins`
- Owner: CE Dot Net team

**Plugin Entries**:
- Source path (relative or GitHub/Git)
- Metadata (version, author, license, keywords)
- Category and tags for discovery

### 2. Plugin Configuration

**File**: `plugins/ace-orchestration/plugin.json`

**Key Settings**:
- Component paths: commands, agents, hooks
- MCP server configuration
- Environment variables

**MCP Server Config** (Local):
```json
{
  "command": "python",
  "args": ["-m", "ace_client"],
  "env": {
    "ACE_SERVER_URL": "http://localhost:8000/mcp",
    "ACE_API_TOKEN": "local-dev-token",
    "ACE_STORAGE_PATH": "${CLAUDE_PLUGIN_ROOT}/.ace-memory/patterns.db"
  }
}
```

**Environment Variables**:
- `${CLAUDE_PLUGIN_ROOT}`: Auto-resolves to plugin installation dir
- `ACE_SERVER_URL`: MCP server endpoint
- `ACE_API_TOKEN`: Authentication token
- `ACE_STORAGE_PATH`: Pattern database location

### 3. MCP Client Configuration

**File**: `mcp-clients/ce-ai-ace-client/pyproject.toml`

**Package Metadata**:
- Name: `ce-ai-ace-client`
- Version: 2.5.0
- Entry point: `ce-ai-ace-client` command
- Dependencies: fastmcp, httpx, pydantic

**Client Architecture**:
- Stateless proxy (no local processing)
- Remote client initialized on first use
- HTTP transport with custom headers

## Milestones & Progress

### ✅ Milestone 1: Marketplace Foundation (v0.1.0)

**Status**: COMPLETED (2025-01-19)

**Achievements**:
- ✅ Marketplace configuration created
- ✅ Plugin structure implemented
- ✅ MCP client packaged
- ✅ Local testing mode configured
- ✅ Comprehensive documentation
- ✅ Testing guides and checklists

**Deliverables**:
- Marketplace catalog (marketplace.json)
- ACE plugin with 8 commands, 3 agents, hooks
- FastMCP client with 6 tools
- 5 documentation files
- CHANGELOG.md
- Production-ready templates

### 🚧 Milestone 2: Production Deployment (Planned)

**Status**: NOT STARTED

**Goals**:
- [ ] Publish MCP client to PyPI
- [ ] Deploy ACE server to production
- [ ] Update plugin.json for production
- [ ] Test GitHub marketplace installation
- [ ] Create public announcement

### 🔮 Milestone 3: Community Growth (Future)

**Goals**:
- [ ] Web dashboard for pattern visualization
- [ ] Pattern sharing across projects
- [ ] Team collaboration features
- [ ] Second plugin added to marketplace
- [ ] Community contributions

## Key Features by Domain

### Domain: Plugin Distribution

**Feature**: Marketplace catalog
- Central JSON file listing all plugins
- Support for local, GitHub, and Git sources
- Version tracking and metadata
- Category-based organization

### Domain: Local Development

**Feature**: Local testing mode
- No PyPI dependency for testing
- Localhost MCP server connection
- Editable pip installation
- Debug mode support

**Testing Flow**:
1. Install client locally (`pip install -e .`)
2. Add marketplace (local path)
3. Install plugin from marketplace
4. Test with localhost MCP server

### Domain: Pattern Learning (ACE)

**Feature**: Automatic pattern discovery
- PostToolUse hook triggers on Edit/Write
- MCP Sampling for analysis (no API key)
- Pattern curation with confidence thresholds
- Offline training on git history

**Research Foundation**:
- Stanford/SambaNova/UC Berkeley paper
- arXiv:2510.04618v1
- 85% similarity threshold for merging
- 70% confidence for constitution

### Domain: MCP Integration

**Feature**: Thin client architecture
- Zero business logic in client
- All algorithms protected on server
- HTTP transport with auth
- Stateless request forwarding

**Tools Exposed**:
1. `ace_reflect` - Pattern discovery from code
2. `ace_train_offline` - Git history training
3. `ace_get_patterns` - Query pattern database
4. `ace_get_playbook` - Generate recommendations
5. `ace_status` - Database statistics
6. `ace_clear` - Reset database

## Technical Decisions

### Decision 1: Dual Configuration Mode

**Rationale**: Support both local testing and production without republishing

**Implementation**:
- `plugin.json` - Local mode (default)
- `plugin.PRODUCTION.json` - Production template
- Switch by copying file

**Benefits**:
- No PyPI dependency for testing
- Easy transition to production
- Clear separation of concerns

### Decision 2: Thin Client Architecture

**Rationale**: Protect proprietary algorithms while providing open client

**Implementation**:
- Client forwards all requests to server
- No pattern logic in client
- Server handles all computation

**Benefits**:
- IP protection
- Client can be open-sourced
- Easy updates (server-side only)

### Decision 3: FastMCP Framework

**Rationale**: Modern, well-maintained MCP implementation

**Benefits**:
- Clean API
- HTTP transport support
- Active development
- Good documentation

## Installation Flow

### Local Testing

```bash
# 1. Install client
cd mcp-clients/ce-ai-ace-client
pip install -e .

# 2. Add marketplace
/plugin marketplace add /path/to/ce-claude-marketplace

# 3. Install plugin
/plugin install ace-orchestration@ce-dot-net-marketplace
```

### Production (After PyPI)

```bash
# 1. Add marketplace from GitHub
/plugin marketplace add ce-dot-net/ce-claude-marketplace

# 2. Install plugin (client auto-installed via uvx)
/plugin install ace-orchestration@ce-dot-net-marketplace
```

## Next Actions

### Immediate (v0.1.0 Release)
- [x] Create CHANGELOG.md
- [x] Update memory banks
- [x] Commit and tag v0.1.0
- [x] Push to GitHub
- [x] Create GitHub release

### Short-term (v0.2.0)
- [ ] Publish to PyPI
- [ ] Deploy production server
- [ ] Update production config
- [ ] Test end-to-end

### Long-term (v1.0.0)
- [ ] Add second plugin
- [ ] Community features
- [ ] Pattern sharing
- [ ] Web dashboard
