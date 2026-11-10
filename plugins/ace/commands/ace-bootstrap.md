---
disable-model-invocation: true
description: Bootstrap ACE playbook from docs, git history, and/or current code
argument-hint: "[mode] [level] | --mode hybrid|both|local-files|git-history|docs-only --thoroughness light|medium|deep [--commit-limit N] [--days-back N] [--max-files N] | --backfill-only [--sources session,git,merge] [--limit N] [--days-back N] [--target-project prj_x --target-org org_x] [--approved]"
context: fork
effort: high
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-context:*), Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli:*), Bash(npm:*), Bash(find:*), Bash(wc:*), Read
---

# ACE Bootstrap

Bootstrap ACE playbook by analyzing your current codebase files and/or git commit history.

## Instructions for Claude

When user runs `/ace-bootstrap` (where mods run, the ACE mod answers it with a preview and a confirm button instead), run:

```bash
#!/usr/bin/env bash
set -euo pipefail

CTX="$("${CLAUDE_PLUGIN_ROOT}/scripts/ace-context" --shell)" || exit 1  # 8.1.0: the one binding lookup
eval "$CTX"
# Only what the user gave is passed; without --mode/--thoroughness the CLI uses the server's defaults.
ARGS=(); [ -n "${1:-}" ] && ARGS+=(--mode "$1"); [ -n "${2:-}" ] && ARGS+=(--thoroughness "$2")
echo "Bootstrapping ACE playbook (${ARGS[*]:-server defaults})..."
"${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli" bootstrap --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" "${ARGS[@]}"
```

**Data Flow**:
```
/ace-bootstrap command
    ↓
ace-cli
    ↓
ACE Server: Reflector analyzes code
    ↓
ace-cli: returns results
    ↓
Command: calls ace-cli status for final counts
    ↓
Command: generates dynamic report for user
```

Where mods run, the ACE mod answers the command itself (no model): it shows a short preview (files by type, commits in the
window, docs found, current playbook size, what leaves the machine) and a confirm button; after the run it prints ONE result line
(patterns extracted, after dedup, time; "keine Patterns gefunden" for zero).

**Arguments** (both forms work, mixed too):
- positional: `/ace:ace-bootstrap [mode] [level]`, e.g. `docs-only light`
- flags: `/ace:ace-bootstrap --mode docs-only --thoroughness light --commit-limit 200 --days-back 60 --max-files 100`
  (`--commit-limit`, `--days-back`, `--max-files` are positive integers and go to the CLI as given)
- nothing given: `--mode`/`--thoroughness` are NOT passed, the CLI uses the server's defaults ("Standard des Servers" in the preview)

**`--approved`** (terminals without a button, e.g. Moshi/herdr): the preview prints the exact line to copy, the same line plus
` --approved` runs the action at once, like the button. A standalone `--approved` token at the end, at the start or next to another
`--flag` counts; inside a text it is just text. `clear` and `cleanup` (destructive) run with `--approved` only when the identical
preview is already waiting. `--approved` is not allowed for bind, clean, login and install.

## Backfill (8.2.0, `--backfill-only`)

```
/ace:ace-bootstrap --backfill-only [--sources session,git,merge] [--limit N] [--days-back N]
                   [--target-project prj_x --target-org org_x] [--approved]
```

Turns Claude Code session transcripts, fix/revert commits and merged PRs into redacted learning traces and sends them to the
server's backfill endpoint in batches of up to 20. Since 8.2.1 the default is hybrid (`session,git,merge`): the limit is shared
round-robin across the sources that have new tasks (each ranked internally: success, then decisive steps, then newest), so one
source never crowds out another; a source with fewer tasks hands its share to the others. Session items were noisier in the
pilots, so a noise filter drops failed lookups and tasks without real work. `--sources` narrows the set (e.g.
`--sources git,merge`). `--limit` is 1..100 (default 100); `--days-back` sets the window; `--target-project`/`--target-org`
send into another project than the bound one. `--sources` and `--target-project` are refused without `--backfill-only`.

- **Server support:** only if the server announces `bootstrap_backfill: true` in the search response (the flag is cached for
  7 days). Otherwise the preview says the server does not support it yet and nothing is sent.
- **Preview is mandatory** (button, or `--approved`).
- **Processing:** the server works through about 5 items per minute in the background. The plugin polls every 60 s with a timer
  chain that lives as long as the Claude Code session: a closed session stops polling, a rerun resumes through the ledger.
  Items the server already knew (duplicates, also inside a mixed batch) are ledgered as sent and reported as "N Aufgaben
  waren dem Server bereits bekannt", so they never take a slot again.
- **Limits:** 500 items per org per UTC day (a 429 stops the run and remembers the resume time); items stuck for 7 days expire.
- **Token:** the plugin never holds one; `engine/backfill.js` sends through the core client.
- **State:** HMAC-signed ledger per target project under the plugin data dir; local log `backfill-log.jsonl` (responses, source
  per key, no content).

Privacy of the backfill: only redacted titles, file names and redacted texts leave the machine. No source code, no diffs,
no docs; author and committer are never read; git texts are labelled "(untrusted text)".

## Usage

Use `${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli bootstrap --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID"` to initialize your playbook from the codebase.

**Basic usage**:
```bash
# CLI reads org/project from environment variables or config automatically
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli bootstrap --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" --json
```

