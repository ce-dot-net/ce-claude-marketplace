// ACE mod suite, 8.4.0: a rejected token (dead/ entries with last_error 'auth' < 30 min) is shown ONCE per conversation, from the
// queue state and not from the search. The check itself is the Python one (`ace_trace_queue.py --auth-held`, tested in
// tests/test_auth_held_notice.py); here: the mod asks it, shows its line once, writes the marker, never depends on the search.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import { HUMAN, PDIR, PROOT, ROOT, SDIR, SID, host, submit } from './helpers.ts'
import { sha256Hex } from '../lib/cohort.ts'

const LINE = (n: number) => `ACE: nicht angemeldet, Traces werden NICHT gesendet (${n} Traces wartend/abgelegt). Bitte \`ace-cli login\` ausführen.`
const asked = (h: any) => h.runs.filter((r: any) => r.argv.some((a: string) => a.endsWith('/ace_trace_queue.py') && r.argv.includes('--auth-held')))
const shown = (h: any) => h.logs.filter((l: string) => l.startsWith('ACE: nicht angemeldet'))

test('auth-held: the line is shown once per conversation, the marker is written, a 2nd prompt asks nothing more', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), authHeld: () => LINE(231) + '\n' })
  await submit($)
  expect(shown(h)).toEqual([LINE(231)])
  expect(h.files.has(`${SDIR}/auth_held_notified`)).toBe(true)
  await submit($, HUMAN + ' again')
  expect(shown(h).length).toBe(1)
  expect(asked(h).length).toBe(1)
  expect(asked(h)[0].argv).toContain(ROOT)  // --data-root: the mod's own data root
  expect(asked(h)[0].argv.some((a: string) => a.startsWith(PROOT))).toBe(true)
})

test('auth-held: a new conversation shows it again', async ($, on) => {
  let sid = SID
  const h = host(on, { search: () => ({ stdout: S8 }), authHeld: () => LINE(3), sid: () => sid, files: { [`${PDIR}/sessions/sess-2/mod-classic`]: '1800000000000' } })
  await submit($)
  sid = 'sess-2'
  await submit($, HUMAN + ' two')
  expect(shown(h).length).toBe(2)
})

test('auth-held: nothing from the queue -> no line, no marker, asked again next prompt', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  await submit($, HUMAN + ' again')
  expect(shown(h).length).toBe(0)
  expect(h.files.has(`${SDIR}/auth_held_notified`)).toBe(false)
  expect(asked(h).length).toBe(2)
})

test('auth-held: independent of the search (a failed search still shows it)', async ($, on) => {
  const h = host(on, { search: () => ({ exitCode: 1, stdout: '', stderr: 'boom' }), authHeld: () => LINE(5) })
  await submit($)
  expect(shown(h)).toEqual([LINE(5)])
})

test('auth-held: a python failure or foreign output never shows anything', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), authHeld: () => 'Traceback (most recent call last): boom' })
  await submit($)
  expect(shown(h).length).toBe(0)
  expect(h.files.has(`${SDIR}/auth_held_notified`)).toBe(false)
})

test('auth-held: machine prompts and disabled sessions get no notice', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), authHeld: () => LINE(2) })
  await submit($, '<task-notification>x</task-notification>', 'task-notification')
  expect(shown(h).length).toBe(0)
  expect(asked(h).length).toBe(0)
})

// ---------- the local-sink notice ----------
const SINK = 'ACE: Traces gehen in die lokale Senke (ACE_TRACE_SINK), es wird NICHTS gesendet.'
const sinkShown = (h: any) => h.logs.filter((l: string) => l === SINK)

test('sink: set -> once per conversation, marker written; 2nd prompt none; new conversation again', async ($, on) => {
  let sid = SID
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: 'file:/tmp/s' }, sid: () => sid, files: { [`${PDIR}/sessions/sess-2/mod-classic`]: '1800000000000' } })
  await submit($)
  await submit($, HUMAN + ' again')
  expect(sinkShown(h).length).toBe(1)
  expect(h.files.has(`${SDIR}/sink_notified`)).toBe(true)
  sid = 'sess-2'
  await submit($, HUMAN + ' two')
  expect(sinkShown(h).length).toBe(2)
})

for (const v of [undefined, '', '   ']) test(`sink: ${JSON.stringify(v)} -> never`, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: v === undefined ? {} : { ACE_TRACE_SINK: v } })
  await submit($)
  await submit($, HUMAN + ' again')
  expect(sinkShown(h).length).toBe(0)
  expect(h.files.has(`${SDIR}/sink_notified`)).toBe(false)
})

test('sink + auth-held together: one line each', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: 'file:/tmp/s' }, authHeld: () => LINE(1) })
  await submit($)
  expect(sinkShown(h).length).toBe(1)
  expect(shown(h)).toEqual([LINE(1)])
})

// 8.4.1 item 3: the held marker alone (no dead/ entry yet) shows the notice too, once per conversation; counts-only wording.
test('auth-held from the marker: shown once (no count), marker written; the queue line wins when there is one', async ($, on) => {
  const CFG = '/home/u/.config/ace/config.json'
  const HELD = { [CFG]: '{}', [`${ROOT}/auth-rejected`]: sha256Hex('{}') }
  const h = host(on, { files: HELD, search: () => ({ stdout: S8 }) })
  await submit($)
  await submit($, HUMAN + ' again')
  expect(shown(h)).toEqual(['ACE: nicht angemeldet, Traces werden NICHT gesendet. Bitte `ace-cli login` ausführen.'])
  expect(h.files.has(`${SDIR}/auth_held_notified`)).toBe(true)
})
// review fixes (8.4.1): a second hold in the same conversation shows the line again; a failing --auth-held spawn cannot suppress it
const MLINE = 'ACE: nicht angemeldet, Traces werden NICHT gesendet. Bitte `ace-cli login` ausführen.'
test('auth-held from the marker: a new hold (new marker mtime) in the same conversation shows the line again', async ($, on) => {
  const CFG = '/home/u/.config/ace/config.json'
  let n = 0
  const h = host(on, { files: { [CFG]: '{}', [`${ROOT}/auth-rejected`]: sha256Hex('{}') }, search: () => (n++, { exitCode: 1, stderr: 'Error: Not logged in' }) })
  await submit($)
  expect(shown(h)).toEqual([MLINE])
  h.advance(31 * 60_000)                     // the hold expires; the next search fails again: a new hold
  await submit($, HUMAN + ' later')
  expect(n).toBe(1)
  await submit($, HUMAN + ' once more')
  expect(shown(h)).toEqual([MLINE, MLINE])
})
test('auth-held from the marker: a throwing --auth-held spawn still shows the marker line', async ($, on) => {
  const CFG = '/home/u/.config/ace/config.json'
  const h = host(on, { files: { [CFG]: '{}', [`${ROOT}/auth-rejected`]: sha256Hex('{}') }, search: () => ({ stdout: S8 }), authHeld: () => { throw new Error('spawn failed') } })
  await submit($)
  expect(shown(h)).toEqual([MLINE])
})
