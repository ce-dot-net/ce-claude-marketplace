# ACE Orchestration Plugin Documentation

Comprehensive documentation for the ACE Orchestration plugin.

## Documentation Structure

### 📖 [Guides](./guides/)
User-facing documentation:
- `CONFIGURATION.md` - Configuration and setup options
- `INSTALL.md` - Installation instructions
- `TROUBLESHOOTING.md` - Common issues and solutions

### 🏗️ [Technical](./technical/)
Technical and architectural documentation:
- `ARCHITECTURE.md` - **System architecture and ACE research paper verification (95% alignment)**
- `SECURITY.md` - Security considerations and best practices

### 🎉 [Releases](./releases/)
Release-specific documentation:
- `RELEASE_NOTES_v3.2.md` - Release notes for version 3.2
- `TEST_RESULTS_v3.2.md` - Test results for version 3.2

## 📊 Implementation Status

**ACE Research Paper Compliance**: **95% alignment**

- ✅ **Core Principles**: 10/10 implemented
  - Three-agent architecture (Generator/Reflector/Curator)
  - Incremental delta updates (ADD/UPDATE/DELETE)
  - Four playbook sections as specified in paper
  - Context collapse prevention
  - No labeled supervision (feedback-only learning)

- ⚠️ **Advanced Features**: 3/3 with smart cost optimizations
  - Semantic deduplication → exact match (cost optimization)
  - Lazy refinement → proactive only (simplified for production)
  - Helpful/harmful marking → Reflector LLM analysis (more accurate)

**See [technical/ARCHITECTURE.md](./technical/ARCHITECTURE.md#-implementation-status-95-paper-alignment) for complete verification details.**

## Main Files

In the plugin root directory:

- **[README.md](../README.md)** - Main plugin README
- **[CHANGELOG.md](../CHANGELOG.md)** - Complete version history
- **[CLAUDE.md](../CLAUDE.md)** - Claude Code integration instructions (copied to projects via `/ace-claude-init`)

## Quick Start

1. **Installation**: Read [guides/INSTALL.md](./guides/INSTALL.md)
2. **Configuration**: See [guides/CONFIGURATION.md](./guides/CONFIGURATION.md)
3. **Troubleshooting**: Check [guides/TROUBLESHOOTING.md](./guides/TROUBLESHOOTING.md)
4. **Architecture**: Learn about the system in [technical/ARCHITECTURE.md](./technical/ARCHITECTURE.md)

## Skills & Commands

### Agent Skills (Model-Invoked)

Located in [skills/](../skills/):
- **ace-playbook-retrieval** - Retrieves learned patterns before tasks
- **ace-learning** - Captures learning after task completion

### Slash Commands (User-Invoked)

Located in [commands/](../commands/):
- `/ace-status` - View playbook statistics
- `/ace-patterns [section]` - View learned patterns
- `/ace-configure` - Configure ACE server
- `/ace-claude-init` - Initialize ACE in project CLAUDE.md
- `/ace-bootstrap` - Bootstrap from git history
- And more...

## Related Documentation

- **Marketplace Root**: [../../../docs/](../../../docs/)
- **MCP Client**: [../../../mcp-clients/ce-ai-ace-client/](../../../mcp-clients/ce-ai-ace-client/)
