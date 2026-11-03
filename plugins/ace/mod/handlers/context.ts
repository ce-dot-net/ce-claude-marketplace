// The session's context step (8.1.0), started by session.start: export the core's ids, adopt a legacy binding,
// remember the remote, then ONE background `status` (verify), the ONE `context` row, the ▼ status and the band.
import { ADOPT_LINE, WARN_LINES, type Ctx, type State, adopt, cliIds, contextRow, exportEnv, localState, problemLine, remember, untracked, verify } from '../context/index.ts'
import { run, writePrivate } from '../io/fs.ts'
import { cliRun } from '../io/cli.ts'
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
export async function publish($: any, L: Load, c: Ctx, state: State | null) {
  L.ctxState = state
  showStatus($, state)
  let projects: { orgId: string, projectId: string, name: string }[] = []
  if (state === 'unbound' || state === 'project_not_found' || state === 'no_access') projects = await projectList($, c)
  const band = { state, line: problemLine(state), projectId: (c as any).projectId ?? null,
    suggestion: state === 'unbound' ? suggest(projects, c.root) : null, projects, picking: false, dismissed: false }
  await $.state.set(BAND, band)
  $.ui.log(`ace band ${JSON.stringify({ state, suggestion: band.suggestion })}`, { to: 'debug' })  // the debug log says what the band shows
}
// The whole step. Never throws: the hooks still run on whatever binding resolved.
export async function startContext($: any, L: Load, cwd: string) {
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
      const st = await verify(c, argv => cliRun($, c as any, argv, { timeoutMs: 20_000 }))
      await publish($, L, c, st === 'ok' ? null : st)
      await logOnce($, L, c, st)
    })().catch(() => undefined)
  } catch { /* the hooks keep the binding they resolved */ }
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
