/**
 * Curator Service - Applies delta operations and performs grow-and-refine
 *
 * Paper Section 3: "The Curator integrates insights into structured context updates"
 * Uses incremental delta updates instead of monolithic rewrites
 */

import { PlaybookBullet, Reflection, DeltaOperation, StructuredPlaybook, BulletSection } from '../types/pattern.js';
import { ACEConfig } from '../types/config.js';
import { ACEServerClient } from './server-client.js';

export class CurationService {
  constructor(
    private serverClient: ACEServerClient,
    private config: ACEConfig
  ) {}

  /**
   * Apply delta operations to playbook
   * Paper: "incremental delta updates... localized edits"
   */
  async applyDeltaOperations(
    playbook: StructuredPlaybook,
    reflection: Reflection
  ): Promise<StructuredPlaybook> {
    // Deep clone to avoid mutations
    const updated: StructuredPlaybook = JSON.parse(JSON.stringify(playbook));

    for (const op of reflection.operations) {
      switch (op.type) {
        case 'ADD':
          this.addBullet(updated, op);
          break;
        case 'UPDATE':
          this.updateBullet(updated, op);
          break;
        case 'DELETE':
          this.deleteBullet(updated, op);
          break;
      }
    }

    // Grow-and-refine: Deduplicate and merge similar bullets
    return await this.growAndRefine(updated);
  }

  /**
   * Add new bullet to playbook
   */
  private addBullet(playbook: StructuredPlaybook, op: DeltaOperation): void {
    if (!op.section || !op.content) {
      console.error('ADD operation missing section or content:', op);
      return;
    }

    const bullet: PlaybookBullet = {
      id: `ctx-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
      section: op.section,
      content: op.content,
      helpful: 0,
      harmful: 0,
      confidence: op.confidence || 0.5,
      evidence: op.evidence || [],
      observations: 1,
      created_at: new Date().toISOString(),
      last_used: new Date().toISOString()
    };

    playbook[op.section].push(bullet);
  }

  /**
   * Update existing bullet counters
   */
  private updateBullet(playbook: StructuredPlaybook, op: DeltaOperation): void {
    if (!op.bullet_id) {
      console.error('UPDATE operation missing bullet_id:', op);
      return;
    }

    // Find bullet across all sections
    for (const section of Object.keys(playbook) as BulletSection[]) {
      const bullet = playbook[section].find(b => b.id === op.bullet_id);

      if (bullet) {
        bullet.helpful += op.helpful_delta || 0;
        bullet.harmful += op.harmful_delta || 0;
        bullet.observations += 1;
        bullet.last_used = new Date().toISOString();

        // Update confidence based on helpful/harmful ratio
        const total = bullet.helpful + bullet.harmful;
        if (total > 0) {
          bullet.confidence = bullet.helpful / total;
        }

        return;
      }
    }

    console.error(`Bullet ${op.bullet_id} not found for UPDATE`);
  }

  /**
   * Delete bullet from playbook
   */
  private deleteBullet(playbook: StructuredPlaybook, op: DeltaOperation): void {
    if (!op.bullet_id) {
      console.error('DELETE operation missing bullet_id:', op);
      return;
    }

    for (const section of Object.keys(playbook) as BulletSection[]) {
      const index = playbook[section].findIndex(b => b.id === op.bullet_id);

      if (index !== -1) {
        playbook[section].splice(index, 1);
        return;
      }
    }

    console.error(`Bullet ${op.bullet_id} not found for DELETE`);
  }

  /**
   * Grow-and-refine deduplication
   * Paper: "periodic or lazy refinement... de-duplication step then prunes redundancy"
   */
  private async growAndRefine(playbook: StructuredPlaybook): Promise<StructuredPlaybook> {
    for (const section of Object.keys(playbook) as BulletSection[]) {
      const bullets = playbook[section];

      if (bullets.length === 0) continue;

      // Get embeddings for all bullets in section
      const texts = bullets.map(b => b.content);
      const embeddings = await this.serverClient.computeEmbeddings(texts);

      // Merge similar bullets (0.85 threshold from ACE paper)
      const merged = this.mergeSimilarBullets(bullets, embeddings);

      // Prune low confidence (0.30 threshold from ACE paper)
      const pruned = merged.filter(b => b.confidence >= this.config.confidenceThreshold);

      // Prune consistently harmful bullets (harmful > helpful)
      const cleaned = pruned.filter(b => b.helpful >= b.harmful);

      playbook[section] = cleaned;
    }

    return playbook;
  }

  /**
   * Merge similar bullets using cosine similarity
   */
  private mergeSimilarBullets(
    bullets: PlaybookBullet[],
    embeddings: number[][]
  ): PlaybookBullet[] {
    const merged: PlaybookBullet[] = [];
    const processed = new Set<number>();

    for (let i = 0; i < bullets.length; i++) {
      if (processed.has(i)) continue;

      const group: number[] = [i];

      // Find similar bullets
      for (let j = i + 1; j < bullets.length; j++) {
        if (processed.has(j)) continue;

        const similarity = this.cosineSimilarity(embeddings[i], embeddings[j]);

        if (similarity >= this.config.similarityThreshold) {
          group.push(j);
          processed.add(j);
        }
      }

      // Merge group into single bullet
      merged.push(this.mergeBulletGroup(bullets, group));
      processed.add(i);
    }

    return merged;
  }

  /**
   * Merge a group of similar bullets
   */
  private mergeBulletGroup(bullets: PlaybookBullet[], indices: number[]): PlaybookBullet {
    const base = bullets[indices[0]];

    return {
      ...base,
      helpful: indices.reduce((sum, i) => sum + bullets[i].helpful, 0),
      harmful: indices.reduce((sum, i) => sum + bullets[i].harmful, 0),
      observations: indices.reduce((sum, i) => sum + bullets[i].observations, 0),
      evidence: [...new Set(indices.flatMap(i => bullets[i].evidence))],
      confidence: indices.reduce((sum, i) => sum + bullets[i].confidence, 0) / indices.length
    };
  }

  /**
   * Cosine similarity between two embedding vectors
   */
  private cosineSimilarity(a: number[], b: number[]): number {
    const dotProduct = a.reduce((sum, val, i) => sum + val * b[i], 0);
    const magA = Math.sqrt(a.reduce((sum, val) => sum + val * val, 0));
    const magB = Math.sqrt(b.reduce((sum, val) => sum + val * val, 0));
    return dotProduct / (magA * magB);
  }
}
