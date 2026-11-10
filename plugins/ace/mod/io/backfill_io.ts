// 8.2.0 real I/O of the bootstrap backfill: sources (Claude Code transcripts, git), the HMAC ledger file with a per-install key,
// the engine/backfill.js calls, the resume time. The orchestration itself is lib/backfill_run.ts (all I/O injected).
// The plugin never holds a token: only engine/backfill.js talks to the server (through the core client).
import { readText, run, writePrivate } from './fs.ts'
import { APPEND_SH } from '../lib/sh.ts'
import { pyDumps } from '../lib/pyjson.ts'
import { engineScript, ids } from './spawn.ts'
import { dataRoot, uuid } from './state.ts'
import { POLL_MS, buildItems, finalLines, newRun, progress, runActive, startLine, stepBackfill, type Built, type Deps, type EngineAnswer, type RunState, type Source } from '../lib/backfill_run.ts'
import type { Item } from '../lib/backfill_send.ts'
import { GIT_LOG_ARGV, GIT_MERGES_ARGV } from '../lib/backfill_git.ts'
import { BACKFILL_FLAG_FILE, storedBackfill } from '../lib/cohort.ts'
import { emptyLedger, parse, serialize, type Ledger } from '../lib/ledger.ts'
import { safeComponent } from '../lib/state.ts'

const MAX_FILES = 200, MAX_FILE_BYTES = 4 * 1024 * 1024 - 1024  // $.fs.read is text only, 4 MiB
const RESUME = { plugin: 'ace', key: 'backfill-resume' } as const
const RUN = { plugin: 'ace', key: 'backfill-run' } as const   // the run marker: RunState JSON (lib/backfill_run.ts)

type C = { root: string, orgId?: string, projectId: string }
export const encodeProjectDir = (root: string) => root.replace(/[^A-Za-z0-9]/g, '-')  // Claude Code's ~/.claude/projects/<encoded cwd>

export async function flagOn($: any, root: string): Promise<boolean> {
  return storedBackfill(await readText($, `${await dataRoot($)}/${BACKFILL_FLAG_FILE}`), await $.clock.now())
}
async function ledgerPath($: any, c: C): Promise<string> { return `${await dataRoot($)}/projects/${safeComponent(c.projectId)}/backfill-ledger.tsv` }
// Per-install random key, created on first use (0600). Not secrecy against the user: an integrity guard against a hand-edited ledger.
async function secret($: any): Promise<string> {
  const p = `${await dataRoot($)}/backfill.key`
  const have = (await readText($, p))?.trim()
  if (have && have.length >= 32) return have
  const k = uuid() + uuid()
  await writePrivate($, p, k)
  return k
}
export async function loadLedger($: any, c: C): Promise<Ledger> {
  try { return parse(await readText($, await ledgerPath($, c)) ?? '', await secret($)) } catch { return emptyLedger() }
}
export async function saveLedger($: any, c: C, l: Ledger) { await writePrivate($, await ledgerPath($, c), serialize(l, await secret($))) }

export async function readSessions($: any, c: C): Promise<{ text: string }[]> {
  const home = await $.env.get('HOME') ?? ''
  const dir = `${home}/.claude/projects/${encodeProjectDir(c.root)}`
  const list: any[] = await $.fs.list(dir).catch(() => [])
  const files = list.filter(f => String(f.name).endsWith('.jsonl') && !f.isLink && (f.size ?? 0) <= MAX_FILE_BYTES)
    .sort((a, b) => (b.mtimeMs ?? 0) - (a.mtimeMs ?? 0)).slice(0, MAX_FILES)
  const out: { text: string }[] = []
  for (const f of files) { const text = await readText($, `${dir}/${f.name}`); if (text) out.push({ text }) }
  return out
}
async function gitText($: any, c: C, argv: string[], days: number): Promise<string> {
  const r = await run($, [...argv, `--since=${days} days ago`], { cwd: c.root, timeoutMs: 60_000 })
  return r && r.exitCode === 0 ? String(r.stdout ?? '') : ''
}
export async function collect($: any, c: C, days: number, limit: number, sources?: readonly Source[]): Promise<Built> {
  const ledger = await loadLedger($, c)
  const has = (x: Source) => !sources || sources.includes(x)   // a source not listed is never read (no session files, no git call)
  return buildItems({ projectId: c.projectId, sessions: has('session') ? await readSessions($, c) : [], gitLog: has('git') ? await gitText($, c, GIT_LOG_ARGV, days) : '',
    mergeLog: has('merge') ? await gitText($, c, GIT_MERGES_ARGV, days) : '', limit, ledger, sources })
}

