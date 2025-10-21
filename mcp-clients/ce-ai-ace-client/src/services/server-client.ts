/**
 * ACE Server Client - HTTP REST API client with 3-tier cache
 *
 * Architecture:
 * 1. RAM cache (fastest, lost on restart)
 * 2. SQLite cache (fast, survives restart)
 * 3. Remote server (slow, source of truth)
 */

import { ACEConfig } from '../types/config.js';
import { StructuredPlaybook, PlaybookStats, DeltaOperation } from '../types/pattern.js';
import { LocalCacheService } from './local-cache.js';

export class ACEServerClient {
  private localCache: LocalCacheService;
  private memoryCache?: StructuredPlaybook; // RAM cache

  constructor(private config: ACEConfig) {
    // Extract org_id from API token (format: ace_{org_id}_...)
    const orgId = this.extractOrgId(config.apiToken);

    // Initialize local SQLite cache
    this.localCache = new LocalCacheService({
      orgId,
      projectId: config.projectId,
      ttlMinutes: 5
    });

    console.error(`🔗 ACE Server: ${config.serverUrl}`);
    console.error(`🔑 API Token: ${config.apiToken.substring(0, 15)}...`);
    console.error(`📂 Project: ${config.projectId}`);
  }

  /**
   * Extract org_id from API token
   * Format: ace_{base64_with_org_id}
   */
  private extractOrgId(apiToken: string): string {
    // Simple extraction - token format varies
    // Fallback to hash if can't extract
    if (!apiToken.startsWith('ace_')) {
      return 'default';
    }

    // For now, use first 8 chars after ace_ as org identifier
    return apiToken.substring(4, 12);
  }

  private async request<T>(
    endpoint: string,
    method: string,
    body?: any
  ): Promise<T> {
    const url = `${this.config.serverUrl}${endpoint}`;

    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.config.apiToken}`,
        'X-ACE-Project': this.config.projectId
      },
      body: body ? JSON.stringify(body) : undefined
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Server error (${response.status}): ${error}`);
    }

    return response.json();
  }

  /**
   * Save structured playbook to server
   * Server endpoint: POST /patterns (saves individual bullets)
   *
   * Note: Server doesn't have POST /playbook - it uses POST /patterns
   * This method flattens the structured playbook and saves all bullets
   */
  async savePlaybook(playbook: StructuredPlaybook): Promise<void> {
    // Flatten playbook into array of bullets
    const allBullets = [
      ...playbook.strategies_and_hard_rules,
      ...playbook.useful_code_snippets,
      ...playbook.troubleshooting_and_pitfalls,
      ...playbook.apis_to_use
    ];

    // Server expects: POST /patterns with array of bullets
    await this.request('/patterns', 'POST', { patterns: allBullets });
  }

  /**
   * Get structured playbook (3-tier cache: RAM → SQLite → Server)
   * Endpoint: GET /playbook
   */
  async getPlaybook(forceRefresh = false): Promise<StructuredPlaybook> {
    // 1. Check RAM cache (fastest)
    if (!forceRefresh && this.memoryCache) {
      console.error('✅ Cache hit (RAM)');
      return this.memoryCache;
    }

    // 2. Check SQLite cache (if fresh)
    if (!forceRefresh && !this.localCache.needsSync()) {
      const cached = this.localCache.getPlaybook();
      if (cached) {
        this.memoryCache = cached;
        return cached;
      }
    }

    // 3. Fetch from server (source of truth)
    console.error('🌐 Fetching playbook from server...');
    const result = await this.request<{ playbook: StructuredPlaybook }>(
      '/playbook',
      'GET'
    );

    const playbook = result.playbook || {
      strategies_and_hard_rules: [],
      useful_code_snippets: [],
      troubleshooting_and_pitfalls: [],
      apis_to_use: []
    };

    // Update caches
    this.memoryCache = playbook;
    this.localCache.savePlaybook(playbook);

    return playbook;
  }

  /**
   * Compute embeddings for texts (with SQLite cache)
   * Endpoint: POST /embeddings
   */
  async computeEmbeddings(texts: string[]): Promise<number[][]> {
    if (texts.length === 0) return [];

    const embeddings: number[][] = [];
    const uncachedTexts: string[] = [];
    const uncachedIndices: number[] = [];

    // Check cache for each text
    for (let i = 0; i < texts.length; i++) {
      const cached = this.localCache.getEmbedding(texts[i]);
      if (cached) {
        embeddings[i] = cached;
      } else {
        uncachedTexts.push(texts[i]);
        uncachedIndices.push(i);
      }
    }

    // Compute uncached embeddings from server
    if (uncachedTexts.length > 0) {
      console.error(`🧮 Computing ${uncachedTexts.length} embeddings...`);
      const result = await this.request<{ embeddings: number[][] }>(
        '/embeddings',
        'POST',
        { texts: uncachedTexts }
      );

      // Fill in results and cache them
      for (let i = 0; i < result.embeddings.length; i++) {
        const embedding = result.embeddings[i];
        const originalIndex = uncachedIndices[i];
        embeddings[originalIndex] = embedding;

        // Cache for future use
        this.localCache.cacheEmbedding(uncachedTexts[i], embedding);
      }
    }

    return embeddings;
  }

  /**
   * Get playbook analytics
   * Endpoint: GET /analytics
   */
  async getAnalytics(): Promise<PlaybookStats> {
    return this.request<PlaybookStats>('/analytics', 'GET');
  }

  /**
   * Clear entire playbook
   * Server endpoint: DELETE /patterns (clears all patterns)
   *
   * Note: Server doesn't have DELETE /playbook - it uses DELETE /patterns
   */
  async clearPlaybook(): Promise<void> {
    await this.request('/patterns?confirm=true', 'DELETE');

    // Invalidate caches
    this.invalidateCache();
  }

  /**
   * Apply delta operation (ADD/UPDATE/DELETE)
   * Server endpoint: POST /delta
   *
   * This is the ACE paper's recommended approach for incremental updates
   * instead of replacing the entire playbook
   */
  async applyDelta(operation: DeltaOperation): Promise<void> {
    await this.request('/delta', 'POST', { operation });

    // Invalidate caches
    this.invalidateCache();
  }

  /**
   * Apply multiple delta operations in batch
   * Server endpoint: POST /delta (multiple calls)
   */
  async applyDeltas(operations: DeltaOperation[]): Promise<void> {
    for (const operation of operations) {
      await this.applyDelta(operation);
    }
  }

  /**
   * Invalidate caches (force refresh on next call)
   * Call after any mutation (save, clear, delta operations)
   */
  invalidateCache(): void {
    this.memoryCache = undefined;
    // Note: We keep SQLite cache - it will be overwritten on next fetch
    console.error('🔄 Cache invalidated');
  }

  /**
   * Get local cache instance (for advanced operations)
   */
  getLocalCache(): LocalCacheService {
    return this.localCache;
  }
}
