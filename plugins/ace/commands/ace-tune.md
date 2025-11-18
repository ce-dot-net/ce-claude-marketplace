---
description: View and update ACE project configuration dynamically at runtime
---

# ACE Configuration Management (Project-Level)

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

When the user runs `/ace-tune [action] [params]`, use ce-ace CLI directly:

### 1. View Current Configuration

```bash
#!/usr/bin/env bash
set -euo pipefail

# Export context for CLI
export ACE_ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
export ACE_PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

# Show current config - CLI fetches from server
ce-ace tune show
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

### 2. Interactive Mode (Recommended)

When user runs `/ace-tune` without arguments, use AskUserQuestion tool for interactive configuration:

```python
# Step 1: Show current config first
ce-ace tune show

# Step 2: Ask what they want to change
AskUserQuestion({
  "questions": [{
    "question": "What would you like to configure?",
    "header": "ACE Setting",
    "multiSelect": false,
    "options": [
      {
        "label": "Search Threshold",
        "description": "Adjust similarity threshold for pattern retrieval (0.0-1.0)"
      },
      {
        "label": "Search Top K",
        "description": "Maximum patterns returned per search (1-100)"
      },
      {
        "label": "Token Budget",
        "description": "Enable automatic playbook pruning at token limit"
      },
      {
        "label": "View Only",
        "description": "Just show current configuration"
      }
    ]
  }]
})

# Step 3: Based on selection, ask for value
# Example: If "Search Threshold" selected
AskUserQuestion({
  "questions": [{
    "question": "What threshold value? (0.0-1.0)",
    "header": "Threshold",
    "multiSelect": false,
    "options": [
      {"label": "0.35", "description": "Broad matches (more results)"},
      {"label": "0.45", "description": "Balanced (recommended)"},
      {"label": "0.60", "description": "Strict matches (fewer results)"},
      {"label": "0.75", "description": "Very strict (only close matches)"}
    ]
  }]
})

# Step 4: Apply with CLI
ce-ace tune --constitution-threshold 0.45
```

### 3. Non-Interactive Mode (Direct)

```bash
# Single setting
ce-ace tune --constitution-threshold 0.6

# Multiple settings
ce-ace tune \
  --constitution-threshold 0.5 \
  --search-top-k 15 \
  --dedup-enabled true
```

**What this does**:
- Enables automatic playbook pruning FOR THIS PROJECT
- When playbook exceeds 50,000 tokens:
  - Server removes low-quality patterns (helpful-harmful < pruning_threshold)
  - Keeps high-quality patterns
  - Maintains playbook size within budget

### 3. Direct CLI Examples

**Adjust Search Threshold**:
```bash
# Lower threshold for broader matches
ce-ace tune --constitution-threshold 0.35

# Higher threshold for stricter matches
ce-ace tune --constitution-threshold 0.8
```

**Effect on `/ace-search`**:
- **Lower (0.3-0.5)**: Broader matches, more results
- **Medium (0.6-0.7)**: Balanced precision/recall
- **Higher (0.8-0.9)**: Stricter matches, fewer but more precise results

**Adjust Multiple Settings**:
```bash
# Configure search behavior
ce-ace tune \
  --constitution-threshold 0.5 \
  --search-top-k 15

# Configure deduplication
ce-ace tune --dedup-similarity-threshold 0.9

# Configure pruning
ce-ace tune --pruning-threshold 0.4

# Enable token budget
ce-ace tune --token-budget-enforcement true --max-playbook-tokens 50000
```

**Reset to Defaults**:
```bash
# Reset project to org/server defaults
ce-ace tune --reset

# Verify reset
ce-ace tune show
```

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

## Example Workflows

### Interactive Mode (Recommended for Exploration)

```
User: "/ace-tune"
Claude: [Shows current config via ce-ace tune show]
Claude: [Uses AskUserQuestion with options: Search Threshold, Search Top K, Token Budget, View Only]
User: Selects "Search Threshold"
Claude: [Uses AskUserQuestion with threshold options: 0.35, 0.45, 0.60, 0.75]
User: Selects "0.45"
Claude: [Runs ce-ace tune --constitution-threshold 0.45]
Claude: "✅ Search threshold updated to 0.45 for this project"
```

### Non-Interactive Mode (Fast Direct Changes)

```bash
# 1. Check current settings
ce-ace tune show

# 2. Adjust search for broader matches
ce-ace tune --constitution-threshold 0.35

# 3. Increase max results
ce-ace tune --search-top-k 15

# 4. Enable token budget
ce-ace tune --token-budget-enforcement true --max-playbook-tokens 50000

# 5. Verify changes
ce-ace tune show

# 6. Later, reset to org/server defaults
ce-ace tune --reset
```

## Output Format

### ce-ace tune show

```
🎛️  ACE Configuration

ℹ Project: prj_d3a244129d62c198
ℹ Organization: org_34fYIlitYk4nyFuTvtsAzA6uUJF

ℹ Search/Retrieval:
ℹ   Constitution Threshold: 0.45 (similarity)
ℹ   Search Top K:           10 (max results)

ℹ Deduplication:
ℹ   Enabled:                true
ℹ   Similarity Threshold:   0.85

ℹ Token Budget:
ℹ   Enforcement:            false
ℹ   Max Playbook Tokens:    (not set)
ℹ   Pruning Threshold:      0.3

ℹ Batch Processing:
ℹ   Max Batch Size:         50

ℹ Learning Pipeline:
ℹ   Auto Learning:          true
ℹ   Reflector (Sonnet 4):   true
ℹ   Curator (Haiku 4.5):    true
```

### ce-ace tune --constitution-threshold 0.5

```
✅ Configuration updated successfully

🎛️  ACE Configuration

ℹ Project: prj_d3a244129d62c198
ℹ Organization: org_34fYIlitYk4nyFuTvtsAzA6uUJF

ℹ Search/Retrieval:
ℹ   Constitution Threshold: 0.5 (similarity)  ← Updated
ℹ   Search Top K:           10 (max results)
...
```

### ce-ace tune --reset

```
✅ Configuration reset successfully

All project-level overrides removed.
Project now inherits organization and server defaults.

Run 'ce-ace tune show' to see current effective config.
```

## Important Notes

### Project-Scoped Configuration

- All `/ace-tune` changes affect **THIS PROJECT ONLY**
- Changes persist on the server and sync across sessions
- Other projects maintain their own independent configurations
- Organization-level defaults can be set via web dashboard

### Environment Context

The `ce-ace` CLI automatically reads context from:
1. `ACE_ORG_ID` environment variable (passed by slash command)
2. `ACE_PROJECT_ID` environment variable (passed by slash command)
3. `~/.config/ace/config.json` for API token

You don't need to manually specify these - the slash command handles it.

### Multi-Tenant Safety

- Each project maintains independent configuration
- Configuration hierarchy: Project > Organization > Server
- Project overrides take precedence over org defaults
- Organization-wide settings require web dashboard access

## Performance Notes

- Configuration changes are **immediate** (no restart required)
- Changes **persist across sessions** (stored on server)
- Configuration is fetched fresh on each command (no stale cache issues)
- Hierarchical config resolved server-side (project → org → server)
- Average response time: 200-500ms for show, 300-600ms for updates

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
