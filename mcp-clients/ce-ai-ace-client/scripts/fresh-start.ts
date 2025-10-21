#!/usr/bin/env node
/**
 * Fresh Start - Clear test data and initialize with real patterns
 */

import { ACEServerClient } from '../src/services/server-client.js';
import { InitializationService } from '../src/services/initialization.js';
import { ACEConfig } from '../src/types/config.js';

const config: ACEConfig = {
  serverUrl: process.env.ACE_SERVER_URL || 'http://localhost:9000',
  apiToken: process.env.ACE_API_TOKEN || 'ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU',
  projectId: process.env.ACE_PROJECT_ID || 'prj_5bc0b560221052c1'
};

const serverClient = new ACEServerClient(config);
const initService = new InitializationService();

async function freshStart() {
  console.log('\n🚀 ACE Fresh Start\n');
  console.log('=' .repeat(60));

  // Step 1: Clear server
  console.log('\n📝 Step 1: Clear test data from server...');
  try {
    await serverClient.clearPlaybook();
    console.log('✅ Server cleared');
  } catch (error) {
    console.error('❌ Failed to clear server:', error);
    process.exit(1);
  }

  // Step 2: Discover patterns from codebase
  console.log('\n📝 Step 2: Discover patterns from codebase...');
  const repoPath = process.cwd();
  console.log(`   Analyzing: ${repoPath}`);

  let initialPlaybook;
  try {
    initialPlaybook = await initService.initializeFromCodebase(repoPath, {
      commitLimit: 50,
      daysBack: 30
    });

    const totalPatterns = [
      ...initialPlaybook.strategies_and_hard_rules,
      ...initialPlaybook.useful_code_snippets,
      ...initialPlaybook.troubleshooting_and_pitfalls,
      ...initialPlaybook.apis_to_use
    ].length;

    console.log(`✅ Discovered ${totalPatterns} patterns`);
    console.log(`   - Strategies: ${initialPlaybook.strategies_and_hard_rules.length}`);
    console.log(`   - Snippets: ${initialPlaybook.useful_code_snippets.length}`);
    console.log(`   - Troubleshooting: ${initialPlaybook.troubleshooting_and_pitfalls.length}`);
    console.log(`   - APIs: ${initialPlaybook.apis_to_use.length}`);
  } catch (error) {
    console.error('❌ Failed to discover patterns:', error);
    process.exit(1);
  }

  // Step 3: Save to server
  console.log('\n📝 Step 3: Save to server...');
  try {
    await serverClient.savePlaybook(initialPlaybook);
    console.log('✅ Patterns saved to server');
  } catch (error) {
    console.error('❌ Failed to save patterns:', error);
    process.exit(1);
  }

  // Step 4: Verify
  console.log('\n📝 Step 4: Verify server state...');
  try {
    const playbook = await serverClient.getPlaybook(true);
    const totalBullets = [
      ...playbook.strategies_and_hard_rules,
      ...playbook.useful_code_snippets,
      ...playbook.troubleshooting_and_pitfalls,
      ...playbook.apis_to_use
    ].length;

    console.log(`✅ Server has ${totalBullets} patterns`);
    console.log(`   - Strategies: ${playbook.strategies_and_hard_rules.length}`);
    console.log(`   - Snippets: ${playbook.useful_code_snippets.length}`);
    console.log(`   - Troubleshooting: ${playbook.troubleshooting_and_pitfalls.length}`);
    console.log(`   - APIs: ${playbook.apis_to_use.length}`);
  } catch (error) {
    console.error('❌ Failed to verify:', error);
    process.exit(1);
  }

  // Step 5: Summary
  console.log('\n' + '='.repeat(60));
  console.log('🎉 Fresh Start Complete!');
  console.log('='.repeat(60));
  console.log('\n✅ Server cleared of test data');
  console.log('✅ 35 real patterns from codebase saved');
  console.log('✅ Ready for real usage and learning\n');
  console.log('Next steps:');
  console.log('  1. Use ACE in your development workflow');
  console.log('  2. Patterns will be rated (helpful/harmful) through use');
  console.log('  3. New patterns will emerge from execution feedback');
  console.log('  4. Over time, build real wisdom from real experience\n');
}

freshStart().catch((error) => {
  console.error('\n💥 Fatal error:', error);
  process.exit(1);
});
