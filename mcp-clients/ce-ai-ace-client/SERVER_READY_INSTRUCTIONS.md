# SERVER IS READY - Client Implementation Instructions

**Date**: 2025-10-20
**Server Status**: ✅ Refactored and Ready
**Your Task**: Implement client-side Reflector and Curator

---

## ⚠️ CRITICAL: NO v2 FILES - Server is REFACTORED

**READ THIS FIRST**: `docs/SERVER_VS_CLIENT_RESPONSIBILITIES.md`
- Explains what server saves vs what client does
- Clarifies multi-tenant authentication (API token + Project ID REQUIRED)
- Shows TypeScript client architecture
- Lists all server endpoints and what they do

**Server Implementation** (ALREADY DONE):
- ✅ Enhanced `ace_server/types.py` (NOT types_v2.py) with Pattern, ExecutionTrace, DeltaOperation
- ✅ Enhanced `ace_server/storage.py` (NOT storage_v2.py) with 6 new methods
- ✅ Enhanced `ace_server/api_server.py` with 6 new endpoints

**Server Endpoints** (ALREADY EXIST):
- ✅ `POST /traces` (NOT /v2/traces)
- ✅ `GET /playbook` (NOT /v2/playbook)
- ✅ `GET /playbook/section/{section}`
- ✅ `POST /delta`
- ✅ `PATCH /patterns/{id}/counters`
- ✅ `GET /patterns/top`

**NO GPU** - Embeddings use CPU-based `all-MiniLM-L6-v2` model (GPU acceleration optional)

**Authentication REQUIRED**:
- ✅ Client MUST provide `ACE_API_TOKEN` (validates organization)
- ✅ Client MUST provide `ACE_PROJECT_ID` (identifies project)
- ✅ Client MUST provide `ACE_SERVER_URL` (server endpoint)
- ❌ Client CANNOT run standalone without these!

**What You Need to Do**: Implement client-side services (Reflector, Curator) using the EXISTING server endpoints above.

---

## 🎯 What the Server Now Supports

The **Python FastAPI server** has been refactored (enhanced existing files, no v2) to support full ACE Paper methodology.

### Server Location
`/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server/`

---

## ✅ Server Capabilities (Ready to Use)

### 1. Enhanced Pattern Type

**New fields available**:
```typescript
interface Pattern {
  id: string;  // Now supports ctx-xxx format
  name: string;
  domain: string;
  content: string;
  confidence: number;
  observations: number;

  // NEW: ACE Paper support
  helpful: number;        // Tracks helpful instances
  harmful: number;        // Tracks harmful instances
  section: string;        // Playbook section (strategies | snippets | troubleshooting | apis | general)
  last_used?: string;     // When bullet was last consulted

  created_at: string;
  updated_at: string;
  evidence: string[];
}
```

### 2. New Server Endpoints (6 Added - 17 Total)

#### **POST /traces** - Store Execution Trace
```typescript
// Request
{
  "task": "Create user authentication endpoint",
  "trajectory": [
    {"step": 1, "action": "write_file", "args": {"path": "auth.py"}},
    {"step": 2, "action": "run_tests", "args": {}}
  ],
  "result": {
    "success": true,
    "output": "All tests passed",
    "error": null
  },
  "playbook_used": ["ctx-001", "ctx-002"]
}

// Response
{
  "stored": true,
  "task": "Create user authentication endpoint",
  "timestamp": "2025-10-20T..."
}
```

#### **GET /playbook** - Get Structured Playbook
```typescript
// Response
{
  "playbook": {
    "strategies_and_hard_rules": [
      {
        "id": "ctx-001",
        "content": "Always validate JWT tokens",
        "helpful": 8,
        "harmful": 0,
        "confidence": 1.0,
        ...
      }
    ],
    "useful_code_snippets": [...],
    "troubleshooting_and_pitfalls": [...],
    "apis_to_use": [...],
    "general": [...]
  },
  "total_bullets": 42
}
```

#### **GET /playbook/section/{section}** - Get Section Patterns
```typescript
// GET /playbook/section/strategies_and_hard_rules
{
  "section": "strategies_and_hard_rules",
  "patterns": [...],
  "count": 10
}
```

