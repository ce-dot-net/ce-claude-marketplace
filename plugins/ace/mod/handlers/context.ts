// The session's context step (8.1.0), started by session.start: export the core's ids, adopt a legacy binding,
// remember the remote, then ONE background `status` (verify), the ONE `context` row, the ▼ status and the band.
import { ADOPT_LINE, WARN_LINES, type Ctx, type State, adopt, cliIds, contextRow, exportEnv, localState, problemLine, remember, untracked, verify } from '../context/index.ts'
import { run, writePrivate } from '../io/fs.ts'
import { cliRun } from '../io/cli.ts'
import { installer } from '../io/installer.ts'
import { nowIso } from '../io/log.ts'
import { type Load, dataRoot, resolveContextOnce } from '../io/state.ts'
import { pyDumps } from '../lib/pyjson.ts'
import { APPEND_SH } from '../lib/sh.ts'

const BAND = { plugin: 'ace', key: 'band' } as const
export const SHORT: Record<string, string> = { unbound: 'nicht verbunden', not_logged_in: 'nicht angemeldet', expired: 'Anmeldung abgelaufen',
  project_not_found: 'Projekt fehlt', no_access: 'kein Zugriff', server_error: 'Server', cli_missing: 'ace-cli fehlt',
  config_refused: 'Konfig abgelehnt', config_invalid: 'Konfig ungültig' }

