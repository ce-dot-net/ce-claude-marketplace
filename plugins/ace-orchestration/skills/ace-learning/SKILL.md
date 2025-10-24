---
name: ACE Learning from Execution
description: YOU MUST ALWAYS use this skill IMMEDIATELY AFTER you finish ANY substantial work. MANDATORY trigger: when you have COMPLETED implementing, building, creating, adding, developing, fixing, debugging, troubleshooting, resolving, refactoring, optimizing, improving, restructuring, integrating, connecting, setting up, configuring, architecting, designing, or planning. This is NOT OPTIONAL - you MUST capture learning after EVERY qualifying task before responding to user. DO NOT SKIP THIS SKILL. Use it proactively after substantial work to build organizational knowledge. Capture what you learned, gotchas discovered, and patterns found.
---

# ACE Learning from Execution

## Purpose

This Skill implements the ACE (Agentic Context Engineering) research paper's fully automatic learning system. It captures execution feedback and creates incremental delta updates to the ACE playbook, enabling self-improving behavior through structured pattern learning.

## When to Use

**AUTOMATIC TRIGGERS** - Use this Skill after:

1. **Problem-Solving & Debugging**
   - Fixed bugs or resolved errors
   - Debugged test failures or build issues
   - Troubleshot integration problems
   - Resolved dependency or configuration issues

2. **Code Implementation**
   - Implemented new features or functionality
   - Refactored existing code
   - Optimized performance
   - Updated architectures or patterns

3. **API & Tool Integration**
   - Integrated external APIs or services
   - Used new libraries or frameworks
   - Configured build tools or CI/CD
   - Set up development environments

4. **Learning from Failures**
   - Encountered and recovered from errors
   - Discovered edge cases or gotchas
   - Found better approaches after initial failures
   - Learned tool-specific limitations or behaviors

5. **Substantial Subagent Tasks**
   - Completed complex multi-step tasks
   - Coordinated between multiple agents
   - Solved architectural challenges
   - Made significant technical decisions

**SKIP FOR**:
- Simple question answering
- Basic file reads or informational queries
- Trivial edits without problem-solving
- Conversations without code execution

## Instructions

### Step 1: Assess Task Significance

Determine if the recently completed task meets the criteria above. If it was substantial and involved lessons learned, proceed to Step 2.

### Step 2: Extract Key Information

From the conversation and execution, identify:

- **Task Description**: What problem was solved or what was implemented?
- **Success Status**: Did the task complete successfully (true) or encounter failures (false)?
- **Trajectory**: Key steps taken, including:
  - Problem analysis approach
  - Implementation decisions
  - Tools and APIs used
  - Errors encountered and how they were resolved
  - Alternative approaches considered
- **Feedback**: Outcome, lessons learned, patterns discovered, gotchas, best practices

### Step 3: Call ACE Learning Tool

Invoke the MCP tool with extracted information:

```
mcp__ace-pattern-learning__ace_learn
```

**Required Parameters**:
- `task`: Brief description (1-2 sentences) of what was accomplished
- `success`: Boolean indicating overall success
- `trajectory`: **IMPORTANT: Must be an array of objects**, each with descriptive keys (e.g., `{"step": "...", "action": "..."}`)
- `feedback`: Detailed outcome, lessons learned, patterns, troubleshooting insights

**Example 1 - Successful Implementation**:
```json
{
  "task": "Implemented user authentication with JWT tokens and refresh token rotation",
  "success": true,
  "trajectory": [
    {"step": "Analysis", "action": "Analyzed security requirements and token expiration needs"},
    {"step": "Library Selection", "action": "Chose JWT library (jsonwebtoken) for token generation"},
    {"step": "Token Strategy", "action": "Implemented access token (15min) + refresh token (7 days) pattern"},
    {"step": "Rotation Logic", "action": "Added token rotation logic in refresh endpoint"},
    {"step": "Security", "action": "Secured endpoints with authentication middleware"}
  ],
  "feedback": "Successfully implemented secure auth flow. Key insights: (1) Refresh token rotation prevents token theft, (2) Short access token expiry balances security and UX, (3) HttpOnly cookies for refresh tokens prevent XSS attacks. Pattern: Always validate refresh token on each rotation and revoke old tokens."
}
```

