# Multi-Tenant Authentication - Client Implementation

**Date**: 2025-10-20
**CRITICAL**: The client MUST send authentication headers with EVERY server request

---

## 🚨 CRITICAL: Every HTTP Request Needs Authentication

The server is **multi-tenant** - multiple organizations and projects share the same server.

**Without proper authentication, ALL requests will fail with 401 Unauthorized!**

---

## 🔑 Required Headers for EVERY Request

```typescript
// EVERY fetch to server must include these headers:
{
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${process.env.ACE_API_TOKEN}`,  // Organization identity
  'X-ACE-Project': process.env.ACE_PROJECT_ID              // Project identity
}
```

**Example**:
```
Authorization: Bearer ace_sZlqtF9-jY8M_4dXXRWMu4e0MyMcyAzargm_TK21YSs
X-ACE-Project: prj_6bba0d15c5a6abc1
```

---

## 📊 Multi-Tenant Data Isolation

### How Server Isolates Data

```
Organization A (org_abc123)
  ├─ Project 1 (prj_xyz789)
  │   └─ ChromaDB Collection: org_abc123_prj_xyz789
  │       ├─ Bullets for Project 1
  │       └─ Traces for Project 1
  └─ Project 2 (prj_def456)
      └─ ChromaDB Collection: org_abc123_prj_def456
          ├─ Bullets for Project 2
          └─ Traces for Project 2

Organization B (org_ghi789)
  └─ Project 3 (prj_jkl012)
      └─ ChromaDB Collection: org_ghi789_prj_jkl012
          ├─ Bullets for Project 3
          └─ Traces for Project 3
```

**Key Point**: Each project gets its own ChromaDB collection, completely isolated.

---

## 🔐 Authentication Flow (Client → Server)

### Step 1: Environment Variables (MCP Config)

**File**: `~/.config/claude-code/mcp-server-config.json` (or Claude Desktop config)

```json
{
  "mcpServers": {
    "ace-pattern-learning": {
      "command": "node",
      "args": ["/path/to/ce-ai-ace-client/dist/index.js"],
      "env": {
        "ACE_SERVER_URL": "http://localhost:9000",
        "ACE_API_TOKEN": "ace_sZlqtF9-jY8M_4dXXRWMu4e0MyMcyAzargm_TK21YSs",
        "ACE_PROJECT_ID": "prj_6bba0d15c5a6abc1"
      }
    }
  }
}
```

**Critical**: These environment variables MUST be set, or client will fail at startup.

---

### Step 2: Client Reads Environment Variables

**File**: `src/services/server-client.ts`

```typescript
export class ACEServerClient {
  private serverUrl: string;
  private apiToken: string;
  private projectId: string;

  constructor(config: ACEConfig) {
    // Read from environment (provided by MCP host)
    this.serverUrl = config.serverUrl || process.env.ACE_SERVER_URL || 'http://localhost:9000';
    this.apiToken = config.apiToken || process.env.ACE_API_TOKEN!;
    this.projectId = config.projectId || process.env.ACE_PROJECT_ID!;

    // CRITICAL: Validate required variables
    if (!this.apiToken) {
      throw new Error('ACE_API_TOKEN environment variable is required!');
    }
    if (!this.projectId) {
      throw new Error('ACE_PROJECT_ID environment variable is required!');
    }

    console.error(`🔗 ACE Server: ${this.serverUrl}`);
    console.error(`🔑 API Token: ${this.apiToken.substring(0, 10)}...`);
    console.error(`📂 Project ID: ${this.projectId}`);
  }

