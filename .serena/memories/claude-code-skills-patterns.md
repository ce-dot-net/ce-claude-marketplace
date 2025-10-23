# Claude Code Agent Skills - Best Practices & Patterns

**Last Updated**: 2025-10-23  
**Sources**: Anthropic official docs, GitHub (anthropics/skills, lackeyjb/playwright-skill, obra/superpowers)

---

## What Are Agent Skills?

Agent Skills are **model-invoked** modular capabilities that extend Claude's functionality. Unlike slash commands (user-invoked) or hooks (lifecycle-triggered), skills are autonomous—**Claude decides when to use them** based on task context.

**Key Quote from Anthropic**:
> "Skills are model-invoked—Claude autonomously decides to use them based on your request and the Skill's description."

---

## Official Specification (Anthropic)

### Required Structure

Every skill MUST have a `SKILL.md` file with:

```yaml
---
name: skill-name-in-hyphen-case  # Must match directory name
description: What it does AND when Claude should use it (CRITICAL!)
---

# Skill Name

## When to Use
- Clear trigger scenarios

## Instructions
1. Step-by-step guidance
2. Tool calls if needed
3. Expected outcomes
```

### Optional Fields

```yaml
---
name: my-skill
description: Clear description with triggers
allowed-tools: [Read, Grep, Glob]  # Pre-approved tools
license: MIT
metadata:
  author: "Your Name"
  category: "automation"
---
```

---

## Progressive Disclosure (3 Levels)

Agent Skills use a **three-level loading system** to manage context efficiently:

### Level 1: Metadata (~100 tokens)
- **Always loaded** at session start
- YAML frontmatter only (name + description)
- Used for skill discovery
- **Token cost**: ~100 tokens per skill

### Level 2: Instructions (<5k tokens)
- **Loaded when triggered** by description match
- Full SKILL.md content
- Procedural knowledge, workflows
- **Token cost**: ~5k tokens when active

### Level 3: Resources (Variable)
- **Loaded as needed** when explicitly referenced
- REFERENCE.md, scripts, templates
- Only accessed if instructions reference them
- **Token cost**: Variable, only when used

**Key Insight**: "Script code itself never enters context window. Only the script's output consumes tokens."

---

## Description Best Practices

The `description` field is **critical for discovery**. Claude uses it to decide when to activate the skill.

