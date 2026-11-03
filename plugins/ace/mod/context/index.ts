// The one core of the mod (8.1.0): binding, verify, export, adopt, the context log row. Every handler and every
// command takes its ids from here; nothing else reads settings.json, .ace/config.json or ACE_* binding env.
// Mirror: shared-hooks/utils/ace_project_context.py (same states, same lines: ./lines.ts).
import { FileTooLarge, MAX_REPO_FILE, dirname, git, join, normPath, originUrl, normalizeRemote, resolve, type Reader, type Result } from './resolve.ts'
import { LINES, ADOPT_LINE, WARN_LINES } from './lines.ts'
import { REALPATH_SH, REPO_WRITE_SH, REPO_WRITE_WHY } from '../lib/sh.ts'

export type State = 'ok' | 'unbound' | 'not_logged_in' | 'expired' | 'project_not_found' | 'no_access' | 'server_error'
  | 'cli_missing' | 'config_refused' | 'config_invalid'
export type Ctx = Result & { root: string, mainRoot: string | null, gitRoot: string | null, via: 'resolver' | 'cli' }
export type Env = { HOME?: string, ACE_ORG_ID?: string, ACE_PROJECT_ID?: string, ACE_CONTEXT?: string, ACE_CONFIG_PATH?: string,
  XDG_CONFIG_HOME?: string, ACE_AUTO_ADOPT?: string, ACE_CONTEXT_ENGINE?: string, ACE_BIND_ROOT?: string }
export { LINES, ADOPT_LINE, WARN_LINES }
export const PROBLEM_STATES: State[] = ['unbound', 'not_logged_in', 'expired', 'project_not_found', 'no_access', 'server_error',
  'cli_missing', 'config_refused', 'config_invalid']
export const FILE_SOURCES = ['repo_file', 'settings_file'], ADOPT_SOURCES = ['settings_file', 'remote_map']
const ORG_ID = /^org_[A-Za-z0-9_-]+$/, PRJ_ID = /^prj_[A-Za-z0-9_-]+$/

// $.fs as the resolver's reader: null when missing, throws for a directory or an unreadable file, FileTooLarge (checked
// by size BEFORE the read) for a file over MAX_REPO_FILE: every file the resolver reads is small.
export function fsReader($: any): Reader {
  return async (p: string) => {
    if (!await $.fs.exists(p).catch(() => false)) return null
    const st = await $.fs.stat(p).catch(() => null)
    if (st && st.kind !== 'file') throw new Error(`not a regular file: ${p}`)  // a FIFO or device would block the read
    if (typeof st?.size === 'number' && st.size > MAX_REPO_FILE) throw new FileTooLarge(`larger than ${MAX_REPO_FILE} bytes: ${p}`)
    return await $.fs.read(p) as string
  }
}
// The env names are literals ($.env.get validates them); read once per load, before the mod exports its own.
export async function readEnv($: any): Promise<Env> {
  const g = (p: Promise<string | undefined>) => p.then(v => v || undefined, () => undefined)
  return { HOME: await g($.env.get('HOME')), ACE_ORG_ID: await g($.env.get('ACE_ORG_ID')), ACE_PROJECT_ID: await g($.env.get('ACE_PROJECT_ID')),
    ACE_CONTEXT: await g($.env.get('ACE_CONTEXT')), ACE_CONFIG_PATH: await g($.env.get('ACE_CONFIG_PATH')),
    XDG_CONFIG_HOME: await g($.env.get('XDG_CONFIG_HOME')), ACE_AUTO_ADOPT: await g($.env.get('ACE_AUTO_ADOPT')),
    ACE_CONTEXT_ENGINE: await g($.env.get('ACE_CONTEXT_ENGINE')), ACE_BIND_ROOT: await g($.env.get('ACE_BIND_ROOT')) }
}
export const globalConfigPath = (env: Env) => env.ACE_CONFIG_PATH
  || `${env.XDG_CONFIG_HOME || `${env.HOME ?? ''}/.config`}/ace/config.json`
async function readJsonObj($: any, p: string): Promise<Record<string, any>> {
  try { const d = JSON.parse(await $.fs.read(p) as string); return d && typeof d === 'object' && !Array.isArray(d) ? d : {} } catch { return {} }
}
export const machineMapPath = (dataRoot: string) => `${dataRoot}/remote-map.json`

