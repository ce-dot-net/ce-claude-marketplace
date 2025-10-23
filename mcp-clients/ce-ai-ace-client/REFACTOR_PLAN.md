# MCP Client Refactoring Plan

## 🎯 Goal
Remove Reflector/Curator analysis from MCP client. Make it a simple HTTP interface to the ACE server.

## ❌ What to Remove

### 1. **Remove Services** (No longer needed in client)
```typescript
// DELETE these files:
- src/services/reflector.ts       // Moves to server
- src/services/curator.ts          // Moves to server
```

### 2. **Remove MCP Sampling Capability**
```typescript
// src/index.ts line 56-60
// REMOVE:
capabilities: {
  tools: {},
  sampling: {}  // ❌ Claude Code doesn't support this
}

// REPLACE WITH:
capabilities: {
  tools: {}  // ✅ Just tools
}
```

### 3. **Simplify ace_learn Tool**
```typescript
// CURRENT (lines 375-460): Complex client-side analysis
case 'ace_learn': {
  // 1. Get playbook
  // 2. Run Reflector (MCP Sampling)
  // 3. Run Curator
  // 4. Save playbook
}

// NEW: Simple HTTP POST
case 'ace_learn': {
  // 1. POST /traces to server
  // 2. Server does Reflector+Curator automatically
  // 3. Return success
}
```

## ✅ What to Keep

### 1. **Keep These Tools** (Already simple HTTP)
- `ace_save_config` - Saves config file
- `ace_get_playbook` - GET /playbook
- `ace_get_status` - GET /analytics
- `ace_clear` - DELETE /patterns

### 2. **Keep These Services**
- `src/services/server-client.ts` - HTTP client (already good!)
- `src/services/config-loader.ts` - Config management
- `src/types/*.ts` - Type definitions

### 3. **Keep ace_init Tool** (But simplify)
- Currently does client-side initialization
- Change to: POST /init endpoint on server
- Let server handle git analysis

## 📝 Detailed Changes

### File 1: `src/index.ts`

#### Change 1: Remove imports
```typescript
// REMOVE lines 23-24:
import { ReflectorService } from './services/reflector.js';
import { CurationService } from './services/curator.js';

// REMOVE lines 32:
import { PlaybookBullet } from './types/pattern.js';
```

#### Change 2: Remove service initialization
```typescript
// REMOVE lines 45-46:
const reflectorService = new ReflectorService();
const curationService = new CurationService(serverClient, config);
```

#### Change 3: Remove sampling capability
```typescript
// CHANGE lines 56-60:
capabilities: {
  tools: {}  // Remove sampling
}
```

#### Change 4: Simplify ace_learn
```typescript
// REPLACE lines 375-460 with:
case 'ace_learn': {
  const { task, trajectory, success, output, error, playbook_used } = args as {
    task: string;
    trajectory: TrajectoryStep[];
    success: boolean;
    output: string;
    error?: string;
    playbook_used?: string[];
  };

  console.error('📤 Sending execution trace to server...');

  // Build execution trace
  const trace: ExecutionTrace = {
    task,
    trajectory,
    result: { success, output, error },
    playbook_used: playbook_used || [],
    timestamp: new Date().toISOString()
  };

  // Send to server - server will handle Reflector + Curator automatically
  try {
    await serverClient.storeExecutionTrace(trace);

    // Invalidate playbook cache so next request gets fresh data
    serverClient.invalidateCache();

    console.error('✅ Execution trace stored. Server is analyzing...');

    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          success: true,
          message: 'Execution trace stored successfully. Server-side Reflector and Curator will process asynchronously.',
          task,
          timestamp: trace.timestamp
        }, null, 2)
      }]
    };
  } catch (error: any) {
    console.error('❌ Error storing trace:', error);
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          success: false,
          error: error.message || 'Failed to store execution trace'
        }, null, 2)
      }],
      isError: true
    };
  }
}
```

