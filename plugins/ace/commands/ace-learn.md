---
description: Capture learning from completed work interactively
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

  # Get changed files (staged + unstaged) - returns List[str] per Issue #7
  CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD 2>/dev/null | head -20 | jq -R -s -c 'split("\n") | map(select(length > 0))' || echo "[]")

  # Build git context JSON
  GIT_CONTEXT=$(jq -n \
    --arg branch "$BRANCH" \
    --arg commit "$COMMIT_HASH" \
    --arg message "$COMMIT_MSG" \
    --argjson files "$CHANGED_FILES" \
    '{branch: $branch, commit_hash: $commit, commit_message: $message, files_changed: $files}')

  echo "   Branch: $BRANCH"
  echo "   Commit: $COMMIT_HASH"
  echo ""
fi
```

### Step 5: Call ace-cli with Flags

```bash
if ! command -v ace-cli >/dev/null 2>&1; then
  echo "❌ ace-cli not found - Install: npm install -g @ace-sdk/cli"
  exit 1
fi

# Read context from .claude/settings.json
ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

# Also try env wrapper format
if [ -z "$ORG_ID" ] || [ -z "$PROJECT_ID" ]; then
  ORG_ID=$(jq -r '.env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
  PROJECT_ID=$(jq -r '.env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")
fi

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

# Build JSON payload for --stdin (includes optional git context)
LEARN_PAYLOAD=$(jq -n \
  --arg task "$TASK_DESCRIPTION" \
  --arg output "$LESSONS_LEARNED" \
  --argjson success "$([ "$SUCCESS_FLAG" = "--success" ] && echo true || echo false)" \
  --argjson git "${GIT_CONTEXT:-null}" \
  '{task: $task, output: $output, success: $success, git: $git}')

# Call ace-cli learn with --stdin for richer payload
if [ -n "$ORG_ID" ]; then
  echo "$LEARN_PAYLOAD" | ace-cli --json --org "$ORG_ID" --project "$PROJECT_ID" \
    learn --stdin
else
  # Single-org mode (no --org flag)
  echo "$LEARN_PAYLOAD" | ace-cli --json --project "$PROJECT_ID" \
    learn --stdin
fi

if [ $? -eq 0 ]; then
  echo "✅ Patterns captured successfully!"
  echo "   Run /ace:status to see updated playbook"
else
  echo "❌ Failed to capture patterns"
  exit 1
fi
```

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
  ace-cli --json --org "org_xxx" --project "prj_xxx" learn \
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
