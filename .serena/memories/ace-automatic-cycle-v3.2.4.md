# ACE Automatic Learning Cycle Architecture (v3.2.4)

## Overview
ACE implements fully automatic pattern learning using **Claude Code Agent Skills** (model-invoked) + **MCP Client** (3-tier cache) + **ACE Server** (Reflector + Curator).

## The Complete Automatic Cycle

```
User Request: "Implement JWT authentication"
    ↓
1. ACE Playbook Retrieval Skill AUTO-INVOKES
   - Claude matches: "implement" → triggers skill automatically
   - Skill calls: mcp__ace-pattern-learning__ace_get_playbook
   - MCP Client: RAM cache → SQLite (~/.ace-cache/) → Server (if stale)
   - Returns: Playbook with learned patterns
   Example: "Refresh token rotation prevents theft attacks"
    ↓
2. Claude Executes Task with Learned Patterns
   - Uses strategies from playbook (security patterns)
   - Applies proven code snippets (JWT implementation)
   - Avoids known pitfalls (token theft risks)
   - Chooses recommended APIs (jsonwebtoken library)
    ↓
3. Task Completion
   - User receives high-quality implementation
   - Implemented using organizational knowledge
    ↓
4. ACE Learning Skill AUTO-INVOKES
   - Claude recognizes substantial work completed
   - Skill calls: mcp__ace-pattern-learning__ace_learn
   - Sends: task + trajectory + feedback → ACE Server
   Example: "Implemented JWT with rotating refresh tokens successfully"
    ↓
5. Server-Side Processing (Automatic)
   - Reflector (Sonnet 4): Analyzes execution trace for patterns
   - Curator (Haiku 4.5): Creates delta updates to playbook
   - Merge Algorithm: Applies incremental updates
   - Playbook updated with new/reinforced patterns
    ↓
6. Next Session
   - Retrieval skill fetches UPDATED playbook
   - New patterns available immediately
   - Knowledge compounds over time! 🎯
```

**Result**: Self-improving system that gets smarter with each task!

## Key Components

### Skills (Model-Invoked)
Location: `plugins/ace-orchestration/skills/`

**ACE Playbook Retrieval** (`ace-playbook-retrieval/SKILL.md`):
- **Description**: "Automatically retrieve ACE playbook patterns before substantial coding tasks..."
- **Triggers**: implement, build, create, fix, debug, refactor, integrate, optimize, architect
- **Calls**: `mcp__ace-pattern-learning__ace_get_playbook`
- **Returns**: 4 sections (strategies, snippets, troubleshooting, APIs)
- **Progressive Disclosure**: ~100 tokens metadata → ~5k tokens instructions → variable playbook content

**ACE Learning from Execution** (`ace-learning/SKILL.md`):
- **Description**: "Learn from execution feedback and update the ACE playbook..."
- **Triggers**: After substantial work (problem-solving, debugging, implementation, integration)
- **Calls**: `mcp__ace-pattern-learning__ace_learn`
- **Captures**: task + success + trajectory + feedback
- **Server Processing**: Automatic Reflector → Curator → Merge

### MCP Client
Location: `mcp-clients/ce-ai-ace-client/`
Version: @ce-dot-net/ace-client@3.2.3

**3-Tier Caching**:
1. **RAM Cache**: In-memory, session-scoped (fastest - instant)
2. **SQLite Cache**: `~/.ace-cache/{org}_{project}.db`, 5-min TTL (fast - milliseconds)
3. **Server Fetch**: Only when cache stale/empty (slower - seconds)

**MCP Tools** (for manual testing/override):
- `ace_get_playbook` - Retrieve playbook (with optional section/min_helpful filters)
- `ace_learn` - Capture learning (task, trajectory, feedback)
- `ace_status` - Check playbook statistics
- `ace_init` - Bootstrap from git history
- `ace_clear` - Clear playbook (requires confirmation)
- `ace_save_config` - Save ACE server configuration

**Transport**: stdio (npx execution)
**Config**: `~/.ace/config.json` (server URL, API token, project ID)

### Hooks (Minimal)
Location: `plugins/ace-orchestration/hooks/hooks.json`

**SessionStart**:
- Injects CLAUDE.md reference
- Makes plugin instructions available

**PostToolUse (Bash)**:
- Logs Bash executions to `~/.ace/execution_log.jsonl`
- Useful for debugging

**Removed in v3.2.4**:
- ❌ UserPromptSubmit reminder (redundant - skills auto-invoke)
- ❌ Stop reminder (redundant - skills auto-invoke)
- ❌ SubagentStop reminder (redundant - skills auto-invoke)

**Rationale**: Skills handle automation now. Hooks only do setup and logging.

### Commands (Manual Override)
Location: `plugins/ace-orchestration/commands/`

**All slash commands remain** for manual control:
- `/ace-patterns [section]` - View playbook manually
- `/ace-status` - Check statistics
- `/ace-configure` - Setup server connection
- `/ace-init` - Bootstrap from git
- `/ace-clear` - Clear playbook
- `/ace-export-patterns`, `/ace-import-patterns` - Backup/restore

**Purpose**: Manual overrides when user wants explicit control.

## Playbook Structure (Per Research Paper Figure 3)

1. **strategies_and_hard_rules**: Architectural patterns, coding principles, best practices
2. **useful_code_snippets**: Reusable code with tested implementations and context
3. **troubleshooting_and_pitfalls**: Known issues, gotchas, common mistakes, solutions
4. **apis_to_use**: Recommended libraries, frameworks, integration patterns, gotchas

