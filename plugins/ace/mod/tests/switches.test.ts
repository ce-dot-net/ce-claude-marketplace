// ACE mod suite, server switches: render_full_pct kill switch, user rejection -> downvote. Harness: ./helpers.ts.
import { expect, test } from 'claude-code/testing'
import S100 from './fixtures/search_100.ts'
import S8 from './fixtures/search_8.ts'
import SEDGE from './fixtures/search_edge.ts'
import G from './fixtures/golden.ts'
import USED_CASES from './fixtures/used_cases.ts'
import REJECTION_CASES from './fixtures/rejection_cases.ts'
import { pyLoads } from '../lib/pyjson.ts'
import { renderPatternsDict } from '../lib/render.ts'
import { traceVariant, renderCohort, serverFullPct, storedFullPct } from '../lib/cohort.ts'
import { hasSubstantialWork, toolRec } from '../lib/trace.ts'
import { rejectionMatch, evalStats, evalInjection, usedPatternIds, toolHaystack } from '../lib/evidence.ts'
import { PRIVATE_WRITE_SH } from '../lib/sh.ts'
import { statusLine, learnLine } from '../ui/status.ts'
import { CWD, EVAL_REQ, FULL_PCT, HOME, HUMAN, LOCAL_CLI, LOCKED, MALFORMED, MIN, PDIR, PLACEHOLDER, PRJ, PROOT, REAL, REL, ROOT, SDIR, SECOND, SID, UUID4, bodyOf, cliOf, cmd, done, dsSearches, execRow, host, mainTask, ranked, rejectFlow, settle, shownOf, spawn, st8a, submit, withPct } from './helpers.ts'
import type { Opts, Run, SearchAnswer } from './helpers.ts'

// ---------- server kill switch: search response render_full_pct (env > server file < 7 days > 50) ----------

test('render_full_pct: only a top-level integer 0-100 counts; the stored value expires after 7 days', async () => {
  for (const v of [0, 50, 100]) expect(serverFullPct({ render_full_pct: v })).toBe(v)
  for (const v of [-1, 101, '0', 12.5, true, null, [0]]) expect(serverFullPct({ render_full_pct: v })).toBe(undefined)
  expect(serverFullPct(pyLoads('{"render_full_pct": 50.0}'))).toBe(undefined)  // a float, as in Python
  expect(serverFullPct(null)).toBe(undefined)
  const now = 1_800_000_000_000
  expect(storedFullPct(JSON.stringify({ pct: 0, at: now / 1000 - 6 * 86400 }), now)).toBe(0)
  expect(storedFullPct(JSON.stringify({ pct: 0, at: now / 1000 - 8 * 86400 }), now)).toBe(undefined)
  for (const t of [undefined, 'x', '[]', '{"pct": 200, "at": 1800000000}', '{"pct": 0}']) expect(storedFullPct(t, now)).toBe(undefined)
  const full = Array.from({ length: 1000 }, (_, i) => `conv-${i}`).find(c => renderCohort(c, {}) === 'full')!
  expect(renderCohort(full, { ACE_RENDER_FULL_PCT: '0' })).toBe('budget')
})

test('render_full_pct 0 in a search response -> the next arm of a full-bucket conversation is budget', async ($, on) => {
  // sess-1 is bucket 66: full under a stored server share of 70
  let pct: unknown = 70
  const h = host(on, { defaultArm: true, search: () => ({ stdout: withPct(pct) }) })
  await submit($)
  expect(JSON.parse(h.files.get(FULL_PCT)!)).toEqual({ pct: 70, at: Math.floor(h.now() / 1000) })
  pct = 0
  await submit($)  // this search stores 0, the render after it is already budget
  const arms = h.rows().filter((x: any) => x.event === 'search').map((x: any) => x.render_cohort)
  expect(arms).toEqual(['full', 'budget'])
  expect(JSON.parse(h.files.get(FULL_PCT)!).pct).toBe(0)
  pct = undefined  // a missing field keeps the stored value
  await submit($)
  expect(JSON.parse(h.files.get(FULL_PCT)!).pct).toBe(0)
  pct = 'off'  // an invalid value is ignored
  await submit($)
  expect(JSON.parse(h.files.get(FULL_PCT)!).pct).toBe(0)
  expect(h.rows().filter((x: any) => x.event === 'search').map((x: any) => x.render_cohort)).toEqual(['full', 'budget', 'budget', 'budget'])
})

