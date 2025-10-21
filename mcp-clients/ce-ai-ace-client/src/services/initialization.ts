/**
 * InitializationService - Offline learning from existing codebase
 *
 * Implements ACE Paper Section 4.1: Offline Adaptation
 * Analyzes git history and existing code to build initial playbook
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { PlaybookBullet, BulletSection, StructuredPlaybook } from '../types/pattern.js';

const execAsync = promisify(exec);

export interface InitOptions {
  /**
   * Number of recent commits to analyze
   * @default 100
   */
  commitLimit?: number;

  /**
   * Days of history to analyze
   * @default 30
   */
  daysBack?: number;

  /**
   * File patterns to analyze (glob patterns)
   * @default ['*.ts', '*.js', '*.py', '*.java']
   */
  filePatterns?: string[];

  /**
   * Skip commits with these patterns in message
   * @default ['merge', 'wip', 'temp']
   */
  skipPatterns?: string[];
}

interface CommitAnalysis {
  hash: string;
  message: string;
  author: string;
  date: string;
  files: string[];
  additions: number;
  deletions: number;
}

interface CodePattern {
  section: BulletSection;
  content: string;
  confidence: number;
  evidence: string[];
}

export class InitializationService {
  /**
   * Initialize playbook from existing codebase
   *
   * HYBRID APPROACH (robust and practical):
   * 1. If git exists → analyze commit history (refactorings, bug fixes)
   * 2. ALWAYS analyze local files → imports, APIs, patterns
   * 3. Combine both sources → comprehensive playbook
   *
   * Works with or without git (pragmatic extension of ACE paper)
   */
  async initializeFromCodebase(
    repoPath: string,
    options: InitOptions = {}
  ): Promise<StructuredPlaybook> {
    const {
      commitLimit = 100,
      daysBack = 30,
      filePatterns = ['*.ts', '*.js', '*.py', '*.java', '*.go'],
      skipPatterns = ['merge', 'wip', 'temp', 'revert']
    } = options;

    console.error('📚 Analyzing codebase for offline initialization...');
    console.error(`   Repo: ${repoPath}`);

    const allPatterns: CodePattern[] = [];

    // 1. Try git analysis (optional, bonus if available)
    const hasGit = await this.hasGitRepo(repoPath);
    if (hasGit) {
      console.error(`   Git repo detected - analyzing commits (${commitLimit} max, ${daysBack} days)`);
      const commits = await this.analyzeGitHistory(
        repoPath,
        commitLimit,
        daysBack,
        skipPatterns
      );
      console.error(`   Found ${commits.length} relevant commits`);

      const gitPatterns = await this.extractPatternsFromCommits(commits);
      console.error(`   Extracted ${gitPatterns.length} patterns from git history`);
      allPatterns.push(...gitPatterns);
    } else {
      console.error('   No git repo - skipping commit analysis');
    }

    // 2. ALWAYS analyze local files (primary, robust)
    console.error('   Analyzing local source files...');
    const sourcePatterns = await this.analyzeSourceFiles(repoPath, filePatterns);
    console.error(`   Extracted ${sourcePatterns.length} patterns from source files`);
    allPatterns.push(...sourcePatterns);

    // 3. Build structured playbook from combined sources
    console.error(`   Total patterns discovered: ${allPatterns.length}`);
    const playbook = this.buildInitialPlaybook(allPatterns);

    console.error('✅ Offline initialization complete');
    return playbook;
  }

