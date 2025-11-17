# MCP Client Implementation Requirements

**IMPORTANT**: ACE is **project-scoped only**. There is NO global `~/.ace/config.json`. Each project must have its own `.ace/config.json` in the project root.

## Updated Bootstrap Features (v3.2.15+)

The plugin documentation (`commands/ace-bootstrap.md`) has been updated with new features that need to be implemented in the `@ce-dot-net/ace-client` MCP client.

### 1. New Bootstrap Mode: `hybrid` (PRIORITY)

**Current implementation:**
- Modes: `local-files`, `git-history`, `both`
- No documentation scanning
- Simple combination logic

**Required implementation:**
```typescript
interface BootstrapParams {
  mode: 'hybrid' | 'both' | 'local-files' | 'git-history' | 'docs-only';
  thoroughness?: 'light' | 'medium' | 'deep';
  // ... existing params
}
```

**Hybrid mode logic:**
```typescript
async function bootstrapHybrid(params: BootstrapParams) {
  const results = {
    docs: { files: [], patterns: [] },
    gitHistory: { commits: [], patterns: [] },
    localFiles: { files: [], patterns: [] }
  };

  // Step 1: Scan for documentation
  const docFiles = await findDocs(['CLAUDE.md', 'README.md', 'ARCHITECTURE.md', 'docs/**/*.md']);
  if (docFiles.length > 0) {
    results.docs = await extractPatternsFromDocs(docFiles);
  }

  // Step 2: Analyze git history (if available)
  if (await isGitRepo()) {
    results.gitHistory = await extractPatternsFromGit(params.commit_limit, params.days_back);
  }

  // Step 3: Scan local files
  results.localFiles = await extractPatternsFromFiles(params.max_files, params.file_extensions);

  // Step 4: Merge and upload to server
  const allPatterns = mergePatterns([results.docs.patterns, results.gitHistory.patterns, results.localFiles.patterns]);
  await uploadToServer(allPatterns);

  return {
    mode: 'HYBRID',
    sources_analyzed: {
      docs: { files_found: docFiles.length, patterns_extracted: results.docs.patterns.length },
      git_history: { commits_analyzed: results.gitHistory.commits.length, patterns_extracted: results.gitHistory.patterns.length },
      local_files: { files_scanned: results.localFiles.files.length, patterns_extracted: results.localFiles.patterns.length }
    },
    total_patterns: allPatterns.length
  };
}
```

### 2. Thoroughness Parameter

**Required implementation:**
```typescript
const THOROUGHNESS_PRESETS = {
  light: {
    max_files: 1000,
    commit_limit: 100,
    days_back: 30
  },
  medium: {
    max_files: 5000,
    commit_limit: 500,
    days_back: 90
  },
  deep: {
    max_files: -1, // unlimited
    commit_limit: 1000,
    days_back: 180
  }
};

function applyThoroughness(params: BootstrapParams): BootstrapParams {
  if (params.thoroughness) {
    const preset = THOROUGHNESS_PRESETS[params.thoroughness];
    return {
      ...params,
      max_files: params.max_files ?? preset.max_files,
      commit_limit: params.commit_limit ?? preset.commit_limit,
      days_back: params.days_back ?? preset.days_back
    };
  }
  return params;
}
```

### 3. Documentation Pattern Extraction

**New function needed:**
```typescript
async function extractPatternsFromDocs(docFiles: string[]): Promise<Pattern[]> {
  const patterns: Pattern[] = [];

  for (const file of docFiles) {
    const content = await readFile(file);

    // Extract sections that look like:
    // - "Best Practices", "Coding Standards" → strategies
    // - "Troubleshooting", "Common Issues", "Known Bugs" → troubleshooting
    // - "API Integration", "Libraries Used" → apis
    // - Code blocks with context → snippets

    // Use LLM or regex to extract structured patterns from markdown
    const extracted = await parseMarkdownForPatterns(content, file);
    patterns.push(...extracted);
  }

  return patterns;
}

async function parseMarkdownForPatterns(content: string, filename: string): Promise<Pattern[]> {
  // Implementation ideas:
  // 1. Use Haiku 4.5 to extract patterns from markdown (cost-effective)
  // 2. Parse markdown structure to identify relevant sections
  // 3. Extract code blocks with surrounding context
  // 4. Identify best practices, warnings, troubleshooting tips

  // Could use prompts like:
  // "Extract coding best practices, architectural patterns, known issues,
  //  and API integration guidance from this documentation file..."
}
```

