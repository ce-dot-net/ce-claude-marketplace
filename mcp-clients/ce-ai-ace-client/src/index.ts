#!/usr/bin/env node
/**
 * ACE MCP Client v3.2.0 - Simple HTTP Interface
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
    version: '3.2.0'
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
    description: 'Store execution trace for server-side analysis (Reflector + Curator run automatically on server)',
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
  },
  {
    name: 'ace_init',
    description: 'Initialize playbook from existing codebase (server-side offline learning from git history)',
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

      case 'ace_init': {
        const { repo_path, commit_limit, days_back, merge_with_existing } = args as {
          repo_path?: string;
          commit_limit?: number;
          days_back?: number;
          merge_with_existing?: boolean;
        };

        console.error('🚀 Requesting server-side initialization from git history...');

        try {
          // POST to server /init endpoint (server does the analysis)
          const response = await serverClient.initializeFromRepo({
            repo_path: repo_path || process.cwd(),
            commit_limit: commit_limit || 100,
            days_back: days_back || 30,
            merge_with_existing: merge_with_existing !== false
          });

          serverClient.invalidateCache();

          console.error('✅ Server initialization complete');

          return {
            content: [{
              type: 'text',
              text: JSON.stringify(response, null, 2)
            }]
          };
        } catch (error: any) {
          console.error('❌ Error during initialization:', error);
          return {
            content: [{
              type: 'text',
              text: JSON.stringify({
                success: false,
                error: error.message || 'Failed to initialize playbook'
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

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('✅ ACE MCP Client v3.2.0 started');
  console.error('🔗 Server:', config.serverUrl);
  console.error('📋 Project:', config.projectId);
  console.error('🌍 Universal MCP compatibility (no sampling required)');
}

main().catch((error) => {
  console.error('❌ Fatal error:', error);
  process.exit(1);
});