**With options**:
```bash
# Hybrid mode (recommended) - docs → git → files
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli bootstrap --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" --json --mode hybrid --thoroughness deep

# Git history only
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli bootstrap --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" --json --mode git-history --commit-limit 1000 --days-back 180

# Local files only
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli bootstrap --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" --json --mode local-files --max-files 5000

# Docs only
${CLAUDE_PLUGIN_ROOT}/scripts/ace-cli bootstrap --org "$ACE_ORG_ID" --project "$ACE_PROJECT_ID" --json --mode docs-only
```

**Parameters**:
- `--mode <mode>` - Analysis mode (default: the server's, usually "hybrid")
  - `hybrid`: RECOMMENDED - Intelligently scan docs → git history → local files
  - `both`: Analyze current files + git history (no docs)
  - `local-files`: Current codebase files only
  - `git-history`: Git commit history only
  - `docs-only`: Documentation files only (*.md, *.txt)

- `--thoroughness <level>` - Analysis depth (default: the server's, usually "medium")
  - `light`: commit_limit=100, days_back=30
  - `medium`: commit_limit=500, days_back=90
  - `deep`: commit_limit=1000, days_back=180
  - The code sample is capped at the first 50 source files in every level, so the three levels differ only in the git history window.

- `--repo-path <path>` - Path to repository (default: current directory)
- `--max-files <number>` - Maximum files to analyze (overrides thoroughness)
- `--commit-limit <number>` - Max commits to analyze (overrides thoroughness)
- `--days-back <number>` - Days of history to analyze (overrides thoroughness)
- `--merge` - Merge with existing playbook (default: true)

**Examples**:
```bash
# RECOMMENDED: Most comprehensive analysis
/ace:ace-bootstrap --mode hybrid --thoroughness deep

# Good balance of speed and coverage
/ace:ace-bootstrap --mode hybrid --thoroughness medium

# Quick local files scan
/ace:ace-bootstrap --mode local-files --thoroughness light

# Deep git history analysis
/ace:ace-bootstrap --mode git-history --thoroughness deep
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

## Integration with ACE Agent Skills (v3.2.36)

**NEW in v3.2.36**: ACE skills now trigger on 35+ action keywords with intent-based fallback!

After bootstrapping your initial playbook, ACE's Agent Skills will automatically use these patterns during your work. The skills trigger on:

**8 Trigger Categories (35+ keywords):**
- **Implementation**: implement, build, create, add, develop, write
- **Modification**: update, modify, change, edit, enhance, extend, revise
- **Debugging**: debug, fix, troubleshoot, resolve, diagnose
- **Refactoring**: refactor, optimize, improve, restructure
- **Integration**: integrate, connect, setup, configure, install
- **Architecture**: architect, design, plan
- **Testing**: test, verify, validate
- **Operations**: deploy, migrate, upgrade

**Intent-based fallback**: Even without exact keywords, skills trigger when requests clearly intend to write/modify code, solve technical problems, make architectural decisions, or perform substantial technical work.

**How it works:**
1. **Playbook Retrieval Skill**: Before tasks (auto-invokes when trigger keywords detected)
2. **Playbook Learning Skill**: After tasks (auto-invokes after substantial work)
3. **Bootstrap command**: Provides initial patterns for skills to retrieve

**Result**: Bootstrap gives you a strong foundation, then skills automatically retrieve and expand patterns as you work!

## After Bootstrap

Once bootstrapped, ACE continues learning through **online learning**:
- Execute tasks → ACE learns from outcomes (ace_learn)
- Successful tasks → adds helpful bullets
- Failed tasks → adds troubleshooting bullets
- Counters update → helpful/harmful tracking

**Bootstrap (ace_bootstrap)** + **Online learning (ace_learn)** = Complete ACE system

## Next Steps

**After bootstrap completes:**

1. **Verify patterns loaded:**
   - Run `/ace:status` to see playbook statistics
   - Should show bullets distributed across 4 sections

2. **Review learned patterns:**
   - Run `/ace:patterns` to view what was discovered
   - Check strategies, snippets, troubleshooting, and API patterns

3. **Start coding:**
   - ACE will now retrieve these patterns before tasks
   - Automatic learning will add new patterns as you work

4. **Optional - Export backup:**
   - Run `/ace:export-patterns` to save initial playbook state
   - Useful for team sharing or restoration

## Complementary Commands

- `/ace:patterns` - View the initialized playbook
- `/ace:status` - Check statistics after initialization
- `/ace:export-patterns` - Backup before re-initialization

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

**Backfill mode (`--backfill-only`)** is the narrow path: see "Backfill" above, only redacted titles, file names and texts leave.

**Legacy bootstrap (without `--backfill-only`)**, what leaves your machine (the CLI sends text blocks to the ACE server; verified in the CLI source, no redaction is applied; modes hybrid/both/local-files/git-history/docs-only):
- `hybrid`, `both`, `local-files`: the **function bodies** of the first 50 source files, up to 20 docs (CLAUDE.md, README.md, docs/*.md) and the commit messages and **diffs** of the git window, **unredacted**
- `docs-only`: up to 20 docs, no source code
- `git-history`: commit messages and diffs, no source files

The preview says this before anything is sent. Do not run a code mode on a repository whose code or history must not leave the machine;
`docs-only` is the narrow choice (it still sends the docs, so keep secrets out of them).

**Storage:**
- Playbook stored on ACE server (configured in plugin.json)
- Project-specific (isolated by project ID)
- Multi-tenant safe (your org's patterns are private)

## See Also

- `/ace-patterns` - View playbook
- `/ace-export-patterns` - Export for backup
- `/ace-import-patterns` - Import from backup
- `/ace-clear` - Clear playbook
