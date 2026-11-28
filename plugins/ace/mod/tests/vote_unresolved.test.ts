// 8.4.3: unresolved votes, gated by the server capability `feedback_unresolved` (exactly true in the /patterns/search answer; stored per
// org/project, 7 days; a real answer without it = off). A vote the client detects (phrase or Haiku >= 0.8) that cannot be tied to the
// evidenced ids of a fresh previous task (empty_ids, prev_stale) goes out as
//   trace.feedback = { kind, unresolved: true, target_retrieval_id?, detect_label: 'reject' (downvotes only), detect_source, model_conf? }
// with NO applied_log_ids and NO retrieval_id in the feedback. too_long and switch_off stay off. Off: byte-identical to 8.4.2 (golden).
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import GOLDEN from './fixtures/vote_golden_842.ts'
import { CWD, HOME, PRJ, ROOT, SDIR, done, host, mainTask, st8a, submit } from './helpers.ts'
import { NEUTRAL, SCENARIOS, T0S, ans, snapshot } from './vote_scenarios.ts'
import { flushRejections } from '../handlers/prompt.ts'
import { serverUnresolved, storedUnresolved, sha256Hex, unresolvedFileFor } from '../lib/cohort.ts'
import { PROOT } from './helpers.ts'
import { buildTrace } from '../lib/trace.ts'

const RID = JSON.parse(S8).retrieval_id as string
const CAP_FILE = `${ROOT}/${unresolvedFileFor('org_t', PRJ)}`
// every search answer carries the capability (a real answer without it switches it off)
const resp = (extra: Record<string, unknown> = {}) => () => { const o = JSON.parse(S8); Object.assign(o, { feedback_unresolved: true }, extra); return { stdout: JSON.stringify(o) } }
const base = (o: any = {}) => ({ defaultArm: true, mockClock: true, search: o.search ?? resp(o.resp), env: { ACE_FEEDBACK_DOWNVOTE: '1', ...(o.env ?? {}) },
  files: { ...(o.files ?? {}) }, ...(o.model ? { model: o.model } : {}) })
const settle = async (h: any) => { await h.clock.advance(1); await flushRejections(); for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 1)) }
const checks = (h: any, text: string) => h.rows().filter((x: any) => x.event === 'rejection_check' && x.chars === [...text].length)
const CAP_ON = { [CAP_FILE]: JSON.stringify({ on: true, at: T0S, org: 'org_t', project: PRJ }) }
const LMA = `${SDIR}/last-main-applied.json`, PD = `${SDIR}/pending-downvote.json`, PU = `${SDIR}/pending-upvote.json`
// a previous task WITHOUT evidenced ids ('done' names no pattern), the reply, the next main task: its trace
async function flow($: any, h: any, reply: string, prev = 'done') {
  await mainTask($, h); await done($, prev); await settle(h)
  await submit($, reply); await settle(h)
  const pending = { down: h.files.get(PD), up: h.files.get(PU) }
  await mainTask($, h); await done($, 'did something else'); await settle(h)
  return { pending, trace: h.trace(h.learns()[h.learns().length - 1]!) }
}
const DOWN = (extra: any = {}) => ({ kind: 'downvote', unresolved: true, target_retrieval_id: RID, detect_label: 'reject', detect_source: 'phrase', ...extra })

// ---------- the capability ----------
test('serverUnresolved: only exactly true; absent -> undefined; storedUnresolved: {on: true, at, org, project} < 7 days for this org/project', () => {
  expect(serverUnresolved({ feedback_unresolved: true })).toBe(true)
  for (const v of [false, 'true', 1, null, {}, [true]]) expect(serverUnresolved({ feedback_unresolved: v })).toBe(false)
  expect([serverUnresolved({}), serverUnresolved(null)]).toEqual([undefined, undefined])
  const f = (o: any) => JSON.stringify({ on: true, at: T0S, org: 'o', project: 'p', ...o }), now = T0S * 1000
  expect(storedUnresolved(f({}), now, 'o', 'p')).toBe(true)
  for (const t of [f({ on: 'true' }), f({ on: false }), f({ at: T0S - 8 * 86400 }), f({ at: T0S + 3600 }), f({ project: 'x' }), f({ org: 'x' }), 'junk', undefined])
    expect(storedUnresolved(t, now, 'o', 'p')).toBe(false)
})
const ENGINE = { [`${PROOT}/engine/search.js`]: '' }
test('capture (engine answer): stores {on, at, org, project} in this project\'s file; an engine answer without the key stores off', async ($, on) => {
  let v: unknown = true
  const h = host(on, { ...base({ files: ENGINE }), engine: () => { const o = JSON.parse(S8); if (v !== undefined) o.feedback_unresolved = v; return { stdout: JSON.stringify(o) } } })
  await submit($)
  expect(JSON.parse(h.files.get(CAP_FILE)!)).toEqual({ on: true, at: Math.floor(h.now() / 1000), org: 'org_t', project: PRJ })
  v = undefined; await submit($, 'second prompt please')
  expect(JSON.parse(h.files.get(CAP_FILE)!).on).toBe(false)
  v = 'true'; await submit($, 'third prompt please')
  expect(JSON.parse(h.files.get(CAP_FILE)!).on).toBe(false)
})

