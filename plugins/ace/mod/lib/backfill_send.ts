// 8.2.0 backfill send helpers (pure, unwired, no I/O): task -> server item, batching, response classification, job status -> ledger.
// Server contract: POST /traces/backfill {source:'bootstrap', items:[{idempotency_key, occurred_at, trace}]}, 1..20 items, body <= 5 MiB.
import { buildTrace } from './trace.ts'
import { safeText } from './backfill_git.ts'
import type { ToolRec } from './evidence.ts'
import { add, MAX_ATTEMPTS, type Ledger } from './ledger.ts'

export type Item = { idempotency_key: string, occurred_at: string, trace: any }
export const MAX_ITEMS = 20
export const MAX_BODY = 5_242_880
const KEY_RE = /^bootstrap:[0-9a-f]{32}$/
const BASE = new TextEncoder().encode(JSON.stringify({ source: 'bootstrap', items: [] })).length

const isoOf = (ms: unknown): string | null => {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms <= 0 || ms > 8.64e15) return null
  return new Date(ms).toISOString()  // always ends in Z
}

// Session tasks carry their trace (the caller sets `key` from taskKey); git tasks get a minimal trace through the live buildTrace.
export function toItem(task: any, kind: 'session' | 'git'): Item | null {
  if (!task || typeof task !== 'object' || typeof task.key !== 'string' || !KEY_RE.test(task.key)) return null
  const at = isoOf(task.endMs)
  if (!at) return null
  let trace: any
  if (kind === 'session') {
    if (!task.trace || typeof task.trace !== 'object') return null
    trace = { ...task.trace }
    // everything that leaves the machine goes through the strict git-side filter (unicode fold, key-word cut), not just redact
    if (typeof trace.task === 'string') trace.task = safeText(trace.task)
    if (Array.isArray(trace.trajectory)) trace.trajectory = trace.trajectory.map((s: any) => s && typeof s === 'object'
      ? { ...s, ...(typeof s.action === 'string' ? { action: safeText(s.action) } : {}), ...(typeof s.result === 'string' ? { result: safeText(s.result) } : {}) } : s)
    if (trace.result && typeof trace.result === 'object' && typeof trace.result.summary === 'string') trace.result = { ...trace.result, summary: safeText(trace.result.summary) }
  } else if (kind === 'git') {
    const files: string[] = Array.isArray(task.steps) ? task.steps.filter((s: unknown) => typeof s === 'string').map((s: string) => safeText(s)) : []
    const tools: ToolRec[] = files.map(f => ({ tool: 'Edit', action: `edit ${f}`, result: 'ok', failed: false, start_ms: task.endMs, end_ms: task.endMs }))
    const b = buildTrace({ userPrompt: `${task._merge === true ? 'Merged PR' : 'Git commit'} (untrusted text): ${safeText(String(task.task ?? ''))}`, tools, answer: '', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: at, effort: 'normal' })
    trace = b.trace
    trace.result.success = task.success === true  // a Revert is a failure, whatever the (all-ok) file steps say
  } else return null
  for (const f of ['session_id', 'retrieval_id', 'conversation_id', 'agent_id', 'parent_agent_id', 'feedback']) delete trace[f]
  trace.playbook_used = []   // the server clears these anyway; empty keeps the live shape valid
  trace.applied_log_ids = []
  return { idempotency_key: task.key, occurred_at: at, trace }
}

const enc = new TextEncoder()
// Chunks of <= 20 items whose serialized body is <= 5 MiB (UTF-8 bytes). An item that alone exceeds it, or repeats a key, is skipped (never sent).
export function batches(items: Item[]): { batches: Item[][], skipped: number } {
  const out: Item[][] = []
  let skipped = 0, cur: Item[] = [], size = BASE, seen = new Set<string>()
  if (!Array.isArray(items)) return { batches: out, skipped }
  for (const it of items) {
    let n = -1
    try { n = enc.encode(JSON.stringify(it)).length } catch { /* unserializable */ }
    if (n < 0 || BASE + n > MAX_BODY || seen.has(it?.idempotency_key)) { skipped++; continue }
    const add1 = n + (cur.length ? 1 : 0)
    if (cur.length >= MAX_ITEMS || size + add1 > MAX_BODY) { out.push(cur); cur = []; size = BASE }
    cur.push(it); size += n + (cur.length > 1 ? 1 : 0)
    seen.add(it.idempotency_key)
  }
  if (cur.length) out.push(cur)
  return { batches: out, skipped }
}

