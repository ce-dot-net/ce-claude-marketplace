# ACE FastMCP Client

**Thin MCP client for connecting to remote ACE Pattern Learning server.**

## Purpose

This client allows users to connect to your hosted ACE server WITHOUT seeing your secret sauce:
- ✅ Curator algorithm (pattern merging logic)
- ✅ Reflector prompts (pattern discovery)
- ✅ Storage implementation (ChromaDB)
- ✅ All proprietary code

## Architecture

```
User's Machine                          Your Server
┌─────────────────────┐                ┌──────────────────────┐
│  Claude Code        │                │  FastMCP Server      │
│  (Client)           │                │  (SECRET SAUCE! 🔐)  │
└──────────┬──────────┘                └──────────┬───────────┘
           │                                      │
           │ STDIO                                │
           │                                      │
┌──────────▼──────────┐                          │
│  Thin MCP Client    │  ← User installs         │
│  (This package)     │    (no secrets here!)    │
└──────────┬──────────┘                          │
           │                                      │
           │ HTTPS/WSS                            │
           │ (encrypted)                          │
           └──────────────────────────────────────┘
```

## Installation

```bash
# Via pip
pip install ce-ai-ace-client

# Via uvx (recommended)
uvx ce-ai-ace-client
```

## Configuration

### For Claude Code Plugin

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "uvx",
      "args": ["ce-ai-ace-client"],
      "env": {
        "ACE_SERVER_URL": "https://ace.your-domain.com/mcp",
        "ACE_API_TOKEN": "${ACE_API_TOKEN}",
        "ACE_STORAGE_PATH": "${CLAUDE_PLUGIN_ROOT}/.ace-memory/patterns.db"
      }
    }
  }
}
```

### Environment Variables

- `ACE_SERVER_URL` - Your hosted server URL (required)
- `ACE_API_TOKEN` - API token for authentication (required)
- `ACE_STORAGE_PATH` - Local path for pattern storage (optional, defaults to `~/.ace-memory/patterns.db`)

## What Gets Stored Locally

Even with a remote server, pattern data is stored **locally on the user's machine**:
- ✅ Pattern database (`.ace-memory/chroma/`)
- ✅ Pattern metadata (confidence, observations)
- ✅ Playbook cache

**What's remote (your secret sauce):**
- ❌ Curator algorithm (how patterns are merged)
- ❌ Reflector prompts (how patterns are discovered)
- ❌ Similarity thresholds and logic
- ❌ Embedding model details

## Security

- All communication is **encrypted** (HTTPS/WSS)
- API tokens are **never logged** or exposed
- User data (code, patterns) is transmitted securely
- Server authenticates all requests

## Development

```bash
# Clone and install
git clone https://github.com/ce-dot-net/ce-ai-ace-client
cd ce-ai-ace-client
pip install -e .

# Run locally (for testing)
python -m ace_client

# Point to local server
export ACE_SERVER_URL="http://localhost:8000/mcp"
export ACE_API_TOKEN="test-token"
python -m ace_client
```

## License

MIT License - Copyright (c) 2025 CE Team