**Each bullet has**:
- `bullet`: Pattern description
- `helpful`: Number of successful applications
- `harmful`: Number of failed applications
- Quality score guides retrieval

## Architecture Alignment

### ACE Research Paper
- **Generator**: Main Claude instance executing tasks
- **Playbook**: Evolving context with learned patterns
- **Reflector**: Pattern analysis from execution traces
- **Curator**: Delta updates to playbook
- **Merge**: Incremental improvements

### Our Implementation
- **Generator**: Claude Code with Agent Skills (YOU!)
- **Playbook**: 4-section structured playbook on ACE Server
- **Reflector**: Server-side Sonnet 4 analysis
- **Curator**: Server-side Haiku 4.5 delta updates
- **Merge**: Non-LLM algorithm for incremental updates

### Why This Works

**Model-Invoked Skills** (Claude decides when to use):
- ✅ No manual intervention needed
- ✅ Triggers based on description matching
- ✅ Progressive disclosure (token-efficient)
- ✅ Fully automatic cycle

**3-Tier Caching** (Fast retrieval):
- ✅ RAM: Instant for repeat queries in session
- ✅ SQLite: Fast for cross-session persistence
- ✅ Server: Only when necessary

**Server-Side Intelligence** (Cost-optimized):
- ✅ Sonnet 4 for pattern analysis (intelligence)
- ✅ Haiku 4.5 for delta updates (efficiency)
- ✅ 60% cost savings vs. all-Sonnet approach

**Delta Updates** (Prevents context collapse):
- ✅ Incremental improvements, not monolithic rewrites
- ✅ Grow-and-refine approach from research paper
- ✅ Quality scores guide pattern evolution

## Benefits

**For Users**:
- ✅ Automatic: No manual playbook management
- ✅ Fast: Cached retrieval in milliseconds
- ✅ Smart: Each task improves the system
- ✅ Seamless: Skills just work in background

**For Development Teams**:
- ✅ Organizational Knowledge: Patterns shared across team
- ✅ Onboarding: New developers benefit from past work
- ✅ Consistency: Proven patterns applied automatically
- ✅ Error Prevention: Known pitfalls avoided

**Research Paper Alignment**:
- ✅ +10.6% improvement on agentic tasks
- ✅ Complete retrieval → learning cycle
- ✅ Server-side intelligence
- ✅ Universal MCP compatibility

## File Locations (Quick Reference)

```
ce-claude-marketplace/
├── plugins/ace-orchestration/
│   ├── skills/
│   │   ├── ace-playbook-retrieval/SKILL.md  # NEW in v3.2.4
│   │   └── ace-learning/SKILL.md             # Enhanced
│   ├── commands/
│   │   ├── ace-patterns.md
│   │   ├── ace-status.md
│   │   ├── ace-configure.md
│   │   ├── ace-init.md
│   │   ├── ace-clear.md
│   │   ├── ace-export-patterns.md
│   │   └── ace-import-patterns.md
│   ├── hooks/hooks.json                      # Simplified in v3.2.4
│   ├── .mcp.json                             # v3.2.3
│   ├── CLAUDE.md                             # Updated with complete cycle
│   └── README.md                             # Updated with skills docs
└── mcp-clients/ce-ai-ace-client/
    ├── src/index.ts                          # MCP tools
    ├── src/services/server-client.ts         # 3-tier cache
    ├── src/services/local-cache.ts           # SQLite cache
    └── package.json                          # v3.2.3
```

## Cache Locations

- **Config**: `~/.ace/config.json` (server URL, API token, project ID)
- **SQLite Cache**: `~/.ace-cache/{org}_{project}.db` (playbook + embeddings)
- **Execution Logs**: `~/.ace/execution_log.jsonl` (Bash tool logs)

## Testing the Cycle

### Manual Test Flow
1. **Check initial state**: `/ace-status`
2. **Request complex task**: "Implement JWT authentication with refresh tokens"
3. **Observe retrieval**: Skills should auto-invoke (check conversation for MCP call)
4. **Complete task**: Implement the feature
5. **Observe learning**: Skills should auto-invoke after completion
6. **Verify update**: `/ace-patterns strategies` should show new/updated patterns

### Success Indicators
- ✅ Playbook retrieval skill activates before task
- ✅ Playbook data returned (from cache or server)
- ✅ Learning skill activates after task
- ✅ Feedback sent to server successfully
- ✅ Next session: Updated playbook retrieved

## Common Issues & Solutions

**Skill doesn't auto-invoke**:
- Check: Task complexity (must be substantial, not trivial Q&A)
- Check: Skill description matches task (implement, debug, etc.)
- Workaround: Manually call `/ace-patterns` or MCP tool

**Playbook returns empty**:
- Cause: New project without learned patterns
- Solution: Use `/ace-init` to bootstrap from git history
- OR: Complete tasks and use learning skill to build playbook

**Cache seems stale**:
- Default TTL: 5 minutes
- Force refresh: Restart Claude Code session
- Check: `~/.ace-cache/{org}_{project}.db` exists

## Future Enhancements

Potential improvements for future versions:
- Configurable skill triggers (allow custom activation patterns)
- Quality score thresholds (filter playbook by helpful score)
- Pattern analytics (track most-used patterns)
- Team playbook sharing (export/import enhancements)
- Visual playbook explorer (web dashboard)

## Version History

- **v3.2.4**: Complete automatic cycle with skills (current)
- **v3.2.3**: MCP client v3.2.3, enhanced tool descriptions
- **v3.2.2**: Server-side intelligence architecture
- **v3.2.0**: Universal MCP compatibility, no sampling required
- Earlier: Various experimental approaches

Last updated: 2025-10-23