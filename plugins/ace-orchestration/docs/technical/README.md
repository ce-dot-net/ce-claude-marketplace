# ACE Orchestration - Technical Documentation

Technical documentation covering architecture, security, and implementation details.

## Contents

### Architecture

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System architecture, design patterns, and component interactions
  - Generator (Claude) + Playbook retrieval/learning cycle
  - MCP Client (3-tier caching)
  - ACE Server (Reflector + Curator)
  - Skills (model-invoked)

### Security

- **[SECURITY.md](./SECURITY.md)** - Security considerations, best practices, and vulnerability reporting

## Architecture Overview

The ACE Orchestration plugin implements the ACE research paper architecture:

```
User Request → ACE Playbook Retrieval (skill) →
Claude Executes Task → ACE Learning (skill) →
Server Analysis (Reflector + Curator) → Updated Playbook
```

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