export function logRoot(cwd: string, r: { gitRoot: string | null, mainRoot: string | null }) {
  return r.mainRoot ?? r.gitRoot ?? normPath(cwd)
}
// A stale or foreign export of our own never counts as the user's env (the Python chain does the same).
export function stripOwnExport(env: Env, root: string): Env {
  let m: any
  try { m = JSON.parse(env.ACE_CONTEXT ?? '') } catch { return env }
  if (!m || env.ACE_PROJECT_ID !== m.projectId) return env
  const out = { ...env }
  delete out.ACE_PROJECT_ID
  if (out.ACE_ORG_ID === m.orgId) delete out.ACE_ORG_ID
  void root
  return out
}
// The seam (8.1.0): the SDK's `ace-cli context --json` (PR #211) replaces our resolver once the CLI has it.
// Feature-detected, never by version (the prerelease still reports 4.3.4): the probe IS the call, once per load
// (resolveContextOnce caches the result). "unknown command" / a usage error / no JSON = old CLI -> our resolver.
// Only stdout's JSON counts (with config_refused/config_invalid the CLI prints a generic unbound line on stderr).
// ACE_CONTEXT_ENGINE=resolver forces ours, =cli insists on the CLI's (still our resolver when it has none).
const ID = { org: /^org_[A-Za-z0-9_-]+$/, prj: /^prj_[A-Za-z0-9_-]+$/ }
export function parseCliContext(stdout: string): Result | null {
  let j: any
  try { j = JSON.parse(String(stdout ?? '')) } catch { return null }
  if (!j || typeof j !== 'object' || typeof j.bound !== 'boolean') return null
  const { projectName: _n, auth: _a, ...r } = j
  // our production strictness on top of the SDK's spec resolver: ids never carry path/argv metacharacters
  if (r.bound && !(ID.org.test(String(r.orgId)) && ID.prj.test(String(r.projectId))))
    return { bound: false, reason: 'config_invalid', source: r.source, path: r.path ?? null, message: 'id must look like org_/prj_' } as Result
  return r as Result
}
// The CLI build the probe result belongs to: the plugin-local cli.js by size + mtime, else the global one.
async function cliIdentity($: any): Promise<string> {
  try { const st = await $.fs.stat(`${$.plugin.root}/node_modules/@ace-sdk/cli/dist/cli.js`); return `local:${st.size}:${st.mtimeMs}` } catch { return 'global' }
}
export const CLI_CONTEXT_UNKNOWN = /unknown command|error: unknown|Usage: ace-cli|too many arguments/i

// Our own guards the SDK's spec resolver does not have (8.1.0 review): when ours trips one, the CLI is never asked.
const OWN_GUARDS = ['worktree_topology_untrusted', 'config_too_large', 'repo_file_outside_root']
export async function resolveContext($: any, cwd: string, envIn: Env, o: { dataRoot?: string, flags?: { org?: string, project?: string },
  cli?: (argv: string[], opts?: any) => Promise<any> } = {}): Promise<Ctx> {
  const read = fsReader($)
  const realpath = memoRealpath(realpathVia((argv, init) => $.process.run(argv, init)))
  const g = await git(normPath(cwd), read, realpath)
  const root = logRoot(cwd, { gitRoot: g.root, mainRoot: g.mainRoot })
  const env = stripOwnExport(envIn, root)
  const base = { root, mainRoot: g.mainRoot, gitRoot: g.root }
  const gc = await readJsonObj($, globalConfigPath(env))
  const remoteMap = { ...(o.dataRoot ? await readJsonObj($, machineMapPath(o.dataRoot)) : {}), ...(gc.projects && typeof gc.projects === 'object' ? gc.projects : {}) }
  const orgs = Array.isArray(gc.auth?.organizations) ? gc.auth.organizations : null
  const r = await resolve(cwd, env, { flags: o.flags ?? null, remoteMap, organizations: orgs, read, realpath,
    defaultOrgId: gc.default_org_id ?? gc.defaultOrgId ?? null, globalProjectId: gc.projectId ?? null })
  const ours = { ...r, ...base, via: 'resolver' } as Ctx
  // an untrusted worktree topology, an oversized or out-of-repo binding file never reach the CLI (its spec resolver
  // would climb a forged commondir, parse the file, follow the symlink)
  if (g.untrusted || ((r as any).warnings ?? []).some((w: string) => OWN_GUARDS.includes(w))) return ours
  const capPath = o.dataRoot ? `${o.dataRoot}/cli-context-cap.json` : null
  const capKey = await cliIdentity($)
  const cap = capPath ? await readJsonObj($, capPath) : {}
  const known = cap.key === capKey ? cap.has : undefined  // an old CLI is probed once per CLI build, not per session
  if (o.cli && env.ACE_CONTEXT_ENGINE !== 'resolver' && (known !== false || env.ACE_CONTEXT_ENGINE === 'cli')) {
    const c = await o.cli(['context', '--json', ...(o.flags?.org ? ['--org', o.flags.org] : []), ...(o.flags?.project ? ['--project', o.flags.project] : [])],
      { cwd, env: { ACE_ORG_ID: env.ACE_ORG_ID ?? '', ACE_PROJECT_ID: env.ACE_PROJECT_ID ?? '', ACE_BIND_ROOT: env.ACE_BIND_ROOT ?? '' }, timeoutMs: 10_000 })
    const parsed = parseCliContext(c?.stdout)
    const old = !parsed && CLI_CONTEXT_UNKNOWN.test(`${c?.stderr ?? ''}\n${c?.stdout ?? ''}`)
    if (capPath && (parsed || old) && known !== !!parsed) await $.fs.write(capPath, JSON.stringify({ key: capKey, has: !!parsed })).catch(() => undefined)
    if (parsed) return { ...parsed, ...base, via: 'cli' } as Ctx
  }
  return ours
}