const lastLine = (t: unknown) => String(t ?? '').trim().split('\n').pop()?.slice(0, 200) ?? ''

function engineCall($: any, script: string, c: C) {
  const base = ['node', script]
  const tail = ids({ org: c.orgId, project: c.projectId } as any)
  const env: Record<string, string> = { ACE_PROJECT_ID: c.projectId, ...(c.orgId ? { ACE_ORG_ID: c.orgId } : {}) }
  return async (cmd: 'post' | 'get', extra: string[], stdin?: string): Promise<EngineAnswer> => {
    let r: any
    try { r = await $.process.run([...base, cmd, ...tail, ...extra], { stdin, env, timeoutMs: 120_000 }) } catch { return { exit: 1 } }
    if (r.exitCode !== 0) return { exit: r.exitCode ?? 1, stderr: lastLine(r.stderr) }
    try {
      const j = JSON.parse(String(r.stdout ?? '').trim().split('\n').pop() ?? '')
      return typeof j?.status === 'number' ? { exit: 0, status: j.status, body: j.body ?? null } : { exit: 1 }
    } catch { return { exit: 1 } }
  }
}

// Real deps of one step. `now` is the synchronous seam: refreshed from the mod clock before every step.
async function stepDeps($: any, c: C, script: string): Promise<{ d: Deps, call: ReturnType<typeof engineCall> }> {
  const call = engineCall($, script, c)
  let t = await $.clock.now()
  const d: Deps = {
    post: body => call('post', [], JSON.stringify(body)),
    get: job => call('get', ['--job', job]),
    now: () => t,
    loadLedger: () => loadLedger($, c), saveLedger: l => saveLedger($, c, l),
    log: async row => { const root = await dataRoot($); await run($, ['/bin/sh', '-c', APPEND_SH, 'sh', `${root}/backfill-log.jsonl`, root], { stdin: pyDumps({ timestamp: new Date(t).toISOString(), ...row }) + '\n' }) },
    setResume: async ms => { await $.state.set(RESUME, { at: ms }) },
  }
  return { d, call }
}
// The items of the running run, kept for the ticks of this module load (lost on a reload: rebuilt from the same sources + ledger).
const memo = new Map<string, Pick<Built, 'items' | 'sources' | 'noiseExcluded'>>()
const alive = new Set<string>()   // a tick chain exists in THIS module load (a reload empties it with the timers)

