#!/usr/bin/env node
/**
 * Code Engine ACE - TypeScript MCP Client
 *
 * Three-Agent Architecture:
 * - Generator: Main agent (Claude Code) that executes tasks
 * - Reflector: Analyzes execution outcomes and generates delta operations
 * - Curator: Applies delta operations and performs grow-and-refine
 *
 * Intelligent pattern learning and code generation for AI assistants
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
import { ReflectorService } from './services/reflector.js';
import { CurationService } from './services/curator.js';
import { InitializationService } from './services/initialization.js';
import {
  ExecutionTrace,
  TrajectoryStep,
  StructuredPlaybook,
  BulletSection,
  PlaybookBullet
} from './types/pattern.js';

// Initialize services
const config = getConfig();
const serverClient = new ACEServerClient(config);
const reflectorService = new ReflectorService();
const curationService = new CurationService(serverClient, config);
const initializationService = new InitializationService();

// Create MCP server
const server = new Server(
  {
    name: 'ace-pattern-learning',
    version: '1.0.0'
  },
  {
    capabilities: {
      tools: {},
      sampling: {}  // IMPORTANT: Enable MCP Sampling for Reflector
    }
  }
);

// Define tools
const tools: Tool[] = [
  {
    name: 'ace_save_config',
    description: 'Save ACE configuration to ~/.ace/config.json (used by /ace-configure command)',
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
    name: 'ace_init',
    description: 'Initialize playbook from existing codebase (offline learning from git history)',
    inputSchema: {
      type: 'object',
      properties: {
        repo_path: {
          type: 'string',
          description: 'Path to git repository (defaults to current directory)'
        },
        commit_limit: {
          type: 'number',
          description: 'Number of commits to analyze (default: 100)'
        },
        days_back: {
          type: 'number',
          description: 'Days of history to analyze (default: 30)'
        },
        merge_with_existing: {
          type: 'boolean',
          description: 'Merge with existing playbook instead of replacing (default: true)'
        }
      }
    }
  },
  {
    name: 'ace_learn',
    description: 'Learn from execution feedback (core ACE methodology: Generator → Reflector → Curator)',
    inputSchema: {
      type: 'object',
      properties: {
        task: {
          type: 'string',
          description: 'Task that was executed'
        },
        trajectory: {
          type: 'array',
          description: 'Execution trajectory (array of {step, action, args, result})'
        },
        success: {
          type: 'boolean',
          description: 'Whether execution succeeded'
        },
        output: {
          type: 'string',
          description: 'Execution output'
        },
        error: {
          type: 'string',
          description: 'Error message if failed (optional)'
        },
        playbook_used: {
          type: 'array',
          description: 'Bullet IDs that were consulted (optional)',
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
  }
];

// Handle tool list
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools
}));

// Handle tool calls
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

        // Import needed modules
        const { writeFileSync, mkdirSync, existsSync } = await import('fs');
        const { homedir } = await import('os');
        const { join } = await import('path');

        // Create config directory
        const configDir = join(homedir(), '.ace');
        if (!existsSync(configDir)) {
          mkdirSync(configDir, { recursive: true });
        }

        // Write config file
        const configPath = join(configDir, 'config.json');
        const config = {
          serverUrl,
          apiToken,
          projectId
        };
        writeFileSync(configPath, JSON.stringify(config, null, 2));

        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({
                success: true,
                message: `✅ Configuration saved to: ${configPath}`,
                config: {
                  serverUrl,
                  apiToken: apiToken.substring(0, 10) + '...',
                  projectId
                }
              }, null, 2)
            }
          ]
        };
      }

      case 'ace_init': {
        const { repo_path, commit_limit, days_back, merge_with_existing } = args as {
          repo_path?: string;
          commit_limit?: number;
          days_back?: number;
          merge_with_existing?: boolean;
        };

        const repoPath = repo_path || process.cwd();
        const mergeMode = merge_with_existing !== false; // Default true

        console.error('🔄 Initializing playbook from codebase...');
        console.error(`   Mode: ${mergeMode ? 'MERGE' : 'REPLACE'}`);

        // Analyze codebase to generate initial playbook
        const initialPlaybook = await initializationService.initializeFromCodebase(
          repoPath,
          {
            commitLimit: commit_limit,
            daysBack: days_back
          }
        );

        if (mergeMode) {
          // Merge with existing playbook using curator
          const currentPlaybook = await serverClient.getPlaybook();

          // Flatten both playbooks
          const currentBullets = [
            ...currentPlaybook.strategies_and_hard_rules,
            ...currentPlaybook.useful_code_snippets,
            ...currentPlaybook.troubleshooting_and_pitfalls,
            ...currentPlaybook.apis_to_use
          ];

          const newBullets = [
            ...initialPlaybook.strategies_and_hard_rules,
            ...initialPlaybook.useful_code_snippets,
            ...initialPlaybook.troubleshooting_and_pitfalls,
            ...initialPlaybook.apis_to_use
          ];

          console.error(`   Merging ${newBullets.length} new bullets with ${currentBullets.length} existing`);

          // Combine and deduplicate using curator's grow-and-refine
          const combined: StructuredPlaybook = {
            strategies_and_hard_rules: [
              ...currentPlaybook.strategies_and_hard_rules,
              ...initialPlaybook.strategies_and_hard_rules
            ],
            useful_code_snippets: [
              ...currentPlaybook.useful_code_snippets,
              ...initialPlaybook.useful_code_snippets
            ],
            troubleshooting_and_pitfalls: [
              ...currentPlaybook.troubleshooting_and_pitfalls,
              ...initialPlaybook.troubleshooting_and_pitfalls
            ],
            apis_to_use: [
              ...currentPlaybook.apis_to_use,
              ...initialPlaybook.apis_to_use
            ]
          };

          // Apply grow-and-refine to deduplicate
          const merged = await curationService['growAndRefine'](combined);
          await serverClient.savePlaybook(merged);

          // Invalidate cache
          serverClient.invalidateCache();

          const finalCount = Object.values(merged).flat().length;
          console.error(`✅ Merged playbook: ${finalCount} total bullets`);

          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                mode: 'MERGE',
                bullets_added: newBullets.length,
                bullets_existing: currentBullets.length,
                bullets_final: finalCount,
                by_section: {
                  strategies: merged.strategies_and_hard_rules.length,
                  snippets: merged.useful_code_snippets.length,
                  troubleshooting: merged.troubleshooting_and_pitfalls.length,
                  apis: merged.apis_to_use.length
                }
              }, null, 2)
            }]
          };
        } else {
          // Replace existing playbook
          await serverClient.savePlaybook(initialPlaybook);

          // Invalidate cache
          serverClient.invalidateCache();

          const totalBullets = Object.values(initialPlaybook).flat().length;
          console.error(`✅ Playbook initialized: ${totalBullets} bullets`);

          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                mode: 'REPLACE',
                total_bullets: totalBullets,
                by_section: {
                  strategies: initialPlaybook.strategies_and_hard_rules.length,
                  snippets: initialPlaybook.useful_code_snippets.length,
                  troubleshooting: initialPlaybook.troubleshooting_and_pitfalls.length,
                  apis: initialPlaybook.apis_to_use.length
                }
              }, null, 2)
            }]
          };
        }
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

        // Build execution trace
        const trace: ExecutionTrace = {
          task,
          trajectory,
          result: { success, output, error },
          playbook_used: playbook_used || [],
          timestamp: new Date().toISOString()
        };

        // 1. Get current playbook from server
        const currentPlaybook = await serverClient.getPlaybook();

        // Flatten playbook for reflector
        const allBullets: PlaybookBullet[] = [
          ...currentPlaybook.strategies_and_hard_rules,
          ...currentPlaybook.useful_code_snippets,
          ...currentPlaybook.troubleshooting_and_pitfalls,
          ...currentPlaybook.apis_to_use
        ];

        // 2. REFLECTOR: Analyze execution outcome
        console.error('🔍 Reflector analyzing execution...');
        const reflection = await reflectorService.analyzeExecution(
          trace,
          allBullets,
          async (messages) => {
            return await server.request({
              method: 'sampling/createMessage',
              params: {
                messages,
                maxTokens: 4000,
                temperature: 0.7
              }
            } as any, {} as any);
          }
        );

        // 3. Optional: Iterative refinement
        console.error('✨ Refining reflection...');
        const refined = await reflectorService.refineReflection(
          reflection,
          trace,
          async (messages) => {
            return await server.request({
              method: 'sampling/createMessage',
              params: {
                messages,
                maxTokens: 2000,
                temperature: 0.7
              }
            } as any, {} as any);
          },
          2  // 2 refinement iterations
        );

        // 4. CURATOR: Apply delta operations
        console.error('📝 Curator applying delta operations...');
        const updatedPlaybook = await curationService.applyDeltaOperations(
          currentPlaybook,
          refined
        );

        // 5. Save to server
        await serverClient.savePlaybook(updatedPlaybook);

        // 6. Invalidate cache (force refresh on next call)
        serverClient.invalidateCache();

        console.error('✅ Playbook updated');

        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              operations_applied: refined.operations.length,
              summary: refined.summary,
              playbook_bullets: Object.values(updatedPlaybook).flat().length,
              by_section: {
                strategies: updatedPlaybook.strategies_and_hard_rules.length,
                snippets: updatedPlaybook.useful_code_snippets.length,
                troubleshooting: updatedPlaybook.troubleshooting_and_pitfalls.length,
                apis: updatedPlaybook.apis_to_use.length
              }
            }, null, 2)
          }]
        };
      }

      case 'ace_get_playbook': {
        const { section, min_helpful } = args as {
          section?: BulletSection;
          min_helpful?: number;
        };

        const playbook = await serverClient.getPlaybook();

        // Filter by section if specified
        let bullets: PlaybookBullet[];
        if (section) {
          bullets = playbook[section];
        } else {
          bullets = [
            ...playbook.strategies_and_hard_rules,
            ...playbook.useful_code_snippets,
            ...playbook.troubleshooting_and_pitfalls,
            ...playbook.apis_to_use
          ];
        }

        // Filter by helpful count
        if (min_helpful !== undefined) {
          bullets = bullets.filter(b => b.helpful >= min_helpful);
        }

        // Generate markdown playbook
        const markdown = generatePlaybookMarkdown(playbook, section);

        return {
          content: [{
            type: 'text',
            text: markdown
          }]
        };
      }

      case 'ace_status': {
        const playbook = await serverClient.getPlaybook();

        const allBullets = [
          ...playbook.strategies_and_hard_rules,
          ...playbook.useful_code_snippets,
          ...playbook.troubleshooting_and_pitfalls,
          ...playbook.apis_to_use
        ];

        // Top helpful bullets
        const topHelpful = [...allBullets]
          .sort((a, b) => b.helpful - a.helpful)
          .slice(0, 5)
          .map(b => ({
            id: b.id,
            section: b.section,
            content: b.content.substring(0, 100),
            helpful: b.helpful,
            harmful: b.harmful,
            confidence: b.confidence
          }));

        // Top harmful bullets
        const topHarmful = [...allBullets]
          .sort((a, b) => b.harmful - a.harmful)
          .slice(0, 5)
          .map(b => ({
            id: b.id,
            section: b.section,
            content: b.content.substring(0, 100),
            helpful: b.helpful,
            harmful: b.harmful
          }));

        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              total_bullets: allBullets.length,
              by_section: {
                strategies_and_hard_rules: playbook.strategies_and_hard_rules.length,
                useful_code_snippets: playbook.useful_code_snippets.length,
                troubleshooting_and_pitfalls: playbook.troubleshooting_and_pitfalls.length,
                apis_to_use: playbook.apis_to_use.length
              },
              avg_confidence: allBullets.length > 0
                ? allBullets.reduce((sum, b) => sum + b.confidence, 0) / allBullets.length
                : 0,
              top_helpful: topHelpful,
              top_harmful: topHarmful
            }, null, 2)
          }]
        };
      }

      case 'ace_clear': {
        const { confirm } = args as { confirm: boolean };

        if (!confirm) {
          throw new Error('Must set confirm=true to clear playbook');
        }

        await serverClient.clearPlaybook();

        return {
          content: [{
            type: 'text',
            text: '✅ ACE playbook cleared'
          }]
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    return {
      content: [{
        type: 'text',
        text: `❌ Error: ${errorMessage}`
      }],
      isError: true
    };
  }
});

// Generate playbook markdown
function generatePlaybookMarkdown(
  playbook: StructuredPlaybook,
  filterSection?: BulletSection
): string {
  let markdown = '# ACE Playbook\n\n';

  const sections: BulletSection[] = filterSection
    ? [filterSection]
    : ['strategies_and_hard_rules', 'useful_code_snippets', 'troubleshooting_and_pitfalls', 'apis_to_use'];

  for (const section of sections) {
    const bullets = playbook[section];

    if (bullets.length === 0) continue;

    // Section header
    const sectionTitle = section
      .split('_')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');

    markdown += `## ${sectionTitle}\n\n`;

    // Sort by helpful count
    const sorted = [...bullets].sort((a, b) => b.helpful - a.helpful);

    for (const bullet of sorted) {
      markdown += `### [${bullet.id}] (✅ ${bullet.helpful} | ❌ ${bullet.harmful} | ${(bullet.confidence * 100).toFixed(0)}%)\n\n`;
      markdown += `${bullet.content}\n\n`;

      if (bullet.evidence.length > 0) {
        markdown += `**Evidence**: ${bullet.evidence.slice(0, 3).join(', ')}\n\n`;
      }

      markdown += `---\n\n`;
    }
  }

  return markdown;
}

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Log to stderr (stdout is for MCP protocol)
  console.error('🚀 Code Engine ACE - MCP Client v3.1.0');
  console.error('   Server: ', config.serverUrl);
  console.error('   Architecture: Generator → Reflector → Curator');
  console.error('   Thresholds: 0.85 similarity, 0.30 confidence');
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