test('render_full_pct: env ACE_RENDER_FULL_PCT overrides the server value', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_FULL_PCT: '100' }, search: () => ({ stdout: withPct(0) }) })
  await submit($)
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('full')
  expect(traceVariant(undefined, SID, { ACE_RENDER_FULL_PCT: '0' })).toBe('budget')
})

test('render_full_pct: a stale (> 7 days) server file falls back to the default 50', async ($, on) => {
  const stale = JSON.stringify({ pct: 70, at: Math.floor(1_800_000_000_000 / 1000) - 8 * 86400 })
  const h = host(on, { defaultArm: true, files: { [FULL_PCT]: stale }, search: () => ({ stdout: S8 }) })
  await submit($)
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('budget')  // sess-1 = 66 >= 50
  expect(h.files.get(FULL_PCT)).toBe(stale)
})

// ---------- user rejection -> downvote on the next main trace (ace_feedback.py parity) ----------

test('rejection phrases: the shared fixture cases (parity with ace_feedback.rejection_match)', async () => {
  for (const c of REJECTION_CASES as any[]) expect([c.text, rejectionMatch(c.text)]).toEqual([c.text, c.match])
})

test('rejection + previous evidenced ids + gate on -> feedback downvote on the next main trace, once', async ($, on) => {
  const { a, log } = st8a()
  const h = host(on, { defaultArm: true, search: () => ({ stdout: S8 }), env: { ACE_FEEDBACK_DOWNVOTE: '1' } })
  const t2 = await rejectFlow($, h, 'applied ' + a, () => submit($, 'falsch'))
  expect(t2.feedback).toEqual({ kind: 'downvote', applied_log_ids: [log] })
  expect(h.trace(h.learns()[0]!).feedback).toBe(undefined)
  const row = h.rows().find((x: any) => x.event === 'rejection_detected')!
  expect([row.matched, row.downvote_sent, row.prev_task?.length]).toEqual(['falsch', true, 8])
  expect(JSON.stringify(row).includes(HUMAN)).toBe(false)
  await mainTask($, h)
  await done($, 'third')
  expect(h.trace(h.learns()[2]!).feedback).toBe(undefined)
})

test('rejection with a real (sub-second) clock: the stored seconds stamp is a float and must still read as fresh', async ($, on) => {
  const { a, log } = st8a()
  const h = host(on, { defaultArm: true, search: () => ({ stdout: S8 }), env: { ACE_FEEDBACK_DOWNVOTE: '1' } })
  h.advance(1234)  // clock no longer on a whole second: `now / 1000` is a float, which pyLoads reads as a PyFloat
  const t2 = await rejectFlow($, h, 'applied ' + a, () => submit($, 'das ist falsch'))
  expect(t2.feedback).toEqual({ kind: 'downvote', applied_log_ids: [log] })
})

test('rejection: gate off (default) -> nothing; the server gate in a search response turns it on', async ($, on) => {
  const { a } = st8a()
  let gate: boolean | undefined
  const h = host(on, { defaultArm: true, search: () => { const o = JSON.parse(S8); if (gate !== undefined) o.feedback_downvote = gate; return { stdout: JSON.stringify(o) } } })
  expect((await rejectFlow($, h, 'applied ' + a, () => submit($, "that's wrong"))).feedback).toBe(undefined)
  expect(h.rows().find((x: any) => x.event === 'rejection_detected')!.downvote_sent).toBe(false)
  gate = true
  await mainTask($, h)  // this search stores the gate
  await done($, 'applied ' + a)
  gate = undefined      // missing field keeps it
  await submit($, 'das ist falsch')
  await mainTask($, h)
  await done($, 'x')
  expect(h.trace(h.learns()[3]!).feedback?.kind).toBe('downvote')
})

