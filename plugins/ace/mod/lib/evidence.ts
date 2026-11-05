// F-080 evidence: self-eval prompt + review parse, used-pattern ids (H1/H2), applied log ids, eval stats/injection,
// user-rejection match (ace_feedback). Pure: no `$`, no I/O.
import { PyFloat, num, pyFloatRepr } from './pyjson.ts'
import { cps, cpSlice, normWs } from './text.ts'

export type ToolRec = { tool: string; action: string; result: string; failed: boolean; start_ms: number; end_ms: number; commit?: string
  hay?: string  // hay: the call's toolHaystack (item H2 used check), never sent in the trace
  key?: string; dec?: boolean; intr?: true }  // 8.1.3 outcome: recovery key, decisive step, interrupted (lib/trace.ts taskOutcome)

// ace_after_task.parse_ace_review
export function parseAceReview(msg: string): { quality_pct: number; time_saved: string } | null {
  const m = /ACE_REVIEW:\s*(\d+)/.exec(msg || '')
  if (!m) return null
  const t = /\d+m\d*s? saved|\d+s saved|\d+ ?min/.exec(msg)
  return { quality_pct: Number(m[1]), time_saved: t ? t[0].replace(' saved', '') : '' }
}

// patterns_used_state.eval_stats: mean confidence of the INJECTED x100 (truncated, 0..100; non-number 0), distinct RETURNED domains
export function evalStats(injected: any[], returned: any[]): { avg_relevance: number; domains: number } {
  const conf = (injected ?? []).map(p => { const c = num(p?.confidence); return c !== undefined && Number.isFinite(c) ? c : 0 })
  const rel = conf.length ? Math.trunc(conf.reduce((x, y) => x + y, 0) / conf.length * 100) : 0
  const doms = new Set((returned ?? []).filter(p => p && p.domain).map(p => String(p.domain)))
  return { avg_relevance: Math.max(0, Math.min(100, rel)), domains: doms.size }
}

