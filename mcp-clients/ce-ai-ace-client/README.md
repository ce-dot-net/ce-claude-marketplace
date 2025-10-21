# ACE Pattern Learning - TypeScript MCP Client

**Full ACE Paper Implementation: Three-Agent Architecture (Generator → Reflector → Curator)**

[![MCP](https://img.shields.io/badge/MCP-TypeScript-blue)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.0.0-green)](package.json)

## What is This?

A **TypeScript MCP client** that implements the full [ACE research paper](https://arxiv.org/abs/2510.04618) (arXiv:2510.04618) with **execution feedback learning** and **three-agent architecture**.

**Key Innovation**: Learns from **execution outcomes** (success/failure), not static code analysis!

**Architecture**:
- ✅ **Generator**: Main agent (Claude Code) executes tasks
- ✅ **Reflector**: Analyzes execution outcomes via **MCP Sampling**
- ✅ **Curator**: Applies delta operations (ADD/UPDATE/DELETE bullets)
- ✅ **Execution Feedback**: Learns from task outcomes with helpful/harmful tracking
- ✅ **Structured Playbook**: Four sections per ACE paper Figure 3
- ✅ **No API key needed**: Uses Claude Code/Desktop/Cursor's existing Claude instance

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Claude Code / Desktop / Cursor                              │
│                                                               │
│  GENERATOR (Main Agent - Your Claude)                        │
│  ├─ Executes tasks                                           │
│  └─ Calls ace_learn tool with execution trace               │
│                   ↓                                           │
│  ace-pattern-learning MCP Client (TypeScript)                │
│  ├─ ReflectorService ────┐                                   │
│  │  (analyzes execution)  ├── Uses YOUR Claude               │
│  ├─ CurationService       │    via MCP Sampling              │
│  │  (delta operations)    │                                  │
│  └─ ServerClient ─────────┘                                  │
│                   ↓                                           │
│              HTTP REST API                                    │
│                   ↓                                           │
│  Remote ACE Storage Server (FastAPI)                         │
│  ├─ StructuredPlaybook storage (4 sections)                  │
│  ├─ ChromaDB (bullet embeddings)                             │
│  ├─ GPU embeddings (grow-and-refine)                         │
│  └─ Multi-tenant isolation                                   │
└──────────────────────────────────────────────────────────────┘
```

**Three-Agent Workflow** (ACE Paper Section 3):
1. **Generator** (Claude Code): Executes task, collects trajectory
2. **Reflector** (MCP Sampling): Analyzes outcome, generates delta operations
3. **Curator** (Client-side): Applies deltas, performs grow-and-refine

## Quick Install

### Prerequisites
- Claude Code (v1.9.0+) or Claude Desktop or Cursor
- Node.js 18+ (for TypeScript MCP)
- Access to ACE storage server (URL + API token)

### Installation

```bash
# Install via npm (when published)
npm install -g @ce-dot-net/ace-client

# Or install locally
cd /path/to/ce-ai-ace-client
npm install
npm run build
```

### Configure Claude Code

Add to your Claude Code MCP settings (`~/.config/claude-code/mcp.json`):

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "node",
      "args": ["/path/to/ce-ai-ace-client/dist/index.js"],
      "env": {
        "ACE_SERVER_URL": "https://your-ace-server.com",
        "ACE_API_TOKEN": "ace_your_token_here",
        "ACE_PROJECT_ID": "prj_your_project_id"
      }
    }
  }
}
```

**That's it!** All 5 ACE tools are now available in Claude Code.

## Tools Available

### 1. `ace_init` (Offline Learning)
Initialize playbook from existing codebase by analyzing git history.

**Parameters**:
- `repo_path` (string, optional): Path to git repository (defaults to current directory)
- `commit_limit` (number, optional): Number of commits to analyze (default: 100)
- `days_back` (number, optional): Days of history to analyze (default: 30)
- `merge_with_existing` (boolean, optional): Merge with existing playbook (default: true)

**What happens**:
1. Analyzes git commit history (refactorings, bug fixes, features)
2. Extracts patterns from code changes
3. Builds initial playbook with 4 sections
4. Merges with existing or replaces (based on merge_with_existing)

**Example**:
```typescript
// Bootstrap playbook from existing codebase:
ace_init({
  commit_limit: 100,
  days_back: 30,
  merge_with_existing: true
})

// Discovers:
// - Strategies from refactoring commits
// - Troubleshooting from bug fix commits
// - APIs from feature additions
// - File co-occurrence patterns
```

**When to use**:
- ✅ New project setup (bootstrap from existing code)
- ✅ Team onboarding (share historical lessons)
- ✅ Post-migration (capture patterns after major refactoring)
- ❌ Empty repository (needs at least 10-20 commits)

### 2. `ace_learn` (Online Learning - Core Innovation!)
Learn from execution feedback using the three-agent architecture.

**Parameters**:
- `task` (string): Task that was executed
- `trajectory` (array): Execution trajectory (steps, actions, results)
- `success` (boolean): Whether execution succeeded
- `output` (string): Execution output
- `error` (string, optional): Error message if failed
- `playbook_used` (array, optional): Bullet IDs that were consulted

**What happens**:
1. **Reflector** analyzes execution outcome via MCP Sampling
2. Generates delta operations (ADD helpful bullets, UPDATE counters, DELETE harmful bullets)
3. **Curator** applies operations and performs grow-and-refine (0.85/0.30 thresholds)
4. Saves updated playbook to server

**Example**:
```typescript
// Claude Code automatically calls this after task execution:
ace_learn({
  task: "Implement JWT authentication",
  trajectory: [
    {step: 1, action: "install", args: {package: "jsonwebtoken"}, result: {success: true}},
    {step: 2, action: "code", args: {file: "auth.ts"}, result: {success: true}}
  ],
  success: true,
  output: "Authentication working with JWT tokens"
})

// Reflector learns: "Install jsonwebtoken before importing"
// Curator adds to strategies_and_hard_rules section
```

### 3. `ace_get_playbook`
Get structured ACE playbook (4 sections from paper Figure 3).

**Parameters**:
- `section` (string, optional): Filter by section (strategies_and_hard_rules, useful_code_snippets, troubleshooting_and_pitfalls, apis_to_use)
- `min_helpful` (number, optional): Minimum helpful count

**Returns**: Markdown playbook with bullets sorted by helpful count

**Example**:
```typescript
// Ask Claude Code:
"Show me the ACE playbook for troubleshooting"

// Returns formatted markdown with top helpful bullets
```

### 4. `ace_status`
Get playbook statistics (bullet counts, top helpful/harmful).

**Returns**:
```json
{
  "total_bullets": 42,
  "by_section": {
    "strategies_and_hard_rules": 10,
    "useful_code_snippets": 15,
    "troubleshooting_and_pitfalls": 12,
    "apis_to_use": 5
  },
  "avg_confidence": 0.78,
  "top_helpful": [...],
  "top_harmful": [...]
}
```

### 5. `ace_clear`
Clear entire ACE playbook (requires confirmation).

**Parameters**:
- `confirm` (boolean): Must be `true` to confirm deletion

## Configuration

### Environment Variables

**Required**:
- `ACE_SERVER_URL`: Your ACE storage server URL (e.g., `http://localhost:9000`)
- `ACE_API_TOKEN`: Your API token (format: `ace_xxx...`)

**Optional**:
- `ACE_PROJECT_ID`: Project ID for multi-tenant isolation (format: `prj_xxx`)
- `ACE_SIMILARITY_THRESHOLD`: Similarity threshold for merging (default: `0.85`)
- `ACE_CONFIDENCE_THRESHOLD`: Confidence threshold for pruning (default: `0.30`)

### Multi-Tenant Setup

ACE storage server supports complete multi-tenant architecture:

1. **Administrator creates organization**:
```bash
# Server admin runs:
python3 -m ace_admin_cli create-org "Your Company" "admin@company.com"
# Output: org_abc123xyz, ace_xxxxxxxxxxxx
```

2. **Administrator creates project**:
```bash
python3 -m ace_admin_cli create-project org_abc123xyz "your-project"
# Output: prj_xyz789abc
```

3. **You configure client** with provided credentials (see above)

4. **Automatic isolation**: All patterns stored in project-specific ChromaDB collection

## How It Works

### 1. Generator Executes Task (Your Claude)

Claude Code executes your task and tracks the execution trajectory:

```typescript
const trace: ExecutionTrace = {
  task: "Implement JWT authentication",
  trajectory: [
    {step: 1, action: "npm install", args: {package: "jsonwebtoken"}, result: {success: true}},
    {step: 2, action: "import jwt", args: {}, result: {success: false, error: "Module not found"}},
    {step: 3, action: "npm install jsonwebtoken", args: {}, result: {success: true}},
    {step: 4, action: "import jwt", args: {}, result: {success: true}}
  ],
  result: {success: true, output: "JWT working"},
  playbook_used: ["ctx-12345"],  // Bullets consulted during execution
  timestamp: "2025-01-20T17:00:00Z"
};
```

### 2. Reflector Analyzes Outcome (MCP Sampling)

Uses **YOUR Claude** to analyze what happened:

```typescript
// ReflectorService
const reflection = await reflectorService.analyzeExecution(
  trace,
  currentPlaybook,
  async (messages) => {
    // Calls YOUR Claude via MCP Sampling
    return await server.request({
      method: 'sampling/createMessage',
      params: { messages, maxTokens: 4000, temperature: 0.7 }
    });
  }
);
```

Your Claude generates delta operations:
```json
{
  "operations": [
    {
      "type": "ADD",
      "section": "strategies_and_hard_rules",
      "content": "Always verify npm package name before importing (jsonwebtoken vs jwt)",
      "confidence": 0.9,
      "evidence": ["ImportError: No module named 'jwt'"],
      "reason": "Import failed due to incorrect package name"
    },
    {
      "type": "UPDATE",
      "bullet_id": "ctx-12345",
      "helpful_delta": 1,
      "reason": "Bullet helped resolve the issue"
    }
  ],
  "summary": "Learned to check package names before importing"
}
```

### 3. Curator Applies Delta Operations (Client-Side)

Implements ACE paper methodology:

```typescript
// CurationService
async applyDeltaOperations(playbook, reflection) {
  // 1. Apply delta operations
  for (const op of reflection.operations) {
    if (op.type === 'ADD') this.addBullet(playbook, op);
    if (op.type === 'UPDATE') this.updateBullet(playbook, op);  // helpful++, harmful++
    if (op.type === 'DELETE') this.deleteBullet(playbook, op);
  }

  // 2. Grow-and-refine deduplication
  return await this.growAndRefine(playbook);
}

async growAndRefine(playbook) {
  // Get embeddings from server (GPU-accelerated)
  const embeddings = await serverClient.computeEmbeddings(texts);

  // Merge similar bullets (0.85 threshold)
  bullets = this.mergeSimilarBullets(bullets, embeddings);

  // Prune low confidence (0.30 threshold)
  bullets = bullets.filter(b => b.confidence >= 0.30);

  // Prune consistently harmful (harmful > helpful)
  bullets = bullets.filter(b => b.helpful >= b.harmful);

  return bullets;
}
```

### Structured Playbook (ACE Paper Figure 3)

```json
{
  "strategies_and_hard_rules": [
    {
      "id": "ctx-1737387600-a1b2c",
      "content": "Verify npm package name before importing",
      "helpful": 5,
      "harmful": 0,
      "confidence": 1.0,
      "evidence": ["ImportError in auth.ts:5"],
      "observations": 5
    }
  ],
  "useful_code_snippets": [...],
  "troubleshooting_and_pitfalls": [...],
  "apis_to_use": [...]
}
```

## Development

### Local Development

```bash
# Clone repo
git clone https://github.com/ce-dot-net/ce-claude-marketplace
cd ce-claude-marketplace/mcp-clients/ce-ai-ace-client

# Install dependencies
npm install

# Build TypeScript
npm run build

# Set up test credentials
export ACE_SERVER_URL="http://localhost:9000"
export ACE_API_TOKEN="ace_sZlqtF9-jY8M_4dXXRWMu4e0MyMcyAzargm_TK21YSs"
export ACE_PROJECT_ID="prj_6bba0d15c5a6abc1"

# Test client
node dist/index.js
```

### Project Structure

```
ce-ai-ace-client/
├── src/
│   ├── index.ts                 # Main MCP server with 4 tools
│   ├── types/
│   │   ├── pattern.ts           # PlaybookBullet, StructuredPlaybook, DeltaOperation, ExecutionTrace
│   │   └── config.ts            # ACEConfig type
│   └── services/
│       ├── server-client.ts     # HTTP REST client for storage server
│       ├── reflector.ts         # Reflector agent (MCP Sampling)
│       └── curator.ts           # Curator agent (delta operations + grow-and-refine)
├── dist/                        # Compiled JavaScript
├── package.json
├── tsconfig.json
└── README.md
```

### Testing with ACE Storage Server

1. **Start storage server** (FastAPI):
```bash
cd /path/to/ace-storage-server
python3 -m ace_server --port 9000
```

2. **Test REST API**:
```bash
curl http://localhost:9000/
# Returns: {"service":"ACE Storage Service","version":"0.3.0"}

curl -X GET http://localhost:9000/patterns \
  -H "Authorization: Bearer $ACE_API_TOKEN" \
  -H "X-ACE-Project: $ACE_PROJECT_ID"
```

3. **Test MCP client** with Claude Code:
```bash
# Add to Claude Code MCP settings
# Then ask: "Show ACE status"
```

## Security

- All communication encrypted (HTTPS)
- API tokens never logged
- Multi-tenant isolation (collection-per-project)
- Bearer token authentication

## Research Background

Based on the ACE paper (arXiv:2510.04618) - Full Implementation:
- **Three-Agent Architecture**: Generator → Reflector → Curator
- **Execution Feedback**: Learns from task outcomes (success/failure)
- **Delta Operations**: Incremental updates (ADD/UPDATE/DELETE) instead of monolithic rewrites
- **Helpful/Harmful Tracking**: Each bullet tracks usefulness via counters
- **Structured Playbook**: Four sections (strategies, snippets, troubleshooting, APIs)
- **Grow-and-Refine**: 0.85 similarity for merging, 0.30 confidence for pruning
- **Iterative Refinement**: Multi-pass reflection for accuracy

## License

MIT License - Copyright (c) 2025 CE Team

## Contributing

Contributions welcome! Please open issues or PRs at:
https://github.com/ce-dot-net/ce-claude-marketplace

## Support

- **Documentation**: See code comments in `src/` folder
- **Issues**: https://github.com/ce-dot-net/ce-claude-marketplace/issues
- **ACE Paper**: https://arxiv.org/abs/2510.04618
