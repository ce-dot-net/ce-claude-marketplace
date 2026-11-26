// ACE mod suite, 8.4.0: after an auth failure no further engine / ace-cli search (each one is a GET /config on the server)
// until the token file changes. Marker <root>/auth-rejected = sha256 of ~/.config/ace/config.json. Python twin: tests/test_auth_guard.py.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import { sha256Hex } from '../lib/cohort.ts'
import { HOME, HUMAN, PROOT, ROOT, SDIR, cliOf, done, host, mainTask, settle, submit } from './helpers.ts'

const CFG = `${HOME}/.config/ace/config.json`
const ENGINE = { [`${PROOT}/engine/search.js`]: '' }
const EXPIRED = { exitCode: 1, stderr: 'Session expired - please log in again: run `ace-cli login`.' }

test('engine auth failure still tries ace-cli; its auth failure holds: marker =  the token-file hash, later prompts spawn nothing, a new token lets one through', async ($, on) => {
  let engine = 0, cli = 0
  let cliAnswer: any = { exitCode: 1, stderr: 'Error: Not logged in' }
  let answer: any = EXPIRED
  const h = host(on, { files: { ...ENGINE, [CFG]: '{"auth":{"token":"dead"}}' }, search: () => (cli++, cliAnswer), engine: () => (engine++, answer) })
  await submit($)
  expect(engine).toBe(1)
  expect(cli).toBe(1)
  expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{"auth":{"token":"dead"}}'))
  await submit($, HUMAN + ' again')
  await submit($, HUMAN + ' once more')
  expect(engine).toBe(1)
  expect(cli).toBe(1)
  h.put(CFG, '{"auth":{"token":"fresh"}}')
  answer = { stdout: S8 }
  await submit($, HUMAN + ' after login')
  expect(engine).toBe(2)
})

test('ace-cli auth failure holds too (no engine)', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{}' }, search: () => ({ exitCode: 1, stderr: 'Error: Not logged in' }) })
  await submit($)
  await submit($, HUMAN + ' again')
  expect(h.searches().length).toBe(1)
  expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{}'))
})

// 8.4.1: the same guard on the other server paths of the mod (learn, session start, backfill: tests/bootstrap_backfill.test.ts).
const HELD = { [CFG]: '{}', [`${ROOT}/auth-rejected`]: sha256Hex('{}') }
test('learn: a held token sends nothing (no launcher, engine, ace-cli) but PARKS the trace in the queue (--enqueue); lock and temp file released', async ($, on) => {
  const h = host(on, { files: HELD, search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(0)
  expect(h.runs.some((r: any) => r.argv.some((a: any) => typeof a === 'string' && a.endsWith('/engine/learn.js')))).toBe(false)
  expect(h.enqueued.length).toBe(1)
  const q = h.enqueued[0]!, job = JSON.parse(q.argv[q.argv.length - 1]!), trace = JSON.parse(q.body!)
  expect([job.root, job.meta.hook, job.meta.project]).toEqual([ROOT, 'Stop', 'prj_t'])
  expect([trace.task.startsWith('User request: '), 'feedback' in trace, trace.evidence_source]).toEqual([true, false, 'none'])
  expect(h.rows().some((x: any) => x.event === 'learn_parked' && x.reason === 'auth_held' && x.enqueued === true)).toBe(true)
  expect([...h.files.keys()].some(k => /learn-inflight-main\.lock$/.test(k) || /\/tmp\/ace-trace-/.test(k))).toBe(false)
})
test('learn: held -> no Haiku self-eval and the pending votes survive (taken by the next sent main trace)', async ($, on) => {
  const h = host(on, { files: { ...HELD, [`${SDIR}/pending-downvote.json`]: '{"applied_log_ids": [7], "at": 1800000000}', [`${SDIR}/pending-upvote.json`]: '{"applied_log_ids": [8], "at": 1800000000}' },
    search: () => ({ stdout: S8 }), selfEval: true })
  await mainTask($, h)
  await done($)
  await settle(h)
  expect(h.modelCalls.length).toBe(0)
  expect([h.files.has(`${SDIR}/pending-downvote.json`), h.files.has(`${SDIR}/pending-upvote.json`)]).toEqual([true, true])
  expect(h.enqueued.length).toBe(1)
})
test('learn: ACE_TRACE_SINK set + held: the sink still gets the trace, nothing parked', async ($, on) => {
  const h = host(on, { files: HELD, search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: 'file:/home/u/sink' } })
  await mainTask($, h)
  await done($)
  expect([...h.files.keys()].some(k => k.startsWith('/home/u/sink/'))).toBe(true)
  expect(h.enqueued.length).toBe(0)
})
test('learn: a new token file releases the guard (the learn goes out again)', async ($, on) => {
  const h = host(on, { files: { ...HELD, [CFG]: '{"auth":{"token":"fresh"}}' }, search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(1)
})
const start = ($: any) => $.session.start({ cwd: '/proj', surface: null, isInteractive: false } as any)
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
for (const [name, a] of [['token_expired (exit 4)', { exitCode: 4, stderr: '{"error":{"code":"token_expired","status":401,"message":"x"}}' }],
  ['not logged in', { exitCode: 1, stderr: 'Error: Not logged in' }], ['Server error (401)', { exitCode: 1, stderr: 'Server error (401): token expired' }]] as const)
  test(`session start: a ${name} status holds the token (one probe, no re-probe), the next prompt searches nothing`, async ($, on) => {
    const h = host(on, { files: { [CFG]: '{"auth":{"token":"dead"}}' }, cli: x => x[0] === 'status' ? a : undefined, search: () => ({ stdout: S8 }) })
    await start($)
    await tick()
    expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{"auth":{"token":"dead"}}'))
    await submit($)
    expect(h.searches().length).toBe(0)
    expect(h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'status').length).toBe(1)
  })
test('session start: status ok releases a held token (the next prompt searches)', async ($, on) => {
  const h = host(on, { files: HELD, cli: x => x[0] === 'status' ? { stdout: '{}' } : undefined, search: () => ({ stdout: S8 }) })
  await start($)
  await tick()
  await submit($)
  expect(h.searches().length).toBe(1)
})
test('session start: a server_error status does not hold the token', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{}' }, cli: x => x[0] === 'status' ? { exitCode: 1, stderr: 'Server error (502): bad gateway' } : undefined, search: () => ({ stdout: S8 }) })
  await start($)
  await tick()
  expect(h.files.has(`${ROOT}/auth-rejected`)).toBe(false)
})

// 8.4.1 item 1: a 401 in the detached learn child shows up as a dead/ queue entry with last_error 'auth' (the child's own
// classification); the mod reads that on the next prompt and holds the token, before it searches.
const DEAD = `${ROOT}/trace-queue/dead`
const deadEntry = (err: string) => JSON.stringify({ v: 1, created_at: 1_800_000_000, last_error: err })
test('learn child 401: a dead auth entry newer than the token file holds the token on the next prompt (no search)', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{"auth":{"token":"dead"}}' }, search: () => ({ stdout: S8 }) })
  h.advance(61_000)
  h.put(`${DEAD}/0123456789abcdef0123456789abcdef.json`, deadEntry('auth'))
  await submit($)
  expect(h.files.get(`${ROOT}/auth-rejected`)).toBe(sha256Hex('{"auth":{"token":"dead"}}'))
  expect(h.searches().length).toBe(0)
})
test('learn child: a dead auth entry OLDER than the token file (re-login since) does not hold; nor does a non-auth dead entry', async ($, on) => {
  const h = host(on, { files: { [`${DEAD}/0123456789abcdef0123456789abcdef.json`]: deadEntry('auth') }, search: () => ({ stdout: S8 }) })
  h.advance(1000)
  h.put(CFG, '{"auth":{"token":"fresh"}}')
  h.put(`${DEAD}/1123456789abcdef0123456789abcdef.json`, deadEntry('4xx'))
  await submit($)
  expect(h.files.has(`${ROOT}/auth-rejected`)).toBe(false)
  expect(h.searches().length).toBe(1)
})

