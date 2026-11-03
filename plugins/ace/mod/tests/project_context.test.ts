// Conformance: context/resolve.ts vs the SDK spec fixtures (60 cases) plus our extra probes. In-memory layout, no `$`.
// Fixtures: ../../tests-fixtures/project-context/ (see its README). Mirror runner: tests/test_project_context_spec.py.
import { expect, test } from 'claude-code/testing'
import SPEC from './fixtures/project_context_cases.ts'
import EXTRA from './fixtures/project_context_extra.ts'
import { resolve, normPath } from '../context/resolve.ts'
import type { Reader } from '../context/resolve.ts'

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

function runCase(c: any): any {
  const gc = c.globalConfig ?? {}
  const env: Record<string, string> = {}
  for (const [k, v] of Object.entries(c.env)) env[k] = sub(v) as string
  const res: any = resolve(`${ROOT}/${c.cwd}`, env, {
    flags: c.flags, remoteMap: gc.projects, organizations: gc.auth?.organizations,
    defaultOrgId: gc.default_org_id, globalProjectId: gc.projectId,
    read: reader(c.layout, c.unreadable), strict: c.strict ?? false,
  })
  if ('message' in res) {
    expect(typeof res.message === 'string' && res.message.length > 0).toBe(true)
    delete res.message
  }
  if ('path' in res) res.path = rel(res.path)
  for (const t of res.tried ?? []) t.path = rel(t.path)
  return res
}

test('project-context fixtures: 60 spec cases plus the plugin extras are loaded', () => {
  expect((SPEC as any[]).length).toBe(60)
  expect((EXTRA as any[]).length >= 5).toBe(true)
})

for (const c of [...(SPEC as any[]), ...(EXTRA as any[])]) {
  test(`project-context: ${c.name}`, () => {
    expect(runCase(c)).toEqual(c.expect)
  })
}
