// 8.1.0 (cli 4.4.1): bind / configure / auto-adopt write through `ace-cli init --json --fix-gitignore`; our writer only
// when the CLI has no init --json. Fixture: ../../tests-fixtures/project-context/init-target.json (spec §9).
// Mirror: tests/test_init_target.py (Python chain + real CLI in tests/test_cli_contract.py).
import { expect, test } from 'claude-code/testing'
import CASES from './fixtures/init_target_cases.ts'
import { initTarget, WARN_LINES } from '../context/index.ts'
import { normPath, type Reader } from '../context/resolve.ts'
import { REPO_WRITE_SH } from '../lib/sh.ts'
import { cliOf, host } from './helpers.ts'

// Everything through events, as the engine drives it: session.start, /ace:ace-configure <org> <prj> (the pending bind),
// the AbovePrompt band mounted and its button pressed.
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
const BAND = { plugin: 'ace', component: 'AbovePrompt', surface: 'terminal', props: { hasSurvey: false, isWorking: false, bodyRows: 10, bodyColumns: 120 } } as any
async function bind($: any, cwd: string, org = 'org_a', prj = 'prj_a') {
  await $.session.start({ cwd, surface: null, isInteractive: false } as any)
  await tick()
  await $.command.run({ command: 'ace:ace-configure', args: `${org} ${prj}` })
  const ui = await $.ui.mount(BAND)
  await ui.press({ key: 'confirm' })
  await tick()
  return ui
}

const R = '/r'
function reader(layout: Record<string, string | null>): Reader {
  const files = new Map<string, string>(), dirs = new Set<string>()
  for (const [rel, content] of Object.entries(layout)) {
    let p = normPath(`${R}/${rel}`)
    if (content === null) dirs.add(p); else files.set(p, content)
    while ((p = normPath(p + '/..')) !== '/') dirs.add(p)
  }
  return (path) => {
    if (files.has(path)) return files.get(path)!
    if (dirs.has(path)) throw new Error(`EISDIR: ${path}`)
    return null
  }
}
const files = (layout: Record<string, string | null>) =>
  Object.fromEntries(Object.entries(layout).filter(([, v]) => v !== null).map(([k, v]) => [`${R}/${k}`, v as string]))
const at = (rel: string) => normPath(`${R}/${rel}`)

for (const c of (CASES as any).cases) {
  test(`init target: ${c.name}`, async () => {
    expect(await initTarget(at(c.cwd), reader(c.layout))).toEqual({ root: at(c.expect.root), mainCheckout: c.expect.mainCheckout, untrusted: !!c.expect.untrusted })
  })
  if (c.expect.root === c.cwd && !c.expect.untrusted && !Object.keys(c.layout).some(k => k.endsWith('.git') || k.includes('.git/'))) continue
  test(`fallback writer: ${c.name}`, async ($, on) => {
    const h = host(on, { noSettings: true, files: files(c.layout), cwd: at(c.cwd), root: at(c.cwd), env: { ACE_AUTO_ADOPT: '0' } })
    const ui = await bind($, at(c.cwd))
    const out = `${at(c.expect.root)}/.ace/config.json`
    expect(JSON.parse(h.files.get(out)!)).toEqual({ orgId: 'org_a', projectId: 'prj_a' })
    expect(h.logs.some(l => l.includes(`${out} geschrieben`))).toBe(true)
    expect(h.logs.includes(WARN_LINES.worktree_topology_untrusted)).toBe(!!c.expect.untrusted)
    if (c.expect.shadowedBy) {
      expect(h.files.get(at(c.expect.shadowedBy))).toBe(c.layout[c.expect.shadowedBy])  // never touched
      expect((await ui.find({ type: 'Text', text: /eigene \.ace\/config\.json/ }))?.text).toContain(WARN_LINES.worktree_file_shadows_main)
    }
    await ui.unmount()
  })
}

const MAIN = '/r/main', WT = '/r/wt'
const tree = (extra: Record<string, string> = {}) => ({ [`${MAIN}/.git/config`]: '[core]\n', [`${MAIN}/.git/HEAD`]: 'ref: refs/heads/main\n',
  [`${WT}/.git`]: `gitdir: ${MAIN}/.git/worktrees/wt\n`, [`${MAIN}/.git/worktrees/wt/commondir`]: '../..\n',
  [`${MAIN}/.git/worktrees/wt/gitdir`]: `${WT}/.git\n`, [`${WT}/src/x.ts`]: '', ...extra })
const initJson = (o: any = {}) => JSON.stringify({ path: `${MAIN}/.ace/config.json`, orgId: 'org_a', projectId: 'prj_a', strippedSecrets: [],
  gitignore: 'ok', warnings: ['written_to_main_checkout'], mainCheckout: true, ...o })
const inits = (h: any) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'init').map((r: any) => cliOf(r.argv))
const repoWrites = (h: any) => h.runs.filter((r: any) => r.argv[0] === '/bin/sh' && r.argv[2] === REPO_WRITE_SH)

