// 8.2.7 (lifeos, remote/mobile): (1) an unbound context is resolved again when a binding file appears (status, commands,
// the band's refresh: throttled, fingerprint of the binding files, never per render); a bound one stays as it is.
// (2) `/ace:ace-configure ... --approved` binds, but only the project of the identical waiting preview; the button still works.
// (3) the three unbound reasons apart (no_binding / no_org / org_not_member), and a hint for a mistyped --approved.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import { LINES } from '../context/index.ts'
import { UNBOUND_RECHECK_MS, newLoad } from '../io/state.ts'
import { refreshUnbound } from '../handlers/context.ts'
import { flagHint } from '../lib/approved.ts'
import { CWD, HOME, cliOf, host as baseHost } from './helpers.ts'
// 8.4.2: the band falls through to next(e) when it shows nothing; the 2.1.311 test kit has no ui.render implementation behind it
// ("$.ui.mount: no implementation for ui.render"), newer kits do. A test-only stub: nothing rendered. Mod code unchanged.
declare const h: any
const host = (on: any, o: any = {}) => { on('ui.render', async (x: any, e: any, next: any) => { try { return await next(e) } catch (err) { if (!/no implementation for ui\.render/.test(String(err))) throw err; return h(x.ui.resolve(e).Box, null) } }); return baseHost(on, o) }

const BAND = { plugin: 'ace', component: 'AbovePrompt', surface: 'terminal', props: { hasSurvey: false, isWorking: false, bodyRows: 10, bodyColumns: 120 } } as any
const start = ($: any) => $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
const run = async ($: any, name: string, args = '') => (await $.command.run({ command: `ace:ace-${name}`, args })).text as string
const runs = (h: any, sub: string) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === sub).length
const ST = (a: string[]) => a[0] === 'status' ? { stdout: '{"playbook":{"total_patterns":3}}' } : undefined
const CFG = `${CWD}/.ace/config.json`, GIT = { [`${CWD}/.git/config`]: '[core]\n' }
const bindFile = (o: any = { orgId: 'org_a', projectId: 'prj_a' }) => JSON.stringify(o)
// fs.stat counted: the band's refresh must not touch the disk on every render
function counted(on: any) {
  const n = { stat: 0 }
  const wrap = (name: string, ...rest: any[]) => name === 'fs.stat' && typeof rest[0] === 'function'
    ? on(name, (...a: any[]) => { n.stat++; return rest[0](...a) }) : on(name, ...rest)
  return { on: wrap, n }
}
const bandText = async (ui: any) => ((await ui.findAll({ type: 'Text' })) as any[]).map(t => t.text).join(' ')
async function render($: any) { const ui = await $.ui.mount(BAND); const t = await bandText(ui); await ui.unmount(); return t }

// ---- (1) re-resolve ----
test('unbound, then .ace/config.json appears: /ace:ace-status shows the binding without a restart', async ($, on) => {
  const h = host(on, { noSettings: true, cli: ST })
  await start($)
  await tick()
  expect(await run($, 'status')).toBe(LINES.unbound)
  h.put(CFG, bindFile())
  const t = await run($, 'status')
  expect(t).toContain('ACE · prj_a (org org_a)')
  expect(t).toContain('patterns: 3')
  await tick()
  expect(h.env.ACE_PROJECT_ID).toBe('prj_a')  // exported again: the hooks get the ids
})

test('unbound, then the file appears: the band refreshes (after the recheck interval) and shows nothing', async ($, on) => {
  const h = host(on, { noSettings: true, cli: ST })
  await start($)
  await tick()
  expect(await render($)).toContain('Repo nicht verbunden')
  h.put(CFG, bindFile())
  h.advance(UNBOUND_RECHECK_MS)
  await render($)
  await tick()
  expect(await render($)).not.toContain('nicht verbunden')
  expect(h.band()?.state ?? null).toBe(null)
  expect(h.statuses.at(-1)).toBe(undefined)
})

