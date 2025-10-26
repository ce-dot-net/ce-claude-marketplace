# ACE Orchestration Plugin for Claude Code

**Make Claude Code smarter with every task** - Automatic pattern learning that compounds organizational knowledge over time.

```
┌─────────────────────────────────────────────────────────┐
│                    What is ACE?                         │
│   Agentic Context Engineering for Self-Improving AI    │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────────┐
        │   You: "Implement JWT auth"         │
        └─────────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────────┐
        │  ACE: Retrieves past auth patterns  │
        │  "Refresh token rotation prevents   │
        │   theft - rotate on each use"       │
        └─────────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────────┐
        │  Claude: Implements using proven    │
        │  pattern (no trial-and-error!)      │
        └─────────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────────┐
        │  ACE: Captures new insights         │
        │  "JWT pairs well with httpOnly      │
        │   cookies for XSS protection"       │
        └─────────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────────┐
        │   Next Session: Enhanced playbook   │
        │   with even more knowledge! 🎯      │
        └─────────────────────────────────────┘
```

## 🎯 Why ACE?

### Before ACE: Starting from Scratch Every Time
- ❌ Claude forgets lessons learned between sessions
- ❌ Repeats same mistakes on similar tasks
- ❌ No organizational knowledge accumulation
- ❌ Each developer reinvents solutions

### After ACE: Compound Intelligence
- ✅ **Learns from every task** - Captures successful patterns automatically
- ✅ **Shares knowledge** - Team benefits from each other's discoveries
- ✅ **Avoids known pitfalls** - Remembers what didn't work
- ✅ **Gets smarter over time** - Knowledge compounds with each session

## 🚀 Key Benefits

### 1. **Automatic Learning** (Zero Manual Effort)
- Learns before tasks start (retrieves relevant patterns)
- Learns after tasks complete (captures new insights)
- No manual note-taking or documentation required

### 2. **Faster Development**
- Skip trial-and-error on solved problems
- Reuse proven code patterns
- Avoid debugging the same issues twice

### 3. **Better Code Quality**
- Apply architectural best practices automatically
- Use recommended APIs and libraries
- Implement security patterns correctly

### 4. **Team Knowledge Sharing**
- Everyone benefits from discovered solutions
- Junior developers learn from senior patterns
- Institutional knowledge survives turnover

## 📦 Installation

### Quick Start (3 minutes)

```bash
# 1. Add CE marketplace to Claude Code
/plugin marketplace add ce-dot-net/ce-claude-marketplace

# 2. Install ACE Orchestration plugin
/plugin install ace-orchestration@ce-dot-net-marketplace

# 3. Configure ACE server connection
/ace-configure

# 4. (Optional) Initialize playbook from project history
/ace-init
```

That's it! ACE now learns from every task automatically.

### First-Time Setup in Your Project

Run this command in your project to add ACE context:

```bash
/ace-claude-init
```

This adds ACE instructions to your project's `CLAUDE.md` file, ensuring optimal skill triggering and always-on pattern learning.

## 🎓 How It Works

### The Automatic Learning Cycle

```
┌──────────────────────────────────────────────────────────┐
│ 1. BEFORE TASK: Playbook Retrieval                     │
│    Claude automatically fetches relevant patterns       │
│    from past work (strategies, code, gotchas, APIs)    │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 2. DURING TASK: Pattern Application                    │
│    Claude applies learned knowledge:                    │
│    - Uses proven architectural patterns                 │
│    - Reuses tested code snippets                       │
│    - Avoids known pitfalls                             │
│    - Chooses recommended APIs                          │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 3. AFTER TASK: Learning Capture                        │
│    Claude automatically captures:                       │
│    - What worked and why                               │
│    - What failed and how to fix                        │
│    - Discovered gotchas and edge cases                 │
│    - Better approaches found                           │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 4. SERVER PROCESSING: Pattern Refinement               │
│    ACE server analyzes feedback and:                    │
│    - Adds valuable insights to playbook                 │
│    - Removes outdated or incorrect patterns            │
│    - Updates quality scores                            │
│    - Deduplicates similar patterns                     │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 5. NEXT SESSION: Enhanced Playbook                     │
│    Playbook now richer with new knowledge!             │
│    Cycle repeats, compounding intelligence 🎯          │
└──────────────────────────────────────────────────────────┘
```

### Four Knowledge Sections

ACE organizes learned patterns into four categories:

1. **Strategies & Hard Rules**
   - Architectural patterns and design principles
   - Coding standards and best practices
   - Security policies and requirements

2. **Useful Code Snippets**
   - Proven implementations with context
   - Reusable patterns for common tasks
   - Framework-specific templates

3. **Troubleshooting & Pitfalls**
   - Known issues and their solutions
   - Common mistakes to avoid
   - Edge cases and gotchas

4. **APIs to Use**
   - Recommended libraries and frameworks
   - Integration patterns
   - Tool configurations

## 🎮 Using ACE

### Automatic Mode (Recommended)

**ACE works automatically - no commands needed!**

Just use Claude Code normally:
- Implement features → ACE retrieves patterns, then captures learnings
- Fix bugs → ACE recalls similar issues, then saves solutions
- Refactor code → ACE suggests proven patterns, then records improvements

### Manual Commands (Optional)

For explicit control or inspection:

```bash
# View learned patterns
/ace-patterns

# Check playbook statistics
/ace-status

# Configure server connection
/ace-configure

# Bootstrap from git history (first time)
/ace-init

# Export patterns for backup
/ace-export-patterns

# Import patterns from backup
/ace-import-patterns

# Clear all patterns (requires confirmation)
/ace-clear --confirm
```