  // ... rest of class
}
```

---

### Step 3: Client Sends Headers with EVERY Request

**File**: `src/services/server-client.ts`

```typescript
export class ACEServerClient {
  private async request<T>(
    endpoint: string,
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    body?: any
  ): Promise<T> {
    const url = `${this.serverUrl}${endpoint}`;

    console.error(`🌐 ${method} ${url}`);

    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiToken}`,  // ← CRITICAL
        'X-ACE-Project': this.projectId              // ← CRITICAL
      },
      body: body ? JSON.stringify(body) : undefined
    });

    // Handle errors
    if (!response.ok) {
      const errorText = await response.text();

      if (response.status === 401) {
        throw new Error(`Authentication failed! Invalid API token or project ID.\n${errorText}`);
      }
      if (response.status === 403) {
        throw new Error(`Access denied! Project ${this.projectId} does not belong to your organization.\n${errorText}`);
      }

      throw new Error(`Server error (${response.status}): ${errorText}`);
    }

    return response.json();
  }

  // All public methods use this.request()
  async getPlaybook(): Promise<StructuredPlaybook> {
    const result = await this.request<{ playbook: StructuredPlaybook }>(
      '/playbook',
      'GET'
    );
    return result.playbook;
  }

  async savePlaybook(playbook: StructuredPlaybook): Promise<void> {
    await this.request('/playbook', 'POST', { playbook });
  }

  // ... etc
}
```

---

### Step 4: Server Validates Authentication

**Server File**: `ace_server/api_server.py`

```python
from fastapi import Depends, Header, HTTPException

async def verify_auth(
    authorization: Optional[str] = Header(None),
    x_ace_project: Optional[str] = Header(None)
) -> dict:
    """
    Verify Bearer token and project access

    Returns:
        dict with org_id, project_id, collection_name

    Raises:
        HTTPException 401: Invalid token
        HTTPException 403: Project access denied
    """
    # 1. Extract Bearer token
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]  # Remove "Bearer " prefix

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authorization header required (Bearer token)"
        )

    # 2. Validate token → Get org_id from tenants.db
    org_id = tenant_manager.validate_token(token)
    if not org_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid API token"
        )

    # 3. Get project ID from header
    project_id = x_ace_project
    if not project_id:
        raise HTTPException(
            status_code=401,
            detail="X-ACE-Project header required"
        )

    # 4. Verify project belongs to org
    project = tenant_manager.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=403,
            detail=f"Project {project_id} not found"
        )

    if project.org_id != org_id:
        raise HTTPException(
            status_code=403,
            detail=f"Project {project_id} does not belong to your organization"
        )

    # 5. Return auth context
    return {
        "org_id": org_id,
        "project_id": project_id,
        "collection_name": project.chromadb_collection_name  # e.g., "org_abc123_prj_xyz789"
    }


# All endpoints use this dependency
@app.get("/playbook")
async def get_playbook(auth: dict = Depends(verify_auth)):
    collection_name = auth["collection_name"]  # ← Isolated by project

    playbook = await storage.get_structured_playbook(collection_name)
    return {"playbook": playbook}


@app.post("/traces")
async def store_trace(
    trace: ExecutionTrace,
    auth: dict = Depends(verify_auth)
):
    collection_name = auth["collection_name"]

    await storage.store_execution_trace(trace, collection_name)
    return {"success": True}
```

---

## 🔧 Server Tenant Management API

### Create Organization (Admin Only)

**Endpoint**: `POST /admin/organizations`

**Request**:
```json
{
  "org_name": "My Company"
}
```

**Response**:
```json
{
  "org_id": "org_abc123",
  "org_name": "My Company",
  "api_token": "ace_sZlqtF9-jY8M_4dXXRWMu4e0MyMcyAzargm_TK21YSs",
  "created_at": "2025-10-20T10:30:00Z"
}
```

**Save this API token!** You need it for `ACE_API_TOKEN`.

---

### Create Project (Admin Only)

**Endpoint**: `POST /admin/projects`

**Headers**:
```
Authorization: Bearer ace_sZlqtF9-jY8M_...
```

**Request**:
```json
{
  "project_name": "My Project"
}
```

**Response**:
```json
{
  "project_id": "prj_6bba0d15c5a6abc1",
  "org_id": "org_abc123",
  "project_name": "My Project",
  "chromadb_collection_name": "org_abc123_prj_6bba0d15c5a6abc1",
  "created_at": "2025-10-20T10:35:00Z"
}
```

**Save this project_id!** You need it for `ACE_PROJECT_ID`.

---

## 🧪 Testing Authentication

### Test 1: Valid Auth

```bash
curl http://localhost:9000/playbook \
  -H "Authorization: Bearer ace_sZlqtF9-jY8M_..." \
  -H "X-ACE-Project: prj_6bba0d15c5a6abc1"

# Expected: 200 OK, playbook JSON
```

### Test 2: Missing Token

```bash
curl http://localhost:9000/playbook \
  -H "X-ACE-Project: prj_6bba0d15c5a6abc1"

# Expected: 401 Unauthorized
# Response: {"detail": "Authorization header required (Bearer token)"}
```

### Test 3: Invalid Token

```bash
curl http://localhost:9000/playbook \
  -H "Authorization: Bearer invalid_token" \
  -H "X-ACE-Project: prj_6bba0d15c5a6abc1"

# Expected: 401 Unauthorized
# Response: {"detail": "Invalid API token"}
```

### Test 4: Missing Project Header

```bash
curl http://localhost:9000/playbook \
  -H "Authorization: Bearer ace_sZlqtF9-jY8M_..."

# Expected: 401 Unauthorized
# Response: {"detail": "X-ACE-Project header required"}
```

### Test 5: Wrong Project (Access Denied)

```bash
# Org A tries to access Org B's project
curl http://localhost:9000/playbook \
  -H "Authorization: Bearer ace_org_a_token" \
  -H "X-ACE-Project: prj_org_b_project"

# Expected: 403 Forbidden
# Response: {"detail": "Project prj_org_b_project does not belong to your organization"}
```

---

## ⚠️ Common Client Mistakes

### ❌ Mistake 1: Hardcoding Credentials

```typescript
// WRONG - Never hardcode tokens!
const apiToken = "ace_sZlqtF9-jY8M_...";
```

```typescript
// CORRECT - Always use environment variables
const apiToken = process.env.ACE_API_TOKEN!;
```

---

### ❌ Mistake 2: Forgetting Headers

```typescript
// WRONG - Missing auth headers
await fetch(`${serverUrl}/playbook`, {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json'
  }
});
```

```typescript
// CORRECT - Include ALL headers
await fetch(`${serverUrl}/playbook`, {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${apiToken}`,  // ← Required
    'X-ACE-Project': projectId              // ← Required
  }
});
```

---

### ❌ Mistake 3: Not Validating Env Vars at Startup

```typescript
// WRONG - Will fail later during first request
constructor(config: ACEConfig) {
  this.apiToken = process.env.ACE_API_TOKEN!;
  this.projectId = process.env.ACE_PROJECT_ID!;
}
```

```typescript
// CORRECT - Fail fast with clear error
constructor(config: ACEConfig) {
  this.apiToken = process.env.ACE_API_TOKEN!;
  this.projectId = process.env.ACE_PROJECT_ID!;

  if (!this.apiToken) {
    throw new Error(
      'ACE_API_TOKEN environment variable is required!\n' +
      'Set it in your MCP server config: ~/.config/claude-code/mcp-server-config.json'
    );
  }
  if (!this.projectId) {
    throw new Error(
      'ACE_PROJECT_ID environment variable is required!\n' +
      'Set it in your MCP server config: ~/.config/claude-code/mcp-server-config.json'
    );
  }
}
```

---

### ❌ Mistake 4: Not Handling Auth Errors

```typescript
// WRONG - Generic error handling
if (!response.ok) {
  throw new Error(`Request failed: ${response.status}`);
}
```

```typescript
// CORRECT - Specific auth error messages
if (!response.ok) {
  const errorText = await response.text();

  if (response.status === 401) {
    throw new Error(
      `❌ Authentication failed!\n` +
      `Check your ACE_API_TOKEN and ACE_PROJECT_ID in MCP config.\n` +
      `Server response: ${errorText}`
    );
  }

  if (response.status === 403) {
    throw new Error(
      `❌ Access denied!\n` +
      `Project ${this.projectId} does not belong to your organization.\n` +
      `Server response: ${errorText}`
    );
  }

  throw new Error(`Server error (${response.status}): ${errorText}`);
}
```

---

## 📋 Implementation Checklist

### Phase 1: Environment Variables (Priority 1)

- [ ] Read `ACE_SERVER_URL` from environment
- [ ] Read `ACE_API_TOKEN` from environment
- [ ] Read `ACE_PROJECT_ID` from environment
- [ ] Validate all required variables at startup
- [ ] Fail fast with clear error messages if missing

### Phase 2: HTTP Client (Priority 1)

- [ ] Create `request()` method with auth headers
- [ ] Add `Authorization: Bearer {token}` header
- [ ] Add `X-ACE-Project: {project_id}` header
- [ ] Add `Content-Type: application/json` header

### Phase 3: Error Handling (Priority 1)

- [ ] Handle 401 Unauthorized (invalid token)
- [ ] Handle 403 Forbidden (wrong project)
- [ ] Handle 404 Not Found (project doesn't exist)
- [ ] Provide clear error messages for users

### Phase 4: Testing (Priority 2)

- [ ] Test with valid credentials → 200 OK
- [ ] Test with missing token → 401
- [ ] Test with invalid token → 401
- [ ] Test with missing project header → 401
- [ ] Test with wrong project → 403

---

## 🎯 Summary

**Client MUST**:
1. ✅ Read `ACE_API_TOKEN` and `ACE_PROJECT_ID` from environment
2. ✅ Send `Authorization: Bearer {token}` header with EVERY request
3. ✅ Send `X-ACE-Project: {project_id}` header with EVERY request
4. ✅ Validate env vars at startup (fail fast)
5. ✅ Handle auth errors gracefully (401, 403)

**Server DOES**:
1. ✅ Validate token → get org_id (from tenants.db)
2. ✅ Validate project → check belongs to org
3. ✅ Return collection_name for ChromaDB isolation
4. ✅ Reject requests with missing/invalid auth (401, 403)

**Without proper authentication, client will NOT work!** 🚫

---

## 📚 References

- **Server Auth Code**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server/ace_server/api_server.py` (verify_auth function)
- **Tenant Manager**: `/Users/ptsafaridis/repos/github_com/ce-dot-net/ce-ai-ace/server/ace_server/tenant_manager.py`
- **Client Implementation**: `src/services/server-client.ts`

---

**Authentication is CRITICAL! Every request must include Bearer token + Project ID.** 🔐
