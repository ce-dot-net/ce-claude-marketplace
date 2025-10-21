# ACE Orchestration Plugin

**Agentic Context Engineering** - Self-improving Claude Code plugin based on Stanford/SambaNova/UC Berkeley research.

## 📚 Research

Based on [Agentic Context Engineering (ACE)](https://arxiv.org/abs/2510.04618v1)
*Stanford University, SambaNova Systems, UC Berkeley*

## 🎯 Features

- **Pattern Learning**: Automatically discovers coding patterns from your code
- **Offline Training**: Analyzes git history to learn from past commits
- **Playbook Generation**: Creates actionable recommendations
- **Domain Discovery**: Bottom-up taxonomy without hardcoded categories
- **Self-Improving**: Grows smarter as you code

## 🚀 Installation

### Prerequisites

1. **Node.js 18+** - For TypeScript MCP client
2. **Python 3.11+** - For ACE server
3. **Claude Code** - Latest version

### Step 1: Clone Repository

```bash
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace
```

### Step 2: Build MCP Client

```bash
cd mcp-clients/ce-ai-ace-client
npm install
npm run build
cd ../..
```

### Step 3: Configure Plugin

⚠️ **Important**: You must configure your own credentials!

```bash
cd plugins/ace-orchestration

# Copy the template
cp plugin.template.json plugin.json

# Set up environment variables (choose one method):

# Method 1: Add to shell profile (recommended)
echo 'export ACE_SERVER_URL="http://localhost:9000"' >> ~/.zshrc
echo 'export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"' >> ~/.zshrc
echo 'export ACE_PROJECT_ID="prj_5bc0b560221052c1"' >> ~/.zshrc
source ~/.zshrc

# Method 2: Edit plugin.json directly (local testing only)
# Replace ${env:*} with actual values
```

**📖 Full configuration guide**: See [CONFIGURATION.md](./CONFIGURATION.md)

### Step 4: Install Plugin

```bash
# Via symlink (recommended for development)
ln -s "$(pwd)/plugins/ace-orchestration" ~/.config/claude-code/plugins/ace-orchestration

# OR via Claude Code UI
# Plugins → Install from Filesystem → Select plugins/ace-orchestration
```

### Step 5: Start ACE Server

```bash
# In a separate terminal
cd ~/repos/github_com/ce-dot-net/ce-ai-ace/server
python -m uvicorn main:app --reload --port 9000
```

### Step 6: Verify Installation

```bash
# Restart Claude Code

# In Claude Code:
/ace-status

# Expected: Shows pattern database statistics
```

## 🔧 Configuration

**⚠️ Security Warning**: Never commit `plugin.json` with real credentials!

### Quick Start (Environment Variables)

```bash
# Add to ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU"
export ACE_PROJECT_ID="prj_5bc0b560221052c1"
```

### Configuration Files

- **`plugin.template.json`** - Template with env vars (✅ safe to commit)
- **`plugin.json`** - Your config with real values (❌ DON'T commit)
- **`.env.example`** - Example environment file
- **`CONFIGURATION.md`** - Complete configuration guide

### Environment Variables

| Variable | Required | Example |
|----------|----------|---------|
| `ACE_SERVER_URL` | Yes | `http://localhost:9000` |
| `ACE_API_TOKEN` | Yes | `ace_wFIuXzQ...` |
| `ACE_PROJECT_ID` | Yes | `prj_5bc0b56...` |

**📖 See [CONFIGURATION.md](./CONFIGURATION.md) for detailed setup instructions**

## 💻 Slash Commands

### `/ace-status`
View pattern database statistics
```
/ace-status
```

### `/ace-patterns [domain] [confidence]`
List learned patterns with optional filtering
```
/ace-patterns                  # All patterns
/ace-patterns python           # Python patterns only
/ace-patterns error-handling 0.7  # High confidence patterns
```

### `/ace-train-offline`
Train on git history
```
/ace-train-offline
```

### `/ace-force-reflect [file]`
Manually trigger pattern reflection
```
/ace-force-reflect              # Most recent file
/ace-force-reflect src/app.py   # Specific file
```

### `/ace-clear --confirm`
Reset pattern database
```
/ace-clear --confirm
```

## 🤖 Agents

### Reflector
Discovers coding patterns from raw code through analysis.

**Usage**: Automatically invoked via PostToolUse hook when you edit/write code.

### Domain Discoverer
Discovers domain taxonomy from patterns through bottom-up analysis.

**Usage**: Called internally during pattern curation.

### Reflector Prompt
Refines previous analysis with more specific evidence.

**Usage**: Iterative improvement during reflection cycle.

## 🪝 Hooks

### PostToolUse Hook
Automatically triggers pattern reflection after Edit/Write operations.

**When it fires**:
- After editing a file
- After writing a new file
- After making code changes

**What it does**:
1. Extracts the code from the file
2. Calls `ace_reflect` MCP tool
3. Discovers patterns via MCP Sampling
4. Curates patterns into database
5. Silent operation (no interruption)

### PostTaskCompletion Hook
Runs after task completion for additional processing.

## 🔬 How It Works

### ACE Research Framework

**Three Roles**:
1. **Generator** → Uses playbook to write code
2. **Reflector** → Discovers patterns from code
3. **Curator** → Merges patterns with confidence thresholds

**Key Thresholds**:
- **85%** similarity → Merge patterns
- **70%** confidence → Constitution (high-confidence principles)
- **30%** confidence → Minimum to keep (pruning threshold)

### Pattern Discovery Flow

```
User writes code
    ↓
PostToolUse hook fires
    ↓
MCP tool: ace_reflect(code, language, file_path)
    ↓
Reflector discovers patterns (via MCP Sampling)
    ↓
Curator merges similar patterns (85% threshold)
    ↓
Patterns stored in ChromaDB
    ↓
Available via /ace-patterns command
```

## 📊 Example Workflow

```bash
# 1. Check initial state
/ace-status
# Output: Total patterns: 0

# 2. Write some code (Edit/Write tools)
# PostToolUse hook automatically triggers reflection

# 3. Check learned patterns
/ace-patterns
# Output: Shows discovered patterns

# 4. Train on git history
/ace-train-offline
# Analyzes recent commits for patterns

# 5. Generate playbook
# Ask Claude: "Generate a playbook for error handling"
# Uses ace_get_playbook MCP tool

# 6. Check final state
/ace-status
# Output: Total patterns: 15, High confidence: 3
```

## 🎓 Research Compliance

This plugin implements the complete ACE research framework:

- ✅ **MCP Sampling** - Uses client's LLM (no API key needed)
- ✅ **Grow-and-Refine** - Incremental pattern updates
- ✅ **Confidence-Based Curation** - Evidence-driven learning
- ✅ **Domain Discovery** - Bottom-up taxonomy (no hardcoded)
- ✅ **Prevents Context Collapse** - Delta updates, not monolithic
- ✅ **Embeddings** - Semantic similarity (sentence-transformers)
- ✅ **Playbook Generation** - ACE Figure 3 format

## 🔐 Data Privacy

### Local Mode
- All data stored locally in `.ace-memory/`
- Pattern database: SQLite + ChromaDB
- No data sent to external servers
- Full control over your patterns

### Remote Mode
- Code analysis done via MCP Sampling (your Claude instance)
- Patterns stored in your account on remote server
- Encrypted in transit (HTTPS)
- API token required for access

## 🐛 Troubleshooting

### Plugin won't start
```bash
# Check MCP server is installed
which python3
pip show fastmcp

# For LOCAL mode, check server location
ls -la ../../../ce-mcp-ace/ce-ai-ace-server
```

### MCP tools not appearing
```bash
# Restart Claude Code
# Check plugin is enabled in settings
# Check MCP logs for errors
```

### Pattern database errors
```bash
# Clear and reset
/ace-clear --confirm
```

## 📝 License

MIT License - See LICENSE file for details

## 🔗 Links

- **Research Paper**: https://arxiv.org/abs/2510.04618
- **Server Repo**: Private (algorithms protected)
- **MCP Client**: `mcp-clients/ce-ai-ace-client/`
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

## 🚀 Coming Soon

- Web dashboard for pattern visualization
- Pattern sharing across projects
- Team collaboration features
- Advanced playbook customization