test('ace-cli fallback answer WITHOUT the key keeps the stored capability; WITH it, the value counts (exactly true)', async ($, on) => {
  let v: unknown
  const h = host(on, base({ files: CAP_ON, search: () => { const o = JSON.parse(S8); if (v !== undefined) o.feedback_unresolved = v; return { stdout: JSON.stringify(o) } } }))
  await submit($)
  expect(JSON.parse(h.files.get(CAP_FILE)!).on).toBe(true)
  v = 'true'; await submit($, 'second prompt please')
  expect(JSON.parse(h.files.get(CAP_FILE)!).on).toBe(false)
})
test('another project\'s file is never written by this project\'s answers; a legacy global file is ignored', async ($, on) => {
  const other = `${ROOT}/${unresolvedFileFor('org_t', 'prj_other')}`, legacy = `${ROOT}/feedback-unresolved.json`
  const otherText = JSON.stringify({ on: true, at: T0S, org: 'org_t', project: 'prj_other' })
  const h = host(on, { ...base({ files: { ...ENGINE, [other]: otherText, [legacy]: JSON.stringify({ on: true, at: T0S, org: 'org_t', project: PRJ }) } }), engine: () => ({ stdout: S8 }) })
  await mainTask($, h); await done($, 'done'); await settle(h)
  expect([h.files.get(other), JSON.parse(h.files.get(CAP_FILE)!).on]).toEqual([otherText, false])
  await submit($, 'das ist falsch'); await settle(h)
  expect(checks(h, 'das ist falsch').shift().failed).toBe('empty_ids')   // the legacy file did not switch it on
})

