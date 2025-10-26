# ACE Orchestration Plugin

**Agentic Context Engineering** - Self-improving Claude Code plugin using automatic pattern learning.

## 🎯 Features (v3.2.4)

### 🤖 Automatic Learning Cycle (NEW!)
- **ACE Playbook Retrieval Skill**: Auto-fetches learned patterns BEFORE tasks
- **ACE Learning Skill**: Auto-captures insights AFTER task completion
- **Model-Invoked**: Claude decides when to use skills (no manual intervention)
- **3-Tier Caching**: RAM → SQLite → Server for fast retrieval
- **Complete Cycle**: Retrieve → Use → Learn → Update → Repeat

### 📚 Pattern Learning
- **Pattern Discovery**: Automatically learns from execution feedback
- **Server-Side Intelligence**: Reflector (Sonnet 4) + Curator (Haiku 4.5)
- **Delta Updates**: Incremental playbook improvements (prevents context collapse)
- **4 Playbook Sections**: Strategies, code snippets, troubleshooting, APIs
- **Quality Scoring**: Helpful/harmful feedback refines patterns over time

### 🚀 Key Benefits
- **Self-Improving**: Each task makes Claude smarter
- **Token-Efficient**: Progressive disclosure, only loads when needed
- **Fast**: Cached playbook retrieval (milliseconds)
- **Universal**: Works with ANY MCP client (Claude Code, Cursor, Cline, etc.)
- **Proven Effective**: Significant performance improvement on agentic tasks

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

### Step 7: Initialize ACE in Your Project (One-Time)

```bash
# Add ACE instructions to your project's CLAUDE.md
/ace-claude-init

# Expected: Full ACE instructions copied inline to CLAUDE.md (~289 lines)

# Optionally bootstrap playbook from git history
/ace-bootstrap --commits 100 --days 30

# Expected: Playbook populated with patterns from past commits
```

**What This Does:**
- `/ace-claude-init` - Copies full ACE plugin instructions inline into your project's CLAUDE.md (~289 lines, provides always-on context about ACE architecture)
- `/ace-bootstrap` - Optional: Analyzes git history and local files to populate initial playbook patterns

**You're Done!** ACE will now automatically:
- Retrieve learned patterns before complex tasks (implementation, debugging, refactoring)
- Capture new insights after substantial work completion

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

## 🤖 Agent Skills (Automatic)

### ACE Playbook Retrieval (Before Tasks)
**Model-Invoked**: Claude automatically activates before complex tasks

**Triggers**: implement, build, create, fix, debug, refactor, integrate, optimize

**What it does**:
- Calls `mcp__ace-pattern-learning__ace_get_playbook`
- Retrieves strategies, code snippets, troubleshooting tips, API recommendations
- Uses 3-tier cache (RAM → SQLite → Server) for speed

**Result**: Claude has organizational knowledge BEFORE starting!

### ACE Learning from Execution (After Tasks)
**Model-Invoked**: Claude automatically activates after substantial work

**Triggers**: Successful implementations, debugging, refactoring, API integrations

**What it does**:
- Calls `mcp__ace-pattern-learning__ace_learn`
- Captures task description, trajectory, feedback, lessons learned
- Sends to ACE Server for Reflector (Sonnet 4) → Curator (Haiku 4.5) analysis

**Result**: Playbook updated with new patterns!

### The Complete Automatic Cycle

```
User Request → Retrieval Skill → Playbook Fetched → Claude Executes with Patterns →
Learning Skill → Server Analysis → Playbook Updated → Next Request (Enhanced!) 🎯
```

**📖 Full documentation**: See [CLAUDE.md](./CLAUDE.md) for complete cycle details

## 💻 Slash Commands (Manual Override)

While skills handle automatic operation, manual commands are available:

### `/ace-patterns [section]`
View playbook manually
```
/ace-patterns                           # All sections
/ace-patterns strategies                # Architectural patterns
/ace-patterns code-snippets             # Reusable code
/ace-patterns troubleshooting           # Known issues & solutions
/ace-patterns apis                      # Recommended libraries
```

### `/ace-status`
Check playbook statistics
```
/ace-status
```

### `/ace-configure`
Interactive ACE server configuration
```
/ace-configure
```

### `/ace-claude-init`
Initialize ACE in project CLAUDE.md (one-time setup)
```
/ace-claude-init
```

### `/ace-bootstrap`
Bootstrap playbook from git history
```
/ace-bootstrap
/ace-bootstrap --commits 100 --days 30
```

### `/ace-clear --confirm`
Clear entire playbook (requires confirmation)
```
/ace-clear --confirm
```

### `/ace-export-patterns` / `/ace-import-patterns`
Backup and restore playbook
```
/ace-export-patterns
/ace-import-patterns
```

## 🪝 Hooks (Minimal)

### SessionStart Hook
Injects CLAUDE.md reference to make plugin instructions available.

**When it fires**: At session start or resume

### PostToolUse Hook (Bash Logging)
Logs Bash command executions for debugging.

**When it fires**: After Bash tool executes

**Note**: Skills handle the main automation now! Hooks are minimal and non-intrusive.

## 🔬 How It Works (v3.2.4)

### ACE Research Paper Architecture

**Generator → Reflector → Curator → Playbook Cycle**

