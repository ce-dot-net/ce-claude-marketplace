// Pure state shapes: data-root derivation (plugin_data_dir), patterns-used merge (append_patterns_used),
// reuse-cache keys (ace_search_cache). No `$`, no I/O.
import { sha256Hex } from './cohort.ts'
import { cpSlice } from './text.ts'
import { isValidPatternId, STATE_CAP } from './render.ts'
import { CONTENT_CAP } from './evidence.ts'

// ---------- plugin_data_dir ----------
export const safeComponent = (c: string | undefined | null): string => {
  const s = String(c ?? '').replace(/[^A-Za-z0-9_.-]/g, '_')
  return s === '' ? 'default' : s === '.' || s === '..' ? '_' : s
}
// F1: a mod reads the HOST env, so the plugin-data variable there may name another plugin. Derive CC's own dir name:
// <config>/plugins/cache/<marketplace>/<name>/<ver> -> <config>/plugins/data/<name>-<marketplace>; else <name>-inline.
export function dataRootFromPluginRoot(home: string, root: string, name: string, configDir?: string): string {
  const m = /^(.*)\/plugins\/cache\/([^/]+)\/([^/]+)\/[^/]+\/?$/.exec(root)
  if (m) return `${m[1]}/plugins/data/${m[3]}-${m[2]}`
  return `${configDir || home + '/.claude'}/plugins/data/${name}-inline`
}

// ---------- patterns_used_state.append_patterns_used: same merge, same key order, same bytes ----------
export type StateUpdate = { ids?: string[]; retrievalId?: string | null; rlog?: Record<string, number>; tsid?: string | null
  userPrompt?: string; rendered?: string; hook?: string; parentTaskId?: string; agentType?: string; renderVariant?: string
  contents?: Record<string, string>; evalStats?: { avg_relevance: number; domains: number } }
export function mergeState(prior: any, u: StateUpdate): any {
  const p = prior && typeof prior === 'object' && !Array.isArray(prior) ? prior : {}
  const ids: string[] = Array.isArray(p.pattern_ids) ? [...p.pattern_ids] : Array.isArray(prior) ? [...prior] : []
  for (const id of u.ids ?? []) if (isValidPatternId(id) && !ids.includes(id)) ids.push(id)
  const state: any = {
    pattern_ids: ids,
    retrieval_id: u.retrievalId ?? p.retrieval_id ?? null,
    retrieval_log_ids: { ...(p.retrieval_log_ids ?? {}), ...(u.rlog ?? {}) },
    task_session_id: u.tsid ?? p.task_session_id ?? null,
  }
  const up = u.userPrompt ?? p.user_prompt
  if (up) state.user_prompt = cpSlice(up, 4000)
  const rc = u.rendered ?? p.rendered_context
  if (rc !== undefined && rc !== null) state.rendered_context = cpSlice(rc, STATE_CAP)
  const he = u.hook ?? p.hook_event_name
  if (he) state.hook_event_name = he
  const pt = u.parentTaskId ?? p.parent_task_id
  if (pt) state.parent_task_id = pt
  const rv = u.renderVariant ?? p.render_variant // §28: the variant ACTUALLY rendered, read back at learn
  if (rv) state.render_variant = rv
  const pc: Record<string, string> = { ...(p.pattern_contents && typeof p.pattern_contents === 'object' ? p.pattern_contents : {}) }
  for (const [id, t] of Object.entries(u.contents ?? {})) if (isValidPatternId(id) && typeof t === 'string' && t) pc[id] = cpSlice(t, CONTENT_CAP)
  if (Object.keys(pc).length) state.pattern_contents = pc  // §31 (Python writes it after its optional keys too)
  const es = u.evalStats ?? p.eval_stats  // self-eval numbers of the task's search, read by Stop (Python key order)
  if (es && typeof es === 'object' && !Array.isArray(es)) state.eval_stats = es
  const at = u.agentType ?? p.agent_type // mod-only: its turn.complete carries no agent type; Python ignores the key
  if (at) state.agent_type = at
  return state
}

// DESIGN §32: ace_search_cache key (sha256 of project \x1f kind \x1f normalized query), same file as the Python chain.
export const REUSE_TTL_MS = 15 * 60_000
export const normalizeQuery = (q: string) => String(q ?? '').replace(/<task-id>[\s\S]*?<\/task-id>/gi, ' ').split(/\s+/).filter(Boolean).join(' ').toLowerCase()
export const reuseKey = (project: string, kind: string, query: string) => sha256Hex([project, kind, normalizeQuery(query)].join('\x1f'))
export const reuseEnabled = (raw: unknown, kind: string) => (raw == null ? 'domain,subagent' : String(raw)).split(',').map(x => x.trim()).includes(kind)