// ONE step of the run, then the next tick is planned (a chain of $.clock.after: no background loop; the marker holds the state).
async function tick($: any, key: string): Promise<void> {
  alive.add(key)
  let st: RunState | undefined
  try {
    st = ((await $.state.get(RUN)) as any).value ?? undefined
    if (!st?.args || keyOf(st) !== key) return
    const a = st.args, c: C = { root: a.root, orgId: a.orgId, projectId: a.projectId }
    const script = await engineScript($, 'backfill.js')
    if (!script) { st.stopped = 'Backfill: Engine nicht verfügbar, abgebrochen.'; st.lines.push(st.stopped); return await end($, st, key) }
    let m = memo.get(key)
    if (!m) { m = await collect($, c, a.days, a.limit, a.sources); memo.set(key, m) }
    const items = m.items
    const { d } = await stepDeps($, c, script)
    d.sources = m.sources
    d.noiseExcluded = m.noiseExcluded
    st.beat = await $.clock.now()
    const r = await stepBackfill(items, st, d)
    if (r.done) return await end($, st, key)
    await $.state.set(RUN, st)
    const n = await progress(items, st, d)
    $.ui.status(`Backfill ${n}/${st.total}`)
    $.clock.after(POLL_MS, () => { void tick($, key).catch(() => undefined) })
  } catch (err) {
    const base: RunState | undefined = st
    if (base) { const m = `Backfill: Fehler ${String(err).slice(0, 160)}`; base.lines.push(m); base.stopped = base.stopped ?? m; await end($, base, key).catch(() => undefined) }
    else await $.state.set(RUN, null).catch(() => undefined)
  }
}
// Run over (finished, stopped or failed): marker cleared first, then status off, one toast and one log entry.
async function end($: any, st: RunState, key: string): Promise<void> {
  memo.delete(key); alive.delete(key)
  await $.state.set(RUN, null).catch(() => undefined)
  $.ui.status(undefined)
  const lines = finalLines(st)
  $.ui.toast(`ACE: ${[lines[0], st.stopped].filter(Boolean).join(' ')}`.slice(0, 400))
  $.ui.log(lines.join('\n'))
}
const keyOf = (st: RunState) => `${st.startedAt}|${st.args?.projectId}`
// Module (re)load or session start: a fresh marker without a live chain in this load continues; a stale one is dropped.
export async function resumeBackfill($: any): Promise<void> {
  const v = ((await $.state.get(RUN)) as any).value
  if (!v) return
  if (!runActive(v, await $.clock.now())) { await $.state.set(RUN, null); return }
  if (alive.has(keyOf(v))) return
  alive.add(keyOf(v))
  $.clock.after(POLL_MS, () => { void tick($, keyOf(v)).catch(() => undefined) })
}
// The backfill phase after a confirmed bootstrap: flag on, engine there, resume time passed, no run active, then the run is STARTED
// (marker + first tick) and the command returns at once; the result arrives as a toast and a log line. Returns the lines to show.
export async function backfillPhase($: any, bound: C, o: { days: number, limit: number, project?: string, org?: string, sources?: Source[] }): Promise<string[]> {
  const c: C = { ...bound, projectId: o.project ?? bound.projectId, orgId: o.org ?? bound.orgId }  // --target-project: only the destination changes (ledger, keys, engine args, marker)
  if (!await flagOn($, c.root)) return ['Backfill: Server unterstützt es noch nicht']
  const script = await engineScript($, 'backfill.js')
  if (!script) return ['Backfill: Engine nicht verfügbar (engine/backfill.js fehlt oder ACE_ENGINE=cli), nichts gesendet']
  const resume = ((await $.state.get(RESUME)) as any)?.value?.at
  const now = await $.clock.now()
  if (typeof resume === 'number' && resume > now) return [`Backfill: Kontingent für heute erreicht, weiter ab ${new Date(resume).toISOString().slice(0, 16).replace('T', ' ')} UTC`]
  if (runActive(((await $.state.get(RUN)) as any).value, now)) return ['Backfill läuft bereits']
  const built = await collect($, c, o.days, o.limit, o.sources)
  const st = newRun(built.items.length, now)
  if (!built.items.length) {  // nothing to send: no run, the one step answers the line
    const { d } = await stepDeps($, c, script)
    await stepBackfill([], st, d)
    return finalLines(st)
  }
  st.args = { root: c.root, orgId: c.orgId, projectId: c.projectId, days: o.days, limit: o.limit, ...(o.sources ? { sources: o.sources } : {}) }
  await $.state.set(RUN, st)
  const key = keyOf(st)
  memo.set(key, built); alive.add(key)
  $.clock.after(1, () => { void tick($, key).catch(() => undefined) })
  return [startLine(built.items.length)]
}