export function localState(c: { bound: boolean, reason?: string }): State | null {
  if (c.bound) return null
  return c.reason === 'config_refused' ? 'config_refused' : c.reason === 'config_invalid' ? 'config_invalid' : 'unbound'
}
export const cliIds = (c: any): string[] => [...(c?.orgId ? ['--org', c.orgId] : []), ...(c?.projectId ? ['--project', c.projectId] : [])]

const CODES: Record<number, State> = { 3: 'not_logged_in', 4: 'expired', 5: 'unbound', 6: 'project_not_found', 7: 'no_access', 8: 'server_error', 9: 'not_logged_in' }
const NAMES: Record<string, State> = { not_logged_in: 'not_logged_in', token_expired: 'expired', unbound: 'unbound', project_not_found: 'project_not_found',
  no_access: 'no_access', server_error: 'server_error', device_limit_exceeded: 'not_logged_in' }
// ace-cli exit code + stderr -> state; stdout is never read (pattern text may say anything). Old 4.3.4 and new codes.
export function classify(exitCode: number | null | undefined, stderr: string, spawnError = false, timeout = false): State {
  if (spawnError) return 'cli_missing'
  if (timeout) return 'server_error'
  if (exitCode === 0) return 'ok'
  if (exitCode != null && CODES[exitCode]) return CODES[exitCode]
  const err = String(stderr ?? '')
  for (const line of err.split('\n')) {
    let code: unknown
    try { code = JSON.parse(line)?.error?.code } catch { continue }
    if (typeof code === 'string' && NAMES[code]) return NAMES[code]
    if (typeof code === 'string' && code) return 'server_error'  // new CLI generic exit 1 (subscription 403): never from text
  }
  if (/Cannot find module|MODULE_NOT_FOUND|ace-cli not found/.test(err)) return 'cli_missing'
  if (/token_expired|Session expired/.test(err)) return 'expired'
  if (/No API token found|Please login first|Not logged in|not_logged_in/i.test(err)) return 'not_logged_in'
  const m = /Server error \((\d{3})\)/.exec(err)
  const code = m ? Number(m[1]) : 0
  return code === 401 ? 'expired' : code === 403 ? 'no_access' : code === 404 ? 'project_not_found' : 'server_error'
}
// `run` = an argv-only CLI spawn; resolves { exitCode, stdout, stderr } or { spawnError } / { timeout }.
export async function verify(c: Ctx, run: (argv: string[]) => Promise<any>): Promise<State> {
  const st = localState(c)
  if (st) return st
  const r = await run(['status', '--json', ...cliIds(c)])
  return classify(r?.exitCode, r?.stderr ?? '', !!r?.spawnError, !!r?.timeout)
}
// The child env: our ids, never a leaked ACE_* binding. ACE_CONTEXT tells the Python chain the mod resolved this root.
export async function exportEnv($: any, c: Ctx, now: number) {
  if (c.bound) {
    await $.env.set('ACE_ORG_ID', c.orgId)
    await $.env.set('ACE_PROJECT_ID', c.projectId)
    await $.env.set('ACE_BIND_ROOT', c.root)  // the ids bind only inside this repo (a child session elsewhere ignores them)
    await $.env.set('ACE_CONTEXT', JSON.stringify({ root: c.root, source: c.source, path: c.path, orgId: c.orgId, projectId: c.projectId, at: now }))
  } else {  // no ids, but the Python chain learns that the mod owns this root's notice and its one context row
    await $.env.set('ACE_ORG_ID', undefined)
    await $.env.set('ACE_PROJECT_ID', undefined)
    await $.env.set('ACE_BIND_ROOT', undefined)
    await $.env.set('ACE_CONTEXT', JSON.stringify({ root: c.root, bound: false, reason: (c as any).reason, at: now }))
  }
}

