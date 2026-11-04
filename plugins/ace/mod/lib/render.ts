// Pattern rendering (ace_pattern_render): allow-list strip, bandit_rank sort, full/budget/compact/domain-shift renders.
// Pure: no `$`, no I/O.
import { PyFloat, num, pyDumps, pyFloatRepr } from './pyjson.ts'
import { cps, cpLen, cpSlice } from './text.ts'

// ---------- utils/validation.is_valid_pattern_id ----------
export const isValidPatternId = (id: unknown): boolean =>
  typeof id === 'string' && (/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(id)
    || /^ctx-[a-z0-9]+(-[a-z0-9]+)*$/.test(id))

// ---------- utils/ace_pattern_render.render_patterns_dict ----------
const KEEP = ['id', 'domain', 'content', 'section', 'evidence', 'root_cause', 'error_context',
  'cumulative_v15_reward', 'n_hot_pos', 'n_hot_neg', 'isAtRisk', 'confidence', 'helpful', 'harmful']
// Allow-list, not deny-list: since @ace-sdk/cli 4.3.0 the search response carries every server field
// (search_params, tokens_in_response, local_count, session_id, feedback_downvote ...); the model needs only these.
const KEEP_TOP = new Set(['retrieval_id', 'count'])
const truthy = (v: any) => !(v === null || v === undefined || v === false || v === 0 || v === ''
  || (Array.isArray(v) && v.length === 0) || (v instanceof PyFloat && v.v === 0)
  || (typeof v === 'object' && !Array.isArray(v) && !(v instanceof PyFloat) && Object.keys(v).length === 0))

export function hoistAndStrip(p: any): any {
  const mf = p.match_factors && typeof p.match_factors === 'object' ? p.match_factors : {}
  const r: any = {}
  for (const k of KEEP) {
    if (k === 'evidence') { if (truthy(p.evidence)) r.evidence = p.evidence.slice(0, 2) }
    else if (k === 'root_cause' || k === 'error_context') { if (truthy(p[k])) r[k] = p[k] }
    else if (k in p) r[k] = p[k]
  }
  if (mf.bandit_rank !== undefined && mf.bandit_rank !== null) r.bandit_rank = mf.bandit_rank
  if (mf.semantic_score !== undefined && mf.semantic_score !== null) r.semantic_score = mf.semantic_score
  return r
}

const isPyInt = (x: any) => typeof x === 'number' && Number.isInteger(x) // bool/PyFloat excluded by type

export function renderPatternsDict(resp: any): { dict: any; ids: string[]; rlog: Record<string, number> } {
  const pats: any[] = resp.similar_patterns || []
  const rank = (p: any) => { const mf = p.match_factors; return mf && typeof mf === 'object' ? num(mf.bandit_rank) ?? null : null }
  const sorted = pats.map((p, idx) => ({ p, idx })).sort((a, b) => {
    const ra = rank(a.p), rb = rank(b.p)
    if (ra === null || rb === null) return ra === null && rb === null ? a.idx - b.idx : ra === null ? 1 : -1
    return ra - rb || a.idx - b.idx
  }).map(x => x.p)
  const rlog: Record<string, number> = {}
  for (const p of sorted) {
    const rl = p.match_factors && typeof p.match_factors === 'object' ? p.match_factors.retrieval_log_id : undefined
    if (truthy(p.id) && isPyInt(rl)) rlog[p.id] = rl
  }
  const processed = sorted.map(hoistAndStrip)
  const ids = processed.filter(p => truthy(p.id) && isValidPatternId(p.id)).map(p => p.id)
  const dict: any = {}
  for (const k of Object.keys(resp)) if (KEEP_TOP.has(k)) dict[k] = resp[k]
  dict.similar_patterns = processed
  dict.count = processed.length
  return { dict, ids, rlog }
}

// ace_before_task: domains.json = domains_summary when non-empty, else per-domain counts.
export function domainsSummary(resp: any): Record<string, any> {
  const ds = resp.domains_summary
  if (ds && typeof ds === 'object' && Object.keys(ds).length) return ds
  const out: Record<string, number> = {}
  for (const p of resp.similar_patterns || []) if (p.domain) out[p.domain] = (out[p.domain] || 0) + 1
  return out
}

// ---------- renderers (ace_pattern_render; per-pattern keys SORTED: Python's own order comes from a
// frozenset and changes with PYTHONHASHSEED, so it has no stable byte form to copy) ----------
export const FULL_CAP = 95000, BUDGET = 9500, STATE_CAP = 10000, DOMAIN_CAP = 10000

const dumpSorted = (pats: any[]) => pats.map(p => pyDumps(p, true))
const baseOf = (dict: any) => Object.keys(dict).filter(k => k !== 'similar_patterns' && k !== 'count')
function envelope(dict: any, items: string[], count: number) {
  return '{' + [...baseOf(dict).map(k => pyDumps(k) + ': ' + pyDumps(dict[k])),
    '"similar_patterns": [' + items.join(', ') + ']', '"count": ' + count].join(', ') + '}'
}
const openTag = (tag: string, shown: number, total: number, attrs: string, extra = '') =>
  `<${tag} shown="${shown}" of="${total}"${extra}${attrs ? ' ' + attrs : ''}>`
function credit(pats: any[], rlog: Record<string, number>) {
  const ids = pats.filter(p => truthy(p.id) && isValidPatternId(p.id)).map(p => p.id as string)
  const keep = new Set(ids), out: Record<string, number> = {}
  for (const k of Object.keys(rlog)) if (keep.has(k)) out[k] = rlog[k]
  return { ids, rlog: out }
}

