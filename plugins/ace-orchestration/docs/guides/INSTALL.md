# ACE Plugin Installation Guide

**Version**: 3.1.9
**Type**: Bundled MCP Server (No Authentication Required)

---

## ✨ What's New in v3.2.36

🚀 **FULLY AUTOMATIC LEARNING** - ACE now learns automatically via Agent Skills!

- **Agent Skills**: Claude automatically triggers learning after substantial work
- **Zero Manual Intervention**: No need to remember to call `/ace-learn`
- **100% Research Paper Alignment**: Implements ACE paper's fully automatic architecture
- **Context-Aware**: Only triggers for meaningful work (debugging, implementation, failures)

**How it works**:
```
Complete substantial work → Agent Skill auto-triggers → Learning happens automatically →
Reflector & Curator run autonomously → Playbook updated with new patterns
```

See "Automatic Learning" section below for details.

---

## 🚀 Quick Install (3 Steps!)

### Step 1: Clone Repository

```bash
git clone https://github.com/ce-dot-net/ce-claude-marketplace.git
cd ce-claude-marketplace
```

### Step 2: Install Plugin in Claude Code

```bash
cd plugins/ace-orchestration

# Via symlink (recommended)
ln -s "$(pwd)" ~/.config/claude-code/plugins/ace-orchestration

# Or via Claude Code UI
# Plugins → Install from Filesystem → Select this directory
```

### Step 3: Restart Claude Code

Restart Claude Code to load the plugin.

### Step 4: Configure ACE (Dual-Config Architecture)

In Claude Code, run the interactive configuration wizard:

```
/ace-orchestration:ace-configure
```

**Creates TWO configuration files**:

