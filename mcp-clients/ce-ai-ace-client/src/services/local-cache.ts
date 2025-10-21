/**
 * LocalCacheService - Client-side SQLite cache
 *
 * Architecture:
 * - Location: ./.ace-cache/{org_id}_{project_id}.db (project directory)
 *             OR ~/.ace-cache/ (home directory, for production)
 * - Purpose: Fast local cache, survives restarts
 * - TTL: 5 minutes (configurable)
 * - Source of truth: Remote server (ChromaDB)
 *
 * From ACE Paper:
 * "cached locally or remotely, avoiding repetitive and expensive prefill operations"
 */

import Database from 'better-sqlite3';
import { homedir } from 'os';
import { join } from 'path';
import { mkdirSync, existsSync } from 'fs';
import { createHash } from 'crypto';
import { StructuredPlaybook, PlaybookBullet } from '../types/pattern.js';

export interface CacheConfig {
  orgId: string;
  projectId: string;
  ttlMinutes?: number;  // Default: 5
  cacheDir?: string;    // Default: ./.ace-cache (project directory)
}

export class LocalCacheService {
  private db: Database.Database;
  private ttlMs: number;
  private cacheDir: string;

  constructor(config: CacheConfig) {
    const { orgId, projectId, ttlMinutes = 5, cacheDir } = config;

    // Cache directory: Use provided cacheDir, or default to ./.ace-cache (project directory)
    // For production, pass cacheDir: join(homedir(), '.ace-cache')
    this.cacheDir = cacheDir || join(process.cwd(), '.ace-cache');
    if (!existsSync(this.cacheDir)) {
      mkdirSync(this.cacheDir, { recursive: true });
    }

    // Database file: {org_id}_{project_id}.db
    const dbPath = join(this.cacheDir, `${orgId}_${projectId}.db`);
    console.error(`💾 Local cache: ${dbPath}`);

    this.db = new Database(dbPath);
    this.ttlMs = ttlMinutes * 60 * 1000;

    this.initializeSchema();
  }

  /**
   * Initialize SQLite schema
   */
  private initializeSchema(): void {
    // Table: playbook_bullets (cached from server)
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS playbook_bullets (
        id TEXT PRIMARY KEY,
        section TEXT NOT NULL,
        content TEXT NOT NULL,
        helpful INTEGER DEFAULT 0,
        harmful INTEGER DEFAULT 0,
        confidence REAL DEFAULT 0.5,
        observations INTEGER DEFAULT 0,
        evidence TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_used TEXT DEFAULT CURRENT_TIMESTAMP,
        synced_at TEXT
      );

      CREATE INDEX IF NOT EXISTS idx_section ON playbook_bullets(section);
      CREATE INDEX IF NOT EXISTS idx_confidence ON playbook_bullets(confidence);
      CREATE INDEX IF NOT EXISTS idx_helpful ON playbook_bullets(helpful DESC);
    `);

    // Table: embedding_cache (avoid re-computing)
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS embedding_cache (
        content_hash TEXT PRIMARY KEY,
        embedding BLOB NOT NULL,
        created_at TEXT NOT NULL
      );
    `);

