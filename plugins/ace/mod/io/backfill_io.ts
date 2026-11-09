// 8.2.0 real I/O of the bootstrap backfill: sources (Claude Code transcripts, git), the HMAC ledger file with a per-install key,
// the engine/backfill.js calls, the resume time. The orchestration itself is lib/backfill_run.ts (all I/O injected).
// The plugin never holds a token: only engine/backfill.js talks to the server (through the core client).
import { readText, run, writePrivate } from './fs.ts'
import { engineScript, ids } from './spawn.ts'
import { dataRoot, uuid } from './state.ts'
import { buildItems, runBackfill, type Built, type Deps, type EngineAnswer } from '../lib/backfill_run.ts'
import { GIT_LOG_ARGV, GIT_MERGES_ARGV } from '../lib/backfill_git.ts'
import { BACKFILL_FLAG_FILE, storedBackfill } from '../lib/cohort.ts'
import { emptyLedger, parse, serialize, type Ledger } from '../lib/ledger.ts'
import { safeComponent } from '../lib/state.ts'

const MAX_FILES = 200, MAX_FILE_BYTES = 4 * 1024 * 1024 - 1024  // $.fs.read is text only, 4 MiB
const RESUME = { plugin: 'ace', key: 'backfill-resume' } as const

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
export async function collect($: any, c: C, days: number, limit: number): Promise<Built> {
  const ledger = await loadLedger($, c)
  return buildItems({ projectId: c.projectId, sessions: await readSessions($, c), gitLog: await gitText($, c, GIT_LOG_ARGV, days),
    mergeLog: await gitText($, c, GIT_MERGES_ARGV, days), limit, ledger })
}

function engineCall($: any, script: string, c: C) {
  const base = ['node', script]
  const tail = ids({ org: c.orgId, project: c.projectId } as any)
  const env: Record<string, string> = { ACE_PROJECT_ID: c.projectId, ...(c.orgId ? { ACE_ORG_ID: c.orgId } : {}) }
  return async (cmd: 'post' | 'get', extra: string[], stdin?: string): Promise<EngineAnswer> => {
    let r: any
    try { r = await $.process.run([...base, cmd, ...tail, ...extra], { stdin, env, timeoutMs: 120_000 }) } catch { return { exit: 1 } }
    if (r.exitCode !== 0) return { exit: r.exitCode ?? 1 }
    try {
      const j = JSON.parse(String(r.stdout ?? '').trim().split('\n').pop() ?? '')
      return typeof j?.status === 'number' ? { exit: 0, status: j.status, body: j.body ?? null } : { exit: 1 }
    } catch { return { exit: 1 } }
  }
}
// The backfill phase after a confirmed bootstrap: flag on, engine there, resume time passed, then the injected loop. Returns the lines to show.
export async function backfillPhase($: any, c: C, o: { days: number, limit: number }): Promise<string[]> {
  if (!await flagOn($, c.root)) return ['Backfill: Server unterstützt es noch nicht']
  const script = await engineScript($, 'backfill.js')
  if (!script) return ['Backfill: Engine nicht verfügbar (engine/backfill.js fehlt oder ACE_ENGINE=cli), nichts gesendet']
  const resume = ((await $.state.get(RESUME)) as any)?.value?.at
  const now = await $.clock.now()
  if (typeof resume === 'number' && resume > now) return [`Backfill: Kontingent für heute erreicht, weiter ab ${new Date(resume).toISOString().slice(0, 16).replace('T', ' ')} UTC`]
  const built = await collect($, c, o.days, o.limit)
  const call = engineCall($, script, c)
  let t = now  // the mocked/real mod clock, refreshed after every sleep (Deps.now is synchronous)
  const d: Deps = {
    post: body => call('post', [], JSON.stringify(body)),
    get: job => call('get', ['--job', job]),
    sleep: async ms => { await run($, ['sleep', String(ms / 1000)], { timeoutMs: ms + 5000 }); t = await $.clock.now() },
    now: () => t,
    loadLedger: () => loadLedger($, c), saveLedger: l => saveLedger($, c, l),
    setResume: async ms => { await $.state.set(RESUME, { at: ms }) },
  }
  return (await runBackfill(built.items, d)).lines
}
