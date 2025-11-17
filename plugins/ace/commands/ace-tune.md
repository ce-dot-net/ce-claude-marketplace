---
description: View and update ACE project configuration dynamically at runtime
---

# ACE Configuration Management (Project-Level)

⚠️ **NOTE**: Runtime configuration tuning is not yet available in ce-ace CLI v1.0.2. This feature is planned for a future release.

For now, runtime configuration (thresholds, token budgets, etc.) must be managed through the ACE web dashboard or server API.

---

Manage ACE configuration for **THIS PROJECT ONLY**. Adjust thresholds, enable token budget, and configure runtime behavior dynamically.

## 🚨 Important: Project-Level Scope

**All `/ace-tune` commands affect THIS PROJECT ONLY.**

- Changes apply to the current project
- Other projects in your organization are NOT affected
- Organization-wide settings are managed via web dashboard

**Hierarchical Configuration:**
- **Server defaults** (global baseline)
- **Organization-level** (per org) ← Set via web dashboard
- **Project-level** (per project) ← `/ace-tune` scope

**Priority**: `Project > Org > Server` (project overrides org overrides server)

**For organization-wide configuration**, use the web dashboard instead.

## What This Does

Allows you to **fetch and update ACE project configuration** in real-time:
- View current effective configuration (with source hierarchy)
- Enable/disable token budget enforcement for this project
- Adjust semantic search sensitivity
- Configure deduplication thresholds
- Control automatic learning features
- Reset project config to org/server defaults

**All changes persist on the server** for this specific project.

## Instructions for Claude

When the user runs `/ace-tune [action] [params]`, follow these steps:

### 1. View Current Configuration

```bash
/ace-tune show
→ Step 1: Call mcp__plugin_ace_ace-pattern-learning__ace_get_config()
→ Step 2: Display config with source attribution (project/org/server)
```

**Display format:**
```
┌─────────────────────────────────────────────────────┐
│ ACE Configuration (Project: {project_name})         │
├─────────────────────────────────────────────────────┤
│ dedup_similarity_threshold: 0.85 (from org)         │
│ constitution_threshold: 0.7 (from server)           │
│ pruning_threshold: 0.3 (from server)                │
│ token_budget_enforcement: false (from server)       │
│ max_playbook_tokens: null (from server)             │
│ max_batch_size: 50 (from server)                    │
│ auto_learning_enabled: true (from server)           │
│ reflector_enabled: true (from server)               │
│ curator_enabled: true (from server)                 │
│ dedup_enabled: true (from server)                   │
│                                                     │
│ 💡 Config source: project < org < server           │
│    To change org defaults, use web dashboard.      │
└─────────────────────────────────────────────────────┘
```

**Returns current effective settings including:**
- `constitution_threshold` - Semantic search threshold (default: 0.7)
- `dedup_similarity_threshold` - Duplicate detection threshold (default: 0.85)
- `pruning_threshold` - Low-quality pattern removal (default: 0.3)
- `token_budget_enforcement` - Auto-pruning enabled/disabled (default: false)
- `max_playbook_tokens` - Token limit before pruning (default: null)
- `max_batch_size` - Max patterns per batch request (default: 50)

### 2. Enable Token Budget

```bash
/ace-tune token-budget 50000

→ Step 1: Show warning
⚠️  This will update config for THIS PROJECT ONLY.

Current project: {project_name}

Other projects in your organization will NOT be affected.

Continue? [y/N]

→ Step 2: If user confirms (y/yes), call:
mcp__plugin_ace_ace-pattern-learning__ace_set_config(
  scope="project",
  token_budget_enforcement=true,
  max_playbook_tokens=50000
)

→ Step 3: Display success message
✅ Project config updated for: {project_name}
   - token_budget_enforcement: true
   - max_playbook_tokens: 50000

💡 Other projects inherit org/server defaults.
```

**What this does**:
- Enables automatic playbook pruning FOR THIS PROJECT
- When playbook exceeds 50,000 tokens:
  - Server removes low-quality patterns (helpful-harmful < pruning_threshold)
  - Keeps high-quality patterns
  - Maintains playbook size within budget

### 3. Adjust Search Threshold