  /**
   * Check if directory has git repository
   */
  private async hasGitRepo(repoPath: string): Promise<boolean> {
    try {
      await execAsync(`git -C "${repoPath}" rev-parse --git-dir`, {
        timeout: 5000
      });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Analyze git history to extract meaningful commits
   */
  private async analyzeGitHistory(
    repoPath: string,
    limit: number,
    daysBack: number,
    skipPatterns: string[]
  ): Promise<CommitAnalysis[]> {
    const sinceDate = new Date();
    sinceDate.setDate(sinceDate.getDate() - daysBack);
    const since = sinceDate.toISOString().split('T')[0];

    try {
      // Get commit log with stats
      const { stdout } = await execAsync(
        `git -C "${repoPath}" log --since="${since}" --pretty=format:"%H|%s|%an|%ai" --numstat -n ${limit}`,
        { maxBuffer: 10 * 1024 * 1024 } // 10MB buffer
      );

      const lines = stdout.split('\n');
      const commits: CommitAnalysis[] = [];
      let currentCommit: Partial<CommitAnalysis> | null = null;

      for (const line of lines) {
        if (!line.trim()) {
          if (currentCommit && currentCommit.hash) {
            commits.push(currentCommit as CommitAnalysis);
          }
          currentCommit = null;
          continue;
        }

        // Commit header: hash|message|author|date
        if (line.includes('|')) {
          const [hash, message, author, date] = line.split('|');

          // Skip commits with skip patterns
          if (skipPatterns.some(p => message.toLowerCase().includes(p))) {
            currentCommit = null;
            continue;
          }

          currentCommit = {
            hash,
            message,
            author,
            date,
            files: [],
            additions: 0,
            deletions: 0
          };
        }
        // File stat: additions deletions filename
        else if (currentCommit) {
          const [additions, deletions, filename] = line.split('\t');
          if (filename) {
            currentCommit.files!.push(filename);
            currentCommit.additions! += parseInt(additions) || 0;
            currentCommit.deletions! += parseInt(deletions) || 0;
          }
        }
      }

      return commits;
    } catch (error) {
      console.error('⚠️  Git analysis failed (not a git repo?), using empty history');
      return [];
    }
  }

  /**
   * Analyze local source files for patterns
   *
   * Discovers:
   * - Import patterns (what libraries are used)
   * - API patterns (endpoints, database queries)
   * - Config patterns (package.json, tsconfig.json)
   * - Architectural patterns (classes, functions, async usage)
   */
  private async analyzeSourceFiles(
    repoPath: string,
    patterns: string[]
  ): Promise<CodePattern[]> {
    const fs = await import('fs/promises');
    const path = await import('path');
    const discoveredPatterns: CodePattern[] = [];

    try {
      // Read package.json for dependencies (TypeScript/JavaScript)
      const packageJsonPath = path.join(repoPath, 'package.json');
      try {
        const packageJson = JSON.parse(await fs.readFile(packageJsonPath, 'utf-8'));
        const allDeps = {
          ...packageJson.dependencies,
          ...packageJson.devDependencies
        };

        // Top dependencies used in project
        const topDeps = Object.keys(allDeps).slice(0, 10);
        for (const dep of topDeps) {
          discoveredPatterns.push({
            section: 'apis_to_use',
            content: `Project uses ${dep} (${allDeps[dep]})`,
            confidence: 0.9,
            evidence: ['package.json']
          });
        }

        // Framework detection
        if (allDeps['react']) {
          discoveredPatterns.push({
            section: 'strategies_and_hard_rules',
            content: 'React framework - use functional components with hooks',
            confidence: 0.85,
            evidence: ['package.json']
          });
        }
        if (allDeps['express'] || allDeps['fastify']) {
          discoveredPatterns.push({
            section: 'strategies_and_hard_rules',
            content: 'Node.js backend - use async/await for all routes',
            confidence: 0.85,
            evidence: ['package.json']
          });
        }
      } catch {
        // No package.json or parse error
      }

      // Read requirements.txt for dependencies (Python)
      const requirementsPath = path.join(repoPath, 'requirements.txt');
      try {
        const requirements = await fs.readFile(requirementsPath, 'utf-8');
        const deps = requirements.split('\n').filter(line => line.trim() && !line.startsWith('#'));

        for (const dep of deps.slice(0, 10)) {
          const pkgName = dep.split('==')[0].split('>=')[0].trim();
          discoveredPatterns.push({
            section: 'apis_to_use',
            content: `Python project uses ${pkgName}`,
            confidence: 0.9,
            evidence: ['requirements.txt']
          });
        }
      } catch {
        // No requirements.txt
      }

      // Scan for common patterns in source files
      const sourceFiles = await this.findSourceFiles(repoPath, patterns);
      const sampleFiles = sourceFiles.slice(0, 20); // Sample first 20 files

      for (const filePath of sampleFiles) {
        try {
          const content = await fs.readFile(filePath, 'utf-8');
          const relativePath = path.relative(repoPath, filePath);

          // Detect import patterns
          const imports = this.extractImports(content, filePath);
          for (const imp of imports.slice(0, 5)) {
            discoveredPatterns.push({
              section: 'useful_code_snippets',
              content: `Common import: ${imp}`,
              confidence: 0.7,
              evidence: [relativePath]
            });
          }

          // Detect API/endpoint patterns
          if (content.includes('app.get(') || content.includes('app.post(')) {
            discoveredPatterns.push({
              section: 'apis_to_use',
              content: `REST API endpoints defined in ${relativePath}`,
              confidence: 0.8,
              evidence: [relativePath]
            });
          }

          // Detect database patterns
          if (content.includes('prisma') || content.includes('mongoose') || content.includes('typeorm')) {
            discoveredPatterns.push({
              section: 'strategies_and_hard_rules',
              content: 'Uses ORM for database access - define models before queries',
              confidence: 0.75,
              evidence: [relativePath]
            });
          }

          // Detect async patterns
          if (content.includes('async ') && content.includes('await ')) {
            discoveredPatterns.push({
              section: 'strategies_and_hard_rules',
              content: 'Codebase uses async/await - ensure all async functions are awaited',
              confidence: 0.8,
              evidence: [relativePath]
            });
          }

        } catch {
          // Skip files that can't be read
        }
      }

    } catch (error) {
      console.error('⚠️  Source file analysis failed:', error);
    }

    return discoveredPatterns;
  }

  /**
   * Find source files matching patterns
   */
  private async findSourceFiles(
    repoPath: string,
    patterns: string[]
  ): Promise<string[]> {
    const fs = await import('fs/promises');
    const path = await import('path');
    const files: string[] = [];

    async function scanDir(dir: string, depth: number = 0): Promise<void> {
      if (depth > 5) return; // Max depth

      try {
        const entries = await fs.readdir(dir, { withFileTypes: true });

        for (const entry of entries) {
          // Skip node_modules, .git, dist, build
          if (['node_modules', '.git', 'dist', 'build', '.next', 'target'].includes(entry.name)) {
            continue;
          }

          const fullPath = path.join(dir, entry.name);

          if (entry.isDirectory()) {
            await scanDir(fullPath, depth + 1);
          } else if (entry.isFile()) {
            // Check if matches patterns
            const ext = path.extname(entry.name);
            if (['.ts', '.js', '.tsx', '.jsx', '.py', '.java', '.go', '.rs'].includes(ext)) {
              files.push(fullPath);
            }
          }
        }
      } catch {
        // Skip directories we can't read
      }
    }

    await scanDir(repoPath);
    return files;
  }

  /**
   * Extract import statements from source code
   */
  private extractImports(content: string, filePath: string): string[] {
    const imports: string[] = [];

    // TypeScript/JavaScript imports
    const jsImportRegex = /import\s+.*?\s+from\s+['"]([^'"]+)['"]/g;
    let match;
    while ((match = jsImportRegex.exec(content)) !== null) {
      imports.push(match[1]);
    }

    // Python imports
    const pyImportRegex = /^(?:from\s+(\S+)\s+)?import\s+(.+)$/gm;
    while ((match = pyImportRegex.exec(content)) !== null) {
      imports.push(match[1] || match[2].split(',')[0].trim());
    }

    return imports;
  }

  /**
   * Extract patterns from commit analysis
   */
  private async extractPatternsFromCommits(
    commits: CommitAnalysis[]
  ): Promise<CodePattern[]> {
    const patterns: CodePattern[] = [];

    // 1. STRATEGIES from successful refactorings
    const refactoringCommits = commits.filter(c =>
      /refactor|improve|optimize|clean/i.test(c.message)
    );
    for (const commit of refactoringCommits.slice(0, 10)) {
      patterns.push({
        section: 'strategies_and_hard_rules',
        content: `Pattern from refactoring: ${commit.message}`,
        confidence: 0.7,
        evidence: [commit.hash, ...commit.files.slice(0, 3)]
      });
    }

    // 2. TROUBLESHOOTING from bug fixes
    const bugFixCommits = commits.filter(c =>
      /fix|bug|error|crash|issue/i.test(c.message)
    );
    for (const commit of bugFixCommits.slice(0, 15)) {
      patterns.push({
        section: 'troubleshooting_and_pitfalls',
        content: `Common issue: ${commit.message}`,
        confidence: 0.8,
        evidence: [commit.hash, ...commit.files.slice(0, 3)]
      });
    }

    // 3. APIS from feature additions
    const featureCommits = commits.filter(c =>
      /add|implement|create|new/i.test(c.message) &&
      !/(test|doc|comment)/i.test(c.message)
    );
    for (const commit of featureCommits.slice(0, 10)) {
      if (commit.files.some(f => /api|service|client|interface/i.test(f))) {
        patterns.push({
          section: 'apis_to_use',
          content: `API pattern: ${commit.message}`,
          confidence: 0.6,
          evidence: [commit.hash, ...commit.files.slice(0, 3)]
        });
      }
    }

    // 4. FILE CHANGE PATTERNS - Files that change together
    const fileCoOccurrence = this.analyzeFileCoOccurrence(commits);
    for (const [fileSet, count] of fileCoOccurrence.slice(0, 5)) {
      if (count >= 3) {
        patterns.push({
          section: 'strategies_and_hard_rules',
          content: `Files that often change together: ${fileSet}`,
          confidence: Math.min(0.9, count / 10),
          evidence: [`Co-occurred ${count} times`]
        });
      }
    }

    // 5. COMMON ERROR PATTERNS
    const errorPatterns = this.extractErrorPatterns(commits);
    patterns.push(...errorPatterns);

    return patterns;
  }

  /**
   * Find files that frequently change together
   */
  private analyzeFileCoOccurrence(
    commits: CommitAnalysis[]
  ): [string, number][] {
    const coOccurrence = new Map<string, number>();

    for (const commit of commits) {
      if (commit.files.length >= 2 && commit.files.length <= 5) {
        // Sort files to create consistent key
        const fileSet = commit.files.sort().join(' + ');
        coOccurrence.set(fileSet, (coOccurrence.get(fileSet) || 0) + 1);
      }
    }

    return Array.from(coOccurrence.entries())
      .sort((a, b) => b[1] - a[1]);
  }

  /**
   * Extract error patterns from commit messages
   */
  private extractErrorPatterns(commits: CommitAnalysis[]): CodePattern[] {
    const patterns: CodePattern[] = [];
    const errorKeywords = [
      'null pointer',
      'undefined',
      'not found',
      'timeout',
      'permission denied',
      'connection refused',
      'out of memory',
      'race condition',
      'deadlock'
    ];

    for (const commit of commits) {
      const messageLower = commit.message.toLowerCase();
      for (const keyword of errorKeywords) {
        if (messageLower.includes(keyword)) {
          patterns.push({
            section: 'troubleshooting_and_pitfalls',
            content: `Watch out for ${keyword} errors: ${commit.message}`,
            confidence: 0.75,
            evidence: [commit.hash, ...commit.files.slice(0, 2)]
          });
        }
      }
    }

    return patterns;
  }

  /**
   * Build initial playbook from extracted patterns
   */
  private buildInitialPlaybook(patterns: CodePattern[]): StructuredPlaybook {
    const playbook: StructuredPlaybook = {
      strategies_and_hard_rules: [],
      useful_code_snippets: [],
      troubleshooting_and_pitfalls: [],
      apis_to_use: []
    };

    // Group patterns by section and deduplicate
    const seenContent = new Set<string>();

    for (const pattern of patterns) {
      // Skip duplicates
      const contentKey = pattern.content.toLowerCase().substring(0, 50);
      if (seenContent.has(contentKey)) continue;
      seenContent.add(contentKey);

      // Create bullet
      const bullet: PlaybookBullet = {
        id: this.generateBulletId(),
        section: pattern.section,
        content: pattern.content,
        helpful: 0,  // Will be updated during online learning
        harmful: 0,
        confidence: pattern.confidence,
        evidence: pattern.evidence,
        observations: 0,
        created_at: new Date().toISOString(),
        last_used: new Date().toISOString()
      };

      playbook[pattern.section].push(bullet);
    }

    return playbook;
  }

  /**
   * Generate bullet ID: ctx-{timestamp}-{random}
   */
  private generateBulletId(): string {
    const timestamp = Math.floor(Date.now() / 1000);
    const random = Math.random().toString(36).substring(2, 7);
    return `ctx-${timestamp}-${random}`;
  }
}
