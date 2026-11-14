// 8.2.5: the device login works without a browser (remote / SSH): `ace-cli login --no-browser` is streamed through
// $.process.spawn, the URL and the code are shown (toast + log) while the CLI still waits. `--approved` runs login and
// install like their button (Moshi/herdr). An unbound repo without ace-cli gets the CLI installed first (CLI -> login -> configure).
import { expect, test } from 'claude-code/testing'
import { parseLogin } from '../ui/band.ts'
import { CWD, cliOf, host } from './helpers.ts'

const start = ($: any, cwd = CWD) => $.session.start({ cwd, surface: null, isInteractive: false } as any)
const run = async ($: any, name: string, args = '') => (await $.command.run({ command: `ace:ace-${name}`, args })).text as string
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
const NOT_LOGGED = (a: string[]) => a[0] === 'status' ? { exitCode: 3, stderr: '{"error":{"code":"not_logged_in","status":null,"message":"x"}}' } : undefined
const OUT = '\n\u001b[36m  Open this URL to authenticate:\u001b[39m\n  https://ace.code-engine.app/device?code=ABCD-EFGH\n\n  Or enter this code manually: \u001b[1mABCD-EFGH\u001b[22m\n\n'
const LINE = 'Öffne https://ace.code-engine.app/device?code=ABCD-EFGH und gib den Code ABCD-EFGH ein'
const instCalls = (h: any) => h.runs.filter((r: any) => r.argv.some((a: string) => a.endsWith('/ace_cli_installer.py'))).map((r: any) => r.argv[r.argv.length - 1])

test('parseLogin: the plain output (ANSI stripped), the --json event, a 3-3 code; nothing without both parts', () => {
  expect(parseLogin(OUT)).toEqual({ url: 'https://ace.code-engine.app/device?code=ABCD-EFGH', code: 'ABCD-EFGH' })
  expect(parseLogin('{"event":"device_code","user_code":"WXYZ-1234","verification_url":"https://ace.code-engine.app/device"}'))
    .toEqual({ url: 'https://ace.code-engine.app/device', code: 'WXYZ-1234' })
  expect(parseLogin('Open https://ace.code-engine.app/device\nOr enter this code manually: ABC-123\n')).toEqual({ url: 'https://ace.code-engine.app/device', code: 'ABC-123' })
  expect(parseLogin('  Open this URL to authenticate:\n  https://ace.code-engine.app/device\n')).toBe(null)  // the code comes in a later piece
  expect(parseLogin('Or enter this code manually: ABCD-EFGH')).toBe(null)
})

test('login (button / --approved): `login --no-browser` streamed; URL + code in toast and log while the CLI still waits; then angemeldet + rebind', async ($, on) => {
  let release!: () => void
  const gate = new Promise<void>(r => { release = r })
  let up = false
  const h: any = host(on, { cli: a => a[0] === 'status' ? (up ? { stdout: '{}' } : NOT_LOGGED(a)) : undefined,
    spawn: async function* () { yield { stream: 'stdout', text: OUT.slice(0, 50) }; yield { stream: 'stdout', text: OUT.slice(50) }; await gate; up = true; return { code: 0, signal: null } } })
  await start($)
  await tick()
  const statusBefore = h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'status').length
  const shown = await run($, 'login', '--approved')  // the button's startLogin; the text comes back once URL + code are known
  expect(cliOf(h.spawns[0])).toEqual(['login', '--no-browser'])
  expect(shown).toContain(LINE)
  expect(h.logs.some((l: string) => l.includes(LINE))).toBe(true)
  expect(h.toasts.some((t: string) => t.includes(LINE))).toBe(true)
  expect(h.toasts).not.toContain('ACE: angemeldet')  // still waiting for the confirmation
  expect(h.toasts.some((t: string) => /Browser/.test(t))).toBe(false)
  release()
  await tick()
  expect(h.toasts.at(-1)).toBe('ACE: angemeldet')
  expect(h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'status').length).toBeGreaterThan(statusBefore)  // rebind re-verifies
})

test('login: unknown output -> its first ~300 characters as a log line; a failed exit -> Login nicht abgeschlossen', async ($, on) => {
  const weird = 'Something unexpected: ' + 'x'.repeat(1000)
  const h: any = host(on, { cli: NOT_LOGGED, spawn: async function* () { yield { stream: 'stderr', text: weird }; return { code: 1, signal: null } } })
  await start($)
  const shown = await run($, 'login', '--approved')  // the button's startLogin; the text comes back once URL + code are known
  await tick()
  expect(shown).toContain('Something unexpected')
  const l = h.logs.find((x: string) => x.includes('Something unexpected'))
  expect(l).toBeTruthy()
  expect(l.length).toBeLessThan(400)
  expect(h.toasts.at(-1)).toBe('ACE: Login nicht abgeschlossen')
})

test('login: the CLI cannot start -> Login nicht abgeschlossen, never throws', async ($, on) => {
  const h: any = host(on, { cli: NOT_LOGGED, spawn: async function* () { throw new Error('spawn ace-cli ENOENT') } })
  await start($)
  await run($, 'login', '--approved')
  await tick()
  expect(h.toasts.at(-1)).toBe('ACE: Login nicht abgeschlossen')
})