    // Table: sync_state (metadata)
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sync_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
    `);
  }

  /**
   * Get cached playbook (if fresh)
   */
  getPlaybook(): StructuredPlaybook | null {
    if (this.needsSync()) {
      return null; // Cache stale
    }

    const bullets = this.db.prepare(`
      SELECT * FROM playbook_bullets
    `).all() as any[];

    if (bullets.length === 0) {
      return null; // No cache
    }

    // Group by section
    const playbook: StructuredPlaybook = {
      strategies_and_hard_rules: [],
      useful_code_snippets: [],
      troubleshooting_and_pitfalls: [],
      apis_to_use: []
    };

    for (const row of bullets) {
      const bullet: PlaybookBullet = {
        id: row.id,
        section: row.section,
        content: row.content,
        helpful: row.helpful,
        harmful: row.harmful,
        confidence: row.confidence,
        observations: row.observations,
        evidence: row.evidence ? JSON.parse(row.evidence) : [],
        created_at: row.created_at,
        last_used: row.last_used
      };

      playbook[bullet.section].push(bullet);
    }

    console.error('✅ Cache hit (SQLite)');
    return playbook;
  }

  /**
   * Save playbook to cache
   */
  savePlaybook(playbook: StructuredPlaybook): void {
    const now = new Date().toISOString();

    // Clear old data
    this.db.prepare('DELETE FROM playbook_bullets').run();

    // Insert all bullets
    const insert = this.db.prepare(`
      INSERT INTO playbook_bullets (
        id, section, content, helpful, harmful, confidence,
        observations, evidence, created_at, last_used, synced_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const insertMany = this.db.transaction((bullets: PlaybookBullet[], section: string) => {
      for (const bullet of bullets) {
        insert.run(
          bullet.id,
          section,
          bullet.content,
          bullet.helpful,
          bullet.harmful,
          bullet.confidence,
          bullet.observations,
          JSON.stringify(bullet.evidence),
          bullet.created_at || now,  // Default to now if missing
          bullet.last_used || now,   // Default to now if missing
          now
        );
      }
    });

    insertMany(playbook.strategies_and_hard_rules, 'strategies_and_hard_rules');
    insertMany(playbook.useful_code_snippets, 'useful_code_snippets');
    insertMany(playbook.troubleshooting_and_pitfalls, 'troubleshooting_and_pitfalls');
    insertMany(playbook.apis_to_use, 'apis_to_use');

    // Update sync state
    this.setSyncState('last_sync', now);

    console.error('💾 Playbook cached to SQLite');
  }

  /**
   * Check if cache needs sync (>TTL)
   */
  needsSync(): boolean {
    const lastSync = this.getSyncState('last_sync');
    if (!lastSync) {
      return true; // No sync yet
    }

    const lastSyncTime = new Date(lastSync).getTime();
    const now = Date.now();

    return (now - lastSyncTime) > this.ttlMs;
  }

  /**
   * Get cached embedding (if exists)
   */
  getEmbedding(content: string): number[] | null {
    const hash = this.hashContent(content);

    const row = this.db.prepare(`
      SELECT embedding FROM embedding_cache WHERE content_hash = ?
    `).get(hash) as { embedding: Buffer } | undefined;

    if (!row) {
      return null;
    }

    // Deserialize Float32Array from buffer
    const float32 = new Float32Array(
      row.embedding.buffer,
      row.embedding.byteOffset,
      row.embedding.byteLength / 4
    );

    return Array.from(float32);
  }

  /**
   * Cache embedding
   */
  cacheEmbedding(content: string, embedding: number[]): void {
    const hash = this.hashContent(content);

    // Serialize Float32Array to buffer
    const float32 = new Float32Array(embedding);
    const buffer = Buffer.from(float32.buffer);

    this.db.prepare(`
      INSERT OR REPLACE INTO embedding_cache (content_hash, embedding, created_at)
      VALUES (?, ?, ?)
    `).run(hash, buffer, new Date().toISOString());
  }

  /**
   * Get sync state value
   */
  getSyncState(key: string): string | null {
    const row = this.db.prepare(`
      SELECT value FROM sync_state WHERE key = ?
    `).get(key) as { value: string } | undefined;

    return row?.value || null;
  }

  /**
   * Set sync state value
   */
  setSyncState(key: string, value: string): void {
    this.db.prepare(`
      INSERT OR REPLACE INTO sync_state (key, value, updated_at)
      VALUES (?, ?, ?)
    `).run(key, value, new Date().toISOString());
  }

  /**
   * Clear entire cache
   */
  clear(): void {
    this.db.exec(`
      DELETE FROM playbook_bullets;
      DELETE FROM embedding_cache;
      DELETE FROM sync_state;
    `);

    console.error('🗑️  Cache cleared');
  }

  /**
   * Hash content for embedding cache key
   */
  private hashContent(content: string): string {
    return createHash('sha256').update(content).digest('hex');
  }

  /**
   * Close database connection
   */
  close(): void {
    this.db.close();
  }
}
