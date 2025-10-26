# ACE Plugin Installation Guide

**Version**: 3.1.9
**Type**: Bundled MCP Server (No Authentication Required)

---

## ✨ What's New in v3.1.9

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

### Step 4: Configure ACE Credentials

In Claude Code, run the interactive configuration wizard:

```
/ace-configure
```

**Prompts for**:
- ACE Server URL (default: http://localhost:9000)
- API Token (from your ACE server)
- Project ID (from your ACE dashboard)

**Saves to**: `~/.ace/config.json`

### Step 5: Test Installation

```
/ace-status
```

**Expected**: Shows ACE system status and connection info

---

## ✨ What's New in v3.0.4

- **Bundled MCP Server** - No package download required!
- **Zero Authentication** - Works offline, no GitHub token needed
- **Interactive Configuration** - `/ace-configure` wizard for credentials
- **Config File Support** - Saves to `~/.ace/config.json`

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

**NEW in v3.1.9**: ACE learns automatically via Agent Skills - no manual intervention required!

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
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="your-token-here"
export ACE_PROJECT_ID="your-project-id"

# Reload shell
source ~/.zshrc

# Restart Claude Code to pick up new variables
```

### Option 2: Config File

```bash
# Create config directory
mkdir -p ~/.ace

# Create config file
cat > ~/.ace/config.json <<EOF
{
  "serverUrl": "http://localhost:9000",
  "apiToken": "your-token-here",
  "projectId": "your-project-id"
}
EOF
```

**Configuration Priority:**
1. Environment variables (highest)
2. `~/.ace/config.json`
3. Default values (lowest)

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
# ACE_SERVER_URL=http://localhost:9000
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

1. **Initialize patterns**: Run `/ace-init` to discover patterns from your codebase
2. **View status**: Run `/ace-status` to see pattern statistics
3. **Use patterns**: ACE automatically learns from your coding sessions
4. **Monitor evolution**: Check pattern growth over time

---

## 🆘 Getting Help

- **Documentation**: See `CONFIGURATION.md` for detailed setup
- **Security**: See `SECURITY.md` for security best practices
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues

---

**Installation complete!** 🎉

The plugin will automatically download `@ce-dot-net/ace-client` from GitHub Packages when first used.
