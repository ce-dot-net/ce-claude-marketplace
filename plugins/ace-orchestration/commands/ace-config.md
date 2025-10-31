---
description: View and update ACE server configuration dynamically at runtime
---

# ACE Configuration Management

Manage ACE server settings without code changes. Adjust thresholds, enable token budget, and configure runtime behavior dynamically.

## What This Does

Allows you to **fetch and update ACE server configuration** in real-time:
- View current thresholds and settings
- Enable/disable token budget enforcement
- Adjust semantic search sensitivity
- Configure deduplication thresholds
- Control automatic learning features

**All changes persist on the server** (not just local session).

## Instructions for Claude

When the user runs `/ace-config [action] [params]`, call the appropriate MCP tool:

### 1. View Current Configuration

```bash
/ace-config show
→ mcp__plugin_ace-orchestration_ace-pattern-learning__ace_get_config()
```

Returns all current server settings including:
- `constitution_threshold` - Semantic search threshold (default: 0.7)
- `dedup_similarity_threshold` - Duplicate detection threshold (default: 0.85)
- `pruning_threshold` - Low-quality pattern removal (default: 0.3)
- `token_budget_enforcement` - Auto-pruning enabled/disabled (default: false)
- `max_playbook_tokens` - Token limit before pruning (default: null)
- `max_batch_size` - Max patterns per batch request (default: 50)

### 2. Enable Token Budget

```bash
/ace-config token-budget 50000
→ mcp__plugin_ace-orchestration_ace-pattern-learning__ace_set_config(
  token_budget_enforcement=true,
  max_playbook_tokens=50000
)
```

**What this does**:
- Enables automatic playbook pruning
- When playbook exceeds 50,000 tokens:
  - Server removes low-quality patterns (helpful-harmful < pruning_threshold)
  - Keeps high-quality patterns
  - Maintains playbook size within budget

### 3. Adjust Search Threshold

```bash
/ace-config search-threshold 0.8
→ mcp__plugin_ace-orchestration_ace-pattern-learning__ace_set_config(
  constitution_threshold=0.8
)
```

**Effect on `/ace-search`**:
- **Lower (0.3-0.5)**: Broader matches, more results
- **Medium (0.6-0.7)**: Balanced precision/recall (default)
- **Higher (0.8-0.9)**: Stricter matches, fewer but more precise results

### 4. Adjust Deduplication Threshold

```bash
/ace-config dedup-threshold 0.9
→ mcp__plugin_ace-orchestration_ace-pattern-learning__ace_set_config(
  dedup_similarity_threshold=0.9
)
```

**What this controls**:
- When server receives new pattern, checks similarity to existing patterns
- If similarity > threshold, merges instead of adding duplicate
- Higher threshold = stricter dedup (more patterns kept)
- Lower threshold = aggressive dedup (fewer duplicates)

### 5. Adjust Pruning Threshold

```bash
/ace-config pruning-threshold 0.4
→ mcp__plugin_ace-orchestration_ace-pattern-learning__ace_set_config(
  pruning_threshold=0.4
)
```

**What this controls**:
- Patterns with `(helpful - harmful) < threshold` are candidates for removal
- Only applies when token budget enforcement is enabled
- Higher threshold = more aggressive pruning
- Lower threshold = keeps more patterns

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
/ace-config search-threshold 0.85
```
**Use when**: You want only highly relevant results, willing to miss some edge cases.

### Optimize for Recall (Broad Search)

```bash
/ace-config search-threshold 0.4
```
**Use when**: You want comprehensive results, okay with some less-relevant matches.

### Enable Automatic Playbook Management

```bash
/ace-config token-budget 50000
```
**Use when**: Your playbook is growing large (10k+ patterns) and you want automatic quality-based pruning.

### Aggressive Deduplication

```bash
/ace-config dedup-threshold 0.75
```
**Use when**: You're getting too many similar patterns and want more aggressive merging.

### Conservative Pruning

```bash
/ace-config pruning-threshold 0.2
```
**Use when**: Token budget is enabled but you want to keep more patterns (only remove clearly harmful ones).

## Example Workflow

```bash
# 1. Check current settings
/ace-config show
→ Returns: constitution_threshold=0.7, token_budget_enforcement=false

# 2. Enable token budget for large playbook
/ace-config token-budget 50000
→ Success: Token budget enabled at 50,000 tokens

# 3. Adjust search for broader matches
/ace-config search-threshold 0.5
→ Success: Search threshold lowered to 0.5

# 4. Verify changes
/ace-config show
→ Returns: constitution_threshold=0.5, max_playbook_tokens=50000, token_budget_enforcement=true
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
  "curator_enabled": true
}
```

### ace_set_config Response:

```json
{
  "message": "Configuration updated successfully",
  ...updated config
}
```

## Performance Notes

- Configuration changes are **immediate** (no restart required)
- Config is **cached for 5 minutes** on MCP client (fast subsequent reads)
- Changes **persist across sessions** (stored on server)
- Use `/ace-cache-clear` to force config refresh if needed

## See Also

- `/ace-search` - Semantic search (uses `constitution_threshold`)
- `/ace-status` - View playbook statistics
- `/ace-patterns` - View full playbook
- `/ace-top` - Get highest-rated patterns