test('bind: ace-cli init --json --fix-gitignore with the ids in the session cwd; the CLI writes, we do not', async ($, on) => {
  const h = host(on, { noSettings: true, root: WT, cwd: `${WT}/src`, env: { ACE_AUTO_ADOPT: '0' }, files: tree(),
    cli: a => a[0] === 'init' ? { stdout: initJson() } : undefined })
  const ui = await bind($, `${WT}/src`)
  expect(inits(h)).toEqual([['init', '--json', '--fix-gitignore', '--org', 'org_a', '--project', 'prj_a']])
  expect(repoWrites(h).length).toBe(0)
  expect(h.logs.some(l => l.includes(`${MAIN}/.ace/config.json geschrieben`))).toBe(true)
  expect(await ui.find({ key: 'rm-shadow' })).toBeUndefined()
  await ui.unmount()
})

test('bind: worktree_file_shadows_main -> the band line with [Entfernen]; the press removes only that file', async ($, on) => {
  const h = host(on, { noSettings: true, root: WT, cwd: `${WT}/src`, env: { ACE_AUTO_ADOPT: '0' },
    files: tree({ [`${WT}/.ace/config.json`]: '{"orgId":"org_a","projectId":"prj_old"}', [`${MAIN}/.ace/config.json`]: '{}' }),
    cli: a => a[0] === 'init' ? { stdout: initJson({ warnings: ['written_to_main_checkout', 'worktree_file_shadows_main'], shadowedBy: `${WT}/.ace/config.json` }) } : undefined })
  const ui = await bind($, `${WT}/src`)
  expect(h.files.has(`${WT}/.ace/config.json`)).toBe(true)  // never deleted silently
  expect(WARN_LINES.worktree_file_shadows_main).toBe('ACE ▼ Dieser Worktree hat eine eigene .ace/config.json, die die Bindung des Haupt-Checkouts überschreibt')
  expect((await ui.find({ type: 'Text', text: /eigene \.ace\/config\.json/ }))?.text).toContain(WARN_LINES.worktree_file_shadows_main)
  await ui.press({ key: 'rm-shadow' })
  await tick()
  expect(h.files.has(`${WT}/.ace/config.json`)).toBe(false)
  expect(h.files.has(`${MAIN}/.ace/config.json`)).toBe(true)
  expect(await ui.find({ key: 'rm-shadow' })).toBeUndefined()
  await ui.unmount()
})

test('bind: the CLI refusal (exit 1, stderr error JSON) is final: a toast, no fallback write', async ($, on) => {
  const h = host(on, { noSettings: true, root: WT, cwd: WT, env: { ACE_AUTO_ADOPT: '0' }, files: tree(),
    cli: a => a[0] === 'init' ? { exitCode: 1, stderr: '{"error":{"code":"generic","status":null,"message":"Refusing to write x: .ace is a symlink."}}' } : undefined })
  await (await bind($, WT)).unmount()
  expect(inits(h).length).toBe(1)
  expect(repoWrites(h).length).toBe(0)
  expect(h.files.has(`${MAIN}/.ace/config.json`)).toBe(false)
})

test('bind: a CLI without init --json (unknown command) -> our writer, the main checkout', async ($, on) => {
  const h = host(on, { noSettings: true, root: WT, cwd: WT, env: { ACE_AUTO_ADOPT: '0' }, files: tree(),
    cli: a => a[0] === 'init' ? { exitCode: 1, stderr: "error: unknown command 'init'" } : undefined })
  await (await bind($, WT)).unmount()
  expect(inits(h).length).toBe(1)
  expect(JSON.parse(h.files.get(`${MAIN}/.ace/config.json`)!)).toEqual({ orgId: 'org_a', projectId: 'prj_a' })
})

test('auto-adopt goes through ace-cli init --json --fix-gitignore', async ($, on) => {
  const h = host(on, { noSettings: true, root: WT, files: tree({ [`${MAIN}/.claude/settings.json`]: JSON.stringify({ env: { ACE_ORG_ID: 'org_m', ACE_PROJECT_ID: 'prj_m' } }) }),
    cli: a => a[0] === 'init' ? { stdout: initJson({ orgId: 'org_m', projectId: 'prj_m' }) } : undefined })
  await $.session.start({ cwd: WT, surface: null, isInteractive: false } as any)
  await tick()
  expect(inits(h)).toEqual([['init', '--json', '--fix-gitignore', '--org', 'org_m', '--project', 'prj_m']])
  expect(repoWrites(h).length).toBe(0)
})

test('auto-adopt never on an untrusted worktree topology (forged commondir): the warning, nothing written', async ($, on) => {
  const h = host(on, { noSettings: true, root: '/r/wt', files: { '/r/victim/HEAD': 'ref: refs/heads/main\n', '/r/victim/config': '[core]\n',
    '/r/wt/.git': 'gitdir: ../gd\n', '/r/gd/commondir': '../victim\n',
    '/r/wt/.claude/settings.json': JSON.stringify({ env: { ACE_ORG_ID: 'org_m', ACE_PROJECT_ID: 'prj_m' } }) } })
  await $.session.start({ cwd: '/r/wt', surface: null, isInteractive: false } as any)
  await tick()
  expect(inits(h).length).toBe(0)
  expect(repoWrites(h).length).toBe(0)
  expect(h.logs.includes(WARN_LINES.worktree_topology_untrusted)).toBe(true)
})
