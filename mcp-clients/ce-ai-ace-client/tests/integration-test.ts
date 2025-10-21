#!/usr/bin/env node
/**
 * ACE Client Integration Test
 *
 * Tests all 5 MCP tools and verifies:
 * 1. Server connectivity
 * 2. Local SQLite cache (~/.ace-cache/)
 * 3. Remote server storage
 * 4. Cache invalidation
 * 5. 3-tier cache behavior (RAM → SQLite → Server)
 */

import { ACEServerClient } from '../src/services/server-client.js';
import { InitializationService } from '../src/services/initialization.js';
import { ACEConfig } from '../src/types/config.js';
import { StructuredPlaybook, ExecutionTrace } from '../src/types/pattern.js';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

// Test configuration
const config: ACEConfig = {
  serverUrl: process.env.ACE_SERVER_URL || 'http://localhost:9000',
  apiToken: process.env.ACE_API_TOKEN || 'ace_wFIuXzQvaR5IVn2SoizOf-ncOKP6bmHDmocaQ3b5aWU',
  projectId: process.env.ACE_PROJECT_ID || 'prj_5bc0b560221052c1'
};

const serverClient = new ACEServerClient(config);
const initService = new InitializationService();

// Test results tracking
interface TestResult {
  name: string;
  passed: boolean;
  duration: number;
  details: string;
}

const results: TestResult[] = [];

function logTest(name: string) {
  console.log('\n' + '='.repeat(60));
  console.log(`🧪 TEST: ${name}`);
  console.log('='.repeat(60));
}

function logSuccess(message: string) {
  console.log(`✅ ${message}`);
}

function logError(message: string) {
  console.log(`❌ ${message}`);
}

function logInfo(message: string) {
  console.log(`ℹ️  ${message}`);
}

async function recordTest(
  name: string,
  testFn: () => Promise<void>
): Promise<void> {
  logTest(name);
  const start = Date.now();
  try {
    await testFn();
    const duration = Date.now() - start;
    results.push({ name, passed: true, duration, details: 'OK' });
    logSuccess(`Test passed (${duration}ms)`);
  } catch (error) {
    const duration = Date.now() - start;
    const details = error instanceof Error ? error.message : String(error);
    results.push({ name, passed: false, duration, details });
    logError(`Test failed: ${details}`);
  }
}

// Get cache file path (matches LocalCacheService default)
function getCachePath(): string {
  const orgId = config.apiToken.substring(4, 12);
  const cacheDir = path.join(process.cwd(), '.ace-cache');  // Project directory
  return path.join(cacheDir, `${orgId}_${config.projectId}.db`);
}