### ❌ Bad Examples
- "Helps with testing" (too vague)
- "Database tool" (doesn't explain when)
- "Code helper" (not specific enough)

### ✅ Good Examples
- "RED-GREEN-REFACTOR cycle for test-driven development. Use when implementing features with TDD approach."
- "Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction."
- "Automatically retrieve ACE playbook patterns before substantial coding tasks (implementation, debugging, refactoring, API integration, architecture decisions)."

### Formula
**Description = WHAT + WHEN**
- **WHAT**: Concrete functionality
- **WHEN**: Specific trigger words/scenarios

---

## Skill Directory Structure

### Minimal (Required)
```
my-skill/
└── SKILL.md  # Only file needed!
```

### Enhanced (Recommended)
```
my-skill/
├── SKILL.md           # Concise instructions (~5k tokens)
├── REFERENCE.md       # Comprehensive docs (lazy-loaded)
└── lib/
    └── helper.js      # Scripts (code never enters context, only output)
```

### Example from Playwright Skill (Production)
```
playwright-skill/
├── SKILL.md           # 314 lines (concise)
├── API_REFERENCE.md   # 630 lines (loaded "when needed")
├── run.js             # Universal executor
└── lib/
    └── helpers.js     # Optional utilities
```

**Pattern**: Keep SKILL.md concise, defer comprehensive docs to REFERENCE.md

---

## Integration with External Systems

### Pattern: Skills Call Tools, Tools Do Work

**❌ Don't**: Hardcode business logic in SKILL.md
```markdown
## Instructions
1. Connect to Stripe API with key xyz...
2. Create checkout session with...
```

**✅ Do**: Skills call MCP tools/executors
```markdown
## Instructions
1. Call: mcp__ace-pattern-learning__ace_get_playbook
2. Review retrieved patterns
3. Apply to current task
```

**Example from Playwright Skill**:
- Skill provides framework and instructions
- Universal executor (`run.js`) handles execution context
- Claude writes custom code for specific requests
- No hardcoded automation logic

**Example from ACE Skills**:
- ACE Playbook Retrieval skill calls MCP tool
- MCP client handles 3-tier caching
- Skill just orchestrates, doesn't implement caching

---

## Real-World Examples from GitHub

### Example 1: Official Template (Anthropic)
```yaml
---
name: template-skill
description: Replace with description of the skill and when Claude should use it.
---

# Insert instructions below
```

**Simplicity**: Absolute minimum needed!

### Example 2: Playwright Skill (Production)
```yaml
---
name: playwright-skill
description: Complete browser automation with Playwright for testing websites, automating interactions, and validating web functionality. Use for e2e testing, browser automation, and web testing workflows.
---

# Playwright Browser Automation

## When to Use
- Testing web applications
- Automating browser interactions
- Validating web functionality

## Instructions
1. Server auto-detection: Always run detectDevServers() first
2. Write test to /tmp/playwright-test-*.js
3. Execute via: cd $SKILL_DIR && node run.js /tmp/playwright-test-*.js
```

**Key Patterns**:
- Clear triggers (e2e testing, automation)
- Three-step workflow
- Executor-based execution (universal run.js)
- Progressive disclosure (API_REFERENCE.md lazy-loaded)

### Example 3: Superpowers Library
```
skills/
├── testing/
│   └── test-driven-development/SKILL.md
├── debugging/
│   └── systematic-debugging/SKILL.md
└── collaboration/
    └── brainstorming/SKILL.md
```

**Organization**: By domain, one capability per skill

---

## Common Patterns & Anti-Patterns

### ✅ Patterns to Follow

**1. One Skill = One Capability**
- Don't create monolithic skills
- Each skill addresses specific need
- Easier for Claude to discover

**2. Progressive Disclosure**
- Keep SKILL.md concise
- Defer details to REFERENCE.md
- Only load when needed

**3. Clear Trigger Words**
- Include in description: implement, debug, test, refactor, integrate
- Specific scenarios: "when user mentions PDFs"
- Domain terms: "TDD", "e2e testing", "authentication"

**4. MCP Tool Integration**
- Skills orchestrate, tools execute
- Don't duplicate logic
- Let existing systems handle complexity

**5. Filesystem-Based Resources**
- Scripts execute outside context
- Only output enters context
- Token-efficient

### ❌ Anti-Patterns to Avoid

**1. Vague Descriptions**
- "Helps with code" → Too generic
- "Useful tool" → Doesn't explain when

**2. Hardcoded Logic**
- Business logic in SKILL.md → Should be in tools
- Specific API keys → Should be in config

**3. Monolithic Skills**
- One skill doing everything → Split by capability
- "Developer productivity mega-skill" → Break down

**4. Loading Unnecessary Content**
- All docs in SKILL.md → Use REFERENCE.md
- Heavy files loaded upfront → Progressive disclosure

**5. Manual Invocation Dependency**
- Requiring user to call skill → Should auto-invoke
- No clear triggers → Claude can't decide when

---

## ACE Skills Implementation (Our Example)

### ACE Playbook Retrieval Skill

**Location**: `plugins/ace-orchestration/skills/ace-playbook-retrieval/SKILL.md`

**Design Decisions**:
1. **Description**: Includes both WHAT and WHEN
   - WHAT: "Retrieve ACE playbook patterns"
   - WHEN: "before substantial coding tasks (implementation, debugging...)"

2. **Trigger Words**: implement, build, create, fix, debug, refactor, integrate, optimize, architect

3. **MCP Integration**: Calls `mcp__ace-pattern-learning__ace_get_playbook`
   - Skill doesn't implement caching
   - MCP client handles 3-tier cache
   - Skill just orchestrates

4. **Progressive Disclosure**:
   - Level 1: ~100 token description
   - Level 2: ~5k token SKILL.md
   - Level 3: Could add REFERENCE.md for ACE architecture details (optional)

5. **Examples**: Three concrete scenarios (JWT, debugging, Stripe)

### ACE Learning Skill

**Location**: `plugins/ace-orchestration/skills/ace-learning/SKILL.md`

**Already Excellent**:
- Clear triggers (after substantial work)
- Specific scenarios (problem-solving, debugging, implementation)
- MCP tool integration (ace_learn)
- Examples with trajectory + feedback

**Why It Works**:
- Description matches Anthropic spec
- Progressive disclosure
- Model-invoked (Claude decides)
- Token-efficient

---

## Testing & Debugging Skills

### How to Test Auto-Invocation

**Method 1: Direct Request**
```
User: "Implement user authentication"
Expected: Skill should auto-invoke (matches "implement")
```

**Method 2: Observation**
- Check conversation for MCP tool calls
- Skills should activate without manual intervention
- Look for skill instructions in Claude's reasoning

**Method 3: Explicit Mention**
```
User: "Use the PDF skill to extract form fields from file.pdf"
Expected: PDF skill activates
```

### Common Issues

**Skill Doesn't Auto-Invoke**:
- ❌ Cause: Vague description
- ✅ Fix: Add specific trigger words
- ❌ Cause: Task too trivial
- ✅ Fix: Skills skip simple Q&A

**Skill Not Discovered**:
- ❌ Cause: Invalid YAML syntax
- ✅ Fix: Validate frontmatter
- ❌ Cause: Wrong file location
- ✅ Fix: Check `skills/` directory

**Wrong Skill Activates**:
- ❌ Cause: Overlapping descriptions
- ✅ Fix: Make descriptions distinct

---

## Skill Locations & Distribution

### Personal Skills
**Location**: `~/.claude/skills/`
**Purpose**: Individual workflows, experimental capabilities
**Distribution**: Not shared

### Project Skills
**Location**: `.claude/skills/` (in repo)
**Purpose**: Team-shared, version-controlled
**Distribution**: Via git (automatic for team)

### Plugin Skills
**Location**: `plugins/{plugin-name}/skills/`
**Purpose**: Bundled with plugin
**Distribution**: Via plugin marketplace

**ACE Skills**: Plugin skills (bundled with ace-orchestration plugin)

---

## Key Takeaways for ACE Implementation

1. **Model-Invoked = Automatic**
   - No manual skill calls needed
   - Claude decides based on description
   - Fully automatic cycle!

2. **Progressive Disclosure = Token-Efficient**
   - Only loads when needed
   - Can include comprehensive docs without penalty
   - Scales to large playbooks

3. **Skills + MCP Tools = Clean Architecture**
   - Skills orchestrate
   - MCP tools execute
   - Clear separation of concerns

4. **Description = Discovery**
   - Must include trigger words
   - Specific scenarios critical
   - WHAT + WHEN formula

5. **One Skill = One Capability**
   - ACE Playbook Retrieval (before)
   - ACE Learning (after)
   - Together = Complete cycle

---

## References

### Official Documentation
- **Anthropic Skills Docs**: https://docs.claude.com/en/docs/claude-code/skills
- **Agent Skills Overview**: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview
- **Skills Specification**: https://github.com/anthropics/skills/blob/main/agent_skills_spec.md

### Real-World Examples
- **Official Skills Repo**: https://github.com/anthropics/skills
- **Playwright Skill**: https://github.com/lackeyjb/playwright-skill (production example)
- **Superpowers Library**: https://github.com/obra/superpowers (core skills library)
- **Awesome Claude Skills**: https://github.com/travisvn/awesome-claude-skills (curated list)

### ACE Implementation
- **ACE Playbook Retrieval**: `plugins/ace-orchestration/skills/ace-playbook-retrieval/SKILL.md`
- **ACE Learning**: `plugins/ace-orchestration/skills/ace-learning/SKILL.md`
- **CLAUDE.md**: Complete cycle documentation

---

**Last Updated**: 2025-10-23 (ACE v3.2.4 skills implementation)