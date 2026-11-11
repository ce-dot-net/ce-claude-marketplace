// 8.2.4: a `server_error` band heals itself. A transient failure at session start (a deploy's 502 window) is re-probed
// in the background on a short bounded backoff ($.clock.after chain), and any later successful server search clears it.
// Non-transient states stay one-shot. Harness: ./helpers.ts (mockClock: the timers move only with h.clock.advance).
import { expect, test } from 'claude-code/testing'
import { classify } from '../context/index.ts'
import { MAX_REPROBES, REPROBE_EVERY_MS, REPROBE_MS, RECOVERED_LINE } from '../handlers/context.ts'
import { SID, cliOf, host, submit } from './helpers.ts'

const start = ($: any) => $.session.start({ cwd: '/proj', surface: null, isInteractive: false } as any)
const tick = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 2)) }
const statusRuns = (h: any) => h.runs.filter((r: any) => cliOf(r.argv)?.[0] === 'status').length
const BAD = { exitCode: 1, stderr: '{"level":"error","message":"{\\"error\\":\\"Server error (502): Bad Gateway\\"}"}' }
const OK = { exitCode: 0, stdout: '{"playbook":{"total_patterns":1}}' }
// a status answer that switches when `up()` says so
const status = (up: () => boolean) => (a: string[]) => a[0] === 'status' ? (up() ? OK : BAD) : undefined
const advance = async (h: any, ms: number) => { await h.clock.advance(ms); await tick() }

test('classify is unchanged: 502, timeout and a generic failure are server_error', () => {
  expect(classify(1, BAD.stderr)).toBe('server_error')
  expect(classify(null, '', false, true)).toBe('server_error')
  expect(classify(1, 'fetch failed')).toBe('server_error')
  expect(classify(4, '')).toBe('expired')
})

test('the schedule is bounded: a few tries within ~2 min, then every few minutes, a hard cap', () => {
  expect(REPROBE_MS.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(120_000)
  expect(REPROBE_EVERY_MS).toBeGreaterThanOrEqual(120_000)
  expect(MAX_REPROBES).toBeGreaterThan(REPROBE_MS.length)
  expect(MAX_REPROBES).toBeLessThanOrEqual(50)
})

test('502 at start: band shown, a recovered re-probe clears it and logs once', async ($, on) => {
  let up = false
  const h = host(on, { mockClock: true, installer: () => ({ state: 'ok' }), cli: status(() => up) })
  await start($)
  await tick()
  expect(h.band()?.state).toBe('server_error')
  expect(statusRuns(h)).toBe(1)
  up = true
  await advance(h, REPROBE_MS[0])
  expect(statusRuns(h)).toBe(2)
  expect(h.band()?.state ?? null).toBe(null)
  expect(h.statuses[h.statuses.length - 1]).toBe(undefined)  // the ▼ is gone
  expect(h.logs.filter((l: string) => l === RECOVERED_LINE).length).toBe(1)
  await advance(h, 3_600_000)  // healed: the chain is over
  expect(statusRuns(h)).toBe(2)
  expect(h.logs.filter((l: string) => l === RECOVERED_LINE).length).toBe(1)
})

for (const [exitCode, state] of [[4, 'expired'], [7, 'no_access'], [3, 'not_logged_in'], [6, 'project_not_found']] as const) {
  test(`non-transient ${state} is never re-probed`, async ($, on) => {
    const h = host(on, { mockClock: true, installer: () => ({ state: 'ok' }), cli: a => a[0] === 'status' ? { exitCode, stderr: '' } : undefined })
    await start($)
    await tick()
    expect(h.band()?.state).toBe(state)
    await advance(h, 3_600_000)
    expect(statusRuns(h)).toBe(1)
  })
}

test('a failing re-probe keeps the band, no log or toast spam; the backoff follows the schedule and stops at the cap', async ($, on) => {
  const h = host(on, { mockClock: true, installer: () => ({ state: 'ok' }), cli: status(() => false) })
  await start($)
  await tick()
  const logs0 = h.logs.length, toasts0 = h.toasts.length
  let at = 1
  for (const ms of REPROBE_MS) { await advance(h, ms - 1); expect(statusRuns(h)).toBe(at); await advance(h, 1); expect(statusRuns(h)).toBe(++at) }
  await advance(h, REPROBE_EVERY_MS)
  expect(statusRuns(h)).toBe(++at)
  for (let i = 0; i < MAX_REPROBES + 5; i++) await advance(h, REPROBE_EVERY_MS)
  expect(statusRuns(h)).toBe(1 + MAX_REPROBES)  // the first status + the capped re-probes, never more
  expect(h.band()?.state).toBe('server_error')
  expect(h.logs.length).toBe(logs0)
  expect(h.toasts.length).toBe(toasts0)
})

test('a successful search clears the server_error band without an extra request, and the re-probe chain stops', async ($, on) => {
  const h = host(on, { mockClock: true, installer: () => ({ state: 'ok' }), cli: status(() => false) })
  await start($)
  await tick()
  expect(h.band()?.state).toBe('server_error')
  await submit($)
  expect(h.searches().length).toBe(1)
  expect(h.band()?.state ?? null).toBe(null)
  expect(statusRuns(h)).toBe(1)
  expect(h.logs.filter((l: string) => l === RECOVERED_LINE).length).toBe(1)
  await advance(h, 3_600_000)
  expect(statusRuns(h)).toBe(1)
})

test('a failed search leaves the server_error band alone', async ($, on) => {
  const h = host(on, { mockClock: true, installer: () => ({ state: 'ok' }), cli: status(() => false), search: () => ({ exitCode: 1, stderr: 'Server error (502)' }) })
  await start($)
  await tick()
  await submit($)
  expect(h.band()?.state).toBe('server_error')
})

test('session end stops the re-probe loop', async ($, on) => {
  const h = host(on, { mockClock: true, installer: () => ({ state: 'ok' }), cli: status(() => false) })
  await start($)
  await tick()
  await $.session.end({ reason: 'other', sessionId: SID, resume: {} } as any)
  await advance(h, 3_600_000)
  expect(statusRuns(h)).toBe(1)
})
