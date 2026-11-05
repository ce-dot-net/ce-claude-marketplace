---
description: Capture learning from completed work interactively
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(npm:*), Bash(git:*), Bash(python3:*), Read
---

# ACE Learn

Manually capture patterns and lessons learned from your recent work using Claude Code's native UI.

## Instructions for Claude

When the user runs `/ace:learn`, follow these steps:

### Step 1: Gather Information with AskUserQuestion

Use the AskUserQuestion tool to collect learning details:

```javascript
{
  questions: [
    {
      question: "What task did you just complete?",
      header: "Task",
      multiSelect: false,
      options: [
        {
          label: "Implemented new feature",
          description: "Built new functionality or component"
        },
        {
          label: "Fixed bug or issue",
          description: "Debugged and resolved a problem"
        },
        {
          label: "Refactored code",
          description: "Improved code structure or performance"
        },
        {
          label: "Integrated API/library",
          description: "Connected external service or tool"
        }
      ]
    }
  ]
}
```

Then ask for task description in "Other" field or follow-up question.

### Step 2: Ask for Success Status

```javascript
{
  questions: [
    {
      question: "Was the task successful?",
      header: "Outcome",
      multiSelect: false,
      options: [
        {
          label: "Success",
          description: "Task completed successfully"
        },
        {
          label: "Partial success",
          description: "Completed but with issues or compromises"
        },
        {
          label: "Failed",
          description: "Task failed or was abandoned"
        }
      ]
    }
  ]
}
```

### Step 3: Ask for Lessons Learned

```javascript
{
  questions: [
    {
      question: "What did you learn? (key insights, gotchas, solutions)",
      header: "Lessons",
      multiSelect: false,
      options: [
        {
          label: "Enter lessons in 'Other' field",
          description: "Describe insights, gotchas, best practices discovered"
        }
      ]
    }
  ]
}
```

User will provide detailed lessons in the "Other" text input.

### Step 4: Gather Git Context (Optional)

If in a git repository, capture git context for AI-Trail correlation (Issue #6):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Check if in a git repository
GIT_CONTEXT=""
if git rev-parse --git-dir >/dev/null 2>&1; then
  echo "📂 Gathering git context..."

  # Get current branch
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

  # Get recent commit info
  COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "")
  COMMIT_MSG=$(git log -1 --format=%s 2>/dev/null || echo "")

  # Get changed files (staged + unstaged) - a List[str] per Issue #7, one per line here
  CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD 2>/dev/null | head -20 || true)
  IN_GIT=1

  echo "   Branch: $BRANCH"
  echo "   Commit: $COMMIT_HASH"
  echo ""
fi
```

### Step 5: Call ace-cli with Flags

```bash
if ! ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --version >/dev/null 2>&1; then
  echo "❌ ACE CLI not found - Install: /ace:ace-install-cli"
  exit 1
fi

# 8.1.0: the one binding lookup (scripts/ace-context, the plugin core); never read binding files here
CTX="$("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --shell)" || exit 1
eval "$CTX"; ORG_ID="$ACE_ORG_ID"; PROJECT_ID="$ACE_PROJECT_ID"

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Run /ace:configure first"
  exit 1
fi

echo "📚 [ACE Learning] Capturing patterns from your work..."
echo ""

# Build ace-cli command based on success status
if [ "$SUCCESS_STATUS" = "Success" ]; then
  SUCCESS_FLAG="--success"
elif [ "$SUCCESS_STATUS" = "Failed" ]; then
  SUCCESS_FLAG="--failure"
else
  # Partial success - treat as success with note in output
  SUCCESS_FLAG="--success"
  LESSONS_LEARNED="Partial success: $LESSONS_LEARNED"
fi

# 8.1.1: same flags as the mod (/ace:ace-learn): ace-cli builds the complete trace itself
# (trajectory, result:{success,output}, playbook_used:[], git context auto-detected).
# A hand-built --stdin payload without those fields is rejected by the server.
CLI="${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli"
ORG_ARGS=(); [ -n "$ORG_ID" ] && ORG_ARGS=(--org "$ORG_ID")
"$CLI" --json "${ORG_ARGS[@]}" --project "$PROJECT_ID" \
  learn --task "${TASK_DESCRIPTION:0:500}" --output "$LESSONS_LEARNED" "$SUCCESS_FLAG" --no-stream

if [ $? -eq 0 ]; then
  echo "✅ Patterns captured successfully!"
  echo "   Run /ace:status to see updated playbook"
else
  echo "❌ Failed to capture patterns"
  exit 1