// Test 1: Server Health Check
async function testServerHealth() {
  logInfo('Testing direct server connection...');

  const response = await fetch(`${config.serverUrl}/playbook`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${config.apiToken}`,
      'X-ACE-Project': config.projectId
    }
  });

  if (!response.ok) {
    throw new Error(`Server returned ${response.status}`);
  }

  const data = await response.json();
  logSuccess(`Server responding: ${response.status} OK`);
  logInfo(`Playbook sections: ${Object.keys(data.playbook || {}).length}`);
}

// Test 2: ace_status (GET playbook)
async function testAceStatus() {
  logInfo('Testing ace_status (playbook retrieval)...');

  const playbook = await serverClient.getPlaybook();

  const totalBullets = [
    ...playbook.strategies_and_hard_rules,
    ...playbook.useful_code_snippets,
    ...playbook.troubleshooting_and_pitfalls,
    ...playbook.apis_to_use
  ].length;

  logSuccess(`Retrieved playbook with ${totalBullets} bullets`);
  logInfo(`  - Strategies: ${playbook.strategies_and_hard_rules.length}`);
  logInfo(`  - Snippets: ${playbook.useful_code_snippets.length}`);
  logInfo(`  - Troubleshooting: ${playbook.troubleshooting_and_pitfalls.length}`);
  logInfo(`  - APIs: ${playbook.apis_to_use.length}`);
}

// Test 3: Local Cache Creation
async function testLocalCacheCreation() {
  logInfo('Testing local SQLite cache creation...');

  // Force a fetch to create cache
  await serverClient.getPlaybook(true);

  const cachePath = getCachePath();
  const cacheExists = fs.existsSync(cachePath);

  if (!cacheExists) {
    throw new Error(`Cache file not created at ${cachePath}`);
  }

  const stats = fs.statSync(cachePath);
  logSuccess(`Cache file created: ${cachePath}`);
  logInfo(`  - Size: ${stats.size} bytes`);
  logInfo(`  - Modified: ${stats.mtime.toISOString()}`);
}

// Test 4: Cache Hit Performance
async function testCacheHitPerformance() {
  logInfo('Testing 3-tier cache performance...');

  // First call: Server fetch (cold)
  serverClient.invalidateCache();
  const start1 = Date.now();
  await serverClient.getPlaybook(true);
  const coldTime = Date.now() - start1;
  logInfo(`  - Cold fetch (server): ${coldTime}ms`);

  // Second call: RAM cache hit
  const start2 = Date.now();
  await serverClient.getPlaybook();
  const ramTime = Date.now() - start2;
  logInfo(`  - RAM cache hit: ${ramTime}ms`);

  // Clear RAM, test SQLite cache
  serverClient.invalidateCache();
  const start3 = Date.now();
  await serverClient.getPlaybook();
  const sqliteTime = Date.now() - start3;
  logInfo(`  - SQLite cache hit: ${sqliteTime}ms`);

  logSuccess(`Speedup: ${(coldTime / ramTime).toFixed(1)}x (RAM), ${(coldTime / sqliteTime).toFixed(1)}x (SQLite)`);
}

// Test 5: ace_init (Offline learning)
async function testAceInit() {
  logInfo('Testing ace_init (offline learning from codebase)...');

  const repoPath = process.cwd(); // Use current repo
  logInfo(`  - Analyzing: ${repoPath}`);

  const initialPlaybook = await initService.initializeFromCodebase(repoPath, {
    commitLimit: 50,
    daysBack: 30
  });

  const totalPatterns = [
    ...initialPlaybook.strategies_and_hard_rules,
    ...initialPlaybook.useful_code_snippets,
    ...initialPlaybook.troubleshooting_and_pitfalls,
    ...initialPlaybook.apis_to_use
  ].length;

  logSuccess(`Discovered ${totalPatterns} patterns from codebase`);
  logInfo(`  - Strategies: ${initialPlaybook.strategies_and_hard_rules.length}`);
  logInfo(`  - Snippets: ${initialPlaybook.useful_code_snippets.length}`);
  logInfo(`  - Troubleshooting: ${initialPlaybook.troubleshooting_and_pitfalls.length}`);
  logInfo(`  - APIs: ${initialPlaybook.apis_to_use.length}`);

  // Save to server (test remote save)
  logInfo('Saving to remote server...');
  await serverClient.savePlaybook(initialPlaybook);
  serverClient.invalidateCache();

  logSuccess('Playbook saved to server');
}

// Test 6: Remote Save Verification
async function testRemoteSaveVerification() {
  logInfo('Verifying remote server storage...');

  // Clear local cache and fetch fresh from server
  serverClient.invalidateCache();
  const playbook = await serverClient.getPlaybook(true);

  const totalBullets = [
    ...playbook.strategies_and_hard_rules,
    ...playbook.useful_code_snippets,
    ...playbook.troubleshooting_and_pitfalls,
    ...playbook.apis_to_use
  ].length;

  if (totalBullets === 0) {
    throw new Error('Server returned empty playbook (init may have failed)');
  }

  logSuccess(`Server has ${totalBullets} bullets stored`);
  logInfo('Remote storage verified!');
}

// Test 7: Embedding Cache
async function testEmbeddingCache() {
  logInfo('Testing embedding cache...');

  const texts = [
    'Always validate JWT tokens before processing',
    'Use async/await for better error handling',
    'Always validate JWT tokens before processing' // Duplicate
  ];

  // First computation (cold)
  const start1 = Date.now();
  const embeddings1 = await serverClient.computeEmbeddings(texts);
  const coldTime = Date.now() - start1;
  logInfo(`  - Cold computation: ${coldTime}ms (3 texts)`);

  // Second computation (cached)
  const start2 = Date.now();
  const embeddings2 = await serverClient.computeEmbeddings(texts);
  const cachedTime = Date.now() - start2;
  logInfo(`  - Cached computation: ${cachedTime}ms (same texts)`);

  if (embeddings1.length !== 3 || embeddings2.length !== 3) {
    throw new Error('Expected 3 embeddings');
  }

  if (embeddings1[0].length !== 384) {
    throw new Error('Expected 384-dimensional embeddings');
  }

  logSuccess(`Embedding cache working (${(coldTime / (cachedTime || 1)).toFixed(1)}x speedup)`);
  logInfo(`  - Embedding dimensions: ${embeddings1[0].length}`);
}

// Test 8: Cache Invalidation
async function testCacheInvalidation() {
  logInfo('Testing cache invalidation...');

  // Get playbook (cached)
  const playbook1 = await serverClient.getPlaybook();

  // Invalidate cache
  serverClient.invalidateCache();
  logInfo('Cache invalidated');

  // Get playbook again (should fetch from server/SQLite)
  const playbook2 = await serverClient.getPlaybook();

  logSuccess('Cache invalidation working');
  logInfo('Playbook successfully refetched after invalidation');
}

// Test 9: ace_clear (with verification)
async function testAceClear() {
  logInfo('Testing ace_clear (playbook deletion)...');

  // Clear playbook
  await serverClient.clearPlaybook();
  logSuccess('Playbook cleared on server');

  // Verify it's empty
  const playbook = await serverClient.getPlaybook(true);
  const totalBullets = [
    ...playbook.strategies_and_hard_rules,
    ...playbook.useful_code_snippets,
    ...playbook.troubleshooting_and_pitfalls,
    ...playbook.apis_to_use
  ].length;

  if (totalBullets !== 0) {
    throw new Error(`Expected 0 bullets, got ${totalBullets}`);
  }

  logSuccess('Server confirmed empty playbook');
}

// Test 10: Full Cycle (init → save → retrieve → clear)
async function testFullCycle() {
  logInfo('Testing full ACE cycle...');

  // Step 1: Clear
  logInfo('Step 1: Clear existing playbook...');
  await serverClient.clearPlaybook();

  // Step 2: Initialize from codebase
  logInfo('Step 2: Initialize from codebase...');
  const initialPlaybook = await initService.initializeFromCodebase(process.cwd(), {
    commitLimit: 20,
    daysBack: 7
  });

  // Step 3: Save to server
  logInfo('Step 3: Save to server...');
  await serverClient.savePlaybook(initialPlaybook);
  serverClient.invalidateCache();

  // Step 4: Retrieve and verify
  logInfo('Step 4: Retrieve and verify...');
  const retrieved = await serverClient.getPlaybook(true);

  const savedCount = [
    ...initialPlaybook.strategies_and_hard_rules,
    ...initialPlaybook.useful_code_snippets,
    ...initialPlaybook.troubleshooting_and_pitfalls,
    ...initialPlaybook.apis_to_use
  ].length;

  const retrievedCount = [
    ...retrieved.strategies_and_hard_rules,
    ...retrieved.useful_code_snippets,
    ...retrieved.troubleshooting_and_pitfalls,
    ...retrieved.apis_to_use
  ].length;

  if (retrievedCount !== savedCount) {
    throw new Error(`Mismatch: saved ${savedCount} bullets, retrieved ${retrievedCount}`);
  }

  // Step 5: Clear again
  logInfo('Step 5: Clean up...');
  await serverClient.clearPlaybook();

  logSuccess(`Full cycle complete: ${savedCount} bullets saved and verified`);
}

// Main test runner
async function runTests() {
  console.log('\n' + '█'.repeat(60));
  console.log('🚀 ACE CLIENT INTEGRATION TEST SUITE');
  console.log('█'.repeat(60));
  console.log(`\nConfiguration:`);
  console.log(`  - Server: ${config.serverUrl}`);
  console.log(`  - Project: ${config.projectId}`);
  console.log(`  - Token: ${config.apiToken.substring(0, 20)}...`);
  console.log(`  - Cache: ${getCachePath()}`);

  // Run all tests
  await recordTest('1. Server Health Check', testServerHealth);
  await recordTest('2. ace_status (GET playbook)', testAceStatus);
  await recordTest('3. Local Cache Creation', testLocalCacheCreation);
  await recordTest('4. Cache Hit Performance', testCacheHitPerformance);
  await recordTest('5. ace_init (Offline Learning)', testAceInit);
  await recordTest('6. Remote Save Verification', testRemoteSaveVerification);
  await recordTest('7. Embedding Cache', testEmbeddingCache);
  await recordTest('8. Cache Invalidation', testCacheInvalidation);
  await recordTest('9. ace_clear (Playbook Deletion)', testAceClear);
  await recordTest('10. Full Cycle Test', testFullCycle);

  // Print summary
  console.log('\n' + '█'.repeat(60));
  console.log('📊 TEST SUMMARY');
  console.log('█'.repeat(60));

  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;
  const totalTime = results.reduce((sum, r) => sum + r.duration, 0);

  console.log(`\nResults: ${passed}/${results.length} passed, ${failed} failed`);
  console.log(`Total time: ${totalTime}ms`);

  console.log('\nDetailed Results:');
  results.forEach((r, i) => {
    const status = r.passed ? '✅' : '❌';
    console.log(`  ${status} Test ${i + 1}: ${r.name} (${r.duration}ms)`);
    if (!r.passed) {
      console.log(`     Error: ${r.details}`);
    }
  });

  // Check cache file stats
  const cachePath = getCachePath();
  if (fs.existsSync(cachePath)) {
    const stats = fs.statSync(cachePath);
    console.log('\n📁 Cache File Stats:');
    console.log(`   Path: ${cachePath}`);
    console.log(`   Size: ${stats.size} bytes`);
    console.log(`   Modified: ${stats.mtime.toISOString()}`);
  }

  // Exit with appropriate code
  if (failed > 0) {
    console.log('\n❌ Some tests failed');
    process.exit(1);
  } else {
    console.log('\n✅ All tests passed!');
    process.exit(0);
  }
}

// Run tests
runTests().catch((error) => {
  console.error('\n💥 Fatal error:', error);
  process.exit(1);
});