test('unbound without a file stays unbound; renders inside the interval never touch the disk; no CLI re-probe', async ($, on) => {
  const c = counted(on)
  const h = host(c.on, { noSettings: true, cli: ST })
  await start($)
  await tick()
  const ctx0 = runs(h, 'context'), stat0 = c.n.stat
  for (let i = 0; i < 30; i++) await render($)
  await tick()
  expect(c.n.stat).toBe(stat0)  // throttled: not one stat per render
  for (let i = 0; i < 5; i++) { h.advance(UNBOUND_RECHECK_MS); await render($); await tick() }
  expect(c.n.stat - stat0).toBeLessThanOrEqual(5 * 12)  // a few stats per interval, bounded
  expect(runs(h, 'context')).toBe(ctx0)  // nothing changed: never resolved again
  expect(await render($)).toContain('Repo nicht verbunden')
  expect(await run($, 'status')).toBe(LINES.unbound)
})

test('a bound session stays stable: no re-resolve, no stat from the band', async ($, on) => {
  const c = counted(on)
  const h = host(c.on, { cli: ST })
  await start($)
  await tick()
  const ctx0 = runs(h, 'context'), stat0 = c.n.stat
  for (let i = 0; i < 5; i++) { h.advance(UNBOUND_RECHECK_MS); await render($); await tick() }
  await run($, 'status')
  expect(runs(h, 'context')).toBe(ctx0)
  expect(c.n.stat).toBe(stat0)
})

test('a changed but still unbound resolution keeps a dismissed band dismissed (an unrelated config rewrite)', async ($, on) => {
  const h = host(on, { noSettings: true, cli: ST })
  await start($)
  await tick()
  const ui = await $.ui.mount(BAND)
  await ui.press({ key: 'x' })
  await ui.unmount()
  const published = () => h.debug.filter((l: string) => l.startsWith('ace band ')).length
  const p0 = published(), ctx0 = runs(h, 'context')
  h.put(`${HOME}/.config/ace/config.json`, JSON.stringify({ auth: { organizations: [{ org_id: 'org_a' }] } }))
  h.advance(UNBOUND_RECHECK_MS)
  await render($)
  await tick()
  expect(runs(h, 'context')).toBe(ctx0 + 1)  // the file changed: resolved again ...
  expect(published()).toBe(p0)               // ... same result: the band is not published again
  expect(await render($)).not.toContain('nicht verbunden')
})

// ---- (2) bind --approved ----
test('configure --approved without a waiting preview: preview + the line to copy, nothing written', async ($, on) => {
  const h = host(on, { env: { ACE_AUTO_ADOPT: '0' }, noSettings: true, files: GIT })
  await start($)
  const t = await run($, 'configure', 'org_a prj_p --approved')
  expect(t).toContain('Noch nichts geändert')
  expect(t).toContain('/ace:ace-configure org_a prj_p --approved')
  expect(t).toMatch(/erst die Vorschau/)
  expect(h.files.has(CFG)).toBe(false)
  expect(runs(h, 'init')).toBe(0)
})

test('configure --approved after the identical preview waits: binds that project, rebinds, status is bound', async ($, on) => {
  const h = host(on, { env: { ACE_AUTO_ADOPT: '0' }, noSettings: true, files: GIT, cli: ST })
  await start($)
  await tick()
  await run($, 'configure', 'org_a prj_p')
  expect(h.files.has(CFG)).toBe(false)
  const t = await run($, 'configure', 'org_a prj_p --approved')
  expect(JSON.parse(h.files.get(CFG)!)).toEqual({ orgId: 'org_a', projectId: 'prj_p' })
  expect(t).toContain('prj_p')
  expect(t).not.toContain('Noch nichts geändert')
  await tick()
  expect(await run($, 'status')).toContain('ACE · prj_p (org org_a)')
  expect(h.env.ACE_PROJECT_ID).toBe('prj_p')
})

test('configure --approved for another project than the waiting preview: nothing written', async ($, on) => {
  const h = host(on, { env: { ACE_AUTO_ADOPT: '0' }, noSettings: true, files: GIT })
  await start($)
  await run($, 'configure', 'org_a prj_p')
  const t = await run($, 'configure', 'org_a prj_q --approved')
  expect(h.files.has(CFG)).toBe(false)
  expect(t).toMatch(/erst die Vorschau/)
  expect(h.pending().label).toContain('prj_q')  // the new preview waits; a second --approved would then bind prj_q
})

