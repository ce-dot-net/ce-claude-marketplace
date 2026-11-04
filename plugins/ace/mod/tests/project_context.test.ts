// Conformance: context/resolve.ts vs the SDK spec fixtures (76 cases) plus our extra probes. In-memory layout, no `$`.
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

// (read, realpath) over the in-memory layout. A value "@symlink:<path relative to the layout root>" is a symlink (spec:
// used by the §9 (e) case); both follow it, like fsReader and realpathVia. Mirror: _fs in tests/test_project_context_spec.py.
function fsOf(layout: Record<string, string | null>, unreadable: string[] = []): { read: Reader, realpath: (p: string) => string } {
  const files = new Map<string, string>(), dirs = new Set<string>(), links = new Map<string, string>()
  for (const [r, content] of Object.entries(layout)) {
    let p = normPath(`${ROOT}/${r}`)
    if (content === null) dirs.add(p)
    else if (content.startsWith('@symlink:')) links.set(p, normPath(`${ROOT}/${content.slice(9)}`))
    else files.set(p, sub(content) as string)
    while ((p = normPath(p + '/..')) !== '/') dirs.add(p)
  }
  const bad = new Set(unreadable.map(u => normPath(`${ROOT}/${u}`)))
  const realpath = (path: string, hops = 0): string => {
    let cur = ''
    for (const seg of normPath(path).split('/').slice(1)) {
      cur = `${cur}/${seg}`
      if (links.has(cur) && hops < 40) cur = realpath(links.get(cur)!, hops + 1)
    }
    return cur || '/'
  }
  const read: Reader = (path) => {
    path = realpath(path)
    if (bad.has(path)) throw new Error(`EACCES: permission denied, open '${path}'`)
    if (files.has(path)) return files.get(path)!
    if (dirs.has(path)) throw new Error(`EISDIR: illegal operation on a directory, read '${path}'`)
    return null
  }
  return { read, realpath }
}

async function runCase(c: any): Promise<any> {
  const gc = c.globalConfig ?? {}
  const env: Record<string, string> = {}
  for (const [k, v] of Object.entries(c.env)) env[k] = sub(v) as string
  const res: any = await resolve(`${ROOT}/${c.cwd}`, env, {
    flags: c.flags, remoteMap: gc.projects, organizations: gc.auth?.organizations,
    defaultOrgId: gc.default_org_id, globalProjectId: gc.projectId,
    ...fsOf(c.layout, c.unreadable), strict: c.strict ?? false,
  })
  if ('message' in res) {
    expect(typeof res.message === 'string' && res.message.length > 0).toBe(true)
    delete res.message
  }
  if ('path' in res) res.path = rel(res.path)
  for (const t of res.tried ?? []) t.path = rel(t.path)
  return res
}

test('project-context fixtures: 76 spec cases plus the plugin extras are loaded', () => {
  expect((SPEC as any[]).length).toBe(76)
  expect((EXTRA as any[]).length >= 4).toBe(true)
})

for (const c of SPEC as any[]) {
  test(`project-context: ${c.name}`, async () => {
    expect(await runCase(c)).toEqual(c.expect)
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