#### Change 5: Simplify ace_init
```typescript
// REPLACE ace_init case (lines 220-373) with:
case 'ace_init': {
  const { repo_path, commit_limit, days_back, merge_with_existing } = args as {
    repo_path?: string;
    commit_limit?: number;
    days_back?: number;
    merge_with_existing?: boolean;
  };

  console.error('🚀 Requesting server-side initialization...');

  try {
    // POST to server /init endpoint
    const response = await serverClient.initializeFromRepo({
      repo_path: repo_path || process.cwd(),
      commit_limit: commit_limit || 100,
      days_back: days_back || 30,
      merge_with_existing: merge_with_existing !== false
    });

    console.error('✅ Server initialization complete');

    return {
      content: [{
        type: 'text',
        text: JSON.stringify(response, null, 2)
      }]
    };
  } catch (error: any) {
    console.error('❌ Error during initialization:', error);
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          success: false,
          error: error.message || 'Failed to initialize playbook'
        }, null, 2)
      }],
      isError: true
    };
  }
}
```

### File 2: `src/services/server-client.ts`

#### Add new method: storeExecutionTrace
```typescript
// Add after line ~180 in server-client.ts:

/**
 * Store execution trace for server-side analysis
 */
async storeExecutionTrace(trace: ExecutionTrace): Promise<void> {
  const url = `${this.config.serverUrl}/traces`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.config.apiToken}`,
      'X-ACE-Project': this.config.projectId
    },
    body: JSON.stringify(trace)
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to store trace: ${response.statusText} - ${errorText}`);
  }

  const result = await response.json();
  return result;
}
```

#### Add new method: initializeFromRepo
```typescript
// Add after storeExecutionTrace:

/**
 * Initialize playbook from git repository (server-side)
 */
async initializeFromRepo(params: {
  repo_path: string;
  commit_limit: number;
  days_back: number;
  merge_with_existing: boolean;
}): Promise<any> {
  const url = `${this.config.serverUrl}/init`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.config.apiToken}`,
      'X-ACE-Project': this.config.projectId
    },
    body: JSON.stringify(params)
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to initialize: ${response.statusText} - ${errorText}`);
  }

  return await response.json();
}
```

### File 3: `package.json`

#### Remove dependencies
```json
// REMOVE (if not used elsewhere):
// Check if these are only used by reflector/curator:
// - May need to remove nothing if types still need them
```

### File 4: DELETE FILES
```bash
# Delete these files entirely:
rm src/services/reflector.ts
rm src/services/curator.ts

# Keep these:
# - src/services/server-client.ts ✅
# - src/services/config-loader.ts ✅
# - src/services/initialization.ts ✅ (git history reading)
```

## 🧪 Testing Plan

### 1. Build Test
```bash
cd /Users/ptsafaridis/repos/github_com/ce-dot-net/ce-claude-marketplace/mcp-clients/ce-ai-ace-client
npm run build
# Should compile without errors
```

### 2. Manual Test
```bash
# Start MCP client
./dist/index.js

# Send test message (in another terminal):
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | ./dist/index.js
# Should return tool list including ace_learn
```

### 3. Integration Test
```bash
# With server running:
# Call ace_learn via Claude Code
# Verify trace appears in server logs
# Verify playbook gets updated
```

## 📦 Publishing

```bash
# 1. Build
npm run build

# 2. Version bump
npm version minor  # 3.2.0 (breaking change: removed sampling)

# 3. Test package
npm pack
tar -tzf ce-dot-net-ace-client-*.tgz | grep -E "(index.js|reflector|curator)"

# 4. Publish
npm publish

# 5. Update plugin
# Edit: plugins/ace-orchestration/.mcp.json
# Change version to 3.2.0
```

## ✅ Benefits of Refactoring

1. **Works with Claude Code** - No MCP Sampling needed
2. **Universal compatibility** - Works with ANY MCP client
3. **Simpler code** - Client just does HTTP
4. **Better architecture** - Analysis on server where it belongs
5. **Easier debugging** - Check server logs for analysis
6. **Cost efficient** - Server uses optimal model mix
7. **Team learning** - Shared server = shared patterns

## 📊 Before vs After

### Before (Current - Broken)
```
Claude Code
    ↓
MCP Client (tries to use sampling) ❌
    ├── Reflector (needs sampling)
    └── Curator
    ↓
Server (just storage)
```

### After (New - Works!)
```
Claude Code (any client!)
    ↓
MCP Client (simple HTTP) ✅
    ↓
Server (does all analysis)
    ├── Reflector (autonomous)
    ├── Curator (autonomous)
    └── Storage
```

## 🚀 Next Steps

1. Make the code changes above
2. Test build and functionality
3. Bump version to 3.2.0
4. Publish to npm
5. Update plugin .mcp.json
6. Test with Claude Code
7. Document multi-client setup

---

Ready to start implementing? Let's do it! 🎯