export type Class =
  | { kind: 'accepted', job_id: string, accepted: number, duplicates: number, statusUrl: string, poll: boolean }
  | { kind: 'capability_off' }
  | { kind: 'too_large', code: string, limit: number }
  | { kind: 'invalid', status: number, detail: string }
  | { kind: 'quota', limit: number, current: number, resumeAfter: number }
  | { kind: 'retry', status: number }

const obj = (b: unknown): any => {
  let j: unknown = b
  if (typeof b === 'string') { try { j = JSON.parse(b) } catch { return {} } }
  return j && typeof j === 'object' && !Array.isArray(j) ? j : {}
}
const num = (v: unknown, d = 0) => typeof v === 'number' && Number.isFinite(v) ? v : d
const str = (v: unknown, max = 200) => typeof v === 'string' ? v.slice(0, max) : ''
const DAY = 86_400_000

// Never throws. status 0 / NaN / missing = network failure. nowMs only feeds the 429 resume time (next UTC midnight, strictly later).
export function classify(status: number, body: unknown, nowMs: number = Date.now()): Class {
  const j = obj(body)
  if (status === 202) {
    const id = str(j.job_id, 100)
    // accepted 0 = the batch held only duplicates: already submitted, and GET on that job id answers 404, so the caller must not poll
    return id ? { kind: 'accepted', job_id: id, accepted: num(j.accepted), duplicates: num(j.duplicates), statusUrl: str(j.status_url), poll: num(j.accepted) > 0 } : { kind: 'retry', status }
  }
  if (status === 404) return { kind: 'capability_off' }
  if (status === 413) return { kind: 'too_large', code: str(j.code, 60), limit: num(j.limit) }
  if (status === 422) return { kind: 'invalid', status, detail: str(typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j.error ?? ''), 300) }
  if (status === 429) {
    const now = Number.isFinite(nowMs) ? nowMs : Date.now()
    return { kind: 'quota', limit: num(j.limit), current: num(j.current), resumeAfter: (Math.floor(now / DAY) + 1) * DAY }
  }
  if (typeof status === 'number' && status >= 400 && status < 500) return { kind: 'invalid', status, detail: str(j.error) }
  return { kind: 'retry', status: num(status) }
}

export type Report = { sent: number, partial: number, failed: number, skipped: number, patternsCreated: number, failedChunks: number, finished: boolean }

// GET /traces/backfill/<id> body -> ledger updates + a readable report. pending/processing/unknown items change nothing.
export function applyJob(l: Ledger, job: unknown, nowMs: number): Report {
  const j = obj(job)
  const r: Report = { sent: 0, partial: 0, failed: 0, skipped: 0, patternsCreated: 0, failedChunks: 0, finished: j.state === 'finished' }
  const items: any[] = Array.isArray(j.items) ? j.items : []
  let pc = 0, fc = 0
  for (const raw of items) {
    const it = obj(raw), key = it.idempotency_key
    if (typeof key !== 'string' || !KEY_RE.test(key)) continue
    const gone = it.error === 'expired' || it.error === 'project_gone'
    if (it.state === 'done') {
      if (!add(l, key, 'sent', nowMs)) continue
      r.sent++
      pc += num(it.patterns_created); fc += num(it.failed_chunks)
      if (num(it.failed_chunks) > 0) r.partial++
    } else if (gone) {
      for (let i = 0; i < MAX_ATTEMPTS; i++) add(l, key, 'failed', nowMs)  // the ledger's retry cap turns it into skipped-failed
      r.failed++
    } else if (it.state === 'skipped') {
      if (add(l, key, 'skipped', nowMs)) r.skipped++
    } else if (it.state === 'failed') {
      if (add(l, key, 'failed', nowMs)) r.failed++
    }
  }
  r.patternsCreated = typeof j.patterns_created === 'number' ? num(j.patterns_created) : pc
  r.failedChunks = typeof j.failed_chunks === 'number' ? num(j.failed_chunks) : fc
  return r
}

export function reportLine(r: Report): string {
  const x = obj(r) as Partial<Report>
  const parts = [`${num(x.sent)} gesendet${num(x.partial) ? ` (${x.partial} teilweise)` : ''}`]
  if (num(x.failed)) parts.push(`${x.failed} fehlgeschlagen`)
  if (num(x.skipped)) parts.push(`${x.skipped} übersprungen`)
  if (num(x.patternsCreated)) parts.push(`${x.patternsCreated} Patterns erstellt`)
  return `${x.finished ? 'Backfill fertig' : 'Backfill läuft noch'}: ${parts.join(', ')}`
}