// 8.4.1 item 5: the hold self-heals: AUTH_HOLD_MS (30 min, fixed) after the marker was written one call is let through again;
// a token-file change still releases at once (test above). A dead entry that already held never holds a second time.
test('self-heal: held inside 30 min, released after; a renewed 401 holds again', async ($, on) => {
  let n = 0
  const h = host(on, { files: { [CFG]: '{}' }, search: () => (n++, { exitCode: 1, stderr: 'Error: Not logged in' }) })
  await submit($)
  expect(n).toBe(1)
  h.advance(29 * 60_000)
  await submit($, HUMAN + ' again')
  expect(n).toBe(1)
  h.advance(2 * 60_000)
  await submit($, HUMAN + ' later')
  expect(n).toBe(2)
  await submit($, HUMAN + ' once more')
  expect(n).toBe(2)
})
test('self-heal: an expired hold is not renewed by the dead entry that set it', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{}' }, search: () => ({ stdout: S8 }) })
  h.advance(61_000)
  h.put(`${DEAD}/0123456789abcdef0123456789abcdef.json`, deadEntry('auth'))
  await submit($)
  expect(h.searches().length).toBe(0)
  h.advance(31 * 60_000)
  await submit($, HUMAN + ' later')
  expect(h.searches().length).toBe(1)
})
test('self-heal: the learn goes out again after the window', async ($, on) => {
  const h = host(on, { files: HELD, search: () => ({ stdout: S8 }) })
  h.mtime.set(`${ROOT}/auth-rejected`, h.now() - 31 * 60_000)  // a hold written 31 min ago
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(1)
})

// review fixes (8.4.1)
const E = (n: number) => `${DEAD}/${String(n).padStart(32, '0')}.json`
test('re-login race: an old-token learn child that dies within 60 s after the new login never holds the new token', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{"auth":{"token":"fresh"}}' }, search: () => ({ stdout: S8 }) })
  h.advance(30_000)
  h.put(E(1), deadEntry('auth'))
  await submit($)
  expect(h.files.has(`${ROOT}/auth-rejected`)).toBe(false)
  expect(h.searches().length).toBe(1)
})
test('a successful search releases a held token (marker kept as a barrier: the dead entry that set it never holds again)', async ($, on) => {
  const h = host(on, { files: { [CFG]: '{}' }, search: () => ({ stdout: S8 }) })
  h.advance(61_000)
  h.put(E(1), deadEntry('auth'))
  await submit($)
  expect(h.searches().length).toBe(0)
  h.mtime.set(`${ROOT}/auth-rejected`, h.now() - 30 * 60_000)  // exactly 30:00 old: released
  await submit($, HUMAN + ' later')
  expect(h.searches().length).toBe(1)
  expect(h.files.get(`${ROOT}/auth-rejected`)).not.toBe(sha256Hex('{}'))
  await submit($, HUMAN + ' once more')
  expect(h.searches().length).toBe(2)
})
test('boundary: 29:59.999 is still held; a marker mtime in the future counts as expired', async ($, on) => {
  const h = host(on, { files: HELD, search: () => ({ stdout: S8 }) })
  h.mtime.set(`${ROOT}/auth-rejected`, h.now() - 30 * 60_000 + 1)
  await submit($)
  expect(h.searches().length).toBe(0)
  h.mtime.set(`${ROOT}/auth-rejected`, h.now() + 60_000)
  await submit($, HUMAN + ' again')
  expect(h.searches().length).toBe(1)
})
for (const [what, stderr, stdout] of [['a UUID ending in 401', 'trace 3fa85f64-5717-4562-b3fc-2c963f66a401 failed', ''],
  ['a number 0.7401', 'score 0.7401 too low', ''], ['auth words on stdout only', 'boom', 'unauthorized 401 not logged in']] as const)
  test(`isAuthFailure: ${what} does not hold`, async ($, on) => {
    const h = host(on, { files: { [CFG]: '{}' }, search: () => ({ exitCode: 1, stderr, stdout }) })
    await submit($)
    expect(h.files.has(`${ROOT}/auth-rejected`)).toBe(false)
  })
test('dead/ scan: at most the 20 newest entries, each read once per load (head only), a symlinked entry never read', async ($, on) => {
  const LINK = `${DEAD}/ffffffffffffffffffffffffffffffff.json`
  const h = host(on, { files: { [CFG]: '{}' }, links: [LINK], search: () => ({ stdout: S8 }) })
  h.advance(61_000)
  h.put(E(0), deadEntry('auth'))           // the oldest: past the cap
  for (let i = 1; i <= 20; i++) { h.advance(10); h.put(E(i), deadEntry('4xx')) }
  await submit($)
  const heads = () => h.runs.filter((r: any) => r.argv[0] === 'head')
  expect(heads().length).toBe(20)
  expect(heads().every((r: any) => r.argv[2] === '1024')).toBe(true)
  expect(heads().some((r: any) => r.argv.includes(LINK) || r.argv.includes(E(0)))).toBe(false)
  expect(h.files.has(`${ROOT}/auth-rejected`)).toBe(false)
  await submit($, HUMAN + ' again')
  expect(heads().length).toBe(20)          // nothing new: nothing re-read
})
