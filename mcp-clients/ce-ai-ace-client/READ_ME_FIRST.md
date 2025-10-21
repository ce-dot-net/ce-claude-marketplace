# 🚨 READ THIS FIRST - Critical Information

**Date**: 2025-10-20
**For**: Client-Side Claude Implementation

---

## ⚠️ STOP! Read These Documents Before Starting

### 1. **`docs/SERVER_VS_CLIENT_RESPONSIBILITIES.md`** (MUST READ)

**Why**: Explains the complete architecture
- What the server saves (ChromaDB, SQLite)
- What the client does (intelligence, NOT storage)
- Multi-tenant authentication (API token + Project ID REQUIRED)
- TypeScript client code examples

### 2. **`SERVER_READY_INSTRUCTIONS.md`** (Implementation Guide)

**Why**: Step-by-step client implementation
- Server endpoints that ALREADY exist
- TypeScript code examples for Reflector and Curator
- Phase-by-phase implementation plan

### 3. **`WHY_CLIENT_SIDE.md`** (Architecture Rationale)

**Why**: Explains design decisions
- Why intelligence is client-side
- Why storage is server-side
- Cost, privacy, and control benefits

---

## 🚫 Critical Mistakes to Avoid

### ❌ Mistake 1: Creating v2 Files

**WRONG**:
- Creating `ace_server/types_v2.py`
- Creating `/v2/` endpoints
- Adding `storage_v2.py` or `api_server_v2.py`

**CORRECT**:
- Server is ALREADY refactored (types.py, storage.py, api_server.py)
- Endpoints ALREADY exist: `/traces`, `/playbook`, `/delta` (NOT `/v2/`)

---

### ❌ Mistake 2: Running Client Standalone

**WRONG**:
- Client can work without server
- Client stores patterns locally
- No authentication needed

**CORRECT**:
- Client MUST connect to server (Python FastAPI)
- Client MUST provide `ACE_API_TOKEN` and `ACE_PROJECT_ID`
- Client sends all data to server for storage
- Authentication example:
  ```typescript
  headers: {
    'Authorization': `Bearer ${process.env.ACE_API_TOKEN}`,
    'X-ACE-Project': process.env.ACE_PROJECT_ID
  }
  ```

---

### ❌ Mistake 3: GPU Claims

**WRONG**: "GPU embeddings", "GPU-accelerated server"

**CORRECT**: CPU-based `all-MiniLM-L6-v2` embeddings (GPU optional, not required)

---

### ❌ Mistake 4: Server Does LLM Calls

**WRONG**:
- Server calls Anthropic API
- Server does pattern discovery
- Server does reflection analysis

**CORRECT**:
- Client uses YOUR Claude via MCP Sampling
- Server has NO LLM access
- Server only stores results

---

## ✅ What You Need to Implement (Client-Side TypeScript)

### Phase 1: Types (`src/types/ace.ts`)

```typescript
export interface ExecutionTrace {
  task: string;
  trajectory: TrajectoryStep[];
  result: { success: boolean; output: string; error?: string };
  playbook_used: string[];
  timestamp: string;
}

export interface DeltaOperation {
  type: 'ADD' | 'UPDATE' | 'DELETE';
  section?: 'strategies_and_hard_rules' | 'useful_code_snippets' | 'troubleshooting_and_pitfalls' | 'apis_to_use';
  content?: string;
  pattern_id?: string;
  helpful_delta?: number;
  harmful_delta?: number;
  confidence?: number;
  evidence?: string[];
}

export interface Reflection {
  operations: DeltaOperation[];
  summary: string;
}
```

### Phase 2: Update ServerClient (`src/services/server-client.ts`)

```typescript
export class ACEServerClient {
  // Add authentication
  private apiToken: string = process.env.ACE_API_TOKEN!;
  private projectId: string = process.env.ACE_PROJECT_ID!;

  // Add new methods
  async storeExecutionTrace(trace: ExecutionTrace): Promise<void> {
    await this.fetch('/traces', { method: 'POST', body: JSON.stringify(trace) });
  }

  async getStructuredPlaybook(): Promise<StructuredPlaybook> {
    const response = await this.fetch('/playbook');
    return response.playbook;
  }

  async applyDeltaOperation(operation: DeltaOperation): Promise<void> {
    await this.fetch('/delta', { method: 'POST', body: JSON.stringify(operation) });
  }

  async updatePatternCounters(patternId: string, helpfulDelta: number, harmfulDelta: number): Promise<void> {
    await this.fetch(`/patterns/${patternId}/counters`, {
      method: 'PATCH',
      body: JSON.stringify({ helpful_delta: helpfulDelta, harmful_delta: harmfulDelta })
    });
  }

  async getTopBullets(limit: number = 10, by: 'helpful' | 'harmful' = 'helpful'): Promise<Pattern[]> {
    const response = await this.fetch(`/patterns/top?limit=${limit}&by=${by}`);
    return response.top_patterns;
  }
}
```