// `ace-cli init --fix-gitignore` semantics: a bare `.ace/` rule becomes `.ace/*` (a dir rule blocks the negation),
// then `!.ace/config.json` is added. Same output as ace_project_context.fix_gitignore.
export function fixGitignore(text: string): { text: string, changed: boolean } {
  const lines = (text ?? '').split('\n')
  if (lines.length && lines[lines.length - 1] === '') lines.pop()
  let changed = false
  const out = lines.map(line => {
    const s = line.trim()
    if (['.ace', '.ace/', '/.ace', '/.ace/', '.ace/**', '/.ace/**'].includes(s)) {
      const n = (s.startsWith('/') ? '/' : '') + '.ace/*'
      if (n !== line) changed = true
      return n
    }
    return line
  })
  if (!out.some(l => ['!.ace/config.json', '!/.ace/config.json'].includes(l.trim()))) {
    if (!out.some(l => ['.ace/*', '/.ace/*'].includes(l.trim()))) out.push('.ace/*')
    out.push('!.ace/config.json')
    changed = true
  }
  return changed ? { text: out.join('\n') + '\n', changed } : { text: text ?? '', changed }
}
export function gitignoreDiff(before: string, after: string): string {
  const b = new Set(before.split('\n')), a = new Set(after.split('\n'))
  return [...before.split('\n').filter(l => l && !a.has(l)).map(l => `- ${l}`), ...after.split('\n').filter(l => l && !b.has(l)).map(l => `+ ${l}`)].join('\n')
}
export type Run = (argv: string[], init?: any) => Promise<any>
export class WriteRefused extends Error {}
// One repo file through REPO_WRITE_SH (no symlink, never outside main). Throws WriteRefused with the reason.
export async function repoWrite(run: Run, main: string, rel: string, text: string) {
  const r = await run(['/bin/sh', '-c', REPO_WRITE_SH, 'sh', main, rel], { stdin: text, timeoutMs: 5000 })
  if (r?.exitCode !== 0) throw new WriteRefused(`${REPO_WRITE_WHY[r?.exitCode] ?? 'write failed'}: ${main}/${rel}`)
}
// Write <main>/.ace/config.json {orgId, projectId} (never a secret) and un-ignore it. Never stages or commits.
// `refused` gets each refusal's reason (the caller logs it).
export async function writeBinding($: any, main: string, orgId: string, projectId: string, run: Run,
  refused: (what: string, reason: string) => Promise<unknown> = async () => {}): Promise<{ path: string, gitignore: 'ok' | 'fixed' | 'still_ignored' | 'refused' }> {
  if (!ORG_ID.test(orgId) || !PRJ_ID.test(projectId)) throw new Error('ids must look like org_... / prj_...')
  const path = `${main}/.ace/config.json`
  try { await repoWrite(run, main, '.ace/config.json', JSON.stringify({ orgId, projectId }, null, 2) + '\n') }
  catch (e) { await refused('.ace/config.json', String((e as Error).message)); throw e }
  const gpath = `${main}/.gitignore`
  const link = ((await $.fs.list(main).catch(() => [])) as any[]).some(f => f.name === '.gitignore' && f.isLink)
  if (link) { await refused('.gitignore', `symlink: ${gpath}`); return { path, gitignore: 'refused' } }
  const ignored = async () => (await run(['git', '-C', main, 'check-ignore', '-q', '.ace/config.json']))?.exitCode === 0
  if (!await ignored()) return { path, gitignore: 'ok' }
  let before = ''
  try { before = await $.fs.read(gpath) as string } catch { /* none yet */ }
  const fx = fixGitignore(before)
  if (fx.changed) {
    try { await repoWrite(run, main, '.gitignore', fx.text) }
    catch (e) { await refused('.gitignore', String((e as Error).message)); return { path, gitignore: 'refused' } }
  }
  return { path, gitignore: await ignored() ? 'still_ignored' : 'fixed' }
}
// ---- cli 4.4.1: `ace-cli init --json` writes the binding (spec §9); our writer only for a CLI without it ----
export type InitOut = { path: string, gitignore: string, warnings: string[], mainCheckout?: boolean, shadowedBy?: string, via: 'cli' | 'fallback' }
export type CliRun = (argv: string[], o?: { cwd?: string, timeoutMs?: number }) => Promise<any>
// `ace-cli init --json --fix-gitignore [--org --project]` in cwd (every caller is past a confirm press, or auto-adopt).
// Its JSON result; null = the CLI has no init --json (missing, unknown command, no JSON: feature-detected like the
// context seam); WriteRefused = it refused (exit 1, stderr {"error":{...}}: symlink, outside the root), final.
// ids null: the CLI reuses the existing binding (a refused file: it strips the secrets where that file is).
export async function cliInit(cli: CliRun, cwd: string, ids: { orgId: string, projectId: string } | null): Promise<InitOut | null> {
  const r = await cli(['init', '--json', '--fix-gitignore', ...(ids ? ['--org', ids.orgId, '--project', ids.projectId] : [])], { cwd, timeoutMs: 15_000 })
  let j: any = null
  try { j = JSON.parse(String(r?.stdout ?? '')) } catch { /* no JSON */ }
  if (r?.exitCode === 0 && j && typeof j === 'object' && typeof j.path === 'string')
    return { ...j, warnings: Array.isArray(j.warnings) ? j.warnings : [], via: 'cli' }
  for (const line of String(r?.stderr ?? '').split('\n')) {
    let e: any
    try { e = JSON.parse(line) } catch { continue }
    if (e && typeof e.error === 'object' && e.error) throw new WriteRefused(String(e.error.message ?? e.error.code ?? 'refused'))
  }
  return null
}
// realpath through the shell ($.fs has none); the path as given when it does not resolve (the in-memory test host).
export const realpathVia = (run: Run) => async (p: string) => String((await run(['/bin/sh', '-c', REALPATH_SH, 'sh', p], { timeoutMs: 5000 }).catch(() => null))?.stdout ?? '').trim() || p
const memoRealpath = (f: (p: string) => Promise<string>) => {
  const m = new Map<string, Promise<string>>()
  return (p: string) => { if (!m.has(p)) m.set(p, f(p)); return m.get(p)! }
}
// Where init writes (spec §9, mirror of ace_project_context.init_target): a linked worktree's MAIN checkout, only when
// the topology verifies like git does it; else the worktree root, untrusted. Plain repo / submodule: its root; no git: cwd.
export async function initTarget(cwd: string, read: Reader, realpath: (p: string) => Promise<string> = async p => p) {
  const g = await git(normPath(cwd), read, realpath)
  if (g.mainRoot) return { root: g.mainRoot, mainCheckout: true, untrusted: false }
  return { root: g.root ?? normPath(cwd), mainCheckout: false, untrusted: g.untrusted }
}
// The first worktree-local .ace/config.json on the walk-up from cwd to the worktree root.
async function findShadow($: any, cwd: string): Promise<string | null> {
  const read = fsReader($), top = (await git(normPath(cwd), read)).root
  for (let d = normPath(cwd); ; d = dirname(d)) {
    const f = `${d}/.ace/config.json`
    if (typeof await read(f).catch(() => null) === 'string') return f
    if (d === top || dirname(d) === d) return null
  }
}
// Our writer for a CLI without `init --json`: the same target, warnings and shadowedBy as the CLI.
// It can go once the CLI floor (the pin AND an accepted global ace-cli) is >= 4.4.1.
export async function fallbackInit($: any, cwd: string, orgId: string, projectId: string, run: Run,
  refused?: (what: string, reason: string) => Promise<unknown>): Promise<InitOut> {
  const t = await initTarget(cwd, fsReader($), realpathVia(run))
  const w = await writeBinding($, t.root, orgId, projectId, run, refused)
  const shadow = t.mainCheckout ? await findShadow($, cwd) : null
  const warnings = [...(t.mainCheckout ? ['written_to_main_checkout'] : []), ...(t.untrusted ? ['worktree_topology_untrusted'] : []),
    ...(shadow ? ['worktree_file_shadows_main'] : [])]
  return { ...w, warnings, via: 'fallback', ...(t.mainCheckout ? { mainCheckout: true } : {}), ...(shadow ? { shadowedBy: shadow } : {}) }
}
// The binding write for cwd: the CLI's init --json, else our writer. Throws WriteRefused (logged through `refused`).
export async function bindInit($: any, cwd: string, orgId: string, projectId: string, cli: CliRun, run: Run,
  refused: (what: string, reason: string) => Promise<unknown> = async () => {}): Promise<InitOut> {
  if (!ORG_ID.test(orgId) || !PRJ_ID.test(projectId)) throw new Error('ids must look like org_... / prj_...')
  let r: InitOut | null
  try { r = await cliInit(cli, cwd, { orgId, projectId }) } catch (e) { await refused('.ace/config.json', String((e as Error).message)); throw e }
  return r ?? fallbackInit($, cwd, orgId, projectId, run, refused)
}
// Automatic adoption: a settings_file / remote_map binding becomes a tracked .ace/config.json in the main checkout.
// Only in git, only when missing, never for flag/env, never on an untrusted worktree topology (checked BEFORE the
// write: the CLI would already have written to the worktree root), opt-out ACE_AUTO_ADOPT=0.
export async function adopt($: any, c: Ctx, env: Env, cwd: string, cli: CliRun, run: Run, refused?: (what: string, reason: string) => Promise<unknown>) {
  if (env.ACE_AUTO_ADOPT === '0' || !c.bound || !ADOPT_SOURCES.includes(c.source)) return null
  if (!(c.mainRoot ?? c.gitRoot)) return null
  const t = await initTarget(cwd, fsReader($), realpathVia(run))
  if (t.untrusted) return { path: null, warnings: ['worktree_topology_untrusted'] }
  if (await $.fs.exists(`${t.root}/.ace/config.json`).catch(() => true)) return null
  try { return await bindInit($, cwd, c.orgId, c.projectId, cli, run, refused) } catch { return null }
}
export async function untracked(main: string, run: Run) {
  return (await run(['git', '-C', main, 'ls-files', '--error-unmatch', '.ace/config.json']))?.exitCode !== 0
}
// Per-machine remote map (shared with the Python chain): a file-bound repo teaches its origin.
export async function remember($: any, c: Ctx, cwd: string, dataRoot: string, write: (path: string, text: string) => Promise<unknown>, now: number) {
  if (!c.bound || !FILE_SOURCES.includes(c.source)) return false
  const g = await git(normPath(cwd), fsReader($))
  if (!g.config) return false
  let cfg: string | null = null
  try { cfg = await fsReader($)(g.config) } catch { return false }
  const key = normalizeRemote(originUrl(cfg))
  if (!key) return false
  const m = await readJsonObj($, machineMapPath(dataRoot))
  if (m[key]?.orgId === c.orgId && m[key]?.projectId === c.projectId) return false
  m[key] = { orgId: c.orgId, projectId: c.projectId, at: Math.floor(now / 1000) }
  await write(machineMapPath(dataRoot), JSON.stringify(m, null, 2) + '\n')
  return true
}
export function contextRow(c: Ctx, state: State, nowIso: string, hook = 'session.start', sessionId?: string) {
  const row: any = { timestamp: nowIso, event: 'context', hook, session_id: sessionId ?? null, state, source: (c as any).source ?? null, path: (c as any).path ?? null,
    reason: c.bound ? null : (c as any).reason, org_id: (c as any).orgId ?? null, project_id: (c as any).projectId ?? null,
    root: c.root, via: c.via, chain: 'mod' }
  if ((c as any).warnings?.length) row.warnings = (c as any).warnings
  return row
}
export const problemLine = (s: State | null | undefined) => (s && s !== 'ok' ? (LINES as Record<string, string>)[s] : undefined)
