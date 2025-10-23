---
description: Bootstrap ACE playbook from current code and/or git history
argument-hint: [--mode local-files|git-history|both] [--commits N] [--days N]
---

# ACE Bootstrap

Bootstrap ACE playbook by analyzing your current codebase files and/or git commit history.

## Instructions for Claude

When the user runs `/ace-bootstrap`, follow these steps:

1. **Call the ace_bootstrap MCP tool** with the following parameters:
   - Tool name: `mcp__ace-pattern-learning__ace_bootstrap`
   - Parameters: `mode`, `repo_path`, `file_extensions`, `max_files`, `commit_limit`, `days_back`, `merge_with_existing`

2. **If the tool is not available:**
   - Check if ACE is configured (look for .ace/config.json or environment variables)
   - Tell the user they need to run `/ace-configure` first to set up the ACE connection
   - Explain that the MCP server must be running to use ACE features

## Usage

```
Call the mcp__ace-pattern-learning__ace_bootstrap tool to bootstrap your playbook.

Parameters:
- mode: Analysis mode (default: "both")
  - "local-files": Analyze current codebase files (committed or uncommitted)
  - "git-history": Analyze git commit history (server-side)
  - "both": Analyze both current files and git history (recommended)

- repo_path: Path to project directory (defaults to current directory)
- file_extensions: Array of file extensions to analyze (default: [".ts", ".js", ".py", ".go", ".java", ".rb"])
- max_files: Maximum files to analyze for local-files mode (default: 1000)
- commit_limit: Number of commits to analyze for git-history mode (default: 100)
- days_back: Days of history to analyze for git-history mode (default: 30)
- merge_with_existing: true (merge) or false (replace) - default: true

Examples:
{
  "mode": "both"  // Recommended: analyze current files + git history
}

{
  "mode": "local-files",
  "file_extensions": [".ts", ".tsx"],
  "max_files": 500
}

{
  "mode": "git-history",
  "commit_limit": 200,
  "days_back": 60
}
```

## What Gets Analyzed

### Mode: local-files (Current Codebase)

Analyzes **current project files** (includes uncommitted/unstaged changes):

**1. Imports & Dependencies → APIs Section**
- TypeScript/JavaScript: `import X from 'Y'`, `require('Y')`
- Python: `import X`, `from X import Y`
- Discovers what libraries you're ACTUALLY using NOW
- Example: "Project uses: express, jsonwebtoken, bcrypt"

**2. Error Handling Patterns → Troubleshooting Section**
- Try-catch patterns with console.error logging
- Try-catch with error re-throwing
- Exception handling with named exceptions (Python)
- Example: "Pattern: try-catch with console.error logging"

**3. Architecture Discovery → Strategies Section** (Future)
- Class/function structure
- Module organization
- Design patterns in use

**Why This Matters:**
- ✅ **Uncommitted code** - Captures work-in-progress and prototypes
- ✅ **Current reality** - What's actually being used, not historical experiments
- ✅ **Fast** - Client-side analysis, no git operations needed

### Mode: git-history (Historical Patterns)

Analyzes **git commit history** (server-side):

**1. Strategies** (from refactorings)
- Commits with "refactor", "improve", "optimize", "clean"
- Extracts successful architectural decisions
- Example: "Pattern from refactoring: Split monolithic service into microservices"

**2. Troubleshooting** (from bug fixes)
- Commits with "fix", "bug", "error", "crash", "issue"
- Captures common pitfalls and solutions
- Example: "Common issue: Null pointer errors in user service"

**3. APIs** (from feature additions)
- Commits touching API/service/client/interface files
- Documents API usage patterns
- Example: "API pattern: Implement JWT auth for user endpoints"

**4. File Co-occurrence**
- Files that frequently change together
- Highlights coupling and dependencies
- Example: "Files that often change together: auth.ts + user.service.ts"

**5. Error Patterns**
- Specific error keywords in commit messages
- Warns about common failure modes
- Example: "Watch out for timeout errors when calling external APIs"

**Why This Matters:**
- ✅ **Problem-solving patterns** - How bugs were fixed
- ✅ **Evolution** - What changed and why
- ✅ **Team knowledge** - Lessons from multiple contributors

### Mode: both (Recommended)

Combines **current codebase** + **git history** for comprehensive analysis:
- Current state (what's used NOW)
- Historical lessons (how problems were solved)
- Most complete picture of your project

## Merge vs Replace

### Merge Mode (Default)
```json
{ "merge_with_existing": true }
```
- Combines new bullets with existing playbook
- Uses curator's grow-and-refine algorithm
- Deduplicates similar bullets (0.85 similarity threshold)
- Preserves helpful/harmful counters on existing bullets

**Use when:** You want to enrich existing playbook with historical patterns

### Replace Mode
```json
{ "merge_with_existing": false }
```
- Clears existing playbook
- Replaces with fresh analysis from git history
- Resets all helpful/harmful counters

**Use when:** Starting fresh or clearing bad patterns

## Example Output

```json
{
  "mode": "MERGE",
  "bullets_added": 42,
  "bullets_existing": 18,
  "bullets_final": 55,
  "by_section": {
    "strategies": 12,
    "snippets": 8,
    "troubleshooting": 25,
    "apis": 10
  }
}
```

## When to Use

### ✅ Good Use Cases
- **New project setup**: Bootstrap playbook from existing code
- **Team onboarding**: Share historical lessons with new members
- **Post-migration**: Capture patterns after major refactoring
- **Periodic refresh**: Re-analyze every few months for new patterns

### ❌ When NOT to Use
- **Empty repository**: Need at least ~20 commits for meaningful analysis
- **Non-git projects**: Requires git history (no other VCS supported yet)
- **Pre-initialized**: If playbook already has good patterns, online learning is better

## After Bootstrap

Once bootstrapped, ACE continues learning through **online learning**:
- Execute tasks → ACE learns from outcomes (ace_learn)
- Successful tasks → adds helpful bullets
- Failed tasks → adds troubleshooting bullets
- Counters update → helpful/harmful tracking

**Bootstrap (ace_bootstrap)** + **Online learning (ace_learn)** = Complete ACE system

## Complementary Commands

- `/ace-patterns` - View the initialized playbook
- `/ace-status` - Check statistics after initialization
- `/ace-export-patterns` - Backup before re-initialization

## Git History Requirements

**Minimum:**
- Git repository with commit history
- At least 10-20 commits

**Optimal:**
- 50+ commits over multiple weeks/months
- Descriptive commit messages
- Mix of features, refactorings, and bug fixes
- Multiple contributors (diverse patterns)

## Privacy & Security

**What gets analyzed:**
- Commit messages
- File paths
- Commit statistics (additions/deletions)

**NOT analyzed:**
- Actual file contents (unless you implement custom analysis)
- Credentials or secrets
- Private comments

**Storage:**
- Playbook stored on ACE server (configured in plugin.json)
- Project-specific (isolated by project ID)
- Multi-tenant safe (your org's patterns are private)

## See Also

- `/ace-patterns` - View playbook
- `/ace-export-patterns` - Export for backup
- `/ace-import-patterns` - Import from backup
- `/ace-clear` - Clear playbook
