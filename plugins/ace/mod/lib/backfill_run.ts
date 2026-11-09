// 8.2.0 backfill orchestration, ALL I/O injected (post/get/sleep/now/ledger/resume): item building, preview text, the sequential send loop.
// Pure of `$`: io/backfill_io.ts supplies the real post/get (engine/backfill.js), ledger file and clock; tests supply fakes.
import { readSession, selectTasks, taskKey } from './backfill.ts'
import { readGitLog, readMergeLog } from './backfill_git.ts'
import { applyJob, batches, classify, reportLine, toItem, type Item, type Report } from './backfill_send.ts'
import { add, pending, type Ledger } from './ledger.ts'

export const DEFAULT_LIMIT = 100, MAX_LIMIT = 100
export const POLL_MS = 60_000, MAX_POLLS = 400   // ~6.7 h of 60 s polls per job: a bound, never an endless loop
export const SECONDS_PER_TRACE = 70              // the server team's rule of thumb

// `--limit N` (1..100, `--limit=N` too) out of the bootstrap arguments; `rest` is what is left for parseBootstrapArgs.
export function parseLimit(args: string): { ok: true, limit: number, rest: string } | { ok: false } {
  const toks = args.trim().split(/\s+/).filter(Boolean), rest: string[] = []
  let limit: number | undefined
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i]
    if (t !== '--limit' && !t.startsWith('--limit=')) { rest.push(t); continue }
    const v = t === '--limit' ? toks[++i] : t.slice(8)
    if (limit !== undefined || v === undefined || !/^\d{1,3}$/.test(v)) return { ok: false }
    const n = Number(v)
    if (n < 1 || n > MAX_LIMIT) return { ok: false }
    limit = n
  }
  return { ok: true, limit: limit ?? DEFAULT_LIMIT, rest: rest.join(' ') }
}

export type Built = { items: Item[], sessionTasks: number, gitTasks: number, skipped: number }
// Session transcripts + git logs -> at most `limit` items (best ranked), tasks the ledger already finished are skipped first.
export function buildItems(o: { projectId: string, sessions: { text: string, sessionId?: string }[], gitLog: string, mergeLog: string, limit: number, ledger: Ledger }): Built {
  const cands: any[] = []
  let sessionTasks = 0
  for (const s of o.sessions) {
    for (const t of readSession(s.text, { sessionId: s.sessionId }).tasks) { sessionTasks++; cands.push({ ...t, key: taskKey(o.projectId, t.sessionId, t.index), _kind: 'session' }) }
  }
  const git = [...(o.gitLog ? readGitLog(o.gitLog, { projectId: o.projectId }) : []), ...(o.mergeLog ? readMergeLog(o.mergeLog, { projectId: o.projectId }).map(t => ({ ...t, _merge: true })) : [])]
  for (const g of git) cands.push({ ...g, _kind: 'git' })
  const open = new Set(pending(o.ledger, cands.map(c => c.key)))
  const fresh = cands.filter(c => open.has(c.key))
  const items: Item[] = []
  for (const c of selectTasks(fresh, o.limit)) { const it = toItem(c, c._kind); if (it) items.push(it) }
  return { items, sessionTasks, gitTasks: git.length, skipped: cands.length - fresh.length }
}

export function duration(n: number): string {
  const min = Math.ceil(n * SECONDS_PER_TRACE / 60)
  return min < 60 ? `etwa ${min} Minuten` : `etwa ${(min / 60).toFixed(1).replace('.', ',')} Stunden`
}
export function previewLines(b: Built, o: { flag: boolean, limit: number }): string[] {
  if (!o.flag) return ['Backfill: Server unterstützt es noch nicht']
  const n = b.items.length
  const out = [`Backfill: ${b.sessionTasks} Session-Aufgaben, ${b.gitTasks} Git-Aufgaben (Fix/Revert + Merges) im Fenster, ${b.skipped} schon gesendet (übersprungen)`,
    `${n} Aufgaben werden gesendet (Limit ${o.limit}, die am besten bewerteten)`]
  if (n) out.push(`Dauer: ${duration(n)} (Richtwert ${SECONDS_PER_TRACE} s pro Trace, der Server verarbeitet im Hintergrund)`,
    'Aufgaben (Titel, Dateinamen, redigierte Texte) verlassen den Rechner.')
  return out
}

