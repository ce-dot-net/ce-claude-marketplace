# ACE Orchestration - Technical Documentation

Technical documentation covering architecture, security, and implementation details.

## Contents

### Architecture

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System architecture, design patterns, and component interactions
  - Generator (Claude) + Playbook retrieval/learning cycle
  - MCP Client (3-tier caching)
  - ACE Server (Reflector + Curator)
  - Skills (model-invoked)
  - **95% paper compliance verification**

- **[ENHANCEMENT_ROADMAP.md](./ENHANCEMENT_ROADMAP.md)** - Detailed enhancement roadmap and missing 5%
  - Semantic de-duplication analysis
  - Lazy refinement mode options
  - Implementation priorities and effort estimates
  - Recommendations for reaching 98% compliance

- **[SEMANTIC_DEDUP_SPEC.md](./SEMANTIC_DEDUP_SPEC.md)** - Complete implementation specification
  - Server-side embedding service with OpenAI integration
  - Curator semantic deduplication logic (85% threshold)
  - Testing strategy and cost analysis ($0.01/10K bullets)
  - Deployment guide with feature flags and rollback plan

### Security

- **[SECURITY.md](./SECURITY.md)** - Security considerations, best practices, and vulnerability reporting

## Architecture Overview

The ACE Orchestration plugin implements the ACE research paper architecture with **95% alignment**:

```
User Request → ACE Playbook Retrieval (skill) →
Claude Executes Task → ACE Learning (skill) →
Server Analysis (Reflector + Curator) → Updated Playbook
```

**Verification Status**:
- ✅ **10/10 Core Principles** - Complete implementation
- ⚠️ **3/3 Advanced Features** - With smart cost optimizations

See [ARCHITECTURE.md](./ARCHITECTURE.md#-implementation-status-95-paper-alignment) for comprehensive verification details.

## Key Components

1. **Agent Skills** (Model-Invoked)
   - `ace-playbook-retrieval` - Fetches patterns before tasks
   - `ace-learning` - Captures learning after tasks

2. **MCP Client** (3-Tier Cache)
   - RAM → SQLite → Server
   - Published as `@ce-dot-net/ace-client` on npm

3. **ACE Server** (Autonomous Analysis)
   - Reflector: Sonnet 4 pattern extraction
   - Curator: Haiku 4.5 delta updates
   - Merge: Non-LLM incremental updates

4. **Playbook Structure** (4 Sections)
   - strategies_and_hard_rules
   - useful_code_snippets
   - troubleshooting_and_pitfalls
   - apis_to_use

## Related Documentation

- **User Guides**: [../guides/](../guides/)
- **Releases**: [../releases/](../releases/)
- **Main README**: [../../README.md](../../README.md)
- **MCP Client**: [../../../../mcp-clients/ce-ai-ace-client/](../../../../mcp-clients/ce-ai-ace-client/)
