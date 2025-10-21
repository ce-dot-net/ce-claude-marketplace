/**
 * Code Engine ACE - Type Definitions
 */

// ============================================================================
// Execution Trace - Records what happened during task execution
// ============================================================================

export interface TrajectoryStep {
  step: number;
  action: string;
  args: Record<string, any>;
  result?: any;
}

export interface ExecutionTrace {
  task: string;
  trajectory: TrajectoryStep[];
  result: {
    success: boolean;
    output: string;
    error?: string;
  };
  playbook_used: string[];  // Bullet IDs that were consulted
  timestamp: string;
}

// ============================================================================
// Playbook Bullet - Core unit of knowledge in ACE
// ============================================================================

export type BulletSection =
  | 'strategies_and_hard_rules'
  | 'useful_code_snippets'
  | 'troubleshooting_and_pitfalls'
  | 'apis_to_use';

export interface PlaybookBullet {
  id: string;  // Format: ctx-{timestamp}-{random}
  section: BulletSection;
  content: string;
  helpful: number;  // Counter: how many times this was helpful
  harmful: number;  // Counter: how many times this was harmful
  confidence: number;  // 0.0-1.0 (derived from helpful/harmful ratio)
  evidence: string[];  // File paths, line numbers, error messages
  observations: number;  // Total times this bullet was used
  created_at: string;
  last_used: string;
}

// ============================================================================
// Structured Playbook - Four sections per ACE paper Figure 3
// ============================================================================

export interface StructuredPlaybook {
  strategies_and_hard_rules: PlaybookBullet[];
  useful_code_snippets: PlaybookBullet[];
  troubleshooting_and_pitfalls: PlaybookBullet[];
  apis_to_use: PlaybookBullet[];
}

// ============================================================================
// Delta Operations - Incremental updates from Reflector
// ============================================================================

export type DeltaOperationType = 'ADD' | 'UPDATE' | 'DELETE';

export interface DeltaOperation {
  type: DeltaOperationType;
  section?: BulletSection;  // For ADD
  content?: string;  // For ADD
  bullet_id?: string;  // For UPDATE/DELETE
  helpful_delta?: number;  // For UPDATE (+1 if helpful, 0 otherwise)
  harmful_delta?: number;  // For UPDATE (+1 if harmful, 0 otherwise)
  confidence?: number;  // For ADD
  evidence?: string[];
  reason?: string;  // Why this operation is needed
}

// ============================================================================
// Reflection - Output from Reflector agent
// ============================================================================

export interface Reflection {
  operations: DeltaOperation[];
  summary: string;
}

// ============================================================================
// Analytics - Playbook statistics
// ============================================================================

export interface PlaybookStats {
  total_bullets: number;
  by_section: Record<BulletSection, number>;
  top_helpful: PlaybookBullet[];
  top_harmful: PlaybookBullet[];
  avg_confidence: number;
}

// ============================================================================
// Legacy types (for migration compatibility only - will be removed)
// ============================================================================

/** @deprecated Use PlaybookBullet instead */
export interface Pattern {
  id: string;
  name: string;
  domain: string;
  content: string;
  confidence: number;
  observations: number;
  harmful: number;
  evidence: string[];
  metadata?: Record<string, any>;
}

/** @deprecated Use ExecutionTrace instead */
export interface Insight {
  category: string;
  observation: string;
  confidence: number;
  harmful: boolean;
  evidence: string[];
}

/** @deprecated No longer used in ACE paper methodology */
export interface DomainTaxonomy {
  concrete: Record<string, string[]>;
  abstract: Record<string, string[]>;
  principles: string[];
}
