#!/usr/bin/env node
/**
 * ACE MCP Client v3.2.12 - Simple HTTP Interface
 *
 * Server-side intelligence: Reflector + Curator run on ACE server
 * Client responsibility: Send traces, retrieve playbooks
 *
 * Compatible with: Claude Code, Cursor, Cline, any MCP client
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool
} from '@modelcontextprotocol/sdk/types.js';

import { getConfig } from './types/config.js';
import { ACEServerClient } from './services/server-client.js';
import {
  ExecutionTrace,
  TrajectoryStep
} from './types/pattern.js';

// Parse command-line arguments for --config-dir
const args = process.argv.slice(2);
const configDirIndex = args.indexOf('--config-dir');
if (configDirIndex !== -1 && args[configDirIndex + 1]) {
  process.env.ACE_CONFIG_DIR = args[configDirIndex + 1];
  console.error('ℹ️  Config directory set from command line:', args[configDirIndex + 1]);
}

// Initialize
const config = getConfig();
const serverClient = new ACEServerClient(config);

// Create MCP server (NO SAMPLING - works with all MCP clients!)
const server = new Server(
  {
    name: 'ace-pattern-learning',
    version: '3.2.12'
  },
  {
    capabilities: {
      tools: {}  // Just tools, no sampling required
    }
  }
);

// Define tools
const tools: Tool[] = [
  {
    name: 'ace_save_config',
    description: 'Save ACE configuration to ~/.ace/config.json',
    inputSchema: {
      type: 'object',
      properties: {
        serverUrl: {
          type: 'string',
          description: 'ACE server URL (e.g., http://localhost:9000)'
        },
        apiToken: {
          type: 'string',
          description: 'ACE API token (e.g., ace_xxxxx)'
        },
        projectId: {
          type: 'string',
          description: 'ACE project ID (e.g., prj_xxxxx)'
        }
      },
      required: ['serverUrl', 'apiToken', 'projectId']
    }
  },
  {
    name: 'ace_learn',
    description: `Capture patterns and lessons learned from substantial coding tasks for automatic playbook improvement. Use AFTER completing:

• Problem-solving: Fixed bugs, debugged test failures, resolved build errors, troubleshot integrations
• Implementation: Implemented features, refactored code, optimized performance, updated architectures
• API Integration: Integrated external APIs, used new libraries/frameworks, configured build tools
• Failures & Recovery: Encountered errors and found solutions, discovered edge cases or gotchas
• Complex Tasks: Multi-step implementations, architectural decisions, technical problem-solving

WHEN TO USE: After completing substantial work where you learned something valuable - especially when you discovered non-obvious solutions, encountered surprising behaviors, or found better approaches after initial failures.

SKIP FOR: Simple Q&A, basic file reads, trivial edits without problem-solving, informational queries.

EXAMPLES:
- "Fixed intermittent async test failures by discovering missing await on database.close()"
- "Integrated Stripe webhooks, learned they require express.raw() for signature verification"
- "Implemented JWT auth with refresh token rotation to prevent token theft"
- "Debugged Next.js hydration error caused by server/client timestamp mismatch"

The server-side Reflector (Sonnet 4) analyzes your execution trace and extracts reusable patterns. The Curator (Haiku 4.5) creates delta updates to the playbook. This builds organizational knowledge over time.`,
    inputSchema: {
      type: 'object',
      properties: {
        task: {
          type: 'string',
          description: 'Brief description (1-2 sentences) of what was accomplished. Example: "Debugged intermittent test failures in async database operations"'
        },
        trajectory: {
          type: 'array',
          description: 'Key steps and decisions made during execution. Can be an array of strings describing: problem analysis, implementation decisions, tools/APIs used, errors encountered and resolutions, alternative approaches considered. Example: ["Observed random test failures in CI", "Suspected race condition in cleanup", "Added transaction isolation", "Tests still failed", "Discovered missing await on db.close()", "Added proper async chain"]'
        },
        success: {
          type: 'boolean',
          description: 'Whether the task ultimately succeeded (true) or failed (false). Even failed tasks provide valuable learning.'
        },
        output: {
          type: 'string',
          description: 'Detailed outcome and lessons learned. Include: root cause analysis, specific solutions, gotchas discovered, best practices, patterns to reuse. Example: "Root cause: Missing await on database.close() caused connection pool exhaustion. Insight: Intermittent failures in async code often indicate missing await. Always check async cleanup functions."'
        },
        error: {
          type: 'string',
          description: 'Error message if the task failed (optional). Include stack traces or error details that helped diagnose the issue.'
        },
        playbook_used: {
          type: 'array',
          description: 'IDs of playbook bullets that were consulted during this task (optional). Helps track which patterns were useful.',
          items: { type: 'string' }
        }
      },
      required: ['task', 'trajectory', 'success', 'output']
    }
  },
  {
    name: 'ace_get_playbook',
    description: 'Get structured ACE playbook (4 sections: strategies, snippets, troubleshooting, APIs)',
    inputSchema: {
      type: 'object',
      properties: {
        section: {
          type: 'string',
          enum: ['strategies_and_hard_rules', 'useful_code_snippets', 'troubleshooting_and_pitfalls', 'apis_to_use'],
          description: 'Filter by section (optional)'
        },
        min_helpful: {
          type: 'number',
          description: 'Minimum helpful count (optional)'
        }
      }
    }
  },
  {
    name: 'ace_status',
    description: 'Get ACE playbook statistics (total bullets, by section, top helpful/harmful)',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'ace_clear',
    description: 'Clear entire ACE playbook (requires confirmation)',
    inputSchema: {
      type: 'object',
      properties: {
        confirm: {
          type: 'boolean',
          description: 'Must be true to confirm deletion'
        }
      },
      required: ['confirm']
    }
  },
  {
    name: 'ace_bootstrap',
    description: 'Bootstrap playbook from existing codebase by analyzing current files and/or git history',
    inputSchema: {
      type: 'object',
      properties: {
        mode: {
          type: 'string',
          enum: ['local-files', 'git-history', 'both'],
          description: 'Analysis mode: local-files (current code), git-history (commits), both (default: both)'
        },
        repo_path: {
          type: 'string',
          description: 'Path to project directory (defaults to current directory)'
        },
        file_extensions: {
          type: 'array',
          items: { type: 'string' },
          description: 'File extensions to analyze (default: [".ts", ".js", ".py", ".go", ".java", ".rb"])'
        },
        max_files: {
          type: 'number',
          description: 'Maximum files to analyze for local-files mode (default: 1000)'
        },
        commit_limit: {
          type: 'number',
          description: 'Number of commits to analyze for git-history mode (default: 100)'
        },
        days_back: {
          type: 'number',
          description: 'Days of history to analyze for git-history mode (default: 30)'
        },
        merge_with_existing: {
          type: 'boolean',
          description: 'Merge with existing playbook instead of replacing (default: true)'
        }
      }
    }
  }
];

// Register handlers
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'ace_save_config': {
        const { serverUrl, apiToken, projectId } = args as {
          serverUrl: string;
          apiToken: string;
          projectId: string;
        };

        console.error('💾 Saving configuration...');

        await serverClient.saveConfig(serverUrl, apiToken, projectId);

        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              message: 'Configuration saved to ~/.ace/config.json',
              config: { serverUrl, projectId }
            }, null, 2)
          }]
        };
      }

      case 'ace_learn': {
        const { task, trajectory, success, output, error, playbook_used } = args as {
          task: string;
          trajectory: TrajectoryStep[];
          success: boolean;
          output: string;
          error?: string;
          playbook_used?: string[];
        };

        console.error('📤 Sending execution trace to server...');

        // Build execution trace
        const trace: ExecutionTrace = {
          task,
          trajectory,
          result: { success, output, error },
          playbook_used: playbook_used || [],
          timestamp: new Date().toISOString()
        };

        // Send to server - Reflector + Curator run automatically server-side
        try {
          const result = await serverClient.storeExecutionTrace(trace);

          // Invalidate playbook cache so next request gets fresh data
          serverClient.invalidateCache();

          console.error('✅ Execution trace stored. Server is analyzing...');

          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                success: true,
                message: 'Execution trace stored successfully. Server-side Reflector and Curator will process asynchronously.',
                task,
                timestamp: trace.timestamp,
                analysis_triggered: result.analysis_triggered || false
              }, null, 2)
            }]
          };
        } catch (error: any) {
          console.error('❌ Error storing trace:', error);
          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                success: false,
                error: error.message || 'Failed to store execution trace'
              }, null, 2)
            }],
            isError: true
          };
        }
      }

      case 'ace_get_playbook': {
        const { section, min_helpful } = args as {
          section?: string;
          min_helpful?: number;
        };

        console.error('📖 Fetching playbook from server...');

        let playbook = await serverClient.getPlaybook();

        // Client-side filtering if requested
        if (section) {
          playbook = {
            strategies_and_hard_rules: section === 'strategies_and_hard_rules' ? playbook.strategies_and_hard_rules : [],
            useful_code_snippets: section === 'useful_code_snippets' ? playbook.useful_code_snippets : [],
            troubleshooting_and_pitfalls: section === 'troubleshooting_and_pitfalls' ? playbook.troubleshooting_and_pitfalls : [],
            apis_to_use: section === 'apis_to_use' ? playbook.apis_to_use : []
          };
        }

        if (min_helpful !== undefined) {
          for (const key of Object.keys(playbook) as Array<keyof typeof playbook>) {
            playbook[key] = playbook[key].filter((b: any) => (b.helpful || 0) >= min_helpful);
          }
        }

        return {
          content: [{
            type: 'text',
            text: JSON.stringify(playbook, null, 2)
          }]
        };
      }

      case 'ace_status': {
        console.error('📊 Fetching status from server...');

        const status = await serverClient.getStatus();

        return {
          content: [{
            type: 'text',
            text: JSON.stringify(status, null, 2)
          }]
        };
      }

      case 'ace_clear': {
        const { confirm } = args as { confirm: boolean };

        if (!confirm) {
          throw new Error('Must set confirm=true to clear playbook');
        }

        console.error('🗑️  Clearing playbook...');

        await serverClient.clearPlaybook();
        serverClient.invalidateCache();

        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              message: 'Playbook cleared successfully'
            }, null, 2)
          }]
        };
      }

      case 'ace_bootstrap': {
        const {
          mode,
          repo_path,
          file_extensions,
          max_files,
          commit_limit,
          days_back,
          merge_with_existing
        } = args as {
          mode?: string;
          repo_path?: string;
          file_extensions?: string[];
          max_files?: number;
          commit_limit?: number;
          days_back?: number;
          merge_with_existing?: boolean;
        };

        const analysisMode = mode || 'both';
        const projectPath = repo_path || process.cwd();

        console.error(`🚀 Bootstrapping playbook (mode: ${analysisMode})...`);

        try {
          let localFileResults: any = null;
          let gitHistoryResults: any = null;

          // Mode 1: Analyze local files (current codebase)
          if (analysisMode === 'local-files' || analysisMode === 'both') {
            console.error('📂 Analyzing current codebase files...');
            localFileResults = await analyzeLocalFiles(projectPath, {
              extensions: file_extensions || ['.ts', '.js', '.py', '.go', '.java', '.rb'],
              maxFiles: max_files || 1000
            });
            console.error(`✅ Analyzed ${localFileResults.filesAnalyzed} files`);
          }

          // Mode 2: Analyze git history (server-side)
          if (analysisMode === 'git-history' || analysisMode === 'both') {
            console.error('📜 Requesting server-side git history analysis...');
            gitHistoryResults = await serverClient.initializeFromRepo({
              repo_path: projectPath,
              commit_limit: commit_limit || 100,
              days_back: days_back || 30,
              merge_with_existing: merge_with_existing !== false
            });
            console.error('✅ Git history analysis complete');
          }

          serverClient.invalidateCache();

          // Combine results
          const combinedResults = {
            mode: analysisMode,
            localFiles: localFileResults,
            gitHistory: gitHistoryResults,
            success: true
          };

          console.error('✅ Bootstrap complete');

          return {
            content: [{
              type: 'text',
              text: JSON.stringify(combinedResults, null, 2)
            }]
          };
        } catch (error: any) {
          console.error('❌ Error during bootstrap:', error);
          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                success: false,
                error: error.message || 'Failed to bootstrap playbook'
              }, null, 2)
            }],
            isError: true
          };
        }
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    console.error(`❌ Error in ${name}:`, error);
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          success: false,
          error: error.message || String(error)
        }, null, 2)
      }],
      isError: true
    };
  }
});

/**
 * Analyze local files in the project directory
 * Extracts patterns from current codebase (imports, architecture, code patterns)
 */