// The mod's default arm: ALL patterns (user ruling 1), whole tail patterns dropped until <= cap (§13.1 100K guard).
export function renderFull(resp: any, tag: string, attrs: string, cap = FULL_CAP) {
  const { dict, rlog } = renderPatternsDict(resp)
  const total: number = dict.count
  let pats: any[] = dict.similar_patterns
  const items = dumpSorted(pats)
  let n = pats.length, context = ''
  for (;;) {
    context = `${openTag(tag, n, total, attrs)}\n${envelope(dict, items.slice(0, n), n)}\n</${tag}>`
    if (context.length <= cap || n === 0) break
    n--
  }
  pats = pats.slice(0, n)
  return { context, ...credit(pats, rlog), patterns: pats, shown: n, total }
}

// render_patterns: top-N verbatim until the whole string fits the budget; count stays the total.
export function renderBudget(resp: any, tag: string, attrs: string, budget = BUDGET) {
  const { dict, rlog } = renderPatternsDict(resp)
  const total: number = dict.count, close = `</${tag}>`
  const available = budget - (openTag(tag, total, total, attrs).length + 1 + envelope(dict, [], total).length + 1 + close.length)
  const picked: any[] = []
  let chars = 2
  for (const p of dict.similar_patterns as any[]) {
    const cost = pyDumps(p, true).length + (picked.length ? 2 : 0)
    if (chars + cost <= available) { picked.push(p); chars += cost; continue }
    if (!picked.length) { // even top-1 alone is too big: no evidence, content cut to fit; never empty
      const c: any = { ...p }; delete c.evidence
      const size = () => pyDumps(c, true).length
      if (chars + size() > available) {
        const content = String(c.content ?? '')
        const excess = chars + size() - available
        c.content = cpSlice(content, Math.max(1, Math.max(4, pyDumps(content).length - excess - 1) - 2))
        while (chars + size() > available && cpLen(c.content) > 1) c.content = cps(c.content).slice(0, -10).join('')
        if (chars + size() > available) c.content = cpSlice(content, 1)
      }
      picked.push(c)
    }
    break
  }
  let context = ''
  for (;;) {
    context = `${openTag(tag, picked.length, total, attrs)}\n${envelope(dict, dumpSorted(picked), total)}\n${close}`
    if (context.length <= budget || !picked.length) break
    picked.pop()
  }
  return { context, ...credit(picked, rlog), patterns: picked, shown: picked.length, total }
}

// f"{x:.1f}": toFixed picks the larger digit on an exact tie (x*4 odd), Python the even one.
function fmt1(v: any): string {
  const x = num(v) ?? 0
  if (Object.is(x, -0)) return '-0.0'
  if (Number.isInteger(x * 4) && (x * 4) % 2 !== 0) {
    let n = Math.floor(Math.abs(x) * 10); n += n % 2
    return (x < 0 ? '-' : '') + (n / 10).toFixed(1)
  }
  return x.toFixed(1)
}

// render_compact_all: every pattern a one-liner, snippet length sized to the budget.
export function renderCompact(resp: any, tag: string, attrs: string, budget = BUDGET) {
  const { dict, rlog } = renderPatternsDict(resp)
  const all: any[] = dict.similar_patterns, total: number = dict.count, close = `</${tag}>`
  const open = (n: number) => openTag(tag, n, total, attrs, ' mode="compact"')
  if (!all.length) return { context: `${open(0)}\n${close}`, ids: [] as string[], rlog: {} as Record<string, number>, patterns: all, shown: 0, total }
  const head = (p: any) => {
    const r = p.bandit_rank
    return `#${r === undefined ? '?' : r instanceof PyFloat ? pyFloatRepr(r.v) : r} [${p.domain ?? ''}] r=${fmt1(p.cumulative_v15_reward)} `
  }
  const fixed = open(total).length + 1 + close.length + all.reduce((a, p) => a + cpLen(head(p)), 0) + all.length
  const snip = Math.max(0, Math.floor((budget - fixed) / all.length))
  const build = (ps: any[]) => `${open(ps.length)}\n${ps.map(p => head(p) + cpSlice(String(p.content ?? ''), snip)).join('\n')}\n${close}`
  let pats = all, context = build(pats)
  while (pats.length && cpLen(context) > budget) { pats = pats.slice(0, -1); context = build(pats) }
  return { context, ...credit(pats, rlog), patterns: pats, shown: pats.length, total }
}

// ace_domain_shift._context, trailing patterns dropped until <= 10,000 chars (count follows).
export function renderDomainShift(resp: any, domain: string) {
  const { dict, rlog } = renderPatternsDict(resp)
  const attr = domain.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;')
  const pats: any[] = dict.similar_patterns
  const items = dumpSorted(pats)
  let n = pats.length, context = ''
  for (;;) {
    const body = '{' + Object.keys(dict).map(k => pyDumps(k) + ': ' + (k === 'similar_patterns' ? '[' + items.slice(0, n).join(', ') + ']'
      : k === 'count' ? String(n) : pyDumps(dict[k]))).join(', ') + '}'
    context = `<ace-patterns-domain-shift domain="${attr}">${body}</ace-patterns-domain-shift>`
    if (context.length <= DOMAIN_CAP || n === 0) break
    n--
  }
  return { context, ...credit(pats.slice(0, n), rlog), shown: n, patterns: pats.slice(0, n) }
}
