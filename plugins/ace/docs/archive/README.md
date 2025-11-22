# ACE Documentation Archive

This directory contains historical documentation from previous ACE plugin versions.

## Directory Structure

### `/v4-mcp-architecture/`

**Deprecated**: v4.x architecture documentation (MCP-based)

Files archived from v4.x (2024-2025):
- `ACE_MCP_SETUP.md` - MCP server setup instructions
- `MCP_CLIENT_IMPLEMENTATION.md` - MCP client implementation guide
- `MCP_CLIENT_IMPLEMENTATION_NOTES.md` - Technical notes on MCP integration
- `MCP_TEAM_SUMMARY.md` - Team communication about MCP architecture
- `SUBAGENTS.md` - Subagent architecture documentation (Task tool invocations)

**Why archived**: ACE v5.0.0+ uses hooks + ce-ace CLI instead of MCP server. See `CHANGELOG.md` for migration details.

---

## Current Documentation

For up-to-date documentation, see:

- **Installation**: `/docs/guides/INSTALL.md`
- **Configuration**: `/docs/guides/CONFIGURATION.md`
- **Troubleshooting**: `/docs/guides/TROUBLESHOOTING.md`
- **Main README**: `/README.md`
- **Plugin Documentation**: `/CLAUDE.md`

---

## Architecture History

**v1.x-v3.x** (Early 2024): Hooks + Skills (model-invoked)
**v4.x** (Mid 2024): Subagents + MCP server
**v5.x** (Late 2024-2025): Hooks + ce-ace CLI (current)

Each architecture evolution solved specific problems:
- v4.x → Avoided Hook Storm Bug (#3523)
- v5.x → Simplified architecture, removed MCP dependency

---

**Note**: Archived documentation is kept for historical reference only and may not reflect current plugin behavior.
