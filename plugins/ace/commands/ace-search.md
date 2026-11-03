---
model: claude-haiku-4-5
description: Semantic search for ACE patterns using natural language query
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(jq:*), Bash(npm:*), Read
---

# ACE Semantic Search

Search for relevant patterns using natural language query instead of retrieving all patterns.

## What This Does

Uses semantic search to find only the most relevant patterns matching your query, reducing context usage by 50-80%.

## Instructions for Claude

When the user runs `/ace-search <query>`:

### Step 1: Pre-flight Auth Check

First, run this bash script to check authentication:

```bash
#!/usr/bin/env bash
# ACE Pre-flight Auth Check (v5.4.21)

# Check ace-cli is available
if ! ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version >/dev/null 2>&1; then
  echo "ACE_STATUS=cli_not_found"
  exit 0
fi

# Check authentication status
AUTH_JSON=$(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli whoami --json 2>/dev/null || echo '{"authenticated":false}')
IS_AUTH=$(echo "$AUTH_JSON" | jq -r '.authenticated // false')

if [ "$IS_AUTH" != "true" ]; then
  echo "ACE_STATUS=not_authenticated"
else
  echo "ACE_STATUS=ok"
fi
```

### Step 2: Handle Auth Status

Based on the output:

- **If `ACE_STATUS=cli_not_found`**: Tell the user to install ace-cli:
  ```
  ❌ ace-cli not found. Install: /ace:ace-install-cli
  ```

- **If `ACE_STATUS=not_authenticated`**: Use the **AskUserQuestion** tool to ask the user:
  - **Question**: "ACE is not authenticated. Would you like to login now?"
  - **Options**:
    1. **"Login now"** - Run `/ace-login` command for them
    2. **"Continue without ACE"** - Show message: "⚠️ ACE pattern learning is disabled for this session. Run /ace-login anytime to enable."
    3. **"Skip"** - Just exit without action

- **If `ACE_STATUS=ok`**: Proceed to Step 3

### Step 3: Run Search (only if authenticated)

```bash
#!/usr/bin/env bash
set -euo pipefail

# 8.1.0: the one binding lookup (scripts/ace-context, the plugin core); never read binding files here
CTX="$("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --shell)" || exit 1
eval "$CTX"; ORG_ID="$ACE_ORG_ID"; PROJECT_ID="$ACE_PROJECT_ID"

if [ -z "$ACE_ORG_ID" ] || [ -z "$ACE_PROJECT_ID" ]; then
  echo "❌ ACE is not bound here (see the line above)"
  echo "Run /ace-configure to set up ACE"
  exit 1
fi

# Call ace-cli search - CLI reads org/project from env vars automatically
# Threshold comes from server config (ace-cli tune show) - don't override!
# --json: the CLI's human formatter never prints root_cause. The wrapper filters only stderr, so stdout stays JSON.
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli search --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" "$*" --json | jq -r '
  (.similar_patterns // []) | to_entries[] | .value as $p |
  "\(.key + 1). \($p.content)",
  "   domain: \($p.domain // "-") | section: \($p.section // "-") | reward: \($p.cumulative_v15_reward // 0) | bandit_rank: \($p.bandit_rank // $p.match_factors.bandit_rank // "-")",
  (($p.evidence // []) | if length > 0 then "   evidence: " + (map(tostring) | join(" | ")) else empty end),
  (if (($p.root_cause // "") | tostring | length) > 0 then "   root cause: \($p.root_cause)" else empty end),
  ""'
```

Show the user this list as is (one block per pattern; `root cause` only appears when the pattern has one).

### Parameters

- **query** (required): Natural language description passed as command argument
  - Examples: "authentication patterns", "async debugging tips", "database connection pooling best practices"
- **--threshold**: Similarity threshold (optional, overrides server config)
  - Default: Uses server config from `ace-cli tune show`
  - Range: 0.0 - 1.0 (higher = stricter matching)
  - Only specify if you want to override project's default
- **--allowed-domains**: Whitelist domains (comma-separated, v5.3.0+)
  - Example: `--allowed-domains auth,security` returns only patterns from those domains
  - Use when entering a new domain to get targeted patterns
- **--blocked-domains**: Blacklist domains (comma-separated, v5.3.0+)
  - Example: `--blocked-domains test,debug` excludes patterns from those domains
  - Cannot use with `--allowed-domains` (mutually exclusive)
- The search always runs with `--json` (Step 3 renders it); a raw `--json` dump is only for scripting

**Note**: To limit number of results, use `jq` for filtering:
```bash
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli search --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" "query" --json | jq '.similar_patterns[:5]'  # First 5 results
```
The `--limit` flag is not supported by ace-cli. Use `--top-k` via server config (`/ace-tune`) instead.

### Example Usage

```bash
/ace-search JWT authentication best practices
→ Calls: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli search --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" "JWT authentication best practices" --json
→ Uses: Server config threshold (e.g., 0.45)

/ace-search async test failures debugging
→ Calls: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli search --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" "async test failures debugging" --json

# Override threshold if needed:
/ace-search "JWT auth" --threshold 0.7
→ Calls: ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli search --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" "JWT auth" --threshold 0.7 --json

# Domain filtering (v5.3.0+):
/ace-search caching patterns --allowed-domains cache,performance
→ Returns ONLY patterns from cache or performance domains

/ace-search patterns --blocked-domains test,debug
→ Excludes test and debug patterns
```

### When to Use This

✅ **Use `/ace-search` when**:
- You have a specific implementation question
- You're debugging a specific type of problem
- You know what domain/topic you need help with
- You want to minimize context usage
- **After domain shift reminder**: When you see "💡 [ACE] Domain shift: X → Y", use `--allowed-domains Y` to get targeted patterns

❌ **Don't use when**:
- You need comprehensive architectural overview
- You're working on multi-domain tasks
- You want to see all patterns in a section

For those cases, use `/ace-patterns` instead.

## Output Format

`ace-cli search --json` returns `similar_patterns` (server order: `bandit_rank`), `count` and `retrieval_id`.
Step 3 prints per pattern: content, domain, section, reward (`cumulative_v15_reward`), `bandit_rank`, evidence,
and `root_cause` when it is not empty.

## Performance Impact

**Before** (full playbook):
- Retrieves: ALL patterns in section
- Token usage: ~10,000-15,000 tokens (measured via metadata)
- Time: 100-300ms

**After** (semantic search with metadata):
- Retrieves: Top 10 relevant patterns only
- Token usage: ~2,400 tokens (confirmed via metadata)
- Time: 150-400ms
- **50-92% token reduction** (exact savings shown in metadata.efficiency_gain)

**After** (semantic search without metadata):
- Token usage: ~2,000-2,200 tokens
- Time: 140-390ms (~10ms faster)
- **85-92% token reduction**

**Metadata overhead**: Adds ~5-10ms response time + ~200-400 tokens for efficiency metrics

## See Also

- `/ace-top` - Get highest-rated patterns by helpful score
- `/ace-patterns` - View full playbook (comprehensive)
- `/ace-status` - Check playbook statistics