test('the button still binds (interactive users)', async ($, on) => {
  const h = host(on, { env: { ACE_AUTO_ADOPT: '0' }, noSettings: true, files: GIT, cli: ST })
  await start($)
  await tick()
  const t = await run($, 'configure', 'org_a prj_p')
  expect(t).toContain('/ace:ace-configure org_a prj_p --approved')
  const ui = await $.ui.mount(BAND)
  await ui.press({ key: 'confirm' })
  await tick()
  await ui.unmount()
  expect(JSON.parse(h.files.get(CFG)!)).toEqual({ orgId: 'org_a', projectId: 'prj_p' })
  expect(await run($, 'status')).toContain('ACE · prj_p')
})

// ---- (3) the reasons apart, and the typo hint ----
test('no_binding: the old line; no_org and org_not_member: their own line and next step (band, status, ▼)', async ($, on) => {
  const h = host(on, { noSettings: true, files: { [CFG]: bindFile({ projectId: 'prj_a' }) }, cli: ST })
  await start($)
  await tick()
  const t = await run($, 'status')
  expect(t).toMatch(/keine Organisation/)
  expect(t).toContain('/ace:ace-configure')
  expect(t).not.toContain('Repo nicht verbunden')
  expect(h.band().line).toBe(t)
  expect(h.statuses.at(-1)).toBe('ACE ▼ keine Organisation')
})

test('org_not_member: names the org, the next step is the login (another account) or configure', async ($, on) => {
  const h = host(on, { noSettings: true, cli: ST, files: { [CFG]: bindFile({ orgId: 'org_x', projectId: 'prj_a' }),
    [`${HOME}/.config/ace/config.json`]: JSON.stringify({ auth: { organizations: [{ org_id: 'org_y' }] } }) } })
  await start($)
  await tick()
  const t = await run($, 'status')
  expect(t).toMatch(/nicht Mitglied/)
  expect(t).toContain('org_x')
  expect(t).toContain('/ace:ace-login')
  expect(h.band().line).toBe(t)
  expect(h.statuses.at(-1)).toBe('ACE ▼ kein Mitglied der Organisation')
  expect((await $.command.run({ command: 'ace', args: '' })).text).toContain('nicht Mitglied')
})

test('flagHint: only a near miss of --approved, never the flag itself or an unrelated flag', () => {
  expect(flagHint('lesson --aproved')).toContain('meintest du --approved?')
  expect(flagHint('--approvd')).toContain('--approvd')
  expect(flagHint('x --Approved')).toContain('meintest du --approved?')
  expect(flagHint('lesson --approved')).toBe(null)
  expect(flagHint('--mode docs-only --days-back 30')).toBe(null)
  expect(flagHint('--approve-all')).toBe(null)
  expect(flagHint('')).toBe(null)
})

test('a mistyped --approved: the hint is added, the behaviour is unchanged (preview only)', async ($, on) => {
  const h = host(on)
  await start($)
  const t = await run($, 'learn', 'always pin the CLI --aproved')
  expect(t).toContain('Noch nichts geändert')
  expect(t).toContain('meintest du --approved?')
  expect(runs(h, 'learn')).toBe(0)
  expect(await run($, 'learn', 'always pin the CLI')).not.toContain('meintest')
})

// ---- review follow-up ----
test('unboundReason: ids from the CLI path that are not org_/prj_ (or too long) give the general line', async ($, on) => {
  const bad = { bound: false, reason: 'no_org', projectId: `prj_${'x'.repeat(200)}`, source: 'repo_file', path: null }
  const h = host(on, { noSettings: true, cli: a => a[0] === 'context' ? { stdout: JSON.stringify(bad) } : ST(a) })
  await start($)
  await tick()
  expect(await run($, 'status')).toBe(LINES.unbound)
  expect(h.band().line).toBe(LINES.unbound)
  expect(h.statuses.at(-1)).toBe('ACE ▼ nicht verbunden')
})

test('unboundReason: a control character in the CLI orgId never reaches the band', async ($, on) => {
  const bad = { bound: false, reason: 'org_not_member', orgId: 'org_x\u001b[31m', source: 'repo_file', path: null, warnings: [] }
  const h = host(on, { noSettings: true, cli: a => a[0] === 'context' ? { stdout: JSON.stringify(bad) } : ST(a) })
  await start($)
  await tick()
  expect(h.band().line).toBe(LINES.unbound)
})