// One row into <log root>/.claude/data/logs (APPEND_SH refuses symlinks). An unbound unrelated repo gets no log dir.
export async function contextLog($: any, c: Ctx, row: any, state: State) {
  if (state === 'unbound' && !await $.fs.exists(`${c.root}/.claude/data/logs`).catch(() => false)) return
  await run($, ['/bin/sh', '-c', APPEND_SH, 'sh', `${c.root}/.claude/data/logs/ace-relevance.jsonl`, c.root], { stdin: pyDumps(row) + '\n' })
}
// ▼ only on problems; nothing (cleared) when ok or still checking.
export function showStatus($: any, state: State | null | undefined) {
  $.ui.status(state && state !== 'ok' ? `ACE ▼ ${SHORT[state] ?? state}` : undefined)
}
// The band's projects: name-matched suggestion for unbound, the pick list for not_found / no_access.
export async function projectList($: any, c: Ctx): Promise<{ orgId: string, projectId: string, name: string }[]> {
  const r = await cliRun($, null, ['projects', '--json'], { timeoutMs: 15_000 })
  if (r.exitCode !== 0) return []
  try {
    const j = JSON.parse(r.stdout)
    const list: any[] = Array.isArray(j) ? j : j.projects ?? []
    return list.filter(p => p && (p.project_id || p.id)).map(p => ({ orgId: String(p.org_id ?? p.orgId ?? ''), projectId: String(p.project_id ?? p.id),
      name: String(p.project_name ?? p.name ?? p.project_id) }))
  } catch { void c; return [] }
}
export function suggest(projects: { orgId: string, projectId: string, name: string }[], root: string) {
  const name = (root.split('/').pop() ?? '').toLowerCase()
  if (!name) return null
  return projects.find(p => p.name.toLowerCase() === name) ?? projects.find(p => p.name.toLowerCase().includes(name) || name.includes(p.name.toLowerCase())) ?? null
}
export const INSTALL_FAILED = 'ACE ▼ ace-cli konnte nicht automatisch installiert werden'
// `retry`: the automatic install failed; the band's one action is then [Erneut versuchen] (the same installer).
export async function publish($: any, L: Load, c: Ctx, state: State | null, retry?: string) {
  L.ctxState = state
  showStatus($, state)
  let projects: { orgId: string, projectId: string, name: string }[] = []
  if (state === 'unbound' || state === 'project_not_found' || state === 'no_access') projects = await projectList($, c)
  const band = { state, line: retry ? INSTALL_FAILED : problemLine(state), retry: retry ?? null, projectId: (c as any).projectId ?? null,
    suggestion: state === 'unbound' ? suggest(projects, c.root) : null, projects, picking: false, dismissed: false }
  await $.state.set(BAND, band)
  $.ui.log(`ace band ${JSON.stringify({ state, suggestion: band.suggestion, retry: band.retry })}`, { to: 'debug' })  // the debug log says what the band shows
}
// The whole step. Never throws: the hooks still run on whatever binding resolved.
export async function startContext($: any, L: Load, cwd: string) {
  const gen = ++L.reprobeGen  // a (re)start stops an earlier re-probe chain
  try {
    const c = await resolveContextOnce($, L, cwd)
    const now = await $.clock.now()
    await exportEnv($, c, now)
    const git = (argv: string[], init?: any) => run($, argv, init)
    const refused = async (what: string, reason: string) => contextLog($, c, { timestamp: await nowIso($), event: 'write_refused', what, reason, chain: 'mod' }, 'ok')
    const root = await dataRoot($)
    await remember($, c, cwd, root, (p, t) => writePrivate($, p, t), now).catch(() => false)
    const a = await adopt($, c, L.env0 ?? {}, cwd, (argv, o) => cliRun($, null, argv, o), git, refused)
    if (a && !a.path) $.ui.log(WARN_LINES.worktree_topology_untrusted)
    else if (a?.path && await untracked(a.path.replace(/\/\.ace\/config\.json$/, ''), git)) $.ui.log(ADOPT_LINE)
    const local = localState(c)
    if (local) {
      await publish($, L, c, local)
      await logOnce($, L, c, local)
      return
    }
    L.verifying = (async () => {
      const probe = () => verify(c, argv => cliRun($, c as any, argv, { timeoutMs: 20_000 }))
      let st = await probe()
      let retry: string | undefined, installed = false
      if (st === 'cli_missing') {
        installed = true  // 8.1.1: the pinned CLI is installed in the background; quiet while it runs, a band only on failure
        const e = await installer($, ['--ensure'], 30_000)
        if (e.state === 'started' || e.state === 'running') {
          await publish($, L, c, null)
          const w = await installer($, ['--wait'], 450_000)
          if (w.state === 'ok') st = await probe()  // the CLI is resolved per call: no restart
          else retry = w.detail || w.state
        } else if (e.state === 'failed') retry = e.detail || 'failed'
      }
      await publish($, L, c, st === 'ok' ? null : st, st === 'cli_missing' ? retry : undefined)
      await logOnce($, L, c, st)
      if (st === 'server_error') reprobeLater($, L, c, gen, 0)  // 8.2.4: only this state is transient
      if (st === 'ok' && !installed) await installer($, ['--ensure'], 30_000)  // 8.1.2: AFTER the status/band: quiet background `npm rebuild better-sqlite3` when only the binding is missing; never a band
    })().catch(() => undefined)
  } catch { /* the hooks keep the binding they resolved */ }
}
// 8.2.4 self-heal of a `server_error` band (a 502/timeout at session start, e.g. a deploy restart). One $.clock.after at a
// time (no loop, no interval): 15 s, 30 s, 60 s, then every 5 min, at most MAX_REPROBES tries (~2.3 h; a later successful
// search still heals it). The chain stops when the band is no longer server_error, on a new startContext, at session end
// (L.reprobeGen bumped) and with the module load (its timers go with it). A failing try is silent.
export const REPROBE_MS = [15_000, 30_000, 60_000], REPROBE_EVERY_MS = 300_000, MAX_REPROBES = 30
export const RECOVERED_LINE = 'ACE: Server wieder erreichbar'
const live = (L: Load, gen: number) => gen === L.reprobeGen && L.ctxState === 'server_error'
function reprobeLater($: any, L: Load, c: Ctx, gen: number, n: number) {
  if (n >= MAX_REPROBES) return
  $.clock.after(REPROBE_MS[n] ?? REPROBE_EVERY_MS, () => { void reprobe($, L, c, gen, n).catch(() => undefined) })
}
async function reprobe($: any, L: Load, c: Ctx, gen: number, n: number) {
  if (!live(L, gen)) return
  const st = await verify(c, argv => cliRun($, c as any, argv, { timeoutMs: 20_000 }))
  if (!live(L, gen)) return  // something else decided meanwhile (a search healed it, a rebind)
  if (st === 'server_error') return reprobeLater($, L, c, gen, n + 1)
  await publish($, L, c, st === 'ok' ? null : st)  // another state now (e.g. expired): that one, one-shot
  if (st === 'ok') $.ui.log(RECOVERED_LINE)
}
// A successful server search proves the server reachable: clear a server_error band (no extra request) and end the chain.
export async function serverReachable($: any, L: Load) {
  if (L.ctxState !== 'server_error' || !L.ctx) return
  L.reprobeGen++
  await publish($, L, L.ctx, null)
  $.ui.log(RECOVERED_LINE)
}
export async function logOnce($: any, L: Load, c: Ctx, state: State) {
  if (L.ctxLogged) return
  L.ctxLogged = true
  await contextLog($, c, contextRow(c, state, await nowIso($), 'session.start', await $.session.id()), state)
}
// The marker refresh re-exports ACE_CONTEXT so the Python chain keeps trusting it (MOD_FRESH_S 900 s).
export async function reexport($: any, L: Load) {
  if (L.ctx?.bound) await exportEnv($, L.ctx, await $.clock.now()).catch(() => undefined)
}
export { cliIds }
