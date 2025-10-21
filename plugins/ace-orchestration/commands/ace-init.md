---
description: Initialize ACE playbook from existing codebase (offline learning)
argument-hint: [--commits N] [--days N] [--merge|--replace]
allowed-tools: mcp__ace-pattern-learning__ace_init
---

# ACE Init

Initialize ACE playbook by analyzing your existing codebase's git history (offline learning).

## Usage

```
Use the mcp__ace-pattern-learning__ace_init tool to bootstrap your playbook.

Parameters:
- repo_path: Path to git repository (defaults to current directory)
- commit_limit: Number of commits to analyze (default: 100)
- days_back: Days of history to analyze (default: 30)
- merge_with_existing: true (merge) or false (replace) - default: true

Example:
{
  "commit_limit": 100,
  "days_back": 30,
  "merge_with_existing": true
}
```

## What Gets Analyzed

ACE analyzes your git history to discover patterns:

### 1. **Strategies** (from refactorings)
- Commits with "refactor", "improve", "optimize", "clean"
- Extracts successful architectural decisions
- Example: "Pattern from refactoring: Split monolithic service into microservices"

### 2. **Troubleshooting** (from bug fixes)
- Commits with "fix", "bug", "error", "crash", "issue"
- Captures common pitfalls and solutions
- Example: "Common issue: Null pointer errors in user service"

### 3. **APIs** (from feature additions)
- Commits touching API/service/client/interface files
- Documents API usage patterns
- Example: "API pattern: Implement JWT auth for user endpoints"

### 4. **File Co-occurrence**
- Files that frequently change together
- Highlights coupling and dependencies
- Example: "Files that often change together: auth.ts + user.service.ts"

### 5. **Error Patterns**
- Specific error keywords in commit messages
- Warns about common failure modes
- Example: "Watch out for timeout errors when calling external APIs"

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

## After Initialization

Once initialized, ACE continues learning through **online learning**:
- Execute tasks → ACE learns from outcomes (ace_learn)
- Successful tasks → adds helpful bullets
- Failed tasks → adds troubleshooting bullets
- Counters update → helpful/harmful tracking

**Offline initialization (ace_init)** + **Online learning (ace_learn)** = Complete ACE system

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