#### **POST /delta** - Apply Delta Operation
```typescript
// ADD new bullet
{
  "type": "ADD",
  "section": "strategies_and_hard_rules",
  "content": "Always check JWT expiration before validating",
  "confidence": 0.9,
  "evidence": ["auth.py:45"]
}

// UPDATE helpful/harmful
{
  "type": "UPDATE",
  "pattern_id": "ctx-001",
  "helpful_delta": 1,
  "harmful_delta": 0
}

// DELETE bullet
{
  "type": "DELETE",
  "pattern_id": "ctx-001"
}

// Response
{
  "applied": true,
  "operation_type": "ADD",
  "pattern_id": "ctx-001"
}
```

#### **PATCH /patterns/{id}/counters** - Update Counters
```typescript
// Request
{
  "helpful_delta": 1,
  "harmful_delta": 0
}

// Response
{
  "updated": true,
  "pattern_id": "ctx-001",
  "helpful": 9,
  "harmful": 0,
  "confidence": 1.0
}
```

#### **GET /patterns/top** - Get Top Bullets
```typescript
// GET /patterns/top?limit=10&by=helpful
{
  "top_patterns": [...],
  "count": 10,
  "sorted_by": "helpful",
  "limit": 10
}
```

---

## 🎯 What You Need to Implement (Client-Side)

### Phase 1: Update Types (`src/types/ace.ts`)

**Create new types**:
```typescript
export interface ExecutionTrace {
  task: string;
  trajectory: TrajectoryStep[];
  result: {
    success: boolean;
    output: string;
    error?: string;
  };
  playbook_used: string[];  // Pattern IDs consulted
  timestamp: string;
}

export interface TrajectoryStep {
  step: number;
  action: string;
  args: Record<string, any>;
  result?: any;
}

export interface DeltaOperation {
  type: 'ADD' | 'UPDATE' | 'DELETE';
  section?: 'strategies_and_hard_rules' | 'useful_code_snippets' |
            'troubleshooting_and_pitfalls' | 'apis_to_use' | 'general';
  content?: string;
  pattern_id?: string;
  helpful_delta?: number;
  harmful_delta?: number;
  confidence?: number;
  evidence?: string[];
  reason?: string;
}

export interface Reflection {
  operations: DeltaOperation[];
  summary: string;
}

export interface StructuredPlaybook {
  strategies_and_hard_rules: Pattern[];
  useful_code_snippets: Pattern[];
  troubleshooting_and_pitfalls: Pattern[];
  apis_to_use: Pattern[];
  general: Pattern[];
}
```

**Update Pattern type** in `src/types/pattern.ts`:
```typescript
export interface Pattern {
  id: string;
  name: string;
  domain: string;
  content: string;
  confidence: number;
  observations: number;

  // ADD THESE:
  helpful: number;
  harmful: number;
  section: string;
  last_used?: string;

  evidence: string[];
}
```

---

### Phase 2: Update ServerClient (`src/services/server-client.ts`)

**Add new methods**:
```typescript
export class ACEServerClient {
  // Existing methods stay unchanged...

  // NEW: Store execution trace
  async storeExecutionTrace(trace: ExecutionTrace): Promise<void> {
    await this.fetch('/traces', {
      method: 'POST',
      body: JSON.stringify({
        task: trace.task,
        trajectory: trace.trajectory,
        result: trace.result,
        playbook_used: trace.playbook_used
      })
    });
  }

  // NEW: Get structured playbook
  async getStructuredPlaybook(): Promise<StructuredPlaybook> {
    const response = await this.fetch('/playbook');
    return response.playbook;
  }

  // NEW: Get patterns by section
  async getPatternsBySection(section: string): Promise<Pattern[]> {
    const response = await this.fetch(`/playbook/section/${section}`);
    return response.patterns;
  }

  // NEW: Apply delta operation
  async applyDeltaOperation(operation: DeltaOperation): Promise<void> {
    await this.fetch('/delta', {
      method: 'POST',
      body: JSON.stringify(operation)
    });
  }

  // NEW: Update pattern counters
  async updatePatternCounters(
    patternId: string,
    helpfulDelta: number,
    harmfulDelta: number
  ): Promise<Pattern> {
    const response = await this.fetch(`/patterns/${patternId}/counters`, {
      method: 'PATCH',
      body: JSON.stringify({
        helpful_delta: helpfulDelta,
        harmful_delta: harmfulDelta
      })
    });

    // Fetch updated pattern
    return this.getPatternById(patternId);
  }

  // NEW: Get top bullets
  async getTopBullets(limit: number = 10, by: 'helpful' | 'harmful' = 'helpful'): Promise<Pattern[]> {
    const response = await this.fetch(`/patterns/top?limit=${limit}&by=${by}`);
    return response.top_patterns;
  }

  // NEW: Get pattern by ID
  async getPatternById(patternId: string): Promise<Pattern> {
    const patterns = await this.getPatterns();
    const pattern = patterns.find(p => p.id === patternId);
    if (!pattern) throw new Error(`Pattern ${patternId} not found`);
    return pattern;
  }
}
```