### Phase 3: Create Reflector (`src/services/reflector.ts`)

```typescript
export class ReflectorService {
  async analyzeExecution(
    trace: ExecutionTrace,
    playbook: Pattern[],
    requestSampling: (messages: any[]) => Promise<any>
  ): Promise<Reflection> {
    // Build prompt for YOUR Claude
    const prompt = `Analyze execution and generate delta operations...`;

    // Call YOUR Claude via MCP Sampling
    const response = await requestSampling([{ role: 'user', content: prompt }]);

    // Parse JSON response
    const reflection = JSON.parse(response.content[0].text);

    return reflection;
  }
}
```

### Phase 4: Create Curator (`src/services/curator-v2.ts`)

```typescript
export class CuratorServiceV2 {
  constructor(private serverClient: ACEServerClient) {}

  async applyDeltaOperations(reflection: Reflection): Promise<void> {
    for (const operation of reflection.operations) {
      await this.serverClient.applyDeltaOperation(operation);
    }
  }
}
```

### Phase 5: Add MCP Tool (`src/index.ts`)

```typescript
{
  name: 'ace_learn_from_execution',
  description: 'Learn from execution feedback (core ACE methodology)',
  inputSchema: {
    type: 'object',
    properties: {
      task: { type: 'string' },
      trajectory: { type: 'array' },
      success: { type: 'boolean' },
      output: { type: 'string' },
      playbook_used: { type: 'array' }
    }
  }
}

// Handler
case 'ace_learn_from_execution': {
  const trace: ExecutionTrace = { ... };

  // 1. Store trace on server
  await serverClient.storeExecutionTrace(trace);

  // 2. Get playbook from server
  const playbook = await serverClient.getStructuredPlaybook();

  // 3. Analyze with YOUR Claude (client-side)
  const reflection = await reflectorService.analyzeExecution(trace, playbook, requestSampling);

  // 4. Apply delta operations via server
  await curatorServiceV2.applyDeltaOperations(reflection);

  return { success: true, operations: reflection.operations.length };
}
```

---

## 🔑 Environment Variables Required

**Client MUST have these set in `~/.config/claude-code/mcp-server-config.json`**:

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "node",
      "args": ["/path/to/ce-ai-ace-client/dist/index.js"],
      "env": {
        "ACE_SERVER_URL": "http://localhost:9000",
        "ACE_API_TOKEN": "ace_sZlqtF9-jY8M_...",
        "ACE_PROJECT_ID": "prj_6bba0d15c5a6abc1"
      }
    }
  }
}
```

**Without these, client will FAIL!**

---

## 📊 Server Endpoints (ALREADY EXIST)

**Original Endpoints** (7):
1. `GET /` - Health check
2. `POST /patterns` - Save patterns
3. `GET /patterns` - Query patterns
4. `POST /patterns/search` - Similarity search
5. `POST /embeddings` - Compute embeddings
6. `GET /analytics` - Statistics
7. `DELETE /patterns` - Clear patterns

**NEW ACE Endpoints** (6):
8. `POST /traces` - Store execution trace
9. `GET /playbook` - Get structured playbook
10. `GET /playbook/section/{section}` - Get section patterns
11. `POST /delta` - Apply delta operation (ADD/UPDATE/DELETE)
12. `PATCH /patterns/{id}/counters` - Update helpful/harmful
13. `GET /patterns/top` - Get top bullets

**Total**: 13 application endpoints

---

## 🎯 Key Takeaways

1. **Server is Python** (FastAPI, ChromaDB, SQLite)
2. **Client is TypeScript** (MCP, runs in Claude Code/Desktop)
3. **NO v2 files** - Server is already refactored
4. **Authentication REQUIRED** - API token + Project ID
5. **Client does intelligence** - Pattern discovery, reflection, curation
6. **Server does storage** - ChromaDB patterns, execution traces, multi-tenancy
7. **Client uses YOUR Claude** - Via MCP Sampling, no Anthropic API key needed
8. **Server never calls LLM** - Only stores data, computes embeddings

---

**Now read `docs/SERVER_VS_CLIENT_RESPONSIBILITIES.md` for full details!** 📚