export type EngineAnswer = { exit: number, status?: number, body?: any }
export type Deps = {
  post: (body: { source: string, items: Item[] }) => Promise<EngineAnswer>
  get: (job: string) => Promise<EngineAnswer>
  sleep?: (ms: number) => Promise<void>   // only the synchronous driver runBackfill waits with it; the mod's detached run uses $.clock.after ticks
  now: () => number
  loadLedger: () => Promise<Ledger>
  saveLedger: (l: Ledger) => Promise<void>
  setResume: (ms: number) => Promise<void>
}
const NO_AUTH = 'Backfill gestoppt: nicht angemeldet (401), bitte /ace:ace-login ausführen. Nichts vermerkt.'
const NO_PLAN = 'Backfill gestoppt: Abo/Zahlung nötig (402), bitte Abo prüfen. Nichts vermerkt.'
const LATER = 'Backfill gestoppt: Server gerade nicht erreichbar, später erneut ausführen (bereits Gesendetes bleibt vermerkt).'

// Run marker: the JSON state of one backfill run (kept in $.state), enough to continue after a module reload. Single flight + TTL.
export const RUN_TTL_MS = 3 * 3_600_000   // a marker whose last beat is older than this is stale (crashed run): ignored
export type RunState = { startedAt: number, beat: number, total: number, posted: string[], job?: string, polls: number, report: Report, lines: string[], stopped?: string,
  args?: { root: string, orgId?: string, projectId: string, days: number, limit: number } }
export const newRun = (total: number, now: number): RunState => ({ startedAt: now, beat: now, total, posted: [], polls: 0, lines: [],
  report: { sent: 0, partial: 0, failed: 0, skipped: 0, patternsCreated: 0, failedChunks: 0, finished: false } })
export const runActive = (v: any, now: number): v is RunState => !!v && typeof v.beat === 'number' && now - v.beat >= 0 && now - v.beat < RUN_TTL_MS
export const startLine = (n: number) => `Backfill gestartet: ${n} Aufgaben, läuft im Hintergrund (ca. ${Math.ceil(n * SECONDS_PER_TRACE / 60)} Min). Ergebnis folgt als Meldung.`
export const finalLines = (st: RunState): string[] => [reportLine(st.report), ...st.lines, ...(st.stopped ? ['Ledger gespeichert; ein erneuter Lauf macht dort weiter.'] : [])]

