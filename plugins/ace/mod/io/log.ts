// Relevance-log rows (ace_relevance_logger): the search row builder.
import { num } from '../lib/pyjson.ts'

// relevance log 'search' row (ace_relevance_logger.log_search_metrics)
export function searchRow(a: { hook: string; sessionId: string; userPrompt: string; query: string; returned: any[];
  injected: any[]; projectId: string; orgId?: string; agentType: string; cohort: string; hookMs: number; nowIso: string; extra?: any }) {
  const conf = a.injected.map(p => num(p.confidence) ?? 0)
  const row: any = {
    timestamp: a.nowIso, event: 'search', hook: a.hook, session_id: a.sessionId, project_id: a.projectId,
    org_id: a.orgId ?? null, agent_type: a.agentType || 'main', user_prompt: a.userPrompt.slice(0, 200),
    search_query: a.query.slice(0, 100), patterns_returned: a.returned.length, patterns_injected: a.injected.length,
    patterns_filtered: a.returned.length - a.injected.length,
    avg_confidence: conf.length ? Math.round(conf.reduce((x, y) => x + y, 0) / conf.length * 1000) / 1000 : 0,
    domains: [...new Set(a.returned.map(p => p.domain).filter(Boolean))].slice(0, 10),
    top_patterns: a.injected.slice(0, 5).map(p => ({ id: p.id ?? 'unknown', confidence: p.confidence ?? 0, helpful: p.helpful ?? 0,
      harmful: p.harmful ?? 0, domain: p.domain ?? 'unknown', section: p.section ?? 'unknown',
      content: String(p.content ?? '').slice(0, 100) + (String(p.content ?? '').length > 100 ? '...' : ''),
      cumulative_v15_reward: p.cumulative_v15_reward ?? null, isAtRisk: p.isAtRisk ?? null,
      n_hot_pos: p.n_hot_pos ?? null, n_hot_neg: p.n_hot_neg ?? null })),
    render_cohort: a.cohort, hook_ms: a.hookMs,
  }
  return Object.assign(row, a.extra || {})
}