```bash
/ace-tune search-threshold 0.8

→ Step 1: Show warning
⚠️  This will update config for THIS PROJECT ONLY.
Current project: {project_name}
Continue? [y/N]

→ Step 2: If confirmed, call:
mcp__plugin_ace_ace-pattern-learning__ace_set_config(
  scope="project",
  constitution_threshold=0.8
)

→ Step 3: Display result
✅ Project config updated
   - constitution_threshold: 0.8 (project override)

💡 Other projects inherit org default.
```

**Effect on `/ace-search`**:
- **Lower (0.3-0.5)**: Broader matches, more results
- **Medium (0.6-0.7)**: Balanced precision/recall (default)
- **Higher (0.8-0.9)**: Stricter matches, fewer but more precise results

### 4. Adjust Deduplication Threshold

```bash
/ace-tune dedup-threshold 0.9

→ Step 1: Show warning
⚠️  This will update config for THIS PROJECT ONLY.
Current project: {project_name}
Continue? [y/N]

→ Step 2: If confirmed, call:
mcp__plugin_ace_ace-pattern-learning__ace_set_config(
  scope="project",
  dedup_similarity_threshold=0.9
)

→ Step 3: Display result
✅ Project config updated
   - dedup_similarity_threshold: 0.9 (project override)
```

**What this controls**:
- When server receives new pattern, checks similarity to existing patterns
- If similarity > threshold, merges instead of adding duplicate
- Higher threshold = stricter dedup (more patterns kept)
- Lower threshold = aggressive dedup (fewer duplicates)

### 5. Adjust Pruning Threshold

```bash
/ace-tune pruning-threshold 0.4

→ Step 1: Show warning
⚠️  This will update config for THIS PROJECT ONLY.
Current project: {project_name}
Continue? [y/N]

→ Step 2: If confirmed, call:
mcp__plugin_ace_ace-pattern-learning__ace_set_config(
  scope="project",
  pruning_threshold=0.4
)

→ Step 3: Display result
✅ Project config updated
   - pruning_threshold: 0.4 (project override)
```

**What this controls**:
- Patterns with `(helpful - harmful) < threshold` are candidates for removal
- Only applies when token budget enforcement is enabled
- Higher threshold = more aggressive pruning
- Lower threshold = keeps more patterns

### 6. Reset Project Config (NEW)

```bash
/ace-tune reset

→ Step 1: Show warning
⚠️  Reset THIS PROJECT to org/server defaults?

Current project: {project_name}

All project-level overrides will be removed.
The project will inherit org and server defaults.

Continue? [y/N]

→ Step 2: If confirmed, call:
mcp__plugin_ace_ace-pattern-learning__ace_reset_config(
  scope="project"
)

→ Step 3: Display result
✅ Project config reset for: {project_name}

All settings now inherit from org/server defaults.

Run `/ace-tune show` to see current effective config.
```

**What this does**:
- Removes all project-level configuration overrides
- Project reverts to organization and server defaults
- Useful for cleaning up project-specific customizations

## Configuration Options Reference

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `constitution_threshold` | float | 0.7 | 0.0-1.0 | Semantic search similarity threshold |
| `dedup_similarity_threshold` | float | 0.85 | 0.0-1.0 | Duplicate detection threshold |
| `pruning_threshold` | float | 0.3 | 0.0-1.0 | Min quality score to keep pattern |
| `token_budget_enforcement` | bool | false | - | Enable automatic pruning |
| `max_playbook_tokens` | int\|null | null | >0 | Token limit for auto-pruning |
| `max_batch_size` | int | 50 | 1-100 | Max patterns per batch request |
| `auto_learning_enabled` | bool | true | - | Enable automatic learning |
| `reflector_enabled` | bool | true | - | Enable Reflector (Sonnet 4) |
| `curator_enabled` | bool | true | - | Enable Curator (Haiku 4.5) |
| `dedup_enabled` | bool | true | - | Enable deduplication |

## Common Use Cases

### Optimize for Precision (Strict Search)

```bash
/ace-tune search-threshold 0.85
```
**Use when**: You want only highly relevant results for this project, willing to miss some edge cases.

### Optimize for Recall (Broad Search)

```bash
/ace-tune search-threshold 0.4
```
**Use when**: You want comprehensive results for this project, okay with some less-relevant matches.

### Enable Automatic Playbook Management

