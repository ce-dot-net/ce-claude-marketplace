// The one core of the mod (8.1.0): binding, verify, export, adopt, the context log row. Every handler and every
// command takes its ids from here; nothing else reads settings.json, .ace/config.json or ACE_* binding env.
// Mirror: shared-hooks/utils/ace_project_context.py (same states, same lines: ./lines.ts).
import { git, normPath, originUrl, normalizeRemote, resolve, type Reader, type Result } from './resolve.ts'
import { LINES, ADOPT_LINE } from './lines.ts'
import { REPO_WRITE_SH, REPO_WRITE_WHY } from '../lib/sh.ts'

export type State = 'ok' | 'unbound' | 'not_logged_in' | 'expired' | 'project_not_found' | 'no_access' | 'server_error'
  | 'cli_missing' | 'config_refused' | 'config_invalid'
export type Ctx = Result & { root: string, mainRoot: string | null, gitRoot: string | null, via: 'resolver' | 'cli' }
export type Env = { HOME?: string, ACE_ORG_ID?: string, ACE_PROJECT_ID?: string, ACE_CONTEXT?: string, ACE_CONFIG_PATH?: string,
  XDG_CONFIG_HOME?: string, ACE_AUTO_ADOPT?: string, ACE_CONTEXT_ENGINE?: string }
export { LINES, ADOPT_LINE }
export const PROBLEM_STATES: State[] = ['unbound', 'not_logged_in', 'expired', 'project_not_found', 'no_access', 'server_error',
  'cli_missing', 'config_refused', 'config_invalid']
// Seam: the SDK's `ace-cli context --json` (PR #211) replaces our resolver once the pinned CLI has it.
// ponytail: a version gate on an unreleased number; set it to the real release when the pin moves.
export const CONTEXT_CLI_MIN = '4.4.0'
export const FILE_SOURCES = ['repo_file', 'settings_file'], ADOPT_SOURCES = ['settings_file', 'remote_map']
const ORG_ID = /^org_[A-Za-z0-9_-]+$/, PRJ_ID = /^prj_[A-Za-z0-9_-]+$/

