# CE Claude Marketplace

Public repository for Claude Code plugins and MCP clients.

## 📦 Available Plugins

### ACE Orchestration
**Agentic Context Engineering** - Self-improving Claude Code plugin based on Stanford/SambaNova/UC Berkeley research.

- **Location**: `plugins/ace-orchestration/`
- **Research**: [arXiv:2510.04618v1](https://arxiv.org/abs/2510.04618)
- **Features**: Pattern learning, offline training, playbook generation

**Installation**:
```bash
claude-code plugin install ce-dot-net/ace-orchestration
```

**Slash Commands**:
- `/ace-status` - View pattern database statistics
- `/ace-patterns [domain] [confidence]` - List learned patterns
- `/ace-train-offline` - Train on git history
- `/ace-force-reflect [file]` - Manually trigger reflection
- `/ace-clear --confirm` - Reset database

## 🔌 Available MCP Clients

### CE AI ACE Client
**Thin MCP client** for connecting to ACE pattern learning server.

- **Location**: `mcp-clients/ce-ai-ace-client/`
- **PyPI**: `ce-ai-ace-client` (coming soon)
- **Purpose**: Connects Claude Code to remote ACE server

**Installation**:
```bash
uvx ce-ai-ace-client
```

**Configuration**:
```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "uvx",
      "args": ["ce-ai-ace-client"],
      "env": {
        "ACE_SERVER_URL": "https://ace.your-server.com/mcp",
        "ACE_API_TOKEN": "${ACE_API_TOKEN}"
      }
    }
  }
}
```

## 📚 Documentation

Each plugin and client includes its own README with detailed documentation.

## 🚀 Coming Soon

More plugins and MCP clients will be added as they become available.

## 📄 License

MIT License - See individual plugin/client directories for details.