// ---------- empty_ids ----------
test('empty_ids + phrase reject -> unresolved downvote {kind, unresolved, target_retrieval_id, detect_label, detect_source}; no ids, no retrieval_id in feedback', async ($, on) => {
  const h = host(on, base())
  const { pending, trace } = await flow($, h, 'das ist falsch')
  expect(JSON.parse(pending.down)).toEqual(expect.objectContaining({ applied_log_ids: [], unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' }))
  expect(trace.feedback).toEqual(DOWN())
  expect(Object.keys(trace.feedback)).toEqual(['kind', 'unresolved', 'target_retrieval_id', 'detect_label', 'detect_source'])
  expect(Array.isArray(trace.applied_log_ids)).toBe(true)                // the trace's own applied_log_ids are untouched
  const r = checks(h, 'das ist falsch').shift()
  expect([r.failed, r.unresolved, r.prev_ids]).toEqual([null, true, 0])
})
test('empty_ids + Haiku reject >= 0.8 -> unresolved downvote with detect_source model and model_conf', async ($, on) => {
  const h = host(on, base({ model: ans('reject', 0.93) }))
  expect((await flow($, h, NEUTRAL)).trace.feedback).toEqual(DOWN({ detect_source: 'model', model_conf: 0.93 }))
})
test('empty_ids + Haiku below 0.8 -> nothing', async ($, on) => {
  const h = host(on, base({ model: ans('reject', 0.79) }))
  expect((await flow($, h, NEUTRAL)).trace.feedback).toBe(undefined)
})
test('empty_ids + upvote phrase -> unresolved upvote {kind upvote, unresolved, target, detect_source phrase}, no detect_label', async ($, on) => {
  const h = host(on, base())
  expect((await flow($, h, 'perfekt')).trace.feedback).toEqual({ kind: 'upvote', unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' })
})
test('headless: the phrase path still sends an unresolved downvote, the model is never asked', async ($, on) => {
  const h = host(on, base({ model: ans('reject', 1) }))
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  const { trace } = await flow($, h, 'das ist falsch')
  expect([trace.feedback, h.modelCalls.length]).toEqual([DOWN(), 0])
})

// ---------- prev_stale ----------
test('prev_stale (record >= 6 h old) -> unresolved with the OLD search as target', async ($, on) => {
  const old = JSON.stringify({ task_session_id: 'old-task', applied_log_ids: [1003], at: T0S - 7 * 3600, answer_tail: 'x', retrieval_id: RID })
  const h = host(on, base({ files: { ...CAP_ON, [LMA]: old } }))
  await submit($, 'das ist falsch'); await settle(h)
  expect(checks(h, 'das ist falsch').shift()).toEqual(expect.objectContaining({ failed: null, unresolved: true, prev_ids: 0 }))
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.trace(h.learns()[0]!).feedback).toEqual(DOWN())
})
test('prev_stale (no record at all) -> unresolved WITHOUT target_retrieval_id', async ($, on) => {
  const h = host(on, base({ files: CAP_ON }))   // the capability from an earlier answer (this prompt is checked before its own search)
  await submit($, 'das ist falsch'); await settle(h)
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.trace(h.learns()[0]!).feedback).toEqual({ kind: 'downvote', unresolved: true, detect_label: 'reject', detect_source: 'phrase' })
})
test('a record whose retrieval_id is not a UUID -> unresolved WITHOUT target_retrieval_id', async ($, on) => {
  const h = host(on, base({ resp: { retrieval_id: 'not-a-uuid' } }))
  expect((await flow($, h, 'das ist falsch')).trace.feedback).toEqual({ kind: 'downvote', unresolved: true, detect_label: 'reject', detect_source: 'phrase' })
})

// review 1 (save Haiku): with the capability, the model only runs when there is a previous record; the phrase path stays
test('no record + capability: no model call; failed no_prev_record; nothing queued', async ($, on) => {
  const h = host(on, base({ files: CAP_ON, model: ans('reject', 1) }))
  await submit($, NEUTRAL); await settle(h)
  expect([h.modelCalls.length, checks(h, NEUTRAL).shift().failed, checks(h, NEUTRAL).shift().unresolved, h.files.has(PD)]).toEqual([0, 'no_prev_record', true, false])
})
test('no record + capability: an upvote phrase still queues an unresolved upvote without target', async ($, on) => {
  const h = host(on, base({ files: CAP_ON }))
  await submit($, 'Perfekt, danke!'); await settle(h)
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.trace(h.learns()[0]!).feedback).toEqual({ kind: 'upvote', unresolved: true, detect_source: 'phrase' })
})
test('a STALE record (>= 6 h) still lets the model run (a record exists)', async ($, on) => {
  const old = JSON.stringify({ task_session_id: 'old-task', applied_log_ids: [1003], at: T0S - 7 * 3600, answer_tail: 'x', retrieval_id: RID })
  const h = host(on, base({ files: { ...CAP_ON, [LMA]: old }, model: ans('reject', 0.95) }))
  await submit($, NEUTRAL); await settle(h)
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.trace(h.learns()[0]!).feedback).toEqual(DOWN({ detect_source: 'model', model_conf: 0.95 }))
})

// review S1: a record WITHOUT a valid retrieval_id counts like no record for the model path (model votes always carry a target)
for (const [name, rec, failed] of [
  ['a task-less answer record (retrieval_id null)', { task_session_id: null, applied_log_ids: [], at: T0S, answer_tail: 'x', retrieval_id: null }, 'no_target_record'],
  ['a Python / 8.4.2 record without ids (no retrieval_id)', { task_session_id: null, applied_log_ids: [], at: T0S }, 'no_target_record'],
  ['a record with a non-UUID retrieval_id', { task_session_id: 't', applied_log_ids: [], at: T0S, retrieval_id: 'nope' }, 'no_target_record'],
] as [string, any, string][])
  test('model path skipped for ' + name + ' (no model call, failed ' + failed + '); a phrase still votes without target', async ($, on) => {
    const h = host(on, base({ files: { ...CAP_ON, [LMA]: JSON.stringify(rec) }, model: ans('reject', 1) }))
    await submit($, NEUTRAL); await settle(h)
    const r = checks(h, NEUTRAL).shift()
    expect([h.modelCalls.length, r.failed, h.files.has(PD)]).toEqual([0, failed, false])
  })
test('a fresh record WITH evidenced ids but no UUID (Python format) stays a RESOLVED vote (8.4.2 path, capability irrelevant)', async ($, on) => {
  const h = host(on, base({ files: { ...CAP_ON, [LMA]: JSON.stringify({ task_session_id: null, applied_log_ids: [1003], at: T0S }) } }))
  await submit($, 'das ist falsch'); await settle(h)
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.trace(h.learns()[0]!).feedback).toEqual({ kind: 'downvote', applied_log_ids: [1003], detect_source: 'phrase' })
})
// review S2: at most one vote per previous answer also without a task id (no record / a task-less record)
test('no record: a phrase downvote, then an upvote phrase -> the upvote is locked (task_voted); the next trace carries the downvote only', async ($, on) => {
  const h = host(on, base({ files: CAP_ON }))
  await submit($, 'das ist falsch'); await settle(h)
  await submit($, 'Perfekt, danke!'); await settle(h)
  expect(h.rows().filter((x: any) => x.event === 'upvote_check').pop().failed).toBe('task_voted')
  expect(h.files.has(PU)).toBe(false)
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.trace(h.learns()[0]!).feedback).toEqual({ kind: 'downvote', unresolved: true, detect_label: 'reject', detect_source: 'phrase' })
})
test('a task-less record: one vote; a NEW record (new at) opens the next one', async ($, on) => {
  const rec = (at: number) => JSON.stringify({ task_session_id: null, applied_log_ids: [], at, answer_tail: 'x', retrieval_id: null })
  const h = host(on, base({ files: { ...CAP_ON, [LMA]: rec(T0S) } }))
  await submit($, 'das ist falsch'); await settle(h)
  await submit($, 'das ist immer noch falsch'); await settle(h)
  expect(checks(h, 'das ist immer noch falsch').shift().failed).toBe('task_downvoted')
  h.put(LMA, rec(T0S + 1))
  h.files.delete(PD)
  await submit($, 'wirklich falsch hier'); await settle(h)
  expect([checks(h, 'wirklich falsch hier').shift().failed, h.files.has(PD)]).toEqual([null, true])
})

