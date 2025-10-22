# ACE Orchestration Plugin - Automatic Learning

This plugin provides fully automatic pattern learning following the ACE research paper architecture.

## 🤖 Automatic Learning via Agent Skills

**IMPORTANT**: The `ACE Learning from Execution` Agent Skill triggers automatically after substantial work.

### When Agent Skill Triggers

The Agent Skill **automatically invokes** after completing:

1. **Problem-Solving & Debugging**
   - Fixed bugs or resolved errors
   - Debugged test failures or build issues
   - Troubleshot integration problems

2. **Code Implementation**
   - Implemented new features or functionality
   - Refactored existing code
   - Optimized performance

3. **API & Tool Integration**
   - Integrated external APIs or services
   - Used new libraries or frameworks
   - Configured build tools or CI/CD

4. **Learning from Failures**
   - Encountered and recovered from errors
   - Discovered edge cases or gotchas
   - Found better approaches after initial failures

5. **Substantial Subagent Tasks**
   - Completed complex multi-step tasks
   - Made significant technical decisions

### What the Agent Skill Does

When triggered, the Agent Skill:
1. **Extracts task information** - What was accomplished
2. **Captures trajectory** - Key steps and decisions made
3. **Gathers feedback** - Lessons learned, patterns discovered, gotchas
4. **Calls `mcp__plugin_ace-orchestration_ace-pattern-learning__ace_learn`** - Triggers automatic learning

### The Automatic Learning Pipeline

```
Substantial Work Completed
    ↓
Agent Skill Auto-Triggers (you invoke the skill based on description matching)
    ↓
ace_learn Called with Trajectory & Feedback
    ↓
Reflector Agent Analyzes (autonomous LLM call via MCP Sampling)
    ↓
Curator Agent Creates Delta Updates (autonomous LLM call)
    ↓
Merge Algorithm Applies Updates
    ↓
Playbook Updated with New Patterns!
```

### Example Learning Scenarios

**Scenario 1: Debugging Async Issue**
```
User: Fix this intermittent test failure
You: [Debug, discover missing await, fix it]
Agent Skill: *triggers automatically*
Result: Pattern captured: "Intermittent failures in async code often mean missing await"
```

**Scenario 2: API Integration**
```
User: Integrate Stripe webhook handling
You: [Implement, discover raw body requirement for signature verification]
Agent Skill: *triggers automatically*
Result: Pattern captured: "Stripe webhooks need express.raw() for signature verification"
```

**Scenario 3: Implementation**
```
User: Add JWT authentication with refresh tokens
You: [Design and implement token rotation pattern]
Agent Skill: *triggers automatically*
Result: Pattern captured: "Refresh token rotation prevents token theft attacks"
```

### Important Notes

- **Automatic invocation only** - Don't manually call unless testing
- **Skips trivial work** - Simple Q&A, file reads, basic informational responses
- **Context-aware** - Only triggers when substantial lessons can be learned
- **Trajectory matters** - Record key steps taken, not just final outcome
- **Capture failures too** - What didn't work is valuable learning

### MCP Tool Format

If you need to manually test (rare), use:
```
mcp__plugin_ace-orchestration_ace-pattern-learning__ace_learn
```

With parameters:
- `task` (required): Brief description of what was accomplished
- `success` (required): true/false
- `trajectory` (optional but valuable): Array of key steps
- `output` (required): Detailed feedback, lessons learned, patterns discovered

## 🎯 Architecture Alignment

This implements the ACE research paper's fully automatic learning:
- **Generator**: Main Claude instance executing tasks
- **Reflector**: Autonomous analysis via MCP Sampling
- **Curator**: Autonomous delta updates via MCP Sampling
- **Merge**: Non-LLM algorithm applying incremental updates

Result: +10.6% improvement on agentic tasks through fully automatic pattern learning!