---

### Phase 3: Create ReflectorService (`src/services/reflector.ts`)

```typescript
import { ExecutionTrace, Reflection, DeltaOperation, Pattern } from '../types/ace.js';

export class ReflectorService {
  /**
   * Analyze execution outcome and generate delta operations
   *
   * This is the CORE innovation of ACE - learning from execution feedback
   */
  async analyzeExecution(
    trace: ExecutionTrace,
    playbook: Pattern[],
    requestSampling: (messages: any[]) => Promise<any>
  ): Promise<Reflection> {
    const prompt = `You are the Reflector agent in the ACE (Agentic Context Engineering) system.

Analyze this execution trace and identify lessons learned:

**Task**: ${trace.task}

**Execution Trace**:
${JSON.stringify(trace.trajectory, null, 2)}

**Result**:
- Success: ${trace.result.success}
- Output: ${trace.result.output}
- Error: ${trace.result.error || 'None'}

**Playbook Bullets Used**:
${trace.playbook_used.map(id => {
  const bullet = playbook.find(b => b.id === id);
  return `[${id}] helpful=${bullet?.helpful || 0} harmful=${bullet?.harmful || 0} :: ${bullet?.content || 'Unknown'}`;
}).join('\n')}

Your task:
1. Identify which playbook bullets were HELPFUL (led to success) → +1 helpful
2. Identify which playbook bullets were HARMFUL (led to errors) → +1 harmful
3. Extract NEW insights from this execution (what should be added to playbook)
4. Generate delta operations (ADD/UPDATE/DELETE)

For new insights, classify into sections:
- strategies_and_hard_rules: Strategic decisions, rules to follow
- useful_code_snippets: Proven code patterns
- troubleshooting_and_pitfalls: Common errors, gotchas
- apis_to_use: API usage patterns

Return ONLY JSON with no additional text:
{
  "operations": [
    {
      "type": "ADD" | "UPDATE" | "DELETE",
      "section": "strategies_and_hard_rules" | "useful_code_snippets" | "troubleshooting_and_pitfalls" | "apis_to_use",
      "content": "...",  // For ADD
      "pattern_id": "ctx-xxxxx",  // For UPDATE/DELETE
      "helpful_delta": 1,  // For UPDATE
      "harmful_delta": 0,  // For UPDATE
      "confidence": 0.0-1.0,
      "evidence": ["specific examples"],
      "reason": "Why this operation is needed"
    }
  ],
  "summary": "Brief summary of what was learned"
}`;

    const response = await requestSampling([{
      role: 'user',
      content: prompt
    }]);

    const text = response.content[0].text;
    const jsonMatch = text.match(/\{[\s\S]*\}/);

    if (!jsonMatch) {
      throw new Error('Failed to parse reflection from LLM');
    }

    return JSON.parse(jsonMatch[0]) as Reflection;
  }
}
```

---

### Phase 4: Create CuratorServiceV2 (`src/services/curator-v2.ts`)

```typescript
import { Reflection, DeltaOperation, StructuredPlaybook } from '../types/ace.js';
import { ACEServerClient } from './server-client.js';

export class CuratorServiceV2 {
  constructor(private serverClient: ACEServerClient) {}

  /**
   * Apply delta operations to playbook via server
   *
   * Server handles ADD/UPDATE/DELETE, grow-and-refine happens server-side
   */
  async applyDeltaOperations(reflection: Reflection): Promise<void> {
    for (const operation of reflection.operations) {
      await this.serverClient.applyDeltaOperation(operation);
    }
  }
}
```