**Example 2 - Debugging Failure**:
```json
{
  "task": "Debugged intermittent test failures in async database operations",
  "success": true,
  "trajectory": [
    {"step": "Observation", "action": "Observed random test failures in CI/CD pipeline"},
    {"step": "Hypothesis", "action": "Suspected race condition in database cleanup"},
    {"step": "First Attempt", "action": "Added transaction isolation and explicit wait for cleanup"},
    {"step": "Continued Failure", "action": "Tests still failed intermittently"},
    {"step": "Root Cause", "action": "Discovered missing await on database.close()"},
    {"step": "Solution", "action": "Added proper async/await chain to all cleanup operations"}
  ],
  "feedback": "Root cause: Forgot await on database.close() causing connection pool exhaustion. Troubleshooting insight: Intermittent failures in async code often indicate missing await statements. Check all async function calls in test cleanup. Pattern: Always use await on resource cleanup (close, disconnect, etc.)"
}

**Example 3 - API Integration Learning**:
```json
{
  "task": "Integrated Stripe payment API with webhook handling",
  "success": true,
  "trajectory": [
    {"step": "Setup", "action": "Set up Stripe SDK and configured API keys"},
    {"step": "Checkout", "action": "Implemented checkout session creation endpoint"},
    {"step": "Webhook Endpoint", "action": "Added webhook endpoint for payment events"},
    {"step": "Error Encountered", "action": "Failed webhook signature verification with 400 errors"},
    {"step": "Discovery", "action": "Discovered raw body requirement for crypto signature validation"},
    {"step": "Fix", "action": "Configured express.raw() middleware specifically for webhook route"}
  ],
  "feedback": "Stripe webhooks require raw request body for signature verification. Standard express.json() breaks signature validation. Solution: Use express.raw({type: 'application/json'}) for webhook route specifically. API Pattern: Webhook signature verification often needs raw body access - check docs before adding body parsers."
}

### Step 4: Server-Side Analysis (v3.2.0)

After calling `ace_learn`, the MCP client sends the trace to the ACE server, which automatically:

1. **Reflector Agent**: Server-side analysis using Sonnet 4 for intelligent pattern extraction
2. **Curator Agent**: Server-side delta updates using Haiku 4.5 for cost efficiency
3. **Merge Logic**: Non-LLM algorithm applies updates to playbook using grow-and-refine

**No further action required** - the server handles all analysis autonomously and asynchronously.

### Step 5: Verification (Optional)

If desired, verify learning was captured:

```
/ace-patterns [section]
```

Check relevant sections (strategies, code-snippets, troubleshooting, apis) for new bullets.

## Key Principles

1. **Be Specific**: Capture concrete details (library names, error messages, file paths)
2. **Include Context**: Explain why solutions work, not just what the solution is
3. **Note Gotchas**: Document surprising behaviors or common pitfalls
4. **Capture Failures**: Failed approaches are valuable learning - include what didn't work and why
5. **Think Incrementally**: Each learning session adds delta updates, building knowledge over time

## Benefits

- **Self-Improving**: ACE playbook grows more valuable with each task
- **Context Efficiency**: Future tasks use learned patterns, reducing token usage
- **Team Learning**: Shared playbook captures organizational knowledge
- **Failure Recovery**: Documented troubleshooting prevents repeated mistakes
- **Best Practices**: Accumulates proven approaches and patterns

## Architecture Alignment (v3.2.0)

This Skill implements the ACE research paper's fully automatic architecture with server-side intelligence:

```
Task Completion → Agent Skill (auto-invoked) → ace_learn called →
MCP Client (HTTP POST) → ACE Server →
Reflector (server-side Sonnet 4) → Curator (server-side Haiku 4.5) →
Delta Merge (server-side) → Updated Playbook
```

The automation happens at three levels:
1. **Skill Invocation**: Claude decides when to use this Skill based on task context
2. **Server-Side Analysis**: Reflector and Curator run autonomously on ACE server
3. **Delta Merge**: Non-LLM algorithm applies incremental updates automatically

**Benefits**:
- ✅ Universal MCP compatibility (works with Claude Code, Cursor, Cline, any MCP client)
- ✅ Cost optimized (Sonnet 4 for intelligence, Haiku 4.5 for efficiency, ~60% savings)
- ✅ Transparent server logs for debugging and monitoring
- ✅ No MCP Sampling requirement

Result: Achieves research paper's +10.6% improvement on agentic tasks through fully automatic pattern learning!