// ONE step of a run (state `st` is mutated, plain JSON between steps): at most one job GET per call, plus any posts that can go
// without waiting. done=false means "call again after POLL_MS" (the server does at most 5 items a minute: never poll faster).
export async function stepBackfill(all: Item[], st: RunState, d: Deps): Promise<{ done: boolean }> {
  const stop = (m: string) => { st.stopped = m; st.lines.push(m) }
  const finish = () => { st.report.finished = !st.stopped; return { done: true } }
  const ledger = await d.loadLedger()
  const posted = new Set(st.posted)
  const open = new Set(pending(ledger, all.map(i => i.idempotency_key)))
  let todo = all.filter(i => open.has(i.idempotency_key) && !posted.has(i.idempotency_key))
  if (!todo.length && !st.job && !st.posted.length) { st.lines.push(all.length ? `Backfill: 0 Aufgaben zu senden, ${all.length} bereits gesendet` : 'Backfill: 0 Aufgaben zu senden'); return finish() }

  // true = job finished, false = ask again later, 'stop' = run ended
  async function pollOne(job: string): Promise<boolean | 'stop'> {
    if (st.polls++ >= MAX_POLLS) { stop('Backfill: der Server ist nach langem Warten noch nicht fertig, später erneut ausführen (Duplikate werden erkannt).'); return 'stop' }
    const g = await d.get(job)
    if (g.exit !== 0) { stop(g.exit === 1 ? 'Backfill gestoppt: keine Antwort beim Abfragen des Jobs, später erneut ausführen.' : `Backfill gestoppt: Job-Abfrage fehlgeschlagen (Engine exit ${g.exit}).`); return 'stop' }
    if (g.status === 404) return true            // unknown job: treated as submitted
    if (g.status === 401) { stop(NO_AUTH); return 'stop' }
    if (g.status === 402) { stop(NO_PLAN); return 'stop' }
    if (g.status !== 200) { stop(LATER); return 'stop' }
    const r = applyJob(ledger, g.body, d.now())
    await d.saveLedger(ledger)
    if (!r.finished) return false
    for (const k of ['sent', 'partial', 'failed', 'skipped', 'patternsCreated', 'failedChunks'] as const) st.report[k] += r[k]
    return true
  }

  for (;;) {
    if (st.job) {
      const p = await pollOne(st.job)
      if (p === 'stop') return finish()
      if (!p) return { done: false }
      st.job = undefined; st.polls = 0
    }
    const batch = batches(todo).batches[0]
    if (!batch) break
    const keys = batch.map(i => i.idempotency_key), gone = new Set(keys)
    todo = todo.filter(i => !gone.has(i.idempotency_key))
    st.posted.push(...keys)
    const a = await d.post({ source: 'bootstrap', items: batch })
    if (a.exit === 3) { stop('Backfill nicht gesendet: Gate fehlgeschlagen (Core/Client nicht nutzbar).'); break }
    if (a.exit === 1) { stop('Backfill gestoppt: keine Antwort vom Server, der Batch kam evtl. an. Ledger unverändert, Wiederholung ist sicher (Duplikate werden erkannt).'); break }
    if (a.exit !== 0) { stop(`Backfill nicht gesendet: Engine exit ${a.exit}.`); break }
    if (a.status === 401) { stop(NO_AUTH); break }
    if (a.status === 402) { stop(NO_PLAN); break }
    const c = classify(a.status ?? 0, a.body, d.now())
    if (c.kind === 'capability_off') { stop('Backfill: Server unterstützt es noch nicht, nichts gesendet.'); break }
    if (c.kind === 'quota') {
      await d.setResume(c.resumeAfter)
      stop(`Backfill gestoppt: Kontingent für heute erreicht (${c.current}/${c.limit}), weiter ab ${new Date(c.resumeAfter).toISOString().slice(0, 10)} (UTC).`)
      break
    }
    if (c.kind === 'retry') { stop(LATER); break }
    if (c.kind === 'too_large' || c.kind === 'invalid') {
      for (const it of batch) add(ledger, it.idempotency_key, 'failed', d.now())
      await d.saveLedger(ledger)
      st.report.failed += batch.length
      st.lines.push(`Backfill: Batch abgelehnt (${c.kind === 'invalid' ? `HTTP ${c.status} ${c.detail}`.trim() : `zu groß ${c.code}`}), ${batch.length} Aufgaben als Fehlversuch vermerkt.`)
      continue
    }
    if (!c.poll) { st.lines.push(`Backfill: ${c.duplicates || batch.length} Aufgaben waren dem Server bereits bekannt.`); continue }
    st.job = c.job_id; st.polls = 0
  }
  return finish()
}
// Fraction done for the status line: items of this run the ledger no longer holds as open.
export async function progress(all: Item[], st: RunState, d: Deps): Promise<number> {
  const open = new Set(pending(await d.loadLedger(), all.map(i => i.idempotency_key)))
  return all.filter(i => !open.has(i.idempotency_key)).length
}

// Synchronous driver (tests, and anything that may block): steps until done, waiting POLL_MS between steps with d.sleep.
export async function runBackfill(all: Item[], d: Deps): Promise<{ report: Report, lines: string[], stopped?: string }> {
  const st = newRun(all.length, d.now())
  for (;;) {
    const r = await stepBackfill(all, st, d)
    if (r.done) break
    await d.sleep!(POLL_MS)
  }
  return { report: st.report, lines: finalLines(st), stopped: st.stopped }
}
