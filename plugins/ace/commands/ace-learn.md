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

### Step 4: Call ce-ace CLI with Flags

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ce-dot-net/ce-ace-cli"
  exit 1
fi

# Read context from .claude/settings.json
ORG_ID=$(jq -r '.orgId // empty' .claude/settings.json 2>/dev/null || echo "")
PROJECT_ID=$(jq -r '.projectId // empty' .claude/settings.json 2>/dev/null || echo "")

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

# Build ce-ace command based on success status
if [ "$SUCCESS_STATUS" = "Success" ]; then
  SUCCESS_FLAG="--success"
elif [ "$SUCCESS_STATUS" = "Failed" ]; then
  SUCCESS_FLAG="--failure"
else
  # Partial success - treat as success with note in output
  SUCCESS_FLAG="--success"
  LESSONS_LEARNED="Partial success: $LESSONS_LEARNED"
fi

# Call ce-ace learn with flags
if [ -n "$ORG_ID" ]; then
  ce-ace --json --org "$ORG_ID" --project "$PROJECT_ID" \
    learn \
    --task "$TASK_DESCRIPTION" \
    $SUCCESS_FLAG \
    --output "$LESSONS_LEARNED"
else
  # Single-org mode (no --org flag)
  ce-ace --json --project "$PROJECT_ID" \
    learn \
    --task "$TASK_DESCRIPTION" \
    $SUCCESS_FLAG \
    --output "$LESSONS_LEARNED"
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
- Check ce-ace is installed
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
  ce-ace --json --org "org_xxx" --project "prj_xxx" learn \
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

The ACE server's Reflector analyzes this and the Curator updates the playbook with new patterns.

## See Also

- `/ace:status` - View playbook statistics
- `/ace:patterns` - Browse learned patterns
- `/ace:search <query>` - Find relevant patterns
- `/ace:bootstrap` - Initialize from codebase