async function analyzeLocalFiles(
  projectPath: string,
  options: { extensions: string[]; maxFiles: number }
): Promise<any> {
  const fs = await import('fs/promises');
  const path = await import('path');

  const patterns: any[] = [];
  let filesAnalyzed = 0;
  const filesByType: Record<string, number> = {};

  // Recursively find files
  async function findFiles(dir: string): Promise<string[]> {
    const files: string[] = [];
    try {
      const entries = await fs.readdir(dir, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);

        // Skip common ignore patterns
        if (entry.name.startsWith('.') ||
            entry.name === 'node_modules' ||
            entry.name === 'dist' ||
            entry.name === 'build' ||
            entry.name === '__pycache__') {
          continue;
        }

        if (entry.isDirectory()) {
          const subFiles = await findFiles(fullPath);
          files.push(...subFiles);
        } else if (entry.isFile()) {
          const ext = path.extname(entry.name);
          if (options.extensions.includes(ext)) {
            files.push(fullPath);
          }
        }

        if (files.length >= options.maxFiles) break;
      }
    } catch (error) {
      // Skip directories we can't read
    }

    return files;
  }

  // Extract patterns from file content
  function extractPatterns(filePath: string, content: string): void {
    const ext = path.extname(filePath);
    filesByType[ext] = (filesByType[ext] || 0) + 1;

    // Extract imports/dependencies
    const imports = extractImports(content, ext);
    if (imports.length > 0) {
      patterns.push({
        section: 'apis_to_use',
        bullet: `File ${path.basename(filePath)} uses: ${imports.join(', ')}`,
        source: 'local-files',
        file: path.relative(projectPath, filePath)
      });
    }

    // Extract error handling patterns
    const errorPatterns = extractErrorPatterns(content, ext);
    if (errorPatterns) {
      patterns.push({
        section: 'troubleshooting_and_pitfalls',
        bullet: errorPatterns,
        source: 'local-files',
        file: path.relative(projectPath, filePath)
      });
    }
  }

  // Extract import statements
  function extractImports(content: string, ext: string): string[] {
    const imports: string[] = [];

    if (ext === '.ts' || ext === '.js') {
      // Match: import X from 'Y', import { X } from 'Y', require('Y')
      const importRegex = /(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))/g;
      let match;
      while ((match = importRegex.exec(content)) !== null) {
        const module = match[1] || match[2];
        if (module && !module.startsWith('.')) {
          imports.push(module);
        }
      }
    } else if (ext === '.py') {
      // Match: import X, from X import Y
      const importRegex = /(?:^|\n)\s*(?:import|from)\s+([\w.]+)/g;
      let match;
      while ((match = importRegex.exec(content)) !== null) {
        imports.push(match[1]);
      }
    }

    return [...new Set(imports)].slice(0, 10); // Unique, max 10
  }

  // Extract error handling patterns
  function extractErrorPatterns(content: string, ext: string): string | null {
    if (ext === '.ts' || ext === '.js') {
      if (content.includes('try {') && content.includes('catch')) {
        if (content.match(/catch\s*\(\s*error[^)]*\)\s*\{[^}]*console\.error/)) {
          return 'Pattern: try-catch with console.error logging';
        }
        if (content.match(/catch\s*\(\s*error[^)]*\)\s*\{[^}]*throw/)) {
          return 'Pattern: try-catch with error re-throwing';
        }
      }
    } else if (ext === '.py') {
      if (content.includes('try:') && content.includes('except')) {
        if (content.match(/except\s+\w+\s+as\s+\w+:/)) {
          return 'Pattern: try-except with named exception';
        }
      }
    }
    return null;
  }

  // Find and analyze files
  const files = await findFiles(projectPath);
  console.error(`📁 Found ${files.length} files to analyze`);

  for (const file of files.slice(0, options.maxFiles)) {
    try {
      const content = await fs.readFile(file, 'utf-8');
      extractPatterns(file, content);
      filesAnalyzed++;
    } catch (error) {
      // Skip files we can't read
    }
  }

  // Send patterns to server via ace_learn
  if (patterns.length > 0) {
    console.error(`📤 Sending ${patterns.length} patterns to server...`);

    const trace: ExecutionTrace = {
      task: `Bootstrap: Analyzed ${filesAnalyzed} local files`,
      trajectory: [
        {
          step: 1,
          action: 'scan_directory',
          args: { path: projectPath },
          result: `Found ${filesAnalyzed} files across ${Object.keys(filesByType).length} file types`
        },
        {
          step: 2,
          action: 'extract_patterns',
          args: { file_types: filesByType },
          result: `Extracted ${patterns.length} patterns (imports, error handling, etc.)`
        },
        {
          step: 3,
          action: 'send_to_server',
          args: { pattern_count: patterns.length },
          result: 'Patterns sent for server-side analysis'
        }
      ],
      result: {
        success: true,
        output: `Discovered patterns from current codebase:\n${JSON.stringify(filesByType, null, 2)}`
      },
      playbook_used: [],
      timestamp: new Date().toISOString()
    };

    await serverClient.storeExecutionTrace(trace);
  }

  return {
    filesAnalyzed,
    filesByType,
    patternsExtracted: patterns.length,
    patterns: patterns.slice(0, 20) // Return sample
  };
}

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('✅ ACE MCP Client v3.2.12 started');
  console.error('🔗 Server:', config.serverUrl);
  console.error('📋 Project:', config.projectId);
  console.error('🌍 Universal MCP compatibility (no sampling required)');
}

main().catch((error) => {
  console.error('❌ Fatal error:', error);
  process.exit(1);
});
