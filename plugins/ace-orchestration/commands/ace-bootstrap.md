---
description: Bootstrap ACE playbook from docs, git history, and/or current code
argument-hint: [--mode hybrid|both|local-files|git-history|docs-only] [--thoroughness light|medium|deep] [--commits N] [--days N]
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
- mode: Analysis mode (default: "hybrid")
  - "hybrid": RECOMMENDED - Intelligently scan docs → git history → local files with fallback
  - "both": Analyze both current files and git history (no docs scan)
  - "local-files": Analyze current codebase files only (committed or uncommitted)
  - "git-history": Analyze git commit history only (server-side)
  - "docs-only": Analyze existing documentation files only (*.md, *.txt)

- repo_path: Path to project directory (defaults to current directory)
- file_extensions: Array of file extensions to analyze (default: [".ts", ".js", ".py", ".go", ".java", ".rb", ".tsx", ".jsx"])
- max_files: Maximum files to analyze for local-files mode (default: 5000 - increased for thoroughness)
- commit_limit: Number of commits to analyze for git-history mode (default: 500 - increased for depth)
- days_back: Days of history to analyze for git-history mode (default: 90 - increased for coverage)
- merge_with_existing: true (merge) or false (replace) - default: true
- thoroughness: "light" | "medium" | "deep" (default: "medium")
  - "light": max_files=1000, commit_limit=100, days_back=30
  - "medium": max_files=5000, commit_limit=500, days_back=90
  - "deep": max_files=unlimited, commit_limit=1000, days_back=180

Examples:
{
  "mode": "hybrid",
  "thoroughness": "deep"  // RECOMMENDED: most comprehensive analysis
}

{
  "mode": "hybrid",
  "thoroughness": "medium"  // Good balance of speed and coverage
}

{
  "mode": "local-files",
  "file_extensions": [".ts", ".tsx"],
  "max_files": 5000,
  "thoroughness": "medium"
}

{
  "mode": "git-history",
  "commit_limit": 1000,
  "days_back": 180,
  "thoroughness": "deep"
}
```

## What Gets Analyzed

### Mode: hybrid (RECOMMENDED - Intelligent Multi-Source Analysis)

The **hybrid mode** uses intelligent fallback logic to extract maximum knowledge from available sources:

**Priority Order:**
1. **Check existing documentation** - Scans for CLAUDE.md, README.md, ARCHITECTURE.md, docs/*.md
2. **Analyze git history** - Extracts patterns from commits (if git repository exists)
3. **Parse local files** - Analyzes current source code files

**Intelligent Fallback Logic:**
```
IF (docs found with substantial content):
    → Extract architectural patterns, best practices, troubleshooting guides from docs
    → STILL analyze git history for bug fix patterns and refactoring insights
    → STILL scan local files for current API usage and dependencies

ELSE IF (git history available):
    → Analyze commit history for strategies, troubleshooting, API patterns
    → Scan local files for current state and dependencies

ELSE (no docs, no git):
    → Deep analysis of local files only
    → Extract patterns from code structure, imports, error handling
```

**Why Hybrid is Superior:**
- ✅ **Documentation-first**: Captures explicit team knowledge and architectural decisions
- ✅ **History-aware**: Learns from past mistakes and successful refactorings
- ✅ **Current-state**: Reflects what's actually being used right now
- ✅ **Comprehensive**: Combines all three sources for maximum coverage
- ✅ **Adaptive**: Automatically falls back based on what's available

**What Gets Extracted:**

From **Documentation** (`*.md`, `*.txt`):
- Architectural patterns and principles (→ strategies section)
- Coding standards and best practices (→ strategies section)
- Known issues and troubleshooting guides (→ troubleshooting section)
- API integration examples (→ apis section)
- Code snippets from docs (→ snippets section)

From **Git History** (commits):
- Refactoring patterns (commits with "refactor", "improve", "optimize")
- Bug fix patterns (commits with "fix", "bug", "error", "crash")
- API integration lessons (commits touching API/service/client files)
- File co-occurrence patterns (frequently changed together)
- Error resolution patterns (specific error keywords in messages)

From **Local Files** (source code):
- Current library usage and dependencies (import statements)
- Error handling patterns (try-catch, exception handling)
- Code structure and organization
- Active API integrations

**Example Output from Hybrid Mode:**
```json
{
  "mode": "HYBRID",
  "sources_analyzed": {
    "docs": {
      "files_found": 12,
      "patterns_extracted": 45
    },
    "git_history": {
      "commits_analyzed": 500,
      "patterns_extracted": 187
    },
    "local_files": {
      "files_scanned": 3421,
      "patterns_extracted": 245
    }
  },
  "total_patterns": 477,
  "by_section": {
    "strategies": 120,
    "snippets": 89,
    "troubleshooting": 178,
    "apis": 90
  }
}
```

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

### Mode: both (Current + History)

Combines **current codebase** + **git history** (without docs scanning):
- Current state (what's used NOW)
- Historical lessons (how problems were solved)
- Good when documentation is missing or sparse

**Note:** Consider using **hybrid mode** instead - it includes docs scanning AND both sources with intelligent fallback!

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

### ✅ Recommended Scenarios

**Use `hybrid` mode with `thoroughness: deep`:**
- ✅ **New project onboarding**: Extract all available knowledge (docs + history + code)
- ✅ **Team knowledge capture**: Comprehensive analysis of architectural decisions
- ✅ **Post-migration**: Understand new codebase from all angles
- ✅ **Large codebases**: Maximum pattern extraction (5000+ files, 500+ commits, 90+ days)

**Use `hybrid` mode with `thoroughness: medium`:**
- ✅ **Periodic refresh**: Re-analyze every few months for new patterns
- ✅ **Medium projects**: Balanced analysis (up to 5000 files, 500 commits, 90 days)
- ✅ **Quick comprehensive scan**: Good coverage without long processing time

**Use `local-files` mode:**
- ✅ **No git history**: Project just started or not in git repo
- ✅ **Current state only**: Only care about what's being used right now
- ✅ **Fast iteration**: Quick dependency and pattern scan

**Use `git-history` mode:**
- ✅ **Legacy understanding**: Learn from how bugs were fixed and refactorings done
- ✅ **Team patterns**: Extract lessons from multiple contributors over time
- ✅ **Architectural evolution**: Understand how system design changed

**Use `docs-only` mode:**
- ✅ **Documentation exists**: Well-documented project with CLAUDE.md, ARCHITECTURE.md, etc.
- ✅ **Quick bootstrap**: Fast startup without code analysis
- ✅ **Explicit knowledge**: Team has written good documentation already

### ❌ When NOT to Use

- **Empty repository**: Need at least ~20 commits for meaningful git-history analysis
- **No sources available**: No docs, no git, and trivial codebase (< 10 files)
- **Pre-initialized playbook**: If playbook already has 100+ quality patterns, online learning is better
- **Frequent re-bootstraps**: Don't run daily - use online learning (ace_learn) instead

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
