# ACE Plugin Agents

This directory contains the three agent roles defined by the ACE research paper (arXiv:2510.04618v1).

## Agent Architecture

ACE implements a **Generator-Reflector-Curator** architecture (Figure 4 of research paper):

1. **Generator** - Produces reasoning trajectories (this is the main Claude instance)
2. **Reflector** - Analyzes pattern effectiveness from execution feedback
3. **Curator** - Integrates insights into structured context (deterministic algorithm in `ace-cycle.py`)

## Defined Agents

### 1. `domain-discoverer.md`
**Name:** `domain-discoverer`
**Invoked as:** `ace-orchestration:domain-discoverer` (via Task tool)

**Purpose:** Discovers domain taxonomy from coding patterns through bottom-up analysis (NO hardcoded domains)

**Invoked by:**
- `domain_discovery.py` when pattern count threshold is met
- Outputs request to stderr asking Claude to invoke via Task tool

**Output:** JSON with concrete domains, abstract patterns, and principles

---

### 2. `reflector.md`
**Name:** `reflector`
**Invoked as:** `ace-orchestration:reflector` (via Task tool)

**Purpose:** Analyzes coding patterns for effectiveness based on execution feedback and test results

**Invoked by:**
- `ace-cycle.py` → `invoke_reflector_agent()` function
- Called after pattern detection and evidence gathering
- Outputs request to stderr asking Claude to invoke via Task tool

**Output:** JSON with pattern analysis (applied_correctly, contributed_to, confidence, insight, recommendation)

---

### 3. `reflector-prompt.md`
**Name:** `reflector-prompt`
**Invoked as:** `ace-orchestration:reflector-prompt` (via Task tool)

**Purpose:** Refines previous reflector analysis through iterative improvement (up to 5 rounds)

**Invoked by:**
- `ace-cycle.py` → `invoke_reflector_agent_with_feedback()` function
- Called in refinement loop with previous insights
- Implements ACE paper's "Iterative Refinement" mechanism (Figure 4)
- Outputs request to stderr asking Claude to invoke via Task tool

**Output:** JSON with refined pattern analysis (more specific evidence, higher confidence)

---

## How Agents are Invoked

### 1. Agent Definition Format

Each agent is a markdown file with YAML frontmatter:

```yaml
---
name: agent-name              # Required: lowercase with hyphens
description: What this agent does  # Required: when to invoke
tools: Read, Grep, Glob       # Optional: comma-separated tool list
model: sonnet                 # Optional: sonnet, opus, haiku, or 'inherit'
---

# Agent prompt/instructions here...
```

### 2. Agent Registration

Agents are **automatically discovered** by Claude Code from the `agents/` directory.
- NO explicit registration in `plugin.json` required
- Plugin agents appear in `/agents` interface
- Can be invoked explicitly or automatically by Claude

### 3. Agent Invocation

**Option A: Automatic (Claude decides)**
Claude can invoke agents automatically based on task context and the `description` field.

**Option B: Explicit (Request via stderr)**
ACE uses this approach - Python scripts output to stderr:

```python
print(f"""
🔬 ACE Reflector Request

Please invoke the reflector agent to analyze pattern effectiveness.

<reflector_analysis_request>
{json.dumps(reflector_input, indent=2)}
</reflector_analysis_request>

Use the Task tool to invoke ace-orchestration:reflector agent with the data above.
""", file=sys.stderr)
```

Claude sees this in stderr and uses Task tool to invoke:
```python
Task(
    description="Analyze coding patterns for effectiveness",
    prompt="<full agent prompt with data>",
    subagent_type="ace-orchestration:reflector"
)
```

### 4. Agent Naming Convention

- **File name:** `agent-name.md` (can be anything)
- **YAML `name` field:** `agent-name` (THIS is what matters!)
- **Invocation reference:** `plugin-name:agent-name`
  - Example: `ace-orchestration:reflector`
  - Example: `ace-orchestration:domain-discoverer`

---

## Key Design Decisions

### Why NO Fallback Heuristics?

The ACE research paper does NOT specify fallback heuristics. From Appendix B:

> "A potential limitation of ACE is its reliance on a reasonably strong Reflector: if the Reflector fails to extract meaningful insights from generated traces or outcomes, the constructed context may become noisy or even harmful."

This is an **acknowledged limitation**, not something to solve with hardcoded fallbacks.

When agent invocation fails or no reliable feedback signals exist:
- Return empty result or previous insights unchanged
- This gracefully degrades (no patterns learned) rather than polluting context with unreliable heuristics

### Agent Tools Access

All ACE agents have access to:
- `Read` - Read files from codebase
- `Grep` - Search for patterns in code
- `Glob` - Find files by name patterns

Agents do NOT have access to:
- `Edit`, `Write` - Reflector only analyzes, doesn't modify code
- `Bash` - No command execution needed for analysis

---

## Testing Agents

To test agent invocation manually:

```bash
# From project root
cd /Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace

# Make a code change to trigger ACE cycle
echo "# test change" >> test.py

# Watch stderr for agent invocation requests
# Claude should see the request and invoke the agent via Task tool
```

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