test('refreshUnbound: a resolution that throws keeps the old context', async () => {
  const L = newLoad()
  const old: any = { bound: false, reason: 'no_binding', tried: [], root: '/p', gitRoot: '/p', mainRoot: null, via: 'resolver' }
  Object.assign(L, { ctx: old, ctxCwd: '/p', env0: { HOME: '/h' }, ctxPrint: 'old', ctxCheckAt: 0 })
  let n = 0
  const $: any = { clock: { now: async () => 1e12 }, fs: { stat: async () => { throw new Error('ENOENT') } },
    plugin: { root: '/h/.claude/plugins/cache/m/ace/1', name: 'ace' },
    env: { get: async () => { if (++n > 2) throw new Error('boom'); return undefined } } }  // the 3rd get = inside the resolution
  expect(await refreshUnbound($, L, true)).toBe(false)
  expect(L.ctx).toBe(old)
  expect(L.refreshing).toBeFalsy()
})

test('a command while the band refresh runs waits for it instead of giving up', async ($, on) => {
  const h = host(on, { noSettings: true, cli: ST })
  await start($)
  await tick()
  h.put(CFG, bindFile())
  h.advance(UNBOUND_RECHECK_MS)
  const [ui, t] = await Promise.all([$.ui.mount(BAND), run($, 'status')])  // the render's refresh runs while the command asks
  await ui.unmount()
  expect(t).toContain('ACE · prj_a (org org_a)')
})

test('the typo hint survives the 60 KB cap', async ($, on) => {
  host(on)
  await start($)
  const t = await run($, 'learn', `${'y'.repeat(70_000)} --aproved`)
  expect(t.endsWith('meintest du --approved?')).toBe(true)
})

test('still unbound but another reason (no_binding -> no_org): the band is published again', async ($, on) => {
  const h = host(on, { noSettings: true, cli: ST })
  await start($)
  await tick()
  expect(h.band().line).toBe(LINES.unbound)
  h.put(CFG, bindFile({ projectId: 'prj_a' }))
  h.advance(UNBOUND_RECHECK_MS)
  await render($)
  await tick()
  expect(h.band().line).toMatch(/keine Organisation/)
  expect(await render($)).toMatch(/keine Organisation/)
})

test('config_invalid, then the file is repaired: bound without a restart', async ($, on) => {
  const h = host(on, { noSettings: true, cli: ST, files: { [CFG]: '{"orgId": ' } })
  await start($)
  await tick()
  expect(h.band().state).toBe('config_invalid')
  h.put(CFG, bindFile())
  h.advance(UNBOUND_RECHECK_MS)
  await render($)
  await tick()
  expect(h.band()?.state ?? null).toBe(null)
  expect(await run($, 'status')).toContain('ACE · prj_a')
})

// the bind target is where the CLI/our writer actually writes: init target of the session cwd, not of the root
const NEST = '/proj/sub'
const nested = () => ({ ...GIT, [`${NEST}/.git/config`]: '[core]\n' })
test('cwd != root: the preview names the file the button writes', async ($, on) => {
  const h = host(on, { env: { ACE_AUTO_ADOPT: '0' }, noSettings: true, files: nested(), cwd: NEST, cli: ST })
  await start($)
  await tick()
  const t = await run($, 'configure', 'org_a prj_p')
  expect(t).toContain(`${NEST}/.ace/config.json`)
  const ui = await $.ui.mount(BAND)
  await ui.press({ key: 'confirm' })
  await tick()
  await ui.unmount()
  expect(JSON.parse(h.files.get(`${NEST}/.ace/config.json`)!)).toEqual({ orgId: 'org_a', projectId: 'prj_p' })
})

test('bind --approved: a preview for another target (cwd moved) is not the same preview', async ($, on) => {
  const o: any = { env: { ACE_AUTO_ADOPT: '0' }, noSettings: true, files: nested() }
  const h = host(on, o)
  await start($)
  await run($, 'configure', 'org_a prj_p')  // target /proj
  o.cwd = NEST
  const t = await run($, 'configure', 'org_a prj_p --approved')
  expect(t).toMatch(/erst die Vorschau/)
  expect(t).toContain(`${NEST}/.ace/config.json`)
  expect(h.files.has(CFG)).toBe(false)
  expect(h.files.has(`${NEST}/.ace/config.json`)).toBe(false)
})