// review (round 6): no_prev_record / no_target_record only when the model would otherwise have run; else the 8.4.2 value no_phrase
for (const [name, env, headless] of [['headless', {}, true], ['ACE_REJECTION_MODEL=0', { ACE_REJECTION_MODEL: '0' }, false]] as [string, any, boolean][])
  test('no record + capability, ' + name + ': failed stays no_phrase (the model would not have run anyway)', async ($, on) => {
    const h = host(on, base({ files: CAP_ON, env }))
    if (headless) await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
    await submit($, NEUTRAL); await settle(h)
    expect(checks(h, NEUTRAL).shift().failed).toBe('no_phrase')
  })

// prod finding: an untargeted unresolved vote books nothing on the server; the log shows whether a target went with it and why not
const ROW_KEYS = (r: any) => ({ target: r.target, no_target_reason: r.no_target_reason })
const detected = (h: any) => h.rows().filter((x: any) => x.event === 'rejection_detected').pop()
const ups = (h: any) => h.rows().filter((x: any) => x.event === 'upvote_check').pop()
test('target log: phrase downvote WITH a target -> target true, no reason (rejection_check and rejection_detected)', async ($, on) => {
  const h = host(on, base())
  await flow($, h, 'das ist falsch')
  expect([ROW_KEYS(checks(h, 'das ist falsch').shift()), ROW_KEYS(detected(h))]).toEqual([{ target: true, no_target_reason: undefined }, { target: true, no_target_reason: undefined }])
  expect('no_target_reason' in checks(h, 'das ist falsch').shift()).toBe(false)
})
test('target log: Haiku downvote with a target -> rejection_detected target true', async ($, on) => {
  const old = JSON.stringify({ task_session_id: 'old-task', applied_log_ids: [1003], at: T0S - 7 * 3600, answer_tail: 'x', retrieval_id: RID })
  const h = host(on, base({ files: { ...CAP_ON, [LMA]: old }, model: ans('reject', 0.95) }))
  await submit($, NEUTRAL); await settle(h)
  expect([ROW_KEYS(checks(h, NEUTRAL).pop()), ROW_KEYS(detected(h)), detected(h).detect_source]).toEqual([{ target: true, no_target_reason: undefined }, { target: true, no_target_reason: undefined }, 'model'])
})
test('target log: no record -> target false, no_target_reason no_prev_record (downvote and upvote rows)', async ($, on) => {
  const h = host(on, base({ files: CAP_ON }))
  await submit($, 'das ist falsch'); await settle(h)
  expect([ROW_KEYS(checks(h, 'das ist falsch').shift()), ROW_KEYS(detected(h))]).toEqual([{ target: false, no_target_reason: 'no_prev_record' }, { target: false, no_target_reason: 'no_prev_record' }])
})
test('target log: no record, upvote phrase -> upvote_check target false, no_prev_record', async ($, on) => {
  const h = host(on, base({ files: CAP_ON }))
  await submit($, 'Perfekt, danke!'); await settle(h)
  expect(ROW_KEYS(ups(h))).toEqual({ target: false, no_target_reason: 'no_prev_record' })
})
test('target log: a task-less record (retrieval_id null) -> target false, no_prev_retrieval; upvote with a target -> target true', async ($, on) => {
  const h = host(on, base({ files: { ...CAP_ON, [LMA]: JSON.stringify({ task_session_id: null, applied_log_ids: [], at: T0S, answer_tail: 'x', retrieval_id: null }) } }))
  await submit($, 'das ist falsch'); await settle(h)
  expect([ROW_KEYS(checks(h, 'das ist falsch').shift()), ROW_KEYS(detected(h))]).toEqual([{ target: false, no_target_reason: 'no_prev_retrieval' }, { target: false, no_target_reason: 'no_prev_retrieval' }])
})
test('target log: upvote phrase WITH a target -> upvote_check target true', async ($, on) => {
  const h = host(on, base())
  await flow($, h, 'perfekt')
  expect(ROW_KEYS(h.rows().filter((x: any) => x.event === 'upvote_check' && x.failed === null).pop())).toEqual({ target: true, no_target_reason: undefined })
})
test('target log: a non-UUID retrieval_id -> no_prev_retrieval', async ($, on) => {
  const h = host(on, base({ files: { ...CAP_ON, [LMA]: JSON.stringify({ task_session_id: 't', applied_log_ids: [], at: T0S, retrieval_id: 'nope' }) } }))
  await submit($, 'das ist falsch'); await settle(h)
  expect(ROW_KEYS(checks(h, 'das ist falsch').shift())).toEqual({ target: false, no_target_reason: 'no_prev_retrieval' })
})
test('target log: capability off -> no target fields on any row (8.4.2)', async ($, on) => {
  const h = host(on, base({ search: () => ({ stdout: S8 }) }))
  await flow($, h, 'das ist falsch', 'applied ' + st8a().a)
  const rows = h.rows().filter((x: any) => /rejection|upvote/.test(x.event))
  expect(rows.some((r: any) => 'target' in r || 'no_target_reason' in r)).toBe(false)
})