```bash
/ace-tune token-budget 50000
```
**Use when**: This project's playbook is growing large (10k+ patterns) and you want automatic quality-based pruning.

### Aggressive Deduplication

```bash
/ace-tune dedup-threshold 0.75
```
**Use when**: This project is getting too many similar patterns and you want more aggressive merging.

### Conservative Pruning

```bash
/ace-tune pruning-threshold 0.2
```
**Use when**: Token budget is enabled for this project but you want to keep more patterns (only remove clearly harmful ones).

### Reset to Organization Defaults

```bash
/ace-tune reset
```
**Use when**: You want to remove project-specific customizations and inherit org/server defaults.

## Example Workflow

```bash
# 1. Check current settings for this project
/ace-tune show
→ Project: ce-ai-ace
→ constitution_threshold=0.7 (from server)
→ token_budget_enforcement=false (from server)

# 2. Enable token budget for THIS PROJECT
/ace-tune token-budget 50000
→ ⚠️  Update THIS PROJECT ONLY? [y/N] y
→ ✅ Project config updated: token_budget_enforcement=true

# 3. Adjust search for broader matches in THIS PROJECT
/ace-tune search-threshold 0.5
→ ⚠️  Update THIS PROJECT ONLY? [y/N] y
→ ✅ Project config updated: constitution_threshold=0.5

# 4. Verify changes
/ace-tune show
→ constitution_threshold=0.5 (from project)  ← Project override
→ max_playbook_tokens=50000 (from project)  ← Project override
→ token_budget_enforcement=true (from project)  ← Project override

# 5. Later, reset to org/server defaults
/ace-tune reset
→ ⚠️  Reset to defaults? [y/N] y
→ ✅ Project config reset. All settings now inherit from org/server.
```

## Output Format

### ace_get_config Response:

```json
{
  "dedup_similarity_threshold": 0.85,
  "dedup_enabled": true,
  "constitution_threshold": 0.7,
  "pruning_threshold": 0.3,
  "max_playbook_tokens": null,
  "token_budget_enforcement": false,
  "max_batch_size": 50,
  "auto_learning_enabled": true,
  "reflector_enabled": true,
  "curator_enabled": true,
  "config_sources": {
    "constitution_threshold": "server",
    "dedup_similarity_threshold": "org",
    "token_budget_enforcement": "project"
  }
}
```

### ace_set_config Response:

```json
{
  "message": "Configuration updated successfully",
  "scope": "project",
  "project_id": "prj_xxx",
  ...updated config
}
```

### ace_reset_config Response:

```json
{
  "message": "Project configuration reset successfully",
  "scope": "project",
  "project_id": "prj_xxx"
}
```

## Important Notes

### Scope Behavior

- **`scope="project"`** (REQUIRED): All `/ace-tune` commands MUST pass this parameter
- **Project isolation**: Changes affect ONLY the current project
- **Org defaults**: Other projects inherit organization or server defaults
- **Web dashboard**: For org-wide settings, use web interface

### Multi-Tenant Safety

- `/ace-tune` is **project-scoped** to prevent multi-tenant conflicts
- Each project maintains independent configuration
- Organization-level settings require web dashboard access

### Migration from v4.1.x

**Breaking change in v4.2.0:**
- MCP tool now REQUIRES `scope` parameter
- Old commands without `scope` will fail with error:
  ```
  ⚠️  ACE server update detected.
  /ace-tune now requires scope parameter.
  Update to plugin v4.2.0+ to continue.
  ```

## Performance Notes

- Configuration changes are **immediate** (no restart required)
- Config is **cached for 5 minutes** on MCP client (fast subsequent reads)
- Changes **persist across sessions** (stored on server)
- Use `/ace-cache-clear` to force config refresh if needed
- Hierarchical config resolved server-side (project → org → server)

## See Also

- `/ace-search` - Semantic search (uses `constitution_threshold`)
- `/ace-status` - View playbook statistics
- `/ace-patterns` - View full playbook
- `/ace-top` - Get highest-rated patterns
- `/ace-configure` - Initial project setup

## Web Dashboard

For organization-wide configuration management:
**https://ace-dashboard.code-engine.app/org/{org_id}/settings**

Use the web dashboard to:
- Set organization-wide defaults
- Manage multiple projects
- View organization-level analytics
- Configure team permissions