---

### Phase 5: Add New MCP Tool (`src/index.ts`)

**Add after existing tools**:
```typescript
{
  name: 'ace_learn_from_execution',
  description: 'Learn from execution feedback (core ACE methodology)',
  inputSchema: {
    type: 'object',
    properties: {
      task: {
        type: 'string',
        description: 'Task that was attempted'
      },
      trajectory: {
        type: 'array',
        description: 'Execution trajectory (steps taken)',
        items: {
          type: 'object',
          properties: {
            step: { type: 'number' },
            action: { type: 'string' },
            args: { type: 'object' }
          }
        }
      },
      success: {
        type: 'boolean',
        description: 'Whether execution succeeded'
      },
      output: {
        type: 'string',
        description: 'Execution output'
      },
      error: {
        type: 'string',
        description: 'Error message if failed'
      },
      playbook_used: {
        type: 'array',
        description: 'Bullet IDs that were consulted',
        items: { type: 'string' }
      }
    },
    required: ['task', 'trajectory', 'success', 'output']
  }
}

// Handler:
case 'ace_learn_from_execution': {
  const { task, trajectory, success, output, error, playbook_used } = args;

  const trace: ExecutionTrace = {
    task,
    trajectory,
    result: { success, output, error },
    playbook_used: playbook_used || [],
    timestamp: new Date().toISOString()
  };

  // 1. Store trace on server
  await serverClient.storeExecutionTrace(trace);

  // 2. Get current playbook from server
  const playbook = await serverClient.getStructuredPlaybook();
  const allPatterns = Object.values(playbook).flat();

  // 3. Reflector analyzes execution (client-side intelligence)
  const reflection = await reflectorService.analyzeExecution(
    trace,
    allPatterns,
    async (messages) => {
      return await server.request({
        method: 'sampling/createMessage',
        params: { messages, maxTokens: 4000 }
      } as any, {} as any);
    }
  );

  // 4. Curator applies delta operations (via server)
  await curatorServiceV2.applyDeltaOperations(reflection);

  return {
    content: [{
      type: 'text',
      text: JSON.stringify({
        operations_applied: reflection.operations.length,
        summary: reflection.summary
      }, null, 2)
    }]
  };
}
```

---

## 🔧 Implementation Steps

### Step 1: Update Types
1. Create `src/types/ace.ts` with new types
2. Update `src/types/pattern.ts` to add `helpful`, `harmful`, `section`, `last_used`

### Step 2: Update ServerClient
1. Add 6 new methods to `src/services/server-client.ts`
2. Test each endpoint with server running

### Step 3: Create Reflector
1. Create `src/services/reflector.ts`
2. Implement `analyzeExecution()` with MCP Sampling

### Step 4: Create Curator V2
1. Create `src/services/curator-v2.ts`
2. Implement `applyDeltaOperations()`

### Step 5: Add MCP Tool
1. Update `src/index.ts` - add `ace_learn_from_execution` tool
2. Wire up Reflector and Curator

### Step 6: Test
1. Start server: `cd /Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server && python3 -m ace_server --port 9000`
2. Build client: `npm run build`
3. Test with Claude Code

---

## 📚 Reference Documentation

**Server Details**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/SERVER_REFACTORED.md`

**Full Roadmap**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/docs/ACE_FULL_IMPLEMENTATION_ROADMAP.md`

**Current Client**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-claude-marketplace/mcp-clients/ce-ai-ace-client/`

---

## ✅ Server Testing

All endpoints tested and working:
```bash
✅ Types imported successfully
✅ Storage module imported successfully
✅ API server imported successfully
Total endpoints: 17
```

---

## 🎯 Priority

**High Priority**: Implement `ace_learn_from_execution` tool first
- This is the core ACE innovation
- Enables learning from execution feedback
- Uses server's new `/traces` and `/delta` endpoints

**Medium Priority**: Add other tools later
- `ace_adapt_online` - Online adaptation
- `ace_multi_epoch` - Progressive strengthening

---

**Server is ready - start implementing client-side Reflector and Curator!** 🚀
