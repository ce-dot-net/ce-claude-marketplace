# ACE Plugin Agents

**Note:** As of v3.0.0, the ACE architecture has been refactored. The three-agent system is now implemented as **services within the MCP client**, not as separate Claude Code agents.

## Agent Architecture (v3.0.0)

ACE implements a **Generator-Reflector-Curator** architecture (Figure 4 of research paper):

1. **Generator** - Claude Code itself (executes tasks)
2. **Reflector** - Service in TypeScript MCP client (uses MCP Sampling)
3. **Curator** - Service in TypeScript MCP client (delta operations + grow-and-refine)

**All three agents are now implemented in `/mcp-clients/ce-ai-ace-client/src/`**:
- `src/services/reflector.ts` - ReflectorService
- `src/services/curator.ts` - CurationService
- `src/services/initialization.ts` - InitializationService (offline learning)

## Old Agent Files (Removed)

These agent files were removed in v3.0.0 as they are now built into the MCP client:

### ~~1. `domain-discoverer.md`~~ (REMOVED)
- **Old purpose:** Domain taxonomy discovery
- **v3.0.0:** Replaced by `InitializationService` (offline learning from git history)

### ~~2. `reflector.md`~~ (REMOVED)
- **Old purpose:** Manual pattern analysis via Claude Code agents
- **v3.0.0:** Replaced by `ReflectorService` (automatic execution analysis via MCP Sampling)

### ~~3. `reflector-prompt.md`~~ (REMOVED)
- **Old purpose:** Iterative refinement via agent prompts
- **v3.0.0:** Replaced by `ReflectorService.refineReflection()` method

## How v3.0.0 Works

Instead of invoking separate agents, the MCP client automatically:

1. **ace_learn** tool is called after task execution
2. ReflectorService analyzes the execution trace via MCP Sampling
3. CurationService applies delta operations and grow-and-refine
4. Updated playbook is saved to server

**No manual agent invocation needed!** The three-agent architecture runs automatically within the MCP client

---

## MCP Tools (v3.0.0)

The three-agent architecture is now exposed via MCP tools:

### 1. `ace_init`
**Initialize playbook from existing codebase** (offline learning)
- Analyzes git history (commits, refactorings, bug fixes)
- Extracts patterns from code changes
- Builds initial playbook with 4 sections
- Merges with existing playbook or replaces

### 2. `ace_learn`
**Learn from execution feedback** (online learning)
- Takes execution trace (task, trajectory, success/failure)
- ReflectorService analyzes via MCP Sampling
- CurationService applies delta operations
- Updates playbook with helpful/harmful tracking

### 3. `ace_get_playbook`
**Get structured playbook** (4 sections)
- Returns strategies_and_hard_rules
- Returns useful_code_snippets
- Returns troubleshooting_and_pitfalls
- Returns apis_to_use

### 4. `ace_status`
**Playbook statistics**
- Total bullets by section
- Top helpful/harmful bullets
- Average confidence scores

### 5. `ace_clear`
**Clear entire playbook** (requires confirmation)

## Migration from v2.x

**Old approach (v2.x):**
```
Python scripts → Invoke agents via Task tool → Agents analyze code → Python updates storage
```

**New approach (v3.0.0):**
```
ace_learn tool → ReflectorService (MCP Sampling) → CurationService → Server storage
```

**Benefits:**
- ✅ No Python dependencies
- ✅ No agent coordination overhead
- ✅ Faster (built into MCP protocol)
- ✅ Simpler deployment (just TypeScript + Node.js)

---

## Research Paper Alignment

✅ **Generator-Reflector-Curator architecture** (Section 3, Figure 4)
✅ **Iterative refinement** for higher quality insights (Page 5)
✅ **No hardcoded patterns or domains** - bottom-up discovery only
✅ **Agent-based reflection** - no hardcoded heuristics
✅ **Acknowledged limitations** when feedback quality is poor (Appendix B)

---

*Last updated: 2025-10-16*
*ACE Plugin Version: 2.3.6*