// ---------- stays off ----------
test('too_long -> no unresolved vote (nothing was classified)', async ($, on) => {
  const h = host(on, base())
  const reply = 'das ist falsch ' + 'x '.repeat(200)
  const { trace } = await flow($, h, reply)
  expect([trace.feedback, checks(h, reply).shift().failed]).toEqual([undefined, 'too_long'])
})
test('switch_off (downvote off) -> no unresolved downvote', async ($, on) => {
  const h = host(on, base({ env: { ACE_FEEDBACK_DOWNVOTE: '0' } }))
  const { trace } = await flow($, h, 'das ist falsch')
  expect([trace.feedback, checks(h, 'das ist falsch').shift().failed]).toEqual([undefined, 'switch_off'])
})
test('one vote per task: a second rejection of the same task -> task_downvoted', async ($, on) => {
  const h = host(on, base())
  await mainTask($, h); await done($, 'done'); await settle(h)
  await submit($, 'das ist falsch'); await settle(h)
  await submit($, 'das ist immer noch falsch'); await settle(h)
  expect(checks(h, 'das ist immer noch falsch').shift()).toEqual(expect.objectContaining({ failed: 'task_downvoted', unresolved: true }))
})
test('capability off (never advertised) -> 8.4.2: empty_ids drops the vote', async ($, on) => {
  const h = host(on, base({ search: () => ({ stdout: S8 }) }))
  const { pending, trace } = await flow($, h, 'das ist falsch')
  expect([pending.down, trace.feedback, checks(h, 'das ist falsch').shift().failed]).toEqual([undefined, undefined, 'empty_ids'])
  expect('unresolved' in checks(h, 'das ist falsch').shift()).toBe(false)
})