1. **Generator**: Claude Code with Agent Skills
2. **Playbook**: Evolving context with learned patterns (4 sections)
3. **Reflector**: Server-side pattern analysis (Sonnet 4 for intelligence)
4. **Curator**: Server-side delta updates (Haiku 4.5 for cost efficiency)
5. **Merge**: Non-LLM algorithm for incremental updates

### Automatic Learning Flow

```
┌─────────────────────────────────────────────┐
│ User: "Implement JWT authentication"        │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ ACE Playbook Retrieval Skill AUTO-INVOKES  │
│ - Fetches learned patterns from cache/server│
│ - Returns: "Refresh token rotation best"   │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Claude Implements with Learned Patterns     │
│ - Uses strategies from playbook             │
│ - Avoids known pitfalls                     │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ ACE Learning Skill AUTO-INVOKES            │
│ - Captures: task + trajectory + feedback   │
│ - Sends to ACE Server                       │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Server-Side Processing                      │
│ - Reflector analyzes execution trace       │
│ - Curator creates delta updates            │
│ - Merge algorithm updates playbook          │
└─────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────┐
│ Next Session: Enhanced Playbook Retrieved! │
│ Knowledge compounds over time! 🎯           │
└─────────────────────────────────────────────┘
```

### Playbook Sections

1. **strategies_and_hard_rules**: Architectural patterns, coding principles
2. **useful_code_snippets**: Reusable code with tested implementations
3. **troubleshooting_and_pitfalls**: Known issues, gotchas, solutions
4. **apis_to_use**: Recommended libraries, frameworks, integration patterns

## 📊 Example Workflow (v3.2.7)

### First-Time Setup
```bash
# 1. Configure ACE server connection
/ace-configure
# Interactive prompts for server URL, API token, project ID

# 2. Initialize ACE in your project (required for full cycle)
/ace-claude-init
# Copies full ACE instructions inline to project CLAUDE.md (~289 lines)

# 3. Optional: Bootstrap playbook from git history
/ace-bootstrap --commits 100 --days 30
# Analyzes past commits to build initial playbook

# 4. Check initial state
/ace-status
# Output: Shows playbook statistics
```

### Automatic Learning in Action

```bash
# 1. User requests task
User: "Implement JWT authentication with refresh tokens"

# 2. ACE Playbook Retrieval Skill AUTO-INVOKES (no manual action!)
# - Fetches learned patterns from previous sessions
# - Returns: "Refresh token rotation prevents theft attacks"

# 3. Claude implements using learned pattern
# - Short-lived access tokens (15 min)
# - Rotating refresh tokens (7 days)
# - HttpOnly cookies for security

# 4. ACE Learning Skill AUTO-INVOKES after completion
# - Captures successful implementation
# - Sends feedback to server
# - Pattern reinforced with +1 helpful score

# 5. Next similar task is faster!
User: "Add OAuth2 authentication"
# Retrieval skill fetches: JWT patterns + auth strategies
# Implementation uses proven patterns from the start
```

### Manual Playbook Review

```bash
# Check what's been learned
/ace-patterns strategies
# Shows architectural patterns

/ace-patterns code-snippets
# Shows reusable code patterns

/ace-patterns troubleshooting
# Shows known issues & solutions

# View statistics
/ace-status
# Shows: total bullets, by section, top helpful/harmful
```

## 🎯 Architecture (v3.2.4)

This plugin implements the complete ACE framework architecture:

- ✅ **Automatic Retrieval** - Skills fetch playbook BEFORE tasks (Generator uses context)
- ✅ **Automatic Learning** - Skills capture feedback AFTER tasks (closes the loop)
- ✅ **Server-Side Intelligence** - Reflector (Sonnet 4) + Curator (Haiku 4.5)
- ✅ **Delta Updates** - Incremental improvements prevent context collapse
- ✅ **4-Section Playbook** - Structured pattern organization
- ✅ **Quality Scoring** - Helpful/harmful feedback refines patterns
- ✅ **Cost Optimized** - Sonnet for intelligence, Haiku for efficiency (60% savings)
- ✅ **Universal MCP** - Works with ANY MCP client (no sampling required)
- ✅ **3-Tier Cache** - Fast retrieval (RAM → SQLite → Server)
- ✅ **Model-Invoked Skills** - Claude decides when to use (fully automatic)

**Result**: Achieves significant performance improvement on agentic tasks!

## 🔐 Data Privacy

### MCP Client (Local)
- **3-Tier Cache**: RAM (session) → SQLite (`~/.ace-cache/`) → Server
- **Config**: `~/.ace/config.json` (server URL, API token, project ID)
- **No Code Sent**: Only execution traces (task, trajectory, feedback)
- **Encrypted Transit**: HTTPS to ACE server

### ACE Server (Your Account)
- **Playbook Storage**: Your patterns stored in your project
- **Server-Side Analysis**: Reflector (Sonnet 4) + Curator (Haiku 4.5)
- **API Token Required**: Secure access to your playbook
- **No Sharing**: Patterns remain in your project unless you export

### What Gets Sent to Server
- ✅ Task descriptions ("Implement JWT auth")
- ✅ Execution trajectories (steps taken)
- ✅ Feedback and lessons learned
- ❌ Full source code files (not sent!)
- ❌ Credentials or secrets

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

- **MCP Client**: `mcp-clients/ce-ai-ace-client/`
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

## 🚀 Coming Soon

- Web dashboard for pattern visualization
- Pattern sharing across projects
- Team collaboration features
- Advanced playbook customization
