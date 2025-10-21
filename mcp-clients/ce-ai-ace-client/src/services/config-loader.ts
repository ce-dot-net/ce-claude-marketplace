/**
 * Configuration Loader
 * Loads ACE configuration from multiple sources with priority order:
 * 1. Environment variables (highest)
 * 2. ./.ace/config.json (project-local)
 * 3. ~/.ace/config.json (global fallback)
 * 4. Default values (lowest)
 */

import { readFileSync, existsSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';
import { execSync } from 'child_process';

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

  // Priority 4: Try global config file (fallback)
  const globalConfigPath = join(homedir(), '.ace', 'config.json');
  if (existsSync(globalConfigPath)) {
    try {
      const fileConfig = JSON.parse(readFileSync(globalConfigPath, 'utf8'));
      if (fileConfig.serverUrl) config.serverUrl = fileConfig.serverUrl;
      if (fileConfig.apiToken) config.apiToken = fileConfig.apiToken;
      if (fileConfig.projectId) config.projectId = fileConfig.projectId;

      console.error('✅ Loaded global config from:', globalConfigPath);
    } catch (error) {
      console.error('⚠️  Failed to load global config from:', globalConfigPath);
      console.error('   Error:', error instanceof Error ? error.message : String(error));
    }
  }

  // Priority 3: Try project-local config file (overrides global)
  let projectRoot: string;

  // First check if ACE_CONFIG_DIR environment variable is set
  if (process.env.ACE_CONFIG_DIR) {
    projectRoot = process.env.ACE_CONFIG_DIR;
    console.error('ℹ️  Using project root from ACE_CONFIG_DIR:', projectRoot);
  } else {
    // Try current working directory first (where user is working)
    const cwdConfigPath = join(process.cwd(), '.ace', 'config.json');
    if (existsSync(cwdConfigPath)) {
      projectRoot = process.cwd();
      console.error('ℹ️  Using current working directory as project root:', projectRoot);
    } else {
      // Otherwise try git to find project root
      try {
        projectRoot = execSync('git rev-parse --show-toplevel', { encoding: 'utf8' }).trim();
      } catch (error) {
        // Not in a git repo, use current working directory anyway
        projectRoot = process.cwd();
      }
    }
  }

  const projectConfigPath = join(projectRoot, '.ace', 'config.json');
  if (existsSync(projectConfigPath)) {
    try {
      const fileConfig = JSON.parse(readFileSync(projectConfigPath, 'utf8'));
      if (fileConfig.serverUrl) config.serverUrl = fileConfig.serverUrl;
      if (fileConfig.apiToken) config.apiToken = fileConfig.apiToken;
      if (fileConfig.projectId) config.projectId = fileConfig.projectId;

      console.error('✅ Loaded project config from:', projectConfigPath);
    } catch (error) {
      console.error('⚠️  Failed to load project config from:', projectConfigPath);
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
    console.error('3. Create ./.ace/config.json (project-local):');
    console.error('   {');
    console.error('     "serverUrl": "http://localhost:9000",');
    console.error('     "apiToken": "your-token-here",');
    console.error('     "projectId": "your-project-id"');
    console.error('   }');
    console.error('');
    console.error('4. Or create ~/.ace/config.json (global fallback)');
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