## 📊 Real-World Example

### Session 1: First JWT Implementation
```
You: "Implement JWT authentication"
Claude: [Implements basic JWT with access tokens]
ACE: ✅ Learned "JWT requires secret rotation strategy"
```

### Session 2: Enhanced with Refresh Tokens
```
You: "Add refresh token support"
Claude: [Retrieves JWT patterns from Session 1]
Claude: [Implements refresh tokens using learned context]
ACE: ✅ Learned "Refresh token rotation prevents theft"
```

### Session 3: Security Hardening
```
You: "Secure the JWT implementation"
Claude: [Retrieves: JWT secrets, refresh rotation]
Claude: [Adds httpOnly cookies, CSRF protection, short expiry]
ACE: ✅ Learned "JWT + httpOnly cookies prevent XSS"
```

### Session 4: Another Project (Instant Benefit!)
```
You: "Implement auth for the new API"
Claude: [Retrieves: All JWT learnings from Sessions 1-3]
Claude: [Implements secure JWT auth correctly from the start!]
Result: ✨ No trial-and-error, all best practices applied ✨
```

## 🔧 Troubleshooting

### Plugin Not Learning

**Problem**: ACE Learning skill doesn't trigger after tasks

**Solutions**:
1. Check `/ace-status` - should show playbook is accessible
2. Verify `/ace-claude-init` was run in your project
3. Ensure task is substantial (not trivial Q&A)
4. Check server connection with `/ace-configure`

### Playbook Returns Empty

**Problem**: No patterns available yet

**Solutions**:
1. **First time?** Run `/ace-init` to bootstrap from git history
2. **New project?** Complete a few tasks - playbook will grow
3. **Check server**: Run `/ace-status` to verify connection

### Patterns Seem Outdated

**Problem**: Retrieved patterns don't match current stack

**Solutions**:
1. Continue working - ACE learns new patterns automatically
2. Old patterns get demoted as new ones prove better
3. Use `/ace-clear --confirm` for fresh start (loses all history)

### Server Connection Issues

**Problem**: Cannot reach ACE server

**Solutions**:
1. Check server URL in `/ace-configure`
2. Verify API token is valid
3. Confirm server is running (if self-hosted)
4. Check network/firewall settings

## 🏗️ Architecture

### Three-Tier Caching for Speed

```
Claude Request
     ↓
┌─────────────────┐
│   RAM Cache     │  ← Instant (session-scoped)
└─────────────────┘
     ↓ (miss)
┌─────────────────┐
│  SQLite Cache   │  ← Fast (5-minute TTL)
│ ~/.ace-cache/   │
└─────────────────┘
     ↓ (miss/stale)
┌─────────────────┐
│   ACE Server    │  ← Fetch latest
└─────────────────┘
```

**Result**: Patterns retrieved in milliseconds, not seconds!

### Server-Side Intelligence

```
                Learning Feedback
                       ↓
              ┌───────────────────┐
              │   ACE Server      │
              └───────────────────┘
                       ↓
        ┌──────────────┴──────────────┐
        ↓                             ↓
┌───────────────┐            ┌───────────────┐
│  Reflector    │            │   Curator     │
│  (Sonnet 4)   │            │  (Haiku 4.5)  │
│               │            │               │
│ Analyzes      │────────→   │ Creates delta │
│ execution     │            │ updates to    │
│ trajectory    │            │ playbook      │
└───────────────┘            └───────────────┘
                                     ↓
                            ┌───────────────┐
                            │     Merge     │
                            │  (Non-LLM)    │
                            │               │
                            │ Applies delta │
                            │ deduplicates  │
                            └───────────────┘
                                     ↓
                            Updated Playbook
```

**Benefits**:
- ✅ Cost-optimized (Sonnet for intelligence, Haiku for efficiency)
- ✅ Fast (incremental delta updates, not full regeneration)
- ✅ Smart (semantic deduplication prevents pattern bloat)

## 🔐 Privacy & Security

- **Your code never leaves your machine** (only execution summaries)
- Patterns stored on your ACE server (self-hosted or managed)
- SQLite cache encrypted at rest (optional)
- API tokens for authentication
- Multi-tenant isolation (organization + project scoping)

## 💡 Pro Tips

### 1. **Run /ace-init on existing projects**
Bootstrap playbook from git history - instant organizational knowledge!

### 2. **Use /ace-claude-init in every project**
Adds ACE context to project's CLAUDE.md for optimal skill triggering.

### 3. **Let ACE learn naturally**
Don't overthink it - just work normally, ACE captures valuable insights automatically.

### 4. **Check /ace-status periodically**
See how your playbook grows and which patterns are most valuable.

### 5. **Export patterns for backup**
Use `/ace-export-patterns` before major playbook cleanups.

## 📈 Performance Impact

**Retrieval Overhead**: ~30-150ms per task (SQLite cache hit)
**Learning Overhead**: ~0-100ms per task (async, non-blocking)
**Storage**: ~1KB per learned pattern
**Network**: Only on cache miss or stale data

**Result**: Negligible overhead for massive productivity gains!

## 🤝 Contributing

Found a bug? Have a feature request?

Report issues at: https://github.com/ce-dot-net/ce-claude-marketplace/issues

## 📄 License

MIT License - See LICENSE file for details.

## 🎉 Get Started!

```bash
/plugin marketplace add ce-dot-net/ce-claude-marketplace
/plugin install ace-orchestration@ce-dot-net-marketplace
/ace-configure
```

**Start building - ACE will start learning!** 🚀