// $.fs as the resolver's reader: null when missing, throws for a directory or an unreadable file.
export const fsReader = ($: any): Reader => async (p: string) => {
  if (!await $.fs.exists(p).catch(() => false)) return null
  return await $.fs.read(p) as string
}
// The env names are literals ($.env.get validates them); read once per load, before the mod exports its own.
export async function readEnv($: any): Promise<Env> {
  const g = (p: Promise<string | undefined>) => p.then(v => v || undefined, () => undefined)
  return { HOME: await g($.env.get('HOME')), ACE_ORG_ID: await g($.env.get('ACE_ORG_ID')), ACE_PROJECT_ID: await g($.env.get('ACE_PROJECT_ID')),
    ACE_CONTEXT: await g($.env.get('ACE_CONTEXT')), ACE_CONFIG_PATH: await g($.env.get('ACE_CONFIG_PATH')),
    XDG_CONFIG_HOME: await g($.env.get('XDG_CONFIG_HOME')), ACE_AUTO_ADOPT: await g($.env.get('ACE_AUTO_ADOPT')),
    ACE_CONTEXT_ENGINE: await g($.env.get('ACE_CONTEXT_ENGINE')) }
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
export function semverGte(v: string | undefined, min: string) {
  const a = String(v ?? '').split('.').map(Number), b = min.split('.').map(Number)
  for (let i = 0; i < 3; i++) { if ((a[i] || 0) !== b[i]) return (a[i] || 0) > b[i] }
  return true
}
async function pinnedCliVersion($: any): Promise<string | undefined> {
  try { return JSON.parse(await $.fs.read(`${$.plugin.root}/node_modules/@ace-sdk/cli/package.json`) as string).version } catch { return undefined }
}
// The seam: ACE_CONTEXT_ENGINE=cli|resolver forces one; else the pinned CLI's version decides.
export async function useCliContext($: any, env: Env) {
  if (env.ACE_CONTEXT_ENGINE === 'resolver') return false
  if (env.ACE_CONTEXT_ENGINE === 'cli') return true
  return semverGte(await pinnedCliVersion($), CONTEXT_CLI_MIN)
}

export async function resolveContext($: any, cwd: string, envIn: Env, o: { dataRoot?: string, flags?: { org?: string, project?: string },
  cli?: (argv: string[], opts?: any) => Promise<any> } = {}): Promise<Ctx> {
  const read = fsReader($)
  const g = await git(normPath(cwd), read)
  const root = logRoot(cwd, { gitRoot: g.root, mainRoot: g.mainRoot })
  const env = stripOwnExport(envIn, root)
  const base = { root, mainRoot: g.mainRoot, gitRoot: g.root }
  if (o.cli && await useCliContext($, env)) {
    const r = await o.cli(['context', '--json', ...(o.flags?.org ? ['--org', o.flags.org] : []), ...(o.flags?.project ? ['--project', o.flags.project] : [])], { cwd })
    try {
      const j = JSON.parse(String(r?.stdout ?? ''))
      if (j && typeof j.bound === 'boolean') return { ...j, ...base, via: 'cli' }
    } catch { /* fall through to our resolver */ }
  }
  const gc = await readJsonObj($, globalConfigPath(env))
  const remoteMap = { ...(o.dataRoot ? await readJsonObj($, machineMapPath(o.dataRoot)) : {}), ...(gc.projects && typeof gc.projects === 'object' ? gc.projects : {}) }
  const orgs = Array.isArray(gc.auth?.organizations) ? gc.auth.organizations : null
  const r = await resolve(cwd, env, { flags: o.flags ?? null, remoteMap, organizations: orgs, read,
    defaultOrgId: gc.default_org_id ?? gc.defaultOrgId ?? null, globalProjectId: gc.projectId ?? null })
  return { ...r, ...base, via: 'resolver' } as Ctx
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
    try { const e = JSON.parse(line); const code = e?.error?.code; if (typeof code === 'string' && NAMES[code]) return NAMES[code] } catch { /* not JSON */ }
  }
  if (/Cannot find module|MODULE_NOT_FOUND|ace-cli not found/.test(err)) return 'cli_missing'
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
    await $.env.set('ACE_CONTEXT', JSON.stringify({ root: c.root, source: c.source, path: c.path, orgId: c.orgId, projectId: c.projectId, at: now }))
  } else {
    await $.env.set('ACE_ORG_ID', undefined)
    await $.env.set('ACE_PROJECT_ID', undefined)
    await $.env.set('ACE_CONTEXT', undefined)
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
// Automatic adoption: a settings_file / remote_map binding becomes a tracked .ace/config.json in the main checkout.
// Only in git, only when missing, never for flag/env, opt-out ACE_AUTO_ADOPT=0.
export async function adopt($: any, c: Ctx, env: Env, run: Run, refused?: (what: string, reason: string) => Promise<unknown>) {
  if (env.ACE_AUTO_ADOPT === '0' || !c.bound || !ADOPT_SOURCES.includes(c.source)) return null
  const main = c.mainRoot ?? c.gitRoot
  if (!main || await $.fs.exists(`${main}/.ace/config.json`).catch(() => true)) return null
  try { return await writeBinding($, main, c.orgId, c.projectId, run, refused) } catch { return null }
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
export function contextRow(c: Ctx, state: State, nowIso: string, hook = 'session.start') {
  const row: any = { timestamp: nowIso, event: 'context', hook, state, source: (c as any).source ?? null, path: (c as any).path ?? null,
    reason: c.bound ? null : (c as any).reason, org_id: (c as any).orgId ?? null, project_id: (c as any).projectId ?? null,
    root: c.root, via: c.via, chain: 'mod' }
  if ((c as any).warnings?.length) row.warnings = (c as any).warnings
  return row
}
export const problemLine = (s: State | null | undefined) => (s && s !== 'ok' ? (LINES as Record<string, string>)[s] : undefined)
