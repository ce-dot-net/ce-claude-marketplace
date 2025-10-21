# Code Engine ACE - MCP Client

**Intelligent pattern learning and code generation for AI assistants**

[![npm version](https://img.shields.io/npm/v/@ce-dot-net/ace-client.svg)](https://www.npmjs.com/package/@ce-dot-net/ace-client)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Code Engine ACE is a TypeScript MCP (Model Context Protocol) client that enables AI assistants to learn from your coding patterns and improve over time. It implements a three-agent architecture (Generator → Reflector → Curator) that continuously refines code generation based on execution feedback.

---

## ✨ Features

- **🧠 Intelligent Pattern Learning**: Automatically discovers coding patterns from your codebase
- **🔄 Self-Improving**: Learns from execution feedback to generate better code over time
- **🎯 Context-Aware**: Builds domain-specific playbooks tailored to your projects
- **⚡ Fast & Efficient**: Uses semantic similarity and confidence scoring for smart curation
- **🔌 MCP Compatible**: Works with Claude Code, Claude Desktop, Cursor, and any MCP-compatible client
- **🛡️ Privacy-First**: Local or remote storage options - you control your data

---

## 🚀 Quick Start

### Installation

```bash
# Global installation
npm install -g @ce-dot-net/ace-client

# Or use directly with npx
npx @ce-dot-net/ace-client
```

### Configuration

Set up your ACE server connection:

```bash
# Option 1: Environment variables
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_your_api_token_here"
export ACE_PROJECT_ID="prj_your_project_id"

# Option 2: Configuration file (~/.ace/config.json)
{
  "serverUrl": "http://localhost:9000",
  "apiToken": "ace_your_api_token_here",
  "projectId": "prj_your_project_id"
}
```

### Usage

```bash
# Start the MCP server
ace-client

# Or with npx
npx @ce-dot-net/ace-client
```

---

## 🔧 For Claude Code Users

Install the ACE Orchestration plugin for seamless integration:

```bash
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace/plugins/ace-orchestration
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration
```

Restart Claude Code and run:

```
/ace-configure
```

---

## 📚 MCP Tools

The MCP client provides these tools:

### `ace_save_config`
Save ACE server configuration to `~/.ace/config.json`

```typescript
{
  serverUrl: "http://localhost:9000",
  apiToken: "ace_your_token",
  projectId: "prj_your_project"
}
```

### `ace_init`
Initialize pattern learning from your codebase (offline learning)

```typescript
{
  repo_path: "./my-project",
  commit_limit: 100,
  days_back: 30,
  merge_with_existing: true
}
```

### `ace_learn`
Learn from execution feedback (online learning)

```typescript
{
  task: "implement authentication",
  trajectory: [...],
  success: true,
  output: "..."
}
```

### `ace_status`
Get current playbook statistics and server status

### `ace_patterns`
List learned patterns with filtering

```typescript
{
  domain: "error-handling",
  min_confidence: 0.7
}
```

### `ace_get_playbook`
Retrieve structured playbook for a domain

### `ace_clear`
Clear the pattern database

---

## 🏗️ Architecture

### Three-Agent System

1. **Generator** (Your AI Assistant)
   - Executes tasks using the current playbook
   - Generates code based on learned patterns

2. **Reflector** (Pattern Discovery)
   - Analyzes execution outcomes
   - Discovers new patterns from successes and failures
   - Generates delta operations (add/update/remove patterns)

3. **Curator** (Pattern Management)
   - Applies delta operations to the playbook
   - Merges similar patterns (85% similarity threshold)
   - Prunes low-confidence patterns (< 30% confidence)
   - Maintains pattern quality over time

### Configuration Priority

1. Environment variables (highest)
2. `~/.ace/config.json`
3. Default values: `http://localhost:9000` (lowest)

---

## 🔐 Data Privacy

### Local Mode
- All data stored in `.ace-cache/` directory
- SQLite database for fast access
- No external server required

### Remote Mode
- Patterns stored on your ACE server
- Encrypted in transit (HTTPS)
- Multi-tenant isolation
- API token authentication

---

## 🎯 Use Cases

- **Code Generation**: Generate code that follows your team's patterns
- **Refactoring**: Learn preferred refactoring approaches
- **Bug Fixing**: Discover common pitfalls and solutions
- **API Usage**: Learn correct API usage patterns
- **Testing**: Generate tests based on existing test patterns

---

## 📖 Configuration Examples

### Minimal Setup

```json
{
  "serverUrl": "http://localhost:9000",
  "apiToken": "ace_your_token",
  "projectId": "prj_default"
}
```

### Advanced Setup with Custom Thresholds

```bash
export ACE_SERVER_URL="https://ace.yourcompany.com"
export ACE_API_TOKEN="ace_your_token"
export ACE_PROJECT_ID="prj_your_project"
export ACE_SIMILARITY_THRESHOLD="0.90"  # Higher = stricter merging
export ACE_CONFIDENCE_THRESHOLD="0.40"  # Higher = more pruning
```

---

## 🛠️ Development

```bash
# Clone repository
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace/mcp-clients/ce-ai-ace-client

# Install dependencies
npm install

# Build
npm run build

# Run tests
npm test

# Run in development mode
npm run dev
```

---

## 📝 License

MIT © CE.NET Team

---

## 🔗 Links

- **GitHub**: https://github.com/ce-dot-net/ce-claude-marketplace
- **npm Package**: https://www.npmjs.com/package/@ce-dot-net/ace-client
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues
- **Documentation**: https://github.com/ce-dot-net/ce-claude-marketplace/tree/main/plugins/ace-orchestration

---

## 🙏 Contributing

Contributions welcome! Please read our contributing guidelines and submit pull requests to our GitHub repository.

---

## 📞 Support

- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues
- **Email**: ace@ce-dot-net.com

---

**Built with ❤️ by the CE.NET Team**