fi
```

## ace-cli learn Flags (ace-cli ≥ 4.0.1)

The `ace-cli learn` subcommand accepts the following flags for enriched trace correlation:

| Flag | Description |
|------|-------------|
| `--retrieval-id <uuid>` | UUID of the ACE search retrieval that preceded this task. Correlates the learn event back to the specific patterns that were retrieved, enabling the reinforcement loop. Supplied automatically by hooks (via #24/#25). |
| `--applied-log-ids <ids>` | Comma-separated list of retrieval log IDs for patterns that were actually applied during the task. Used by the Curator to reinforce those specific patterns. Supplied automatically by hooks (via #24/#25). |
| `--pin-session <sessionId>` | Recall `retrieval_id` + `applied_log_ids` from the pinned search session (the hooks use it; you rarely need it by hand). |
| `--stdin` / `--transcript <file>` | Send a complete ExecutionTrace JSON (`task`, `trajectory`, `result`, `playbook_used`); hooks use `--transcript` (stdin breaks above ~64KB). |
| `--success` / `--failure` | Mark the task outcome. |

> **Note on `task_intent`:** `task_intent` is a **search-only** flag passed to `ace-cli search`; it is
> never part of the learn payload. The server ignores a client-supplied `task_intent` by default
> (it infers intent itself), so it does not change retrieval weighting.

> **Hooks and enriched trace:** As of #24/#25, hooks automatically send enriched trace data — including `--retrieval-id` and `--applied-log-ids` — when calling `ace-cli learn` after a task completes. `ace-cli learn` accepts the same flags (`--retrieval-id`, `--applied-log-ids`, `--pin-session`) when supplied explicitly; the `/ace:ace-learn` command itself sends only `--task/--output/--success|--failure`.

## Implementation Notes for Claude

**Key Points:**
1. **Always use AskUserQuestion** for user input (Claude Code native UI)
2. **Map user selections** to appropriate values:
   - "Success" → `--success` flag
   - "Failed" → `--failure` flag
   - "Partial success" → `--success` with note in output
3. **Extract task description** from user's "Other" input or category selection
4. **Extract lessons learned** from "Other" text input
5. **Handle both org formats**: Direct (`orgId`) and env wrapper (`env.ACE_ORG_ID`)
6. **Enriched trace flags** (`--retrieval-id`, `--applied-log-ids`): pass these through when available in the session context (hooks supply them automatically; for manual `/ace:learn`, they are optional)

**Error Handling:**
- Check ace-cli is installed
- Verify project context exists
- Provide clear error messages
- Show success confirmation with next steps

## When to Use

✅ **Use /ace:learn after**:
- Implementing new features
- Debugging and fixing issues
- Discovering edge cases or gotchas
- Integrating APIs or libraries
- Making architectural decisions
- Learning something non-obvious

❌ **Skip for**:
- Trivial changes
- Simple Q&A
- Reading/exploring code only
- No new insights gained

## Example Workflow

```
User: /ace:learn

Claude: [Shows AskUserQuestion UI]
  Question 1: What task did you just complete?
  User selects: "Fixed bug or issue"
  User types in Other: "Debugged intermittent test failures in async database operations"

Claude: [Shows AskUserQuestion UI]
  Question 2: Was the task successful?
  User selects: "Success"

Claude: [Shows AskUserQuestion UI]
  Question 3: What did you learn?
  User types in Other: "Root cause was missing await on database.close() causing connection pool exhaustion. Intermittent failures in async code often indicate missing await statements. Always check async cleanup functions."

Claude runs:
  ${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli --json --org "org_xxx" --project "prj_xxx" learn \
    --task "Debugged intermittent test failures in async database operations" \
    --success \
    --output "Root cause was missing await on database.close() causing connection pool exhaustion. Intermittent failures in async code often indicate missing await statements. Always check async cleanup functions."

✅ Patterns captured successfully!
   Run /ace:status to see updated playbook
```

## What Gets Captured

The learning event sent to ACE includes:
- **Task description**: Brief summary of the work
- **Success/failure status**: Outcome of the task
- **Lessons learned**: Key insights, gotchas, solutions, best practices
- **Timestamp**: When the learning was captured
- **Project context**: Organization and project IDs
- **Git context** (if in repo - Issue #6):
  - `branch`: Current git branch name
  - `commit_hash`: Current commit SHA
  - `commit_message`: Latest commit message
  - `files_changed`: List of modified file paths (Issue #7)

The ACE server's Reflector analyzes this and the Curator updates the playbook with new patterns.

## See Also

- `/ace:status` - View playbook statistics
- `/ace:patterns` - Browse learned patterns
- `/ace:search <query>` - Find relevant patterns
- `/ace:bootstrap` - Initialize from codebase