1. **Global Config** (`~/.config/ace/config.json`):
   - Server URL (default: https://ace-api.code-engine.app)
   - API Token (from your ACE server)
   - Cache TTL (default: 120 minutes)
   - Auto-update settings

2. **Project Config** (`.claude/settings.json`):
   - MCP server definition
   - Project ID (from your ACE dashboard)

**Why two files?**
- Global config: Org-level settings shared across all projects
- Project config: Claude Code standard, project-specific MCP setup

### Step 5: Test Installation

```
/ace-orchestration:ace-status
```

**Expected**: Shows ACE system status and connection info

**Or run comprehensive diagnostic**:
```
/ace-orchestration:ace-doctor
```

**Expected**: Full health check of entire ACE system

---

## ✨ What's New in v3.3.2

- **Dual-Config Architecture** - Global org settings (`~/.config/ace/config.json`) + project MCP config (`.claude/settings.json`)
- **ace-doctor Diagnostic** - Comprehensive health check for entire ACE system
- **Version Checking** - Auto-detects plugin & CLAUDE.md updates
- **Auto-Migration** - Seamless upgrade from v3.3.1 config structure
- **MCP Client v3.7.0** - Version checking, config migration, improved caching

---

## 🎯 How It Works

**Automatic npm integration!** MCP server fetched on-demand.

When you install the plugin:

1. **Plugin installed** → Claude Code finds it at `~/.config/claude-code/plugins/ace-orchestration`
2. **MCP server starts** → Automatically fetched from npm (`@ce-dot-net/ace-client@latest`)
3. **Commands available** → All `/ace-*` commands ready to use
4. **Tools available** → MCP tools (`ace_status`, `ace_init`, etc.) ready

**What's included:**
- ✅ Plugin files (commands, skills, hooks)
- ✅ MCP Server (automatically fetched from npm)
- ✅ Slash commands (/ace-configure, /ace-status, etc.)
- ✅ Configuration wizard (interactive prompts)

**MCP server automatically fetched from npm when plugin activates!**

---

## 🤖 Automatic Learning with Agent Skills

**NEW in v3.2.36**: ACE skills now trigger on 35+ action keywords with intent-based fallback - no more missed triggers!

### How It Works

**Agent Skills** are model-invoked capabilities that Claude automatically triggers based on task context. Unlike slash commands (which require user input), Agent Skills activate autonomously when Claude determines they're relevant.

**The ACE Learning Agent Skill**:
- **Location**: `skills/ace-learning/SKILL.md`
- **Trigger**: Automatically activates after substantial work
- **Mechanism**: Claude analyzes task completion against Skill description
- **Action**: Calls `ace_learn` MCP tool to capture patterns

### Automatic Trigger Conditions

The Agent Skill automatically activates after:

1. **Problem-Solving & Debugging**
   - Fixed bugs or resolved errors
   - Debugged test failures or build issues
   - Troubleshot integration problems

2. **Code Implementation**
   - Implemented new features
   - Refactored existing code
   - Optimized performance

3. **API & Tool Integration**
   - Integrated external APIs
   - Used new libraries or frameworks
   - Configured build tools

4. **Learning from Failures**
   - Encountered and recovered from errors
   - Discovered edge cases or gotchas
   - Found better approaches after failures

5. **Substantial Subagent Tasks**
   - Completed complex multi-step tasks
   - Made significant technical decisions

**Skips**: Simple Q&A, basic file reads, trivial edits without problem-solving

### The Automatic Learning Pipeline

```
1. You complete substantial work (e.g., fix a bug, implement a feature)
   ↓
2. Agent Skill auto-triggers (Claude detects substantial work pattern)
   ↓
3. Skill calls ace_learn with trajectory and feedback
   ↓
4. Reflector Agent analyzes execution (autonomous LLM call via MCP Sampling)
   ↓
5. Curator Agent creates delta updates (autonomous LLM call)
   ↓
6. Merge algorithm applies updates to playbook
   ↓
7. Playbook updated with new patterns automatically!
```

### Benefits

- ✅ **Zero Manual Work**: Learning happens automatically
- ✅ **Context-Aware**: Only triggers for meaningful work
- ✅ **Trajectory Capture**: Records key steps and decisions
- ✅ **Failure Learning**: Captures lessons from errors
- ✅ **Research-Aligned**: Matches ACE paper's architecture 100%

### Verification

After completing substantial work, check if learning occurred:

```
/ace-patterns
```

You should see new patterns automatically added to relevant sections (strategies, code-snippets, troubleshooting, apis).

### Manual Learning (Still Available)

You can still manually trigger learning if needed:

```
mcp__ace-pattern-learning__ace_learn
```

But with Agent Skills, you shouldn't need to!

### 📄 Plugin CLAUDE.md (Automatic)

The plugin includes a `CLAUDE.md` file with instructions for optimal Agent Skill triggering:

**Location**: `~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md`

**Discovery**: Claude Code automatically discovers CLAUDE.md files in plugin directories. The plugin's CLAUDE.md:
- ✅ **Never modifies your existing CLAUDE.md files**
- ✅ **Loads automatically** alongside your personal/project CLAUDE.md
- ✅ **Provides context** for when to trigger automatic learning
- ✅ **Updates with the plugin** when you update the plugin

**Optional - Explicit Import**: If you want to ensure it's always loaded, add this line to your `./CLAUDE.md` or `~/.claude/CLAUDE.md`:
```markdown
# ACE Plugin Instructions
@~/.claude/plugins/marketplaces/ce-dot-net-marketplace/plugins/ace-orchestration/CLAUDE.md
```

**Check what's loaded**: Run `/memory` in Claude Code to see all active CLAUDE.md files.

---

## 📋 Alternative: Manual Configuration

If you prefer to configure manually instead of using `/ace-configure`:

### Option 1: Environment Variables

```bash
# Add to ~/.zshrc or ~/.bashrc
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="your-token-here"
export ACE_PROJECT_ID="your-project-id"

# Reload shell
source ~/.zshrc

# Restart Claude Code to pick up new variables
```

### Option 2: Config File

```bash
# 1. Create global org-level config
mkdir -p ~/.ace
cat > ~/.config/ace/config.json <<EOF
{
  "serverUrl": "https://ace-api.code-engine.app",
  "apiToken": "your-token-here",
  "cacheTtlMinutes": 120,
  "autoUpdateEnabled": true
}
EOF

# 2. Create project MCP config
mkdir -p .claude
cat > .claude/settings.json <<EOF
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "npx",
      "args": ["--yes", "@ce-dot-net/ace-client@3.7.1", "--project-id", "your-project-id"]
    }
  }
}
EOF
```

**Configuration Priority:**
1. Environment variables (highest)
2. Command-line arguments (`--server-url`, `--api-token`, `--project-id`)
3. Global config (`~/.config/ace/config.json`)
4. Default values (lowest)

**Architecture**: Dual-config system separates org settings (global) from project setup (local)

---

## 🔐 For Private Packages (Optional)

If the package is private on GitHub Packages:

### 1. Create GitHub Token

Go to: https://github.com/settings/tokens

**Required scopes**:
- ✅ `read:packages`

### 2. Add Token to .npmrc

Edit `.npmrc`:

```
@ce-dot-net:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

### 3. Set Token

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
```

---

## 🧪 Verification

### Check .npmrc Configuration

```bash
cat .npmrc

# Should show:
# @ce-dot-net:registry=https://npm.pkg.github.com
```

### Check Environment Variables

```bash
env | grep ACE_

# Should show:
# ACE_SERVER_URL=https://ace-api.code-engine.app
# ACE_API_TOKEN=ace_...
# ACE_PROJECT_ID=prj_...
```

### Check Plugin Installation

```bash
ls -la ~/.config/claude-code/plugins/ace-orchestration

# Should show symlink to plugin directory
```

### Test npx Download

```bash
# From marketplace root (where .npmrc is)
cd ce-claude-marketplace
npx @ce-dot-net/ace-client --help

# Should download from GitHub Packages and show help
```

---

## 🐛 Troubleshooting

### Error: "404 Not Found" when downloading package

**Cause**: npm can't find package on GitHub Packages

**Fix**:
1. Check `.npmrc` exists in marketplace root
2. Verify `.npmrc` has: `@ce-dot-net:registry=https://npm.pkg.github.com`
3. For private packages, set `GITHUB_TOKEN`

```bash
# Verify registry
npm config get @ce-dot-net:registry

# Should show: https://npm.pkg.github.com
```

### Error: "Unauthorized" when downloading package

**Cause**: Missing or invalid GitHub token (for private packages)

**Fix**:
1. Create GitHub token: https://github.com/settings/tokens
2. Set token: `export GITHUB_TOKEN=ghp_xxxxx`
3. Add to `.npmrc`: `//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}`

### Plugin Commands Not Working

**Cause**: Environment variables not set or plugin not loaded

**Fix**:
1. Check environment variables: `env | grep ACE_`
2. Set missing variables
3. Restart Claude Code completely
4. Run `/ace-status` to verify

### "Command not found: npx"

**Cause**: Node.js not installed

**Fix**:
```bash
# Install Node.js 18+
# macOS:
brew install node

# Or download from: https://nodejs.org
```

---

## 📂 File Structure After Installation

```
ce-claude-marketplace/
├── .npmrc                          # ← Created by install script
│   └── @ce-dot-net:registry=https://npm.pkg.github.com
├── plugins/
│   └── ace-orchestration/
│       ├── plugin.json             # ← Copied from template
│       ├── plugin.template.json    # ← Original template
│       ├── scripts/
│       │   ├── install.sh          # ← Installation script
│       │   └── setup.js            # ← Node.js setup script
│       └── ...
└── ...

~/.config/claude-code/plugins/
└── ace-orchestration/              # ← Symlink to plugin directory
```

---

## 🔄 Update Plugin

```bash
cd ce-claude-marketplace

# Pull latest changes
git pull origin main

# Restart Claude Code
# Plugin updates automatically via symlink!
```

---

## 🗑️ Uninstall Plugin

```bash
# Remove symlink
rm ~/.config/claude-code/plugins/ace-orchestration

# Optionally remove .npmrc
rm ce-claude-marketplace/.npmrc

# Restart Claude Code
```

---

## 📚 Next Steps

After installation:

1. **Configure server**: Run `/ace-orchestration:ace-configure` to set up ACE server connection
2. **Initialize ACE**: Run `/ace-orchestration:ace-claude-init` to add ACE instructions to CLAUDE.md
3. **Bootstrap patterns**: Run `/ace-orchestration:ace-bootstrap` to discover patterns from your codebase
4. **View status**: Run `/ace-orchestration:ace-status` to see pattern statistics
5. **Use patterns**: ACE automatically learns from your coding sessions
6. **Monitor evolution**: Check pattern growth over time

---

## 🆘 Getting Help

- **Documentation**: See `CONFIGURATION.md` for detailed setup
- **Security**: See `SECURITY.md` for security best practices
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

---

**Installation complete!** 🎉

The plugin will automatically download `@ce-dot-net/ace-client` from GitHub Packages when first used.
