// ACE project binding resolver (plugin 8.1.0). Mirror of shared-hooks/utils/ace_project_context.py; same semantics.
// Contract: ce-ace-clients spec/project-context.md @ 9c049a0 (AOP-1361). Pure: no `$`, no spawn, no network.
// All file access goes through the injected reader: text, null when missing, throws for a directory or unreadable.
// Precedence: flag > repo_file (.ace/config.json walk-up to the git root, then the linked worktree's main checkout)
// > settings_file (.claude/settings.json, same walk) > env > remote_map > unbound.
// Refusals (spec; no fallback to lower sources; CLI exit 5): apiToken/serverUrl in a repo file -> config_refused with
// warning repo_file_contains_secret; broken/unreadable JSON, a non-object or a non-string id -> config_invalid.

export type Reader = (path: string) => string | null | Promise<string | null>
export type Source = 'flag' | 'repo_file' | 'settings_file' | 'env' | 'remote_map'
export type Tried = { source: string, path: string | null, key: string | null }
export type Result =
  | { bound: true, orgId: string, projectId: string, source: Source, path: string | null, warnings?: string[] }
  | { bound: false, reason: 'no_binding', tried: Tried[], warnings?: string[] }
  | { bound: false, reason: 'no_org', projectId: string, source: Source, path: string | null, warnings?: string[] }
  | { bound: false, reason: 'org_not_member', orgId: string, source: Source, path: string | null, warnings: string[] }
  | { bound: false, reason: 'config_refused' | 'config_invalid', source: Source, path: string | null,
      message?: string, warnings?: string[] }

export type ResolveOpts = {
  flags?: { org?: string, project?: string } | null
  remoteMap?: Record<string, { orgId?: string, projectId?: string }> | null   // global config `projects`
  organizations?: { org_id?: string }[] | null                                 // auth.organizations; null = skip check
  read: Reader
  defaultOrgId?: string | null
  globalProjectId?: string | null                                              // never used, only warned about
  realpath?: (p: string) => string | Promise<string>                           // HOME compare (spec 9500190); default: as given
  osHome?: string | null                                                       // when env HOME is unset
  strict?: boolean                                                             // id format check; default true
}

export const SECRET_KEYS = ['apiToken', 'serverUrl', 'api_token', 'server_url']
const ALIAS_RE = /^(.+\.[a-z]+)-[A-Za-z0-9_-]+$/

type Entry = { source: Source, path: string | null, org: string | null, prj: string | null }
class Refused { constructor(public result: Result) {} }
const invalid = (source: Source, path: string, message?: string): Refused =>
  new Refused({ bound: false, reason: 'config_invalid', source, path, ...(message ? { message } : {}) })

// posix path helpers (absolute paths only)
export function normPath(p: string): string {
  const out: string[] = []
  for (const seg of p.split('/')) {
    if (!seg || seg === '.') continue
    if (seg === '..') out.pop(); else out.push(seg)
  }
  return '/' + out.join('/')
}
const join = (a: string, b: string) => normPath(b.startsWith('/') ? b : `${a}/${b}`)
const dirname = (p: string) => normPath(p + '/..')

async function quiet(read: Reader, p: string): Promise<string | null> {
  try { return await read(p) } catch { return null }
}

export async function git(cwd: string, read: Reader): Promise<{ root: string | null, mainRoot: string | null, config: string | null }> {
  let d = cwd
  for (;;) {
    const dotgit = join(d, '.git')
    let txt: string | null
    try { txt = await read(dotgit) } catch { return { root: d, mainRoot: null, config: join(dotgit, 'config') } }
    if (txt !== null) {
      const m = /^\s*gitdir:\s*(.+?)\s*$/.exec(txt)
      if (!m) return { root: d, mainRoot: null, config: null }
      const gitdir = join(d, m[1])
      const common = await quiet(read, join(gitdir, 'commondir'))
      if (common === null) return { root: d, mainRoot: null, config: join(gitdir, 'config') }   // submodule
      const cd = join(gitdir, common.trim())
      return { root: d, mainRoot: dirname(cd), config: join(cd, 'config') }
    }
    const parent = dirname(d)
    if (parent === d) return { root: null, mainRoot: null, config: null }
    d = parent
  }
}