// ---------- followup_judging ----------
test('followup_judging live -> no client vote at all, also no unresolved one', async ($, on) => {
  const h = host(on, base({ resp: { followup_judging: true } }))
  const { pending, trace } = await flow($, h, 'das ist falsch')
  expect([pending.down, trace.feedback]).toEqual([undefined, undefined])
})
test('followup_judging shadow -> the unresolved vote AND the followup', async ($, on) => {
  let n = 0   // own retrieval ids per search: the follow-up of a task never rides on that task's own trace
  const h = host(on, base({ search: () => { const o = JSON.parse(S8); Object.assign(o, { feedback_unresolved: true, followup_judging: 'shadow', retrieval_id: `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}` }); return { stdout: JSON.stringify(o) } } }))
  const { trace } = await flow($, h, 'das ist falsch')
  expect(trace.feedback).toEqual(DOWN({ target_retrieval_id: trace.followup?.target_retrieval_id }))
  expect([trace.followup?.text, trace.followup?.target_retrieval_id]).toEqual(['das ist falsch', '00000000-0000-4000-8000-000000000001'])
})

// ---------- take time ----------
const pend = (o: any) => JSON.stringify({ at: T0S, task_session_id: null, applied_log_ids: [], ...o })
async function nextTrace($: any, h: any) { await mainTask($, h); await done($, 'x'); await settle(h); return h.trace(h.learns()[0]!) }
for (const [name, file, cap, fb] of [
  ['ids [] without unresolved (8.4.2 shape)', {}, true, undefined],
  ['unresolved, a non-UUID target -> sent without it', { unresolved: true, target_retrieval_id: 'nope', detect_source: 'phrase' }, true, { kind: 'downvote', unresolved: true, detect_label: 'reject', detect_source: 'phrase' }],
  ['unresolved "true" string', { unresolved: 'true', target_retrieval_id: RID }, true, undefined],
  ['unresolved, the capability withdrawn since', { unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' }, false, undefined],
  ['unresolved, older than 6 h', { unresolved: true, target_retrieval_id: RID, at: T0S - 6 * 3600 }, true, undefined],
  ['unresolved, valid', { unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' }, true, DOWN()],
] as [string, any, boolean, any][])
  test('takeVote: ' + name, async ($, on) => {
    const h = host(on, base({ files: { [PD]: pend(file) }, ...(cap ? {} : { search: () => ({ stdout: S8 }) }) }))
    expect((await nextTrace($, h)).feedback).toEqual(fb)
    expect(h.files.has(PD)).toBe(false)
  })
test('takeVote: a vote on the carrying task itself (self-eval window: same task_session_id) stays pending for the next main learn', async ($, on) => {
  let release = () => {}
  const gate = new Promise<void>(r => { release = r })
  const h = host(on, { ...base(), selfEval: true, model: (req: any) => req.system ? { isAnswered: false, reason: 'api-error' } : gate.then(() => ({ isAnswered: true, text: '{"used": []}' })) })
  await mainTask($, h); await done($, 'applied ' + st8a().a)
  expect(JSON.parse(h.files.get(LMA)!)).toEqual(expect.objectContaining({ applied_log_ids: [], retrieval_id: RID }))   // the Stop placeholder
  await submit($, 'das ist falsch'); await settle(h)
  expect(JSON.parse(h.files.get(PD)!).unresolved).toBe(true)
  release(); await settle(h); await settle(h)
  expect([h.trace(h.learns()[0]!).feedback, h.files.has(PD)]).toEqual([undefined, true])
})
test('precedence: a pending RESOLVED downvote wins over a pending unresolved upvote (the upvote waits)', async ($, on) => {
  const h = host(on, base({ files: { [PD]: pend({ applied_log_ids: [7] }), [PU]: pend({ unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' }) } }))
  expect((await nextTrace($, h)).feedback).toEqual({ kind: 'downvote', applied_log_ids: [7] })
  expect(h.files.has(PU)).toBe(true)
})
test('precedence: a pending unresolved downvote blocks the upvote too (one feedback per trace)', async ($, on) => {
  const h = host(on, base({ files: { [PD]: pend({ unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' }), [PU]: pend({ applied_log_ids: [8] }) } }))
  expect((await nextTrace($, h)).feedback).toEqual(DOWN())
  expect(h.files.has(PU)).toBe(true)
})
test('held login (8.4.1): a parked learn does not take an unresolved vote; nothing parked carries feedback', async ($, on) => {
  const CFG = `${HOME}/.config/ace/config.json`
  const h = host(on, base({ files: { [CFG]: '{}', [PD]: pend({ unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' }) } }))
  h.put(`${ROOT}/auth-rejected`, sha256Hex('{}'))
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.files.has(PD)).toBe(true)
  expect(h.enqueued.length > 0 && h.enqueued.every((q: any) => !('feedback' in JSON.parse(q.body)))).toBe(true)
})
test('ACE_TRACE_SINK: the sinked trace carries the unresolved feedback unchanged', async ($, on) => {
  const h = host(on, base({ env: { ACE_TRACE_SINK: 'file:/home/u/sink' } }))
  await mainTask($, h); await done($, 'done'); await settle(h)
  await submit($, 'das ist falsch'); await settle(h)
  await mainTask($, h); await done($, 'x'); await settle(h)
  const fb = [...h.files.keys()].filter(k => k.startsWith('/home/u/sink/')).map(k => JSON.parse(h.files.get(k)!).feedback).filter(Boolean)
  expect(fb).toEqual([DOWN()])
})
test('buildTrace: unresolved feedback shape; resolved feedback byte-identical (no unresolved keys)', () => {
  const b = (o: any) => buildTrace({ userPrompt: 'p', tools: [], answer: '', playbookUsed: [], agentType: 'main', appliedLogIds: [5], nowIso: 'x', effort: 'normal', ...o }).trace
  expect(b({ downvote: [], downvoteDetect: { unresolved: true, target_retrieval_id: RID, detect_source: 'model', model_conf: 0.912 } }).feedback)
    .toEqual({ kind: 'downvote', unresolved: true, target_retrieval_id: RID, detect_label: 'reject', detect_source: 'model', model_conf: 0.91 })
  expect(b({ downvote: [], downvoteDetect: { unresolved: true, target_retrieval_id: 'x' } }).feedback).toEqual({ kind: 'downvote', unresolved: true, detect_label: 'reject' })
  expect(b({ downvote: [3], downvoteDetect: { unresolved: true, target_retrieval_id: RID, detect_source: 'phrase' } }).feedback).toEqual({ kind: 'downvote', applied_log_ids: [3], detect_source: 'phrase' })
  expect(b({ upvote: [], upvoteDetect: { unresolved: true, target_retrieval_id: RID, detect_source: 'model', model_conf: 0.9 } }).feedback).toEqual({ kind: 'upvote', unresolved: true, target_retrieval_id: RID })
  expect(b({ downvote: [], downvoteDetect: { detect_source: 'phrase' } }).feedback).toBe(undefined)
  expect(b({ downvote: [], downvoteDetect: { unresolved: true } }).applied_log_ids).toEqual([5])
})

// ---------- the golden scenarios with the capability ON: resolved votes unchanged ----------
// (the first prompt of each scenario has no record: with the capability it is a prev_stale check and may ask the model, so only the
// sent traces, feedback and the vote files are compared, for the scenarios whose prompts carry no rejection the model could find)
const strip = (snap: any) => ({ afterReply: snap.afterReply, end: snap.end, feedback: snap.feedback, enqueued: snap.enqueued, traces: snap.full.traces, sink: snap.full.sink })
for (const name of ['phrase_down', 'phrase_up', 'switch_off', 'too_long', 'revote_lock', 'up_bare_ack', 'up_reject_phrase', 'up_blocked', 'sink_phrase_down', 'model_err', 'model_off'])
  test('golden with feedback_unresolved true: ' + name + ' -> sent traces and vote files identical to 8.4.2', async ($, on) => {
    const { snap } = await snapshot($, on, SCENARIOS[name]!, {}, {}, (o: any) => { o.feedback_unresolved = true })
    expect(strip(snap)).toEqual(strip((GOLDEN as any)[name]))
  })