### 4. Updated Default Values

**Current defaults:**
```typescript
max_files: 1000
commit_limit: 100
days_back: 30
```

**New defaults (medium thoroughness):**
```typescript
max_files: 5000
commit_limit: 500
days_back: 90
file_extensions: [".ts", ".js", ".py", ".go", ".java", ".rb", ".tsx", ".jsx"]
```

### 5. Docs-Only Mode

**New mode implementation:**
```typescript
async function bootstrapDocsOnly(params: BootstrapParams) {
  const docFiles = await findDocs([
    'CLAUDE.md',
    'README.md',
    'ARCHITECTURE.md',
    'docs/**/*.md',
    'docs/**/*.txt',
    '*.md' // All root-level markdown files
  ]);

  const patterns = await extractPatternsFromDocs(docFiles);
  await uploadToServer(patterns);

  return {
    mode: 'DOCS_ONLY',
    files_analyzed: docFiles.length,
    patterns_extracted: patterns.length
  };
}
```

## Bug Fix Required: Upload to Server

**CRITICAL ISSUE:** Bootstrap extracts patterns but doesn't upload them to the server.

**Current behavior (BUG):**
```typescript
async function ace_bootstrap(params: BootstrapParams) {
  const patterns = await extractPatterns(); // ✅ Works (477 patterns found)

  // ❌ MISSING OR FAILING:
  // await uploadToServer(patterns);

  return { patterns_extracted: patterns.length };
}
```

**Required fix:**
```typescript
async function ace_bootstrap(params: BootstrapParams) {
  const patterns = await extractPatterns();

  console.log(`Extracted ${patterns.length} patterns`);
  console.log('Uploading to ACE server...');

  // MUST call the server endpoint
  const response = await this.client.post('/api/playbook/bootstrap', {
    projectId: this.config.projectId,
    patterns: patterns,
    mode: params.mode,
    merge_with_existing: params.merge_with_existing ?? true
  });

  if (!response.ok) {
    throw new Error(`Bootstrap upload failed: ${response.statusText}`);
  }

  console.log('✅ Upload complete');

  return response.json();
}
```

## Priority Order for Implementation

1. **HIGH PRIORITY**: Fix upload bug (patterns not reaching server)
2. **HIGH PRIORITY**: Implement `thoroughness` parameter (easy win, big UX improvement)
3. **MEDIUM PRIORITY**: Implement `hybrid` mode with docs scanning
4. **MEDIUM PRIORITY**: Update default values (5000 files, 500 commits, 90 days)
5. **LOW PRIORITY**: Implement `docs-only` mode

## Testing Checklist

- [ ] Bootstrap with `mode: "hybrid"` extracts from all three sources
- [ ] Bootstrap with `thoroughness: "deep"` processes more files/commits
- [ ] Patterns actually upload to server (verify server receives them)
- [ ] `/ace-status` shows patterns after bootstrap completes
- [ ] `/ace-patterns` displays bootstrapped patterns correctly
- [ ] Documentation scanning finds CLAUDE.md, README.md, docs/*.md
- [ ] Fallback logic works (tries docs → git → local files)
- [ ] Error handling for missing sources (no docs, no git, etc.)

## Related Files in MCP Client Repository

```
@ce-dot-net/ace-client/
├── src/
│   ├── tools/
│   │   └── ace_bootstrap.ts         ← Main implementation
│   ├── services/
│   │   ├── pattern-extractor.ts     ← Pattern extraction logic
│   │   ├── docs-parser.ts           ← NEW: Documentation parsing
│   │   └── git-analyzer.ts          ← Git history analysis
│   └── client/
│       └── ace-client.ts            ← HTTP client (uploadToServer)
└── package.json
```

## Notes

- The plugin documentation has been updated to reflect these features
- Users will see the new options in `/ace-bootstrap --help`
- **Until MCP client implements these features, they won't work!**
- Consider this a specification document for the MCP client team

---

**Updated:** 2025-10-28
**Plugin Version:** 3.2.14 (docs updated)
**Required MCP Client Version:** 3.2.15+ (to implement these features)