export function originUrl(text: string | null): string | null {
  let section: string | null = null
  for (const line of (text ?? '').split(/\r?\n/)) {
    const s = line.trim()
    if (s.startsWith('[')) { section = s; continue }
    if (section === '[remote "origin"]') {
      const m = /^url\s*=\s*(.+)$/.exec(s)
      if (m) return m[1].trim()
    }
  }
  return null
}

export function normalizeRemote(url: string | null): string | null {
  if (!url) return null
  url = url.trim()
  let host: string, path: string
  const m = /^[A-Za-z][A-Za-z0-9+.-]*:\/\/(.*)$/.exec(url)
  if (m) {
    const i = m[1].indexOf('/')
    const hostpart = i < 0 ? m[1] : m[1].slice(0, i)
    path = i < 0 ? '' : m[1].slice(i + 1)
    host = hostpart.slice(hostpart.lastIndexOf('@') + 1)
  } else {
    const s = /^(?:[^@/]+@)?([^:/]+):(.+)$/.exec(url)
    if (!s) return null
    host = s[1]; path = s[2]
  }
  host = host.toLowerCase()
  const a = ALIAS_RE.exec(host)
  if (a) host = a[1]
  path = path.replace(/^\/+|\/+$/g, '')
  if (path.endsWith('.git')) path = path.slice(0, -4)
  return host && path ? `${host}/${path}` : null
}

function parseJson(text: string, source: Source, path: string): Record<string, unknown> {
  let data: unknown
  try { data = JSON.parse(text) } catch (e) { throw invalid(source, path, String((e as Error).message ?? e)) }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw invalid(source, path, 'top level is not an object')
  return data as Record<string, unknown>
}

// strict (production, the default): every id from a file, the env or a remote map must look like org_... / prj_...,
// so an id can never carry path or argv metacharacters (security review 8.1.0). Only the spec runner passes strict:false
// (the SDK fixtures use ids like proj_a).
const ID_RE = { org: /^org_[A-Za-z0-9_-]+$/, prj: /^prj_[A-Za-z0-9_-]+$/ }
function id(v: unknown, source: Source, path: string | null, kind: 'org' | 'prj', strict: boolean): string | null {
  if (v === undefined || v === null || v === '') return null
  if (typeof v !== 'string') throw invalid(source, path as string, 'id is not a string')
  if (strict && !ID_RE[kind].test(v)) throw invalid(source, path as string, `id must look like ${kind}_...`)
  return v
}

type Parse = (text: string, path: string, strict: boolean) => Entry

const repoEntry: Parse = (text, path, strict) => {
  const d = parseJson(text, 'repo_file', path)
  if (SECRET_KEYS.some(k => k in d)) throw new Refused({ bound: false, reason: 'config_refused', source: 'repo_file', path,
    message: 'repo .ace/config.json contains apiToken/serverUrl; remove them', warnings: ['repo_file_contains_secret'] })
  return { source: 'repo_file', path, org: id(d.orgId ?? d.org_id, 'repo_file', path, 'org', strict), prj: id(d.projectId ?? d.project_id, 'repo_file', path, 'prj', strict) }
}

const settingsEntry: Parse = (text, path, strict) => {
  const d = parseJson(text, 'settings_file', path)
  const env = (d.env && typeof d.env === 'object' && !Array.isArray(d.env) ? d.env : {}) as Record<string, unknown>
  return { source: 'settings_file', path, org: id(env.ACE_ORG_ID, 'settings_file', path, 'org', strict), prj: id(env.ACE_PROJECT_ID, 'settings_file', path, 'prj', strict) }
}

// Spec 1.1/7: the first existing file in the walk ends it; the main checkout is checked only without a projectId yet.
// lenient (projectId already decided: a --project flag or a higher source): a refused/invalid file contributes
// nothing and only warns (spec 9500190).
async function search(source: Source, rel: string, dirs: string[], mainRoot: string | null, home: string | null, read: Reader,
  tried: Tried[], parse: Parse, warnings: string[], lenient: boolean, strict = true): Promise<Entry[]> {
  const found: Entry[] = []
  const probe = async (path: string) => {
    tried.push({ source, path, key: null })
    try {
      let text: string | null
      try { text = await read(path) } catch (e) { throw invalid(source, path, String((e as Error)?.message ?? e)) }
      if (text === null) return false
      found.push(parse(text, path, strict))
    } catch (e) {
      if (!(e instanceof Refused) || !lenient) throw e
      const w = e.result.reason === 'config_refused' ? 'repo_file_contains_secret' : 'config_invalid'
      if (!warnings.includes(w)) warnings.push(w)
      found.push({ source, path, org: null, prj: null })
    }
    return true
  }
  for (const d of dirs) if (await probe(join(d, rel))) break
  if (mainRoot && mainRoot !== home && !(found[0]?.prj)) await probe(join(mainRoot, rel))
  return found
}

