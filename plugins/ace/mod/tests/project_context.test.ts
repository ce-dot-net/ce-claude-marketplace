// Conformance: context/resolve.ts vs the SDK spec fixtures (70 cases) plus our extra probes. In-memory layout, no `$`.
// Fixtures: ../../tests-fixtures/project-context/ (see its README). Mirror runner: tests/test_project_context_spec.py.
import { expect, test } from 'claude-code/testing'
import SPEC from './fixtures/project_context_cases.ts'
import EXTRA from './fixtures/project_context_extra.ts'
import { resolve, normPath } from '../context/resolve.ts'
import type { Reader } from '../context/resolve.ts'
import { fsReader } from '../context/index.ts'

const ROOT = '/r'
const sub = (v: unknown) => (typeof v === 'string' ? v.replaceAll('$ROOT', ROOT) : v)
const rel = (p: string | null) => (p === null ? p : p === ROOT ? '.' : p.startsWith(ROOT + '/') ? p.slice(ROOT.length + 1) : p)

function reader(layout: Record<string, string | null>, unreadable: string[] = []): Reader {
  const files = new Map<string, string>(), dirs = new Set<string>()
  for (const [r, content] of Object.entries(layout)) {
    let p = normPath(`${ROOT}/${r}`)
    if (content === null) dirs.add(p); else files.set(p, sub(content) as string)
    while ((p = normPath(p + '/..')) !== '/') dirs.add(p)
  }
  const bad = new Set(unreadable.map(u => normPath(`${ROOT}/${u}`)))
  return (path) => {
    if (bad.has(path)) throw new Error(`EACCES: permission denied, open '${path}'`)
    if (files.has(path)) return files.get(path)!
    if (dirs.has(path)) throw new Error(`EISDIR: illegal operation on a directory, read '${path}'`)
    return null
  }
}

// The SDK spec layouts are schematic: their linked worktrees lack what `git worktree add` always writes (<common>/HEAD
// and the <gitdir>/gitdir back-pointer), which git() verifies (8.1.0: commondir is untrusted). Complete only that;
// every plugin extra runs as written. Mirror: _as_git_writes_it in tests/test_project_context_spec.py.
function asGitWritesIt(layout: Record<string, string | null>): Record<string, string | null> {
  const out = { ...layout }
  const n = (p: string) => normPath(`/${p}`).slice(1)
  for (const [rel, txt] of Object.entries(layout)) {
    if (!rel.endsWith('/.git') || typeof txt !== 'string' || !txt.startsWith('gitdir:')) continue
    const gitdir = n(`${rel.slice(0, rel.lastIndexOf('/'))}/${txt.slice(7).trim()}`)
    const cd = layout[`${gitdir}/commondir`]
    if (typeof cd !== 'string') continue
    const common = n(`${gitdir}/${cd.trim()}`)
    out[`${gitdir}/gitdir`] = `${ROOT}/${rel}\n`
    if (!(`${common}/HEAD` in out)) out[`${common}/HEAD`] = 'ref: refs/heads/main\n'
  }
  return out
}

async function runCase(c: any, spec = false): Promise<any> {
  const gc = c.globalConfig ?? {}
  const env: Record<string, string> = {}
  for (const [k, v] of Object.entries(c.env)) env[k] = sub(v) as string
  const res: any = await resolve(`${ROOT}/${c.cwd}`, env, {
    flags: c.flags, remoteMap: gc.projects, organizations: gc.auth?.organizations,
    defaultOrgId: gc.default_org_id, globalProjectId: gc.projectId,
    read: reader(spec ? asGitWritesIt(c.layout) : c.layout, c.unreadable), strict: c.strict ?? false,
  })
  if ('message' in res) {
    expect(typeof res.message === 'string' && res.message.length > 0).toBe(true)
    delete res.message
  }
  if ('path' in res) res.path = rel(res.path)
  for (const t of res.tried ?? []) t.path = rel(t.path)
  return res
}

test('project-context fixtures: 70 spec cases plus the plugin extras are loaded', () => {
  expect((SPEC as any[]).length).toBe(70)
  expect((EXTRA as any[]).length >= 4).toBe(true)
})

for (const c of SPEC as any[]) {
  test(`project-context: ${c.name}`, async () => {
    expect(await runCase(c, true)).toEqual(c.expect)
  })
}
for (const c of (EXTRA as any[]).map((x: any) => ({ strict: true, ...x }))) {
  test(`project-context: ${c.name}`, async () => {
    expect(await runCase(c)).toEqual(c.expect)
  })
}

// fsReader refuses a non-regular file (a FIFO or device would block the read), as ace_project_context.read_file does
test('fsReader throws for a non-regular file and reads a regular one', async () => {
  const fake = (kind: string) => ({ fs: { exists: async () => true, stat: async () => ({ kind, size: 0, isLink: false }), read: async () => '{}' } })
  await expect(fsReader(fake('other'))('/r/.ace/config.json')).rejects.toThrow('not a regular file')
  expect(await fsReader(fake('file'))('/r/.ace/config.json')).toBe('{}')
})