test('/ace:ace-login: button label "Anmelden" (no browser promise), nothing runs by itself', async ($, on) => {
  const h: any = host(on, { cli: NOT_LOGGED })
  await start($)
  const t = await run($, 'login')
  expect(h.pending()).toMatchObject({ kind: 'login', label: 'Anmelden' })
  expect(t).not.toMatch(/Browser|opens the browser/)
  expect(h.spawns.length).toBe(0)
})

test('/ace:ace-login --approved: runs the device login at once (same as the button); URL + code in the command text', async ($, on) => {
  const h: any = host(on, { cli: NOT_LOGGED, spawn: async function* () { yield { stream: 'stdout', text: OUT }; return { code: 0, signal: null } } })
  await start($)
  const t = await run($, 'login', '--approved')
  expect(cliOf(h.spawns[0])).toEqual(['login', '--no-browser'])
  expect(t).toContain(LINE)
  expect(t).not.toContain('gilt hier nicht')
})

test('/ace:ace-install-cli --approved: runs the installer at once (same as the button), the result in the text', async ($, on) => {
  const h: any = host(on, { cli: a => a[0] === '--version' ? { exitCode: 1, stderr: 'not found' } : undefined,
    installer: a => a[0] === '--run' ? { state: 'ok', detail: '4.4.2' } : { state: 'ok' } })
  await start($)
  const t = await run($, 'install-cli', '--approved')
  expect(instCalls(h)).toContain('--run')
  expect(t).toContain('ace-cli installiert')
  expect(t).not.toContain('gilt hier nicht')
})

// ---- unbound + no ace-cli: install first (the band said only "Repo nicht verbunden", and configure/login need the CLI) ----
const NOCLI = (a: string[]) => a[0] === '--version' ? { exitCode: 1, stderr: "Error: Cannot find module '/x/cli.js'" } : undefined

test('unbound + CLI missing: the installer starts in the background (quiet), not the unbound band while it runs', async ($, on) => {
  let installed = false
  const h: any = host(on, { noSettings: true, env: { ACE_PROJECT_ID: '' }, cli: a => installed ? undefined : NOCLI(a),
    installer: a => a[0] === '--wait' ? (installed = true, { state: 'ok', detail: '4.4.2' }) : { state: 'started' } })
  await start($)
  await tick()
  expect(instCalls(h)).toEqual(['--ensure', '--wait'])
  expect(h.band()?.state).toBe('unbound')  // installed: next step is configure
})

test('unbound + CLI missing + install failed: band cli_missing with [Erneut versuchen], not unbound', async ($, on) => {
  const h: any = host(on, { noSettings: true, env: { ACE_PROJECT_ID: '' }, cli: NOCLI,
    installer: a => a[0] === '--wait' ? { state: 'failed', detail: 'npm ci exit 1' } : { state: 'started' } })
  await start($)
  await tick()
  expect(h.band()).toMatchObject({ state: 'cli_missing', retry: 'npm ci exit 1' })
  expect(h.statuses.at(-1)).toBe('ACE ▼ ace-cli fehlt')
})

test('unbound + CLI present: unchanged (band unbound, no installer, no status call)', async ($, on) => {
  const h: any = host(on, { noSettings: true, env: { ACE_PROJECT_ID: '' }, installer: () => ({ state: 'started' }) })
  await start($)
  await tick()
  expect(h.band()?.state).toBe('unbound')
  expect(instCalls(h)).toEqual([])
  expect(h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'status').length).toBe(0)
})

// ---- no node / npm on the machine: no install attempt, the reason in band, /ace:ace-install-cli and doctor ----
const TOOL = 'npm/node fehlt (Node >= 20 nötig): installiere z.B. via nvm/apt, dann /ace:ace-install-cli'
const BOUND_NOCLI = (a: string[]) => a[0] === 'status' || a[0] === '--version' ? { exitCode: 1, stderr: "Error: Cannot find module '/x/cli.js'" } : undefined

for (const [name, opts] of [['unbound', { noSettings: true, env: { ACE_PROJECT_ID: '' }, cli: NOCLI }], ['bound', { cli: BOUND_NOCLI }]] as const) {
  test(`${name} + CLI missing + no node/npm: band cli_missing naming the toolchain, no --wait`, async ($, on) => {
    const h: any = host(on, { ...(opts as any), installer: () => ({ state: 'unavailable', detail: TOOL }) })
    await start($)
    await tick()
    expect(instCalls(h)).toEqual(['--ensure'])
    expect(h.band()).toMatchObject({ state: 'cli_missing', retry: TOOL })
    expect(h.band().line).toContain('npm/node fehlt (Node >= 20 nötig)')
  })
}

test('/ace:ace-install-cli without node/npm: the preview names the reason', async ($, on) => {
  host(on, { cli: a => a[0] === '--version' ? { exitCode: 1, stderr: 'not found' } : undefined, installer: () => ({ state: 'unavailable', detail: TOOL }) })
  await start($)
  expect(await run($, 'install-cli')).toContain(TOOL)
})

test('/ace:ace-doctor without node/npm: the reason on the ace-cli line', async ($, on) => {
  host(on, { cli: a => a[0] === '--version' ? { exitCode: 1, stderr: 'not found' } : undefined, installer: () => ({ state: 'unavailable', detail: TOOL }) })
  await start($)
  expect(await run($, 'doctor')).toMatch(/ace-cli  ✗ .*npm\/node fehlt \(Node >= 20 nötig\)/)
})
