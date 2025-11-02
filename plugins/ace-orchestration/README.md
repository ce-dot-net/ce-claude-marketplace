# ACE Orchestration Plugin

**Agentic Context Engineering** - Self-improving Claude Code plugin using automatic pattern learning.

## 🎯 Features

### 🤖 Automatic Learning Cycle
- **ACE Playbook Retrieval Skill**: Auto-fetches learned patterns BEFORE tasks
- **ACE Learning Skill**: Auto-captures insights AFTER task completion
- **Model-Invoked**: Claude decides when to use skills (no manual intervention)
- **3-Tier Caching**: RAM → SQLite → Server for fast retrieval
- **Complete Cycle**: Retrieve → Use → Learn → Update → Repeat

### 🔍 Semantic Search & Targeted Retrieval (NEW in v3.3.0!)
- **50-80% Token Reduction**: Semantic search returns only relevant patterns
- **Intelligent Tool Selection**: Skills automatically choose optimal retrieval method
- **Natural Language Queries**: `/ace-search "JWT authentication"` finds matching patterns
- **Quality Filtering**: `/ace-top` retrieves highest-rated patterns by helpful score
- **Batch Retrieval**: 10x-50x faster bulk pattern fetching

### 📚 Pattern Learning
- **Pattern Discovery**: Automatically learns from execution feedback
- **Server-Side Intelligence**: Reflector (Sonnet 4) + Curator (Haiku 4.5)
- **Delta Operations**: Manual pattern management (add/update/remove)
- **Runtime Configuration**: Adjust server settings without code changes
- **4 Playbook Sections**: Strategies, code snippets, troubleshooting, APIs
- **Quality Scoring**: Helpful/harmful feedback refines patterns over time

### 🚀 Key Benefits
- **Self-Improving**: Each task makes Claude smarter
- **Token-Efficient**: 50-80% reduction with semantic search
- **Fast**: Cached playbook retrieval (milliseconds) + batch operations
- **Universal**: Works with ANY MCP client (Claude Code, Cursor, Cline, etc.)
- **Proven Effective**: Significant performance improvement on agentic tasks

## 🚀 Installation

### Prerequisites

1. **Node.js 18+** - For TypeScript MCP client
2. **Python 3.11+** - For ACE server (optional, for self-hosted)
3. **Claude Code** - Latest version

### Step 1: Clone Repository

```bash
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace
```

### Step 2: MCP Client

The ACE MCP Client (@ce-dot-net/ace-client) is maintained in a separate repository and published to npm. The plugin automatically uses the latest version from npm - no manual build required!

**MCP Client Repository**: https://github.com/ce-dot-net/ce-ace-mcp

### Step 3: Configure ACE

**ACE uses dual-configuration**: Global org settings + per-project settings.

**Option 1: Interactive Configuration (Recommended)**
```bash
# In Claude Code, run:
/ace-orchestration:ace-configure

# This creates:
# - ~/.config/ace/config.json (global: serverUrl, apiToken, cache settings)
# - .claude/settings.json (project: MCP server with projectId)
```

**What Gets Created**:

**Global Config** (`~/.config/ace/config.json`):
```json
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "ace_your_api_token_here",
  "cacheTtlMinutes": 120,
  "autoUpdateEnabled": true
}
```

**Project Config** (`.claude/settings.json`):
```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": ["--yes", "@ce-dot-net/ace-client@3.7.2", "--project-id", "prj_your_project_id"]
    }
  }
}
```

**Option 2: Environment Variables**
```bash
# Add to shell profile
echo 'export ACE_SERVER_URL="https://ace-api.code-engine.app"' >> ~/.zshrc
echo 'export ACE_API_TOKEN="ace_your_api_token_here"' >> ~/.zshrc
echo 'export ACE_PROJECT_ID="prj_your_project_id"' >> ~/.zshrc
source ~/.zshrc
```

**📖 Full configuration guide**: See [docs/guides/CONFIGURATION.md](./docs/guides/CONFIGURATION.md)

### Step 4: Install Plugin

```bash
# Via symlink (recommended for development)
ln -s "$(pwd)/plugins/ace-orchestration" ~/.config/claude-code/plugins/ace-orchestration

# OR via Claude Code UI
# Plugins → Install from Filesystem → Select plugins/ace-orchestration
```

### Step 5: Verify Installation

```bash
# Restart Claude Code

# In Claude Code:
/ace-orchestration:ace-status

# Expected: Shows pattern database statistics
```

### Step 6: Initialize ACE in Your Project (One-Time)

