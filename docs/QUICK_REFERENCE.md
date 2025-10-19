# ACE Orchestration - Quick Reference

## 🎯 One-Liner Installation (LOCAL MODE)

```bash
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace/plugins/ace-orchestration && cp plugin.LOCAL.json plugin.json && cd ../.. && claude-code plugin install ./plugins/ace-orchestration
```

## 📁 File Locations

| File | Path | Purpose |
|------|------|---------|
| Plugin (REMOTE) | `plugins/ace-orchestration/plugin.json` | Production config |
| Plugin (LOCAL) | `plugins/ace-orchestration/plugin.LOCAL.json` | Development config |
| Plugin README | `plugins/ace-orchestration/README.md` | Full documentation |
| Client Code | `mcp-clients/ce-ai-ace-client/` | Thin MCP client |
| Client Install | `mcp-clients/ce-ai-ace-client/INSTALL.md` | PyPI instructions |
| Setup Guide | `docs/SETUP_INSTRUCTIONS.md` | This comprehensive guide |
| Quick Reference | `docs/QUICK_REFERENCE.md` | This file |

## ✅ Configuration Status

**Files Present**:
- ✅ `plugin.json` (REMOTE mode)
- ✅ `plugin.LOCAL.json` (LOCAL mode)
- ✅ Complete documentation
- ✅ Thin MCP client ready

**Not Required**:
- ❌ `marketplace.json` (optional, not needed)

## 🔧 MCP Server Details

**Server Name**: `ace-pattern-learning`

**Tool Prefix**: `mcp__ace-pattern-learning__*`

**Available Tools**:
```
mcp__ace-pattern-learning__ace_reflect
mcp__ace-pattern-learning__ace_train_offline
mcp__ace-pattern-learning__ace_get_patterns
mcp__ace-pattern-learning__ace_get_playbook
mcp__ace-pattern-learning__ace_status
mcp__ace-pattern-learning__ace_clear
```

## 💬 Plugin Commands

| Command | Description |
|---------|-------------|
| `/ace-status` | System status and stats |
| `/ace-patterns` | List learned patterns |
| `/ace-playbook` | Generate workflow guide |
| `/ace-reflect` | Manual reflection trigger |
| `/ace-train-offline` | Import external patterns |
| `/ace-clear --confirm` | Delete all patterns |

## 🚀 Quick Test

```bash
# 1. Open Claude Code
claude-code

# 2. Check plugin loaded
# Look for "ace-pattern-learning" in MCP servers list

# 3. Test command
/ace-status

# Expected output:
# Total Patterns: 0
# Active Generator: TRUE
# Active Reflector: TRUE
# Active Curator: TRUE
```

## 🔄 Switch Between Modes

### Switch to LOCAL Mode (Development)
```bash
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace/plugins/ace-orchestration
cp plugin.LOCAL.json plugin.json
claude-code plugin reload ace-orchestration
```

### Switch to REMOTE Mode (Production)
```bash
cd ~/repos/github_com/ce-dot-net/ce-claude-marketplace/plugins/ace-orchestration
git restore plugin.json  # Reset to REMOTE mode
export ACE_API_TOKEN="your-token-here"
claude-code plugin reload ace-orchestration
```

## 🐛 Common Issues

### Plugin Not Found
```bash
# Verify path
ls -la ~/repos/github_com/ce-dot-net/ce-claude-marketplace/plugins/ace-orchestration/plugin.json
```

### MCP Server Not Starting (LOCAL)
```bash
# Check server repo exists
ls -la ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server/

# Test server manually
cd ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server
python3 -m ace_server
```

### Tools Not Available
```bash
# Check Claude Code logs
tail -f ~/.claude/logs/claude-code.log

# Restart Claude Code
claude-code restart
```

## 📦 Server Dependencies

**Private Server Repo**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace`

**Required for LOCAL Mode**:
```bash
cd ~/repos/github_com/ce-dot-net/ce-ai-ace/ce-ai-ace-server
pip install -e .
```

**Key Dependencies**:
- `fastmcp>=2.12.5` - MCP server framework
- `chromadb>=0.5.23` - Vector database
- `sentence-transformers>=3.3.1` - Embeddings (all-MiniLM-L6-v2)
- `pydantic>=2.0` - Data validation
- `httpx>=0.28.1` - HTTP client

## 🌐 Production Deployment

**Required Steps**:
1. Deploy server to production domain
2. Publish client to PyPI: `cd mcp-clients/ce-ai-ace-client && python -m build && twine upload dist/*`
3. Update `plugin.json` with production URL
4. Set `ACE_API_TOKEN` environment variable
5. Reload plugin: `claude-code plugin reload ace-orchestration`

## 📚 Documentation Links

- **Full Setup**: `docs/SETUP_INSTRUCTIONS.md`
- **Plugin README**: `plugins/ace-orchestration/README.md`
- **Client Install**: `mcp-clients/ce-ai-ace-client/INSTALL.md`
- **ACE Research**: https://arxiv.org/abs/2510.04618v1
- **FastMCP**: https://gofastmcp.com
- **MCP Protocol**: https://modelcontextprotocol.io

## 🎓 Serena Memory

Access setup info from Serena Memory Bank:
```python
# Read ACE setup from memory
mcp__serena__read_memory(memory_file_name="ace_plugin_setup.md")

# List all memories
mcp__serena__list_memories()
```

---

**Version**: 2.5.0
**Last Updated**: 2025-10-19
**Status**: ✅ Ready for testing
