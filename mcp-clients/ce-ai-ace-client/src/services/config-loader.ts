/**
 * Configuration Loader
 * Loads ACE configuration from multiple sources with priority order
 */

import { readFileSync, existsSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';

export interface AceConfig {
  serverUrl: string;
  apiToken: string;
  projectId: string;
}

/**
 * Load configuration with priority:
 * 1. Environment variables (highest)
 * 2. ~/.ace/config.json
 * 3. Default values (lowest)
 */
export function loadConfig(): AceConfig {
  const config: AceConfig = {
    serverUrl: '',
    apiToken: '',
    projectId: ''
  };

  // Priority 3: Try config file
  const configPath = join(homedir(), '.ace', 'config.json');
  if (existsSync(configPath)) {
    try {
      const fileConfig = JSON.parse(readFileSync(configPath, 'utf8'));
      if (fileConfig.serverUrl) config.serverUrl = fileConfig.serverUrl;
      if (fileConfig.apiToken) config.apiToken = fileConfig.apiToken;
      if (fileConfig.projectId) config.projectId = fileConfig.projectId;

      console.error('✅ Loaded config from:', configPath);
    } catch (error) {
      console.error('⚠️  Failed to load config from:', configPath);
      console.error('   Error:', error instanceof Error ? error.message : String(error));
    }
  }

  // Priority 2: Environment variables override config file
  if (process.env.ACE_SERVER_URL) {
    config.serverUrl = process.env.ACE_SERVER_URL;
    console.error('✅ Using ACE_SERVER_URL from environment');
  }
  if (process.env.ACE_API_TOKEN) {
    config.apiToken = process.env.ACE_API_TOKEN;
    console.error('✅ Using ACE_API_TOKEN from environment');
  }
  if (process.env.ACE_PROJECT_ID) {
    config.projectId = process.env.ACE_PROJECT_ID;
    console.error('✅ Using ACE_PROJECT_ID from environment');
  }

  // Priority 1: Defaults for missing values
  if (!config.serverUrl) {
    config.serverUrl = 'http://localhost:9000';
    console.error('ℹ️  Using default server URL: http://localhost:9000');
  }

  // Validate required fields
  if (!config.apiToken) {
    console.error('');
    console.error('⚠️  WARNING: ACE_API_TOKEN not configured!');
    console.error('');
    console.error('Configure using one of these methods:');
    console.error('');
    console.error('1. Run in Claude Code: /ace-configure');
    console.error('');
    console.error('2. Set environment variables:');
    console.error('   export ACE_API_TOKEN="your-token-here"');
    console.error('   export ACE_PROJECT_ID="your-project-id"');
    console.error('');
    console.error('3. Create ~/.ace/config.json:');
    console.error('   {');
    console.error('     "serverUrl": "http://localhost:9000",');
    console.error('     "apiToken": "your-token-here",');
    console.error('     "projectId": "your-project-id"');
    console.error('   }');
    console.error('');
  }

  if (!config.projectId) {
    console.error('⚠️  WARNING: ACE_PROJECT_ID not configured!');
    console.error('   Pattern learning will use default project');
  }

  return config;
}

/**
 * Get config file path
 */
export function getConfigPath(): string {
  return join(homedir(), '.ace', 'config.json');
}

/**
 * Check if configuration is complete
 */
export function isConfigured(): boolean {
  const config = loadConfig();
  return !!(config.apiToken && config.projectId);
}
