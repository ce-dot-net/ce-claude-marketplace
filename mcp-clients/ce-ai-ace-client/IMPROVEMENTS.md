# ACE Client v3.2.3 - Improved Automatic Learning

## Summary

Dramatically improved the automatic invocation of ACE learning by following Anthropic's best practices for MCP tool descriptions. This aligns with how successful MCP servers (Serena, Context7, Sequential Thinking) achieve "automatic" behavior.

## Key Discovery

**MCP servers don't automatically trigger themselves** - they rely on:
1. Claude's intelligent decision-making
2. Excellent tool descriptions with clear use cases
3. Keywords and examples that match user queries
4. System instructions (CLAUDE.md) that encourage usage

## What Changed

### 1. Improved `ace_learn` Tool Description (src/index.ts)

**Before:**
```typescript
description: 'Store execution trace for server-side analysis (Reflector + Curator run automatically on server)'
```

**After:**
```typescript
description: `Capture patterns and lessons learned from substantial coding tasks for automatic playbook improvement. Use AFTER completing:

• Problem-solving: Fixed bugs, debugged test failures, resolved build errors, troubleshot integrations
• Implementation: Implemented features, refactored code, optimized performance, updated architectures
• API Integration: Integrated external APIs, used new libraries/frameworks, configured build tools
• Failures & Recovery: Encountered errors and found solutions, discovered edge cases or gotchas
• Complex Tasks: Multi-step implementations, architectural decisions, technical problem-solving

WHEN TO USE: After completing substantial work where you learned something valuable...

SKIP FOR: Simple Q&A, basic file reads, trivial edits without problem-solving...

EXAMPLES:
- "Fixed intermittent async test failures by discovering missing await on database.close()"
- "Integrated Stripe webhooks, learned they require express.raw() for signature verification"
...
```

**Why this works:**
- Clear use cases with bullet points
- Explicit "WHEN TO USE" and "SKIP FOR" guidance
- Real-world examples Claude can pattern-match against
- Keywords Claude recognizes ("debugging", "implementing", "API integration")
- Detailed context about server-side processing

### 2. Enhanced Parameter Descriptions

Each parameter now includes:
- Clear explanation of what to provide
- Concrete examples
- Guidance on formatting

Example:
```typescript
task: {
  type: 'string',
  description: 'Brief description (1-2 sentences) of what was accomplished. Example: "Debugged intermittent test failures in async database operations"'
}
```

### 3. Updated CLAUDE.md Documentation

- Clarified that "automatic" means Claude's autonomous decision-making
- Emphasized two pathways: Skills and direct tool invocation
- Updated terminology to match how MCP tools actually work
- Added explicit trust in tool descriptions

### 4. Code Cleanup

Removed abandoned "event-driven SQLite + WAL watching" approach:
- ❌ Removed `execution_events` table from local-cache.ts
- ❌ Removed `chokidar` dependency
- ❌ Deleted unused `write-execution-event.sh` hook script
- ✅ Kept WAL mode pragma (general optimization)

## Why This Approach Works

### Research Findings

We investigated how successful MCP servers achieve "automatic" behavior:

**Serena**:
- Uses `--project` flag for automatic activation at startup
- Relies on tool descriptions for Claude to invoke tools appropriately

**Context7**:
- Detects library mentions in prompts
- Users can explicitly say "use context7" but it also auto-triggers based on context

**Sequential Thinking**:
- Claude identifies when tasks require sequential reasoning
- Automatically shifts into enhanced reasoning mode based on tool description

**Common Pattern:**
All rely on **Claude's intelligence + excellent tool descriptions**, not forced automation!

### Anthropic's Best Practices

From Anthropic's official guide "Writing effective tools for AI agents":

1. **Think Like Onboarding a New Hire** - Make implicit knowledge explicit
2. **Clarity Over Brevity** - Detailed descriptions work better than terse ones
3. **Include Examples** - Real-world use cases help Claude pattern-match
4. **Describe When NOT to Use** - "SKIP FOR" is as important as "USE FOR"
5. **Iterate Based on Usage** - Monitor and refine based on actual behavior

## Impact

**Before:**
- Vague tool description: "Store execution trace for server-side analysis"
- Claude unclear when to invoke
- Required explicit user instruction or Skill invocation

**After:**
- Rich, contextual tool description with 20+ lines of guidance
- Clear trigger keywords Claude recognizes
- Real-world examples matching common scenarios
- Explicit "WHEN TO USE" and "SKIP FOR" sections

**Expected Improvement:**
Claude will now **autonomously recognize** situations matching the description:
- After fixing bugs → "Fixed bugs" keyword matches
- After API integration → "Integrated external APIs" matches
- After debugging → Real-world examples match
- After problem-solving → Use cases match

## Architecture Alignment

This maintains the ACE research paper architecture:
- **Generator**: Claude (main instance) - now better informed about when to learn
- **MCP Client**: Simple HTTP interface (unchanged)
- **ACE Server**: Reflector + Curator (unchanged, server-side)

The improvement is in **better communication** between Generator and the learning system through superior tool descriptions.

## Testing

✅ Build successful - TypeScript compiled without errors
✅ Integration tests passing - all 6 tests pass
✅ Tool description verified in compiled output
✅ CLAUDE.md updated with clarified expectations

## Next Steps

1. **Monitor Usage**: Watch how often Claude invokes `ace_learn` in real usage
2. **Iterate**: Refine tool description based on patterns of overuse/underuse
3. **Gather Feedback**: Ask users if learning captures the right moments
4. **Measure Impact**: Track playbook growth and pattern quality

## Files Changed

- `src/index.ts` - Dramatically improved ace_learn tool description
- `src/services/local-cache.ts` - Removed unused execution_events table
- `package.json` - Removed unused chokidar dependency
- `CLAUDE.md` (plugin) - Updated to reflect how automation actually works
- `tests/verify-tool-description.ts` - Added verification test

## Version

Recommend bumping to **v3.2.3** - significant UX improvement in automatic learning invocation.
