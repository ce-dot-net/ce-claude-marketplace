#!/usr/bin/env node
/**
 * Interactive ACE Configuration
 * Prompts user for server URL, API token, and project ID
 * Saves to ~/.ace/config.json
 */

import { createInterface } from 'readline';
import { writeFileSync, mkdirSync, existsSync, readFileSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';

const rl = createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(prompt) {
  return new Promise((resolve) => {
    rl.question(prompt, resolve);
  });
}

async function main() {
  console.log('');
  console.log('🔧 ACE Configuration Wizard');
  console.log('============================');
  console.log('');

  const configPath = join(homedir(), '.ace', 'config.json');
  let existingConfig = {};

  // Load existing config if it exists
  if (existsSync(configPath)) {
    try {
      existingConfig = JSON.parse(readFileSync(configPath, 'utf8'));
      console.log('✅ Found existing configuration at:', configPath);
      console.log('');
    } catch (error) {
      console.log('⚠️  Could not read existing config, starting fresh');
      console.log('');
    }
  }

  // Prompt for server URL
  const defaultUrl = existingConfig.serverUrl || 'http://localhost:9000';
  const serverUrl = await question(`ACE Server URL [${defaultUrl}]: `);
  const finalServerUrl = serverUrl.trim() || defaultUrl;

  console.log('');

  // Prompt for API token
  const defaultToken = existingConfig.apiToken ? '(existing token)' : '(none)';
  console.log(`API Token ${defaultToken}:`);
  console.log('(Get from your ACE server logs or dashboard)');
  const apiToken = await question('> ');
  const finalApiToken = apiToken.trim() || existingConfig.apiToken || '';

  console.log('');

  // Prompt for project ID
  const defaultProject = existingConfig.projectId || '(none)';
  console.log(`Project ID [${defaultProject}]:`);
  console.log('(Get from your ACE server dashboard)');
  const projectId = await question('> ');
  const finalProjectId = projectId.trim() || existingConfig.projectId || '';

  console.log('');
  console.log('================================');
  console.log('📝 Configuration Summary');
  console.log('================================');
  console.log('Server URL:', finalServerUrl);
  console.log('API Token: ', finalApiToken ? finalApiToken.substring(0, 10) + '...' : 'NOT SET');
  console.log('Project ID:', finalProjectId || 'NOT SET');
  console.log('');

  const confirm = await question('Save this configuration? [Y/n]: ');

  if (confirm.toLowerCase() === 'n') {
    console.log('');
    console.log('❌ Configuration cancelled');
    rl.close();
    process.exit(0);
  }

  // Save configuration
  const config = {
    serverUrl: finalServerUrl,
    apiToken: finalApiToken,
    projectId: finalProjectId
  };

  // Ensure directory exists
  const configDir = join(homedir(), '.ace');
  if (!existsSync(configDir)) {
    mkdirSync(configDir, { recursive: true });
  }

  // Write config file
  writeFileSync(configPath, JSON.stringify(config, null, 2));

  console.log('');
  console.log('✅ Configuration saved to:', configPath);
  console.log('');

  if (!finalApiToken || !finalProjectId) {
    console.log('⚠️  WARNING: Configuration incomplete!');
    console.log('');
    if (!finalApiToken) {
      console.log('   Missing API Token - ACE server connection will fail');
    }
    if (!finalProjectId) {
      console.log('   Missing Project ID - Pattern learning will use default project');
    }
    console.log('');
    console.log('   Run /ace-configure again to complete setup');
  } else {
    console.log('🎉 Configuration complete!');
    console.log('');
    console.log('Next steps:');
    console.log('1. Restart Claude Code (Cmd+Q, then start again)');
    console.log('2. Run: /mcp');
    console.log('3. Verify ace-pattern-learning server is connected');
    console.log('4. Run: /ace-status to check connection');
  }

  console.log('');
  rl.close();
}

main().catch((error) => {
  console.error('❌ Error:', error.message);
  rl.close();
  process.exit(1);
});