export async function resolve(cwd: string, env: Record<string, string | undefined>, opts: ResolveOpts): Promise<Result> {
  try { return await resolveInner(normPath(cwd), env ?? {}, opts) } catch (e) {
    if (!(e instanceof Refused)) throw e
    return e.result  // spec 9500190: only its own warning
  }
}

async function resolveInner(cwd: string, env: Record<string, string | undefined>, o: ResolveOpts): Promise<Result> {
  const flags = o.flags ?? {}
  const read = o.read
  const warnings: string[] = typeof o.globalProjectId === 'string' && o.globalProjectId ? ['global_project_id_ignored'] : []
  const rp = o.realpath ?? ((p: string) => p)
  const homeRaw = env.HOME || o.osHome
  const homeReal = homeRaw ? await rp(normPath(homeRaw)) : null
  const isHome = async (d: string | null) => d !== null && homeReal !== null && await rp(d) === homeReal
  const home = null
  const { root, mainRoot, config } = await git(cwd, read)

  const dirs: string[] = []
  for (let d = cwd; ; d = dirname(d)) {
    if (!await isHome(d)) dirs.push(d)
    if (root === null || d === root) break
  }

  const tried: Tried[] = []
  const entries: Entry[] = [{ source: 'flag', path: null, org: flags.org || null, prj: flags.project || null }]
  const main = await isHome(mainRoot) ? null : mainRoot
  const strict = o.strict ?? true
  entries.push(...await search('repo_file', '.ace/config.json', dirs, main, home, read, tried, repoEntry, warnings, entries.some(e => e.prj), strict))
  entries.push(...await search('settings_file', '.claude/settings.json', dirs, main, home, read, tried, settingsEntry, warnings, entries.some(e => e.prj), strict))
  // a malformed env / remote-map id is dropped with a warning (never blocks a file binding)
  const soft = (v: unknown, kind: 'org' | 'prj') => {
    try { return id(v, 'env', null, kind, strict) } catch {
      if (!warnings.includes('invalid_id_ignored')) warnings.push('invalid_id_ignored')
      return null
    }
  }
  entries.push({ source: 'env', path: null, org: soft(env.ACE_ORG_ID, 'org'), prj: soft(env.ACE_PROJECT_ID, 'prj') })
  tried.push({ source: 'env', path: null, key: null })
  const key = config ? normalizeRemote(originUrl(await quiet(read, config))) : null
  const hit = key ? o.remoteMap?.[key] : undefined
  if (hit && typeof hit === 'object') entries.push({ source: 'remote_map', path: null, org: soft(hit.orgId, 'org'), prj: soft(hit.projectId, 'prj') })
  tried.push({ source: 'remote_map', path: null, key })

  const done = <T extends Result>(r: T): T => {
    if (warnings.length) (r as any).warnings = [...warnings, ...((r as any).warnings ?? [])]
    return r
  }

  const win = entries.find(e => e.prj)
  if (!win) return done({ bound: false, reason: 'no_binding', tried })

  // Spec 1.4: --org > winner's org > first org in order > default_org_id. orgFrom = where the org came from.
  let org: string | null | undefined
  let orgFrom: Entry | undefined
  if (entries[0].org) org = entries[0].org
  else if (win.org) { org = win.org; orgFrom = win }
  else { orgFrom = entries.find(e => e.org); org = orgFrom ? orgFrom.org : o.defaultOrgId }
  if (!org) return done({ bound: false, reason: 'no_org', projectId: win.prj!, source: win.source, path: win.path })

  if (orgFrom && ['repo_file', 'settings_file', 'remote_map'].includes(orgFrom.source) && o.organizations
    && !o.organizations.some(x => x && x.org_id === org)) {
    return done({ bound: false, reason: 'org_not_member', orgId: org, source: orgFrom.source, path: orgFrom.path, warnings: ['org_not_member'] })
  }

  return done({ bound: true, orgId: org, projectId: win.prj!, source: win.source, path: win.path })
}