```bash
# Add ACE instructions to your project's CLAUDE.md
/ace-orchestration:ace-claude-init

# Expected: Full ACE instructions copied inline to CLAUDE.md (~289 lines)

# Optionally bootstrap playbook from git history
/ace-orchestration:ace-bootstrap --commits 100 --days 30

# Expected: Playbook populated with patterns from past commits
```

**What This Does:**
- `/ace-orchestration:ace-claude-init` - Copies full ACE plugin instructions inline into your project's CLAUDE.md (~289 lines, provides always-on context about ACE architecture)
- `/ace-orchestration:ace-bootstrap` - Optional: Analyzes git history and local files to populate initial playbook patterns

**You're Done!** ACE will now automatically:
- Retrieve learned patterns before complex tasks (implementation, debugging, refactoring)
- Capture new insights after substantial work completion

## 🔧 Configuration

**⚠️ Security Warning**: Never commit `plugin.json` with real credentials!

### Quick Start (Environment Variables)

```bash
# Add to ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_your_api_token_here"
export ACE_PROJECT_ID="prj_your_project_id"
```

### Configuration Files

- **`plugin.template.json`** - Template with env vars (✅ safe to commit)
- **`plugin.json`** - Your config with real values (❌ DON'T commit)
- **`.env.example`** - Example environment file
- **`CONFIGURATION.md`** - Complete configuration guide

### Environment Variables

| Variable | Required | Example |
|----------|----------|---------|
| `ACE_SERVER_URL` | Yes | `https://ace-api.code-engine.app` |
| `ACE_API_TOKEN` | Yes | `ace_your_api_token...` |
| `ACE_PROJECT_ID` | Yes | `prj_your_project...` |

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

## 💻 Slash Commands

While skills handle automatic operation, manual commands are available:

### 🔍 Retrieval Commands (NEW in v3.3.0)

#### `/ace-orchestration:ace-search <query>`
Semantic search for patterns (50-80% token reduction)
```
/ace-orchestration:ace-search "JWT authentication"        # Find auth patterns
/ace-orchestration:ace-search "async debugging"           # Find async troubleshooting
/ace-orchestration:ace-search "database optimization"     # Find DB performance patterns
```

#### `/ace-orchestration:ace-top <section> [limit]`
Get highest-rated patterns by helpful score
```
/ace-orchestration:ace-top strategies_and_hard_rules 10   # Top 10 architectural patterns
/ace-orchestration:ace-top troubleshooting_and_pitfalls 5 # Top 5 debugging patterns
/ace-orchestration:ace-top apis_to_use                    # All top-rated APIs
```

#### `/ace-orchestration:ace-patterns [section]`
View full playbook (comprehensive)
```
/ace-orchestration:ace-patterns                           # All sections
/ace-orchestration:ace-patterns strategies                # Architectural patterns
/ace-orchestration:ace-patterns code-snippets             # Reusable code
/ace-orchestration:ace-patterns troubleshooting           # Known issues & solutions
/ace-orchestration:ace-patterns apis                      # Recommended libraries
```

**When to use**: `/ace-orchestration:ace-search` for specific queries, `/ace-orchestration:ace-top` for best practices, `/ace-orchestration:ace-patterns` for multi-domain tasks.

### ⚙️ Configuration Commands (NEW in v3.3.0)

#### `/ace-orchestration:ace-tune [action] [params]`
Runtime server configuration
```
/ace-orchestration:ace-tune show                        # View current configuration
/ace-orchestration:ace-tune token-budget 50000          # Enable token budget
/ace-orchestration:ace-tune search-threshold 0.8        # Adjust semantic search sensitivity
```

#### `/ace-orchestration:ace-configure`
Interactive ACE server connection setup
```
/ace-orchestration:ace-configure
```

### 📝 Management Commands

#### `/ace-orchestration:ace-delta [operation] [pattern]` (NEW in v3.3.0)
Manual pattern operations (advanced)
```
/ace-orchestration:ace-delta add "pattern text" section   # Add pattern manually
/ace-orchestration:ace-delta update pattern-id helpful=5  # Update pattern score
/ace-orchestration:ace-delta remove pattern-id            # Remove pattern
```

#### `/ace-orchestration:ace-status`
Check playbook statistics
```
/ace-orchestration:ace-status
```

#### `/ace-orchestration:ace-claude-init`
Initialize ACE in project CLAUDE.md (one-time setup)
```
/ace-orchestration:ace-claude-init                       # Initial setup
/ace-orchestration:ace-claude-init --update              # Update existing ACE section
```

#### `/ace-orchestration:ace-enable-auto-update`
Toggle automatic CLAUDE.md updates on plugin version changes
```
/ace-orchestration:ace-enable-auto-update                # Check status and toggle
```

**What it does:**
- Enables/disables automatic ACE instruction updates in your project's CLAUDE.md
- When enabled: ACE silently updates your CLAUDE.md on session start when plugin version changes
- When disabled: You'll be notified but must run `/ace-orchestration:ace-claude-init --update` manually
- Creates backups before updates (CLAUDE.md.backup-YYYYMMDD-HHMMSS)
- Zero-token cost when enabled (script-based updates)

#### `/ace-orchestration:ace-test`
Verify ACE plugin is working correctly
```
/ace-orchestration:ace-test
```

**What it does:**
- Checks if ACE skills are loaded (ace-playbook-retrieval, ace-learning)
- Verifies MCP server connection
- Shows playbook statistics
- Lists available ACE tools
- Displays current configuration

#### `/ace-orchestration:ace-bootstrap`
Bootstrap playbook from docs, git history, and current code
```
/ace-orchestration:ace-bootstrap                          # Hybrid mode (docs → git → files)
/ace-orchestration:ace-bootstrap --mode git-history       # Git history only
/ace-orchestration:ace-bootstrap --thoroughness deep      # Deep analysis
```

#### `/ace-orchestration:ace-clear --confirm`
Clear entire playbook (requires confirmation)
```
/ace-orchestration:ace-clear --confirm
```

#### `/ace-orchestration:ace-export-patterns` / `/ace-orchestration:ace-import-patterns`
Backup and restore playbook
```
/ace-orchestration:ace-export-patterns
/ace-orchestration:ace-import-patterns
```

## 🪝 Hooks (ACE Enforcement & Automation)

### UserPromptSubmit Hook (NEW in v3.3.1)
**Critical for ACE auto-triggering reliability!**

Injects ACE trigger reminder before EVERY user prompt.

**When it fires**: Before Claude processes each user message

**What it does**:
```
⚠️ ACE TRIGGER CHECK: If this message contains trigger words
(implement|build|create|update|modify|fix|debug|refactor|optimize|integrate|
configure|setup|deploy|test|verify|validate|add|develop|write|change|edit|
enhance|extend|revise|troubleshoot|resolve|diagnose|improve|restructure|
connect|install|architect|design|plan|migrate|upgrade), invoke
ace-playbook-retrieval skill BEFORE other tools, then ace-learning skill
AFTER completing work.
```

**Why this matters**: Ensures Claude sees ACE trigger instructions BEFORE responding, making skill activation more reliable.

### SessionStart Hook (Enhanced in v3.3.1)
Announces ACE system activation and loads plugin instructions.

**When it fires**: At session start or resume

**What it does**:
```
🚨 ACE SYSTEM ACTIVE: Skills ace-playbook-retrieval (BEFORE work) and
ace-learning (AFTER work) auto-trigger on keywords: implement, build,
create, update, modify, fix, debug, refactor, optimize, integrate,
configure, setup, deploy, test, verify.
```

**Additional functionality**:
- Injects CLAUDE.md reference to make plugin instructions available
- Checks for ACE version updates
- Runs auto-update if enabled (via `/ace-orchestration:ace-enable-auto-update`)
- Ensures `.gitignore` includes ACE config files

### PostToolUse Hook
Logs Bash command executions for debugging.

**When it fires**: After Bash tool executes

**What it does**: Captures command history for troubleshooting and learning

**Note**: Hooks are now **enforcement mechanisms** for reliable ACE skill triggering, not just helpers!

## 🔬 How It Works

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

## 📊 Example Workflow

### First-Time Setup
```bash
# 1. Configure ACE server connection
/ace-orchestration:ace-configure
# Interactive prompts for server URL, API token, project ID

# 2. Initialize ACE in your project (required for full cycle)
/ace-orchestration:ace-claude-init
# Copies full ACE instructions inline to project CLAUDE.md (~289 lines)

# 3. Optional: Bootstrap playbook from git history
/ace-orchestration:ace-bootstrap --commits 100 --days 30
# Analyzes past commits to build initial playbook

# 4. Check initial state
/ace-orchestration:ace-status
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
/ace-orchestration:ace-patterns strategies
# Shows architectural patterns

/ace-orchestration:ace-patterns code-snippets
# Shows reusable code patterns

/ace-orchestration:ace-patterns troubleshooting
# Shows known issues & solutions

# View statistics
/ace-orchestration:ace-status
# Shows: total bullets, by section, top helpful/harmful
```

## 🎯 Architecture

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
- **Global Config**: `~/.config/ace/config.json` (server URL, API token, cache settings)
- **Project Config**: `.claude/settings.json` (MCP server + project ID)
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

**Check plugin installation:**
```bash
# Verify plugin directory exists
ls -la ~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/

# Expected: Plugin directory should contain:
# - skills/ (ace-playbook-retrieval, ace-learning)
# - commands/ (slash commands)
# - hooks/ (session hooks)
# - plugin.json (plugin metadata)
```

**Check configuration:**
```bash
# Global config (org-level settings)
cat ~/.config/ace/config.json

# Project config (MCP server + projectId)
cat .claude/settings.json
```

### MCP client not working

**The ACE MCP client is npm-based** - no Python/pip required!

```bash
# MCP client is auto-installed from npm when Claude Code starts
# It uses @ce-dot-net/ace-client package (v3.7.2)

# Check project MCP configuration
cat .claude/settings.json

# Expected output shows:
# {
#   "mcpServers": {
#     "ace-pattern-learning": {
#       "command": "npx",
#       "args": ["--yes", "@ce-dot-net/ace-client@3.7.2", "--project-id", "prj_xxxxx"]
#     }
#   }
# }
```

**If MCP tools not appearing:**
```bash
# 1. Restart Claude Code (required after plugin installation)
# 2. Check plugin is enabled in Claude Code settings
# 3. Verify global config exists:
cat ~/.config/ace/config.json

# 4. Verify project config exists:
cat .claude/settings.json

# 5. Run diagnostic command:
/ace-orchestration:ace-doctor
```

### Connection errors

**Error: "ECONNREFUSED" or "Connection refused"**

```bash
# Check global ACE configuration
cat ~/.config/ace/config.json

# Should contain:
# {
#   "serverUrl": "https://ace-api.code-engine.app",
#   "apiToken": "ace_your_token_here",
#   "cacheTtlMinutes": 120,
#   "autoUpdateEnabled": true
# }

# If missing or invalid, reconfigure:
/ace-orchestration:ace-configure --global
```

**Error: "401 Unauthorized"**

```bash
# Invalid or missing API token in global config
# Reconfigure with correct credentials:
/ace-orchestration:ace-configure --global
```

**Error: "404 Project not found"**

```bash
# Invalid project ID in .claude/settings.json
# Check project config:
cat .claude/settings.json

# Update projectId:
/ace-orchestration:ace-configure --project
```

### Skills not triggering

**ACE skills not auto-invoking when they should?**

1. **Verify skills are loaded:**
   ```
   /ace-orchestration:ace-test
   ```
   Should show ace-playbook-retrieval and ace-learning as LOADED

2. **Check CLAUDE.md has ACE instructions:**
   ```bash
   grep "ACE_SECTION_START" CLAUDE.md
   ```
   If missing, run:
   ```
   /ace-orchestration:ace-claude-init
   ```

3. **Ensure trigger words are present:**
   - Skills trigger on: implement, build, create, update, modify, fix, debug, refactor, etc.
   - Use explicit trigger words in your requests
   - Check hooks are working (UserPromptSubmit should inject reminders)

### Pattern database errors

**Clear and reset playbook:**
```bash
/ace-orchestration:ace-clear --confirm
```

**Export backup before clearing:**
```bash
/ace-orchestration:ace-export-patterns
# Then clear if needed
/ace-orchestration:ace-clear --confirm
```

### Auto-update not working

**ACE CLAUDE.md not updating automatically?**

```bash
# Check if auto-update is enabled
ls -la ~/.ace/auto-update-enabled

# If missing, enable it:
/ace-orchestration:ace-enable-auto-update

# Check update history
cat ~/.ace/update-history.log
```

### Getting help

**Still having issues?**

1. Run diagnostic command:
   ```
   /ace-orchestration:ace-doctor
   ```

2. Check Claude Code logs for errors

3. Report issues: https://github.com/ce-dot-net/ce-claude-marketplace/issues

Include:
- Output from `/ace-orchestration:ace-doctor`
- Error messages from Claude Code
- Your `~/.config/ace/config.json` (redact apiToken!)
- Your `.claude/settings.json`
- Plugin version from `plugin.json`
- MCP client version: `npx @ce-dot-net/ace-client --version`

## 📝 License

MIT License - See LICENSE file for details

## 🔗 Links

- **MCP Client Repository**: https://github.com/ce-dot-net/ce-ace-mcp
- **npm Package**: https://www.npmjs.com/package/@ce-dot-net/ace-client
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

## 🚀 Coming Soon

- Web dashboard for pattern visualization
- Pattern sharing across projects
- Team collaboration features
- Advanced playbook customization