// item D / H1: the Haiku self-eval request (a $.model.complete prompt, never the conversation): the task, its tool
// calls, the injected patterns as `id: content` lines and the final answer, each capped; two lines back.
export function selfEvalPrompt(a: { task: string; answer: string; ids: string[]; contents: Record<string, string>; tools: ToolRec[] }): string {
  const lines: string[] = []
  let n = 0
  for (const id of a.ids) {
    const l = `${id}: ${normWs(a.contents?.[id] ?? '')}`
    if (n + l.length + 1 > 6000) break
    lines.push(l); n += l.length + 1
  }
  const tools = cpSlice(a.tools.map(t => `${t.tool}: ${t.action}${t.failed ? ' (failed)' : ''}`).join('\n'), 4000)
  return 'You review one finished coding task for a pattern library. Patterns were injected into the agent before it worked.\n' +
    '<task>\n' + cpSlice(a.task, 2000) + '\n</task>\n<tool_calls>\n' + tools + '\n</tool_calls>\n' +
    '<patterns>\n' + lines.join('\n') + '\n</patterns>\n<final_answer>\n' + cpSlice(a.answer, 4000) + '\n</final_answer>\n' +
    'Answer with exactly two lines and nothing else:\n' +
    'ACE_REVIEW: N% | Xm saved | one-line reason   (N = how much the patterns helped; X = minutes a human developer saved)\n' +
    'ACE_USED: the comma-separated ids of the patterns the task DEMONSTRABLY applied (visible in its tool calls or answer), or none'
}
// ACE_USED ids, whitelisted against the injected set, injected order
export function parseUsedIds(text: string, injected: string[]): string[] {
  const m = /ACE_USED:\s*([^\n]*)/.exec(text || '')
  if (!m) return []
  const named = new Set(m[1].split(/[\s,;]+/).map(x => x.replace(/^[`'"<\[(]+|[`'">\]).]+$/g, '')).filter(Boolean))
  return injected.filter(id => named.has(id))
}

// ace_before_task.check_eval_request_and_review text. §24: the file is repo-controlled and reaches the model's
// context, so every field is a number (finite int/float; anything else 0), never text.
export function evalInjection(d: any): string {
  const g = (k: string) => {
    const v = d?.[k]
    if (v instanceof PyFloat) return Number.isFinite(v.v) ? pyFloatRepr(v.v) : '0'
    return typeof v === 'number' && Number.isFinite(v) ? String(v) : '0'
  }
  // never "0% relevance" / "0 domains": an unknown number is left out
  const stats = (g('avg_relevance') !== '0' ? `${g('avg_relevance')}% relevance, ` : '') + (g('domains') !== '0' ? `${g('domains')} domains, ` : '')
  return `<!-- ACE Self-Eval Request: Previous task used ${g('patterns_injected')} patterns ` +
    `(${stats}${g('tools_executed')} tools). ` +
    `As a human developer, how much time did these patterns save? ` +
    `Without ACE, a developer would search docs, explore codebases, ask colleagues, or trial-and-error. ` +
    `Rate from a HUMAN DEVELOPER perspective, not AI perspective. ` +
    `Include in your response: ACE_REVIEW: N% | Xm saved | one-line reason -->`
}

// §31 / item H2 "actually used" (patterns_used_state.used_pattern_ids): evidence in what the task DID. Its id in the
// final message / report or the tool inputs, or >= 2 of its distinctive tokens in the tool-call inputs; a token in
// more than 30% of the injected patterns (and more than one) is too generic. Injected order.
export const CONTENT_CAP = 600, USED_MESSAGE_CAP = 50000
const TOOL_INPUT_KEYS = ['command', 'file_path', 'path', 'pattern', 'glob', 'notebook_path', 'url']
const TOKEN_STOP = new Set(['and/or', 'e.g.', 'i.e.', 'etc.', 'n/a', 'w/o', 'http://', 'https://', 'true/false', 'yes/no'])
const STRIP = new Set(Array.from("`'\"()[]{}<>,;:!?*"))
// tool_haystack: lowercased tool-call inputs (Bash commands, paths, Grep/Glob patterns, Edit targets), never edit bodies
export function toolHaystack(inputs: any[]): string {
  const parts: string[] = []
  for (const ti of inputs ?? []) if (ti && typeof ti === 'object') for (const k of TOOL_INPUT_KEYS) if (typeof ti[k] === 'string' && ti[k]) parts.push(ti[k])
  return parts.join('\n').toLowerCase()
}
const qualifies = (w: string) => {
  if (cps(w).length < 4 || TOKEN_STOP.has(w)) return false
  if (w.includes('/') || w.includes('_') || w.includes('::') || /[a-z][A-Z]/.test(w)) return true
  if (/^--?[A-Za-z][A-Za-z0-9_-]*$/.test(w)) return true
  return /[A-Za-z0-9_]\.[A-Za-z0-9_]/.test(w)
}
export function distinctiveTokens(content: unknown): Set<string> {
  const text = cpSlice(String(content ?? ''), CONTENT_CAP), toks = new Set<string>()
  for (const m of text.matchAll(/`([^`\n]+)`/g)) {
    const span = normWs(m[1])
    if (cps(span).length >= 4) toks.add(span.toLowerCase())
    const w = span.split(' ')
    if (w.length >= 2 && cps(w[0] + ' ' + w[1]).length >= 4) toks.add((w[0] + ' ' + w[1]).toLowerCase())
  }
  for (const raw of text.split(/\s+/).filter(Boolean)) {
    let a = Array.from(raw), i = 0, j = a.length
    while (i < j && STRIP.has(a[i])) i++
    while (j > i && STRIP.has(a[j - 1])) j--
    let w = a.slice(i, j).join('')
    while (w.endsWith('.')) w = w.slice(0, -1)
    if (qualifies(w)) toks.add(w.toLowerCase())
  }
  for (const t of [...toks]) if (TOKEN_STOP.has(t)) toks.delete(t)
  return toks
}
export function usedPatternIds(ids: string[], contents: Record<string, string>, message: string | undefined, haystack = ''): string[] {
  const msg = cpSlice(normWs(message), USED_MESSAGE_CAP)
  const list = (ids ?? []).filter(id => typeof id === 'string' && id)
  const toks = new Map(list.map(id => [id, distinctiveTokens(contents?.[id])] as const))
  const df = new Map<string, number>()
  for (const ts of toks.values()) for (const t of ts) df.set(t, (df.get(t) ?? 0) + 1)
  const generic = new Set([...df].filter(([, n]) => n > 1 && n > 0.3 * list.length).map(([t]) => t))
  return list.filter(id => {
    if (msg.includes(id) || haystack.includes(id.toLowerCase())) return true
    if (!haystack) return false
    let hits = 0
    for (const t of toks.get(id)!) if (!generic.has(t) && haystack.includes(t)) hits++
    return hits >= 2
  })
}
export function injectedContents(patterns: any[], ids: string[]): Record<string, string> {
  const byId = new Map<string, unknown>(), out: Record<string, string> = {}
  for (const p of patterns ?? []) if (p && !byId.has(p.id)) byId.set(p.id, p.content)
  for (const id of ids) { const c = byId.get(id); if (c) out[id] = cpSlice(String(c), CONTENT_CAP) }  // injected order (Python parity)
  return out
}
// §31: applied_log_ids = the USED ids that have a retrieval log id, for every variant. Server 5.15.8: more than 20 in
// one trace count as "all shown" (the trace falls to COLD), so `used` comes ordered by evidence and is cut at 20.
export const APPLIED_LOG_IDS_CAP = 20
export function appliedLogIds(used: string[], rlog: Record<string, number>): { ids: number[]; capped: boolean } {
  const all = used.filter(id => id in rlog).map(id => rlog[id])
  return { ids: all.slice(0, APPLIED_LOG_IDS_CAP), capped: all.length > APPLIED_LOG_IDS_CAP }
}

// prompt <= 300 chars with a phrase as a whole word, not right after "nicht"/"not". The longest hit wins (ties: list order).
export const REJECTION_PHRASES = ["falsch", "stimmt nicht", "geht nicht", "funktioniert nicht", "klappt nicht", "rückgängig",
  "mach das rückgängig", "immer noch kaputt", "immer noch nicht", "nicht das was ich wollte", "das war nicht gemeint", "doch nicht",
  "das ist falsch", "kaputt gemacht", "wrong", "that's wrong", "doesn't work", "does not work", "not working", "still broken",
  "still not", "not what i asked", "that broke", "you broke"]
export const REJECTION_PREV_MAX_AGE_S = 6 * 3600
const isWordChar = (c: string) => /[\p{L}\p{N}_]/u.test(c)
export function rejectionMatch(text: string | undefined): string | null {
  const low = String(text ?? '').trim().toLowerCase().replace(/[\u2018\u2019]/g, "'")
  if ([...low].length > 300) return null
  let best: string | null = null
  for (const phrase of REJECTION_PHRASES) {
    for (let i = low.indexOf(phrase); i >= 0; i = low.indexOf(phrase, i + 1)) {
      const j = i + phrase.length
      if ((i > 0 && isWordChar(low[i - 1])) || (j < low.length && isWordChar(low[j]))) continue
      const before = low.slice(0, i), words = before.split(/\s+/).filter(Boolean)
      if (words.length && before !== before.trimEnd() && ['nicht', 'not'].includes(words[words.length - 1])) continue
      if (best === null || phrase.length > best.length) best = phrase
      break
    }
  }
  return best
}
