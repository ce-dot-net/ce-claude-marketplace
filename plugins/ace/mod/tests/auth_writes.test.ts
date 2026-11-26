// ACE mod suite, 8.4.2: the auth hold (io/auth.ts) also guards the confirm-type CLI writes (clear, delta, import-patterns,
// learn, tune; bootstrap: bootstrap_backfill.test.ts). Held: one login line, no preview, no ace-cli call, nothing pending. A failed
// write whose classify() says not_logged_in / expired holds the token. Harness: ./helpers.ts.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import { sha256Hex } from '../lib/cohort.ts'
import { CWD, HOME, PROOT, ROOT, cliOf, host } from './helpers.ts'
import { execPending, noAuthLine } from '../io/pending.ts'
import { dataRoot } from '../io/state.ts'

const start = ($: any) => $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
const run = async ($: any, name: string, args = '') => (await $.command.run({ command: `ace:ace-${name}`, args })).text as string
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
const cliRuns = (h: any, sub: string) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === sub)
const CFG = `${HOME}/.config/ace/config.json`
const FILE = `${CWD}/pb.json`
const HELD = { [CFG]: '{}', [`${ROOT}/auth-rejected`]: sha256Hex('{}'), [FILE]: '{"playbook":{"s":[{"content":"c"}]}}' }
const EXPIRED = (a: string[]) => a[0] === 'status' ? { exitCode: 4, stderr: '{"error":{"code":"token_expired","status":401}}' } : undefined
const CASES = [['clear', '', 'clear'], ['delta', 'add [{"content":"c","section":"s"}]', 'delta'], ['import-patterns', 'pb.json', 'import'],
  ['learn', 'always pin the CLI', 'learn'], ['tune', 'search-top-k=20', 'tune']] as const

for (const [name, args, sub] of CASES) {
  test(`${name} while held: the login line, no preview, no ace-cli ${sub}, nothing pending`, async ($, on) => {
    const h = host(on, { files: HELD, cli: EXPIRED })  // the session-start status agrees (an ok status would release the hold)
    await start($)
    for (const a of [args, `${args} --approved`]) {
      const t = await run($, name, a)
      expect(t).toContain('nicht angemeldet, bitte /ace:ace-login ausführen')
      expect(t).not.toContain('Noch nichts geändert')
    }
    expect(cliRuns(h, sub).length).toBe(0)
    expect(h.pending()).toBe(null)
  })
  test(`${name}: a failed ${sub} with an expired token holds it`, async ($, on) => {
    const h = host(on, { files: { [CFG]: '{"auth":{"token":"dead"}}', [FILE]: HELD[FILE] },
      cli: a => a[0] === 'status' ? { stdout: '{}' } : a[0] === sub ? { exitCode: 4, stderr: '{"error":{"code":"token_expired","status":401}}' } : undefined })
    await start($)
    await run($, name, args)                      // the preview (clear runs only on an identical waiting pending)
    await run($, name, `${args} --approved`)
    expect(cliRuns(h, sub).length).toBe(1)
    expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{"auth":{"token":"dead"}}'))
  })
}
test('a failed write that is no auth failure (server_error) never holds', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{}' }, cli: a => a[0] === 'status' ? { stdout: '{}' } : a[0] === 'learn' ? { exitCode: 1, stderr: 'Server error (502): bad gateway' } : undefined })
  await start($)
  await run($, 'learn', 'always pin the CLI --approved')
  expect(h.files.has(`${ROOT}/auth-rejected`)).toBe(false)
})

// review (8.4.2): read-only tune stays allowed while held
test('tune while held: no args and `show` still read (tune show --json); a tune write stays blocked', async ($, on) => {
  const h = host(on, { files: HELD, cli: a => EXPIRED(a) ?? (a[0] === 'tune' ? { stdout: '{"search_top_k":10}' } : undefined) })
  await start($)
  expect(await run($, 'tune')).toContain('search_top_k')
  expect(await run($, 'tune', 'show')).toContain('search_top_k')
  expect(cliRuns(h, 'tune').map((r: any) => r.argv.slice(r.argv.indexOf('tune'), r.argv.indexOf('tune') + 3))).toEqual([['tune', 'show', '--json'], ['tune', 'show', '--json']])
  expect(await run($, 'tune', 'search-top-k=20 --approved')).toContain('nicht angemeldet')
  expect(cliRuns(h, 'tune').length).toBe(2)
})

// review (8.4.2): the button (execPending) refuses every guarded subcommand when the hold started after the preview
for (const [name, args, sub] of [['bootstrap', 'docs-only light', 'bootstrap'], ...CASES] as const)
  test(`button pressed after the hold started: ${sub} runs nothing, the login toast`, async ($, on) => {
    const h = host(on, { files: { [CFG]: '{}', [FILE]: HELD[FILE] }, cli: a => a[0] === 'status' ? { stdout: '{"playbook":{"total_patterns":3}}' } : undefined })
    await start($)
    expect(await run($, name, args)).toContain('Noch nichts geändert')  // not held: the preview, a pending
    const p = h.pending()
    expect(p.argv[0]).toBe(sub)
    const files = new Map<string, string>(), ran: string[][] = []
    const fake: any = { env: { get: async (k: string) => (k === 'HOME' ? HOME : undefined) }, plugin: { root: PROOT, name: 'ace' },
      clock: { now: async () => 1_800_000_000_000 }, state: { get: async () => ({ value: null }), set: async () => ({}) },
      fs: { read: async (f: string) => { if (!files.has(f)) throw new Error('ENOENT'); return files.get(f) }, stat: async () => ({ mtimeMs: 1_800_000_000_000 - 1000 }) },
      process: { run: async (argv: string[]) => { ran.push(argv); return { exitCode: 0, stdout: '', stderr: '' } } } }
    files.set(CFG, '{}'); files.set(`${await dataRoot(fake)}/auth-rejected`, sha256Hex('{}'))  // the hold, written after the preview
    const d = await execPending(fake, { root: CWD, orgId: 'org_t', projectId: 'prj_t' }, { ...p, backfill: undefined })
    expect([d.ok, d.toast]).toEqual([false, noAuthLine(sub)])
    expect(ran.length).toBe(0)
  })

// review (8.4.2): a successful status probe releases a wrong hold by hand (/ace:ace-status, -doctor, -test)
for (const cmd of ['status', 'doctor', 'test'])
  test(`/ace:ace-${cmd} with status ok releases the hold; a guarded command works again`, async ($, on) => {
    let ok = false
    const h = host(on, { files: HELD, cli: a => a[0] === 'status' ? (ok ? { stdout: '{"playbook":{"total_patterns":3}}' } : EXPIRED(a)) : a[0] === 'learn' ? { stdout: '{}' } : undefined })
    await start($)
    await tick()                                  // the session-start status (expired) has run and holds
    expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{}'))
    ok = true
    await run($, cmd)
    expect(h.files.get(`${ROOT}/auth-rejected`)).toBe('ok')
    await run($, 'learn', 'always pin the CLI --approved')
    expect(cliRuns(h, 'learn').length).toBe(1)
  })
test('/ace:ace-status with a failing status keeps the hold', async ($, on) => {
  const h = host(on, { files: HELD, cli: EXPIRED })
  await start($)
  await run($, 'status')
  expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{}'))
})
