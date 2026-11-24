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
- `ARCHITECTURE.md` - **System architecture and ACE framework implementation**
- `SECURITY.md` - Security considerations and best practices

### 🎉 [Releases](./releases/)
Release-specific documentation:
- `RELEASE_NOTES_v3.2.md` - Release notes for version 3.2
- `TEST_RESULTS_v3.2.md` - Test results for version 3.2

## 📊 Implementation Status

**ACE Framework Implementation**: **Complete**

- ✅ **Core Principles**: Fully implemented
  - Three-agent architecture (Generator/Reflector/Curator)
  - Incremental delta updates (ADD/UPDATE/DELETE)
  - Four playbook sections (structured pattern organization)
  - Context collapse prevention
  - No labeled supervision (feedback-only learning)

- ✅ **Advanced Features**: Implemented with smart optimizations
  - Semantic deduplication → exact match (cost optimization)
  - Lazy refinement → proactive only (simplified for production)
  - Helpful/harmful marking → Reflector LLM analysis (more accurate)

**See [technical/ARCHITECTURE.md](./technical/ARCHITECTURE.md) for complete implementation details.**

## Main Files

In the plugin root directory:

- **[README.md](../README.md)** - Main plugin README
- **[CHANGELOG.md](../CHANGELOG.md)** - Complete version history

## Quick Start

1. **Installation**: Read [guides/INSTALL.md](./guides/INSTALL.md)
2. **Configuration**: See [guides/CONFIGURATION.md](./guides/CONFIGURATION.md)
3. **Troubleshooting**: Check [guides/TROUBLESHOOTING.md](./guides/TROUBLESHOOTING.md)
4. **Architecture**: Learn about the system in [technical/ARCHITECTURE.md](./technical/ARCHITECTURE.md)

## Commands

### Slash Commands (User-Invoked)

Located in [commands/](../commands/):
- `/ace:ace-status` - View playbook statistics
- `/ace:ace-patterns [section]` - View learned patterns
- `/ace:ace-configure` - Configure ACE server
- `/ace:ace-bootstrap` - Bootstrap from git history
- And more...

## Related Documentation

- **Marketplace Root**: [../../../docs/](../../../docs/)
- **MCP Client**: [ace-sdk repository](https://github.com/ce-dot-net/ace-sdk) (separate repo)