test('rejection: no previous evidenced ids, a negated phrase, a machine prompt or a slash command -> nothing', async ($, on) => {
  const { a } = st8a()
  const h = host(on, { defaultArm: true, search: () => ({ stdout: S8 }), env: { ACE_FEEDBACK_DOWNVOTE: '1' } })
  expect((await rejectFlow($, h, 'done', () => submit($, 'falsch'))).feedback).toBe(undefined)
  expect(h.rows().filter((x: any) => x.event === 'rejection_detected').map((x: any) => x.downvote_sent)).toEqual([false])
  for (const reply of [() => submit($, 'das ist nicht falsch, mach weiter'), () => submit($, 'falsch', 'task-notification'),
    () => $.prompt.submit({ text: '/review falsch', wait: false, origin: { kind: 'composer' }, command: { name: 'review', args: 'falsch' } } as any)]) {
    const n = h.learns().length
    await mainTask($, h)
    await done($, 'applied ' + a)
    await reply()
    await mainTask($, h)
    await done($, 'x')
    expect(h.trace(h.learns()[n + 1]!).feedback).toBe(undefined)
  }
  expect(h.rows().filter((x: any) => x.event === 'rejection_detected').length).toBe(1)
})

test('rejection: a previous-task record older than 6 h is ignored', async ($, on) => {
  const { a } = st8a()
  const h = host(on, { defaultArm: true, search: () => ({ stdout: S8 }), env: { ACE_FEEDBACK_DOWNVOTE: '1' } })
  const t2 = await rejectFlow($, h, 'applied ' + a, async () => {
    const f = `${SDIR}/last-main-applied.json`, rec = JSON.parse(h.files.get(f)!)
    h.put(f, JSON.stringify({ ...rec, at: rec.at - 7 * 3600 }))
    await submit($, 'falsch')
  })
  expect(t2.feedback).toBe(undefined)
})

test('trace label without a search: the conversation arm (server request); a stored label wins', async () => {
  expect(traceVariant(undefined, 'conv-1', { ACE_RENDER_FULL_PCT: '100' })).toBe('full')
  expect(traceVariant('budget', 'conv-1', { ACE_RENDER_FULL_PCT: '100' })).toBe('budget')
  expect(traceVariant(undefined, undefined, {})).toBe(undefined)
  expect(traceVariant(undefined, 'conv-1', { ACE_AB_CONTROL_PCT: '100', ACE_RENDER_FULL_PCT: '0' })).toBe(undefined)
})

test('handoff: the mod rewrites mod-active right before the Python UPS runs (after its own search)', async ($, on) => {
  let hh: any
  const h = host(on, { search: () => { hh.advance(20_000); return { stdout: S8 } } })
  hh = h
  await submit($)
  expect(Number(h.files.get(`${SDIR}/mod-active`))).toBe(h.now())  // written after the 20 s search, not only before it
})

test('fix 5a: a Bash call with a non-zero exit code is a failed step (trace success false), an interpreted exit is not', async () => {
  const rec = (res: any, isError = false) => toolRec('Bash', { command: 'curl -s http://x' }, res, isError, undefined, 0, 1)
  expect(rec({ stdout: '', stderr: '', interrupted: false, exitCode: 6 }).failed).toBe(true)
  expect(rec({ stdout: '', stderr: '', interrupted: false, exitCode: 6 }).result).toBe('Exit code 6')
  expect(rec({ stdout: '', stderr: '', exit_code: 6 }).failed).toBe(true)
  expect(rec('Exit code 6').failed).toBe(true)
  expect(rec({ stdout: '', stderr: '', exitCode: 1, returnCodeInterpretation: 'No matches found' }).failed).toBe(false)
  expect(rec({ stdout: 'ok', stderr: '', exitCode: 0 }).failed).toBe(false)
  expect(rec({ stdout: 'ok', stderr: '' }).failed).toBe(false)
})

test('render keeps only retrieval_id and count at top level (cli 4.3.0 passes every server field through)', async () => {
  const resp: any = { retrieval_id: 'r1', count: 1, search_params: { top_k: 100 }, tokens_in_response: 4000, local_count: 1,
    session_id: 's', feedback_downvote: true, render_full_pct: 50,
    similar_patterns: [{ id: '11111111-2222-4333-8444-555555555555', content: 'x', domain: 'd' }] }
  expect(Object.keys(renderPatternsDict(resp).dict).sort()).toEqual(['count', 'retrieval_id', 'similar_patterns'])
})
