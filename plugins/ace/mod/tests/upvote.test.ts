// Upvote path, PHRASE ONLY (3d: the model path found no real approval in 4 rounds on 400 real prompts and the shared prompt cost
// downvote precision, so the classifier is back on its 8.3.0 3-way prompt). Gates, bare acks, one feedback per task, trace shape.
// $.model is stubbed (no network): every stub here answers as loudly as it can, to prove the model never decides an upvote.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import { NEG, POS } from './fixtures/upvote_cases.ts'
import { CWD, SDIR, done, host, mainTask, st8a, submit } from './helpers.ts'
import { flushRejections } from '../handlers/prompt.ts'
import { REJECTION_PHRASES, upvoteProbe } from '../lib/evidence.ts'
import { REJECTION_LABELS, REJECTION_SYSTEM, parseRejection } from '../lib/rejection.ts'
import { buildTrace } from '../lib/trace.ts'

const ans = (label: string, confidence: number) => ({ isAnswered: true, text: JSON.stringify({ label, confidence }) })
const APPROVE = () => ans('approve', 1)   // an 8.3.0 parser reads this as model_error: never an upvote
const NEUTRAL = 'could you look at the second file again please'
const ups = (h: any) => h.rows().filter((x: any) => x.event === 'upvote_check')
const upOf = (h: any, text: string) => ups(h).filter((x: any) => x.chars === [...text].length).pop()
const settle = async (h: any) => { await h.clock.advance(1); await flushRejections() }
async function flow($: any, h: any, reply: string) {
  const { a } = st8a()
  await mainTask($, h)
  await done($, 'applied ' + a)
  await submit($, reply)
  await settle(h)
  await mainTask($, h)
  await done($, 'did something else')
  return h.trace(h.learns()[1]!)
}
const base = (o: any = {}) => ({ defaultArm: true, mockClock: true, search: () => ({ stdout: S8 }), env: { ACE_FEEDBACK_DOWNVOTE: '1', ...(o.env ?? {}) }, ...(o.model ? { model: o.model } : {}) })
const calls = (h: any, text: string) => h.modelCalls.filter((c: any) => String(c.prompt).includes('<user_message>\n' + text + '\n'))
const UPVOTE = { kind: 'upvote', applied_log_ids: [st8a().log], detect_source: 'phrase' }

test('phrase: "Perfekt, danke!" -> upvote on the next main trace, exactly {kind, applied_log_ids, detect_source: phrase}; no model call; text-free row', async ($, on) => {
  const h = host(on, base({ model: () => ans('reject', 1) }))
  const t = await flow($, h, 'Perfekt, danke!')
  expect(t.feedback).toEqual(UPVOTE)
  expect(calls(h, 'Perfekt, danke!').length).toBe(0)
  const r = upOf(h, 'Perfekt, danke!')
  expect([r.failed, r.detect_source, r.matched, r.source]).toEqual([null, 'phrase', 'perfekt', 'mod'])
  expect(['model_conf' in r, 'model_label' in r, 'model_ms' in r]).toEqual([false, false, false])
  expect(JSON.stringify(ups(h)).includes('danke')).toBe(false)
  const d = h.rows().filter((x: any) => x.event === 'rejection_check' && x.chars === 15).pop()
  expect([d.failed, d.detect_source]).toEqual(['upvote_phrase', null])   // the phrase hit skips the downvote model too
})

test('no model upvote: a model "approve" answer to a phrase-less prompt never upvotes (8.3.0 parser: approve is no label)', async ($, on) => {
  const h = host(on, base({ model: APPROVE }))
  expect((await flow($, h, NEUTRAL)).feedback).toBe(undefined)
  expect(ups(h).length).toBe(0)                                                    // no upvote decision was even possible
  expect(h.rows().filter((x: any) => x.event === 'rejection_check' && x.chars === NEUTRAL.length).pop().failed).toBe('model_error')
})
test('no model call for the upvote: downvote off but upvote on (server feedback_upvote) -> the model is never asked', async ($, on) => {
  const resp = JSON.parse(S8); resp.feedback_upvote = true
  const h = host(on, { ...base({ model: APPROVE, env: { ACE_FEEDBACK_DOWNVOTE: '0' } }), search: () => ({ stdout: JSON.stringify(resp) }) })
  expect((await flow($, h, NEUTRAL)).feedback).toBe(undefined)
  expect(calls(h, NEUTRAL).length).toBe(0)
})
test('ACE_UPVOTE_MODEL / ACE_UPVOTE_MIN_CONF are gone: never read', async ($, on) => {
  const h = host(on, base({ model: APPROVE, env: { ACE_UPVOTE_MIN_CONF: '0', ACE_UPVOTE_MODEL: '1' } }))
  expect((await flow($, h, NEUTRAL)).feedback).toBe(undefined)
  expect(h.envAsked.filter((k: string) => k.startsWith('ACE_UPVOTE'))).toEqual([])
})

test('classifier is the 8.3.0 one: 3 labels, no approve in prompt or parser', () => {
  expect([...REJECTION_LABELS]).toEqual(['reject', 'new_request', 'neutral'])
  expect(parseRejection('{"label": "approve", "confidence": 0.9}')).toBe(null)
  const p = REJECTION_SYSTEM.toLowerCase()
  for (const w of ['approve', 'sarcasm', 'irony', 'accepting its offer']) expect([w, p.includes(w)]).toEqual([w, false])
  expect(REJECTION_SYSTEM.endsWith('Reply with strict JSON only, nothing else: {"label": "reject" | "new_request" | "neutral", "confidence": <number from 0 to 1>}')).toBe(true)
})

test('a rejection phrase beside an upvote phrase -> downvote only', async ($, on) => {
  const h = host(on, base({ model: APPROVE }))
  const t = await flow($, h, 'perfekt ist anders, das ist falsch')
  expect(t.feedback).toEqual({ kind: 'downvote', applied_log_ids: [st8a().log], detect_source: 'phrase' })
})
test('a model reject (0.95) stays a downvote, never an upvote', async ($, on) => {
  const h = host(on, base({ model: () => ans('reject', 0.95) }))
  expect((await flow($, h, NEUTRAL)).feedback?.kind).toBe('downvote')
})
test('approval plus a new task: phrase blocked -> no upvote (logged blocked, no_phrase)', async ($, on) => {
  const h = host(on, base({ model: APPROVE }))
  expect((await flow($, h, 'perfekt, jetzt noch die doku')).feedback).toBe(undefined)
  const r = upOf(h, 'perfekt, jetzt noch die doku')
  expect([r.matched, r.blocked, r.failed]).toEqual([null, 'perfekt', 'no_phrase'])
})
for (const bare of ['ok', 'ja', 'weiter', 'thanks', '👍'])
  test(`bare "${bare}" is never an upvote`, async ($, on) => {
    const h = host(on, base({ model: APPROVE }))
    expect((await flow($, h, bare)).feedback).toBe(undefined)
  })
test('emoji / symbol-only replies are bare acknowledgements', () => {
  for (const t of ['👍', '👍👍', '🙏', '✅', '...', '!!']) expect([t, upvoteProbe(t).bareAck]).toEqual([t, true])
  expect(upvoteProbe('   ').bareAck).toBe(false)
})

test('gates: no record (prev_stale), empty ids -> no upvote', async ($, on) => {
  const h = host(on, base())
  await submit($, 'perfekt')                        // no previous record
  await mainTask($, h, [])                          // skipped task -> []
  await done($, 'talk')
  await submit($, 'perfekt')
  await settle(h)
  expect(ups(h).map((x: any) => x.failed)).toEqual(['prev_stale', 'empty_ids'])
})
test('switch: ACE_FEEDBACK_UPVOTE=0 -> no upvote', async ($, on) => {
  const h = host(on, base({ env: { ACE_FEEDBACK_UPVOTE: '0' } }))
  expect((await flow($, h, 'perfekt')).feedback).toBe(undefined)
  expect(upOf(h, 'perfekt').failed).toBe('switch_off')
})
test('switch: without feedback_upvote the upvote follows the downvote switch (off -> off)', async ($, on) => {
  const h = host(on, base({ env: { ACE_FEEDBACK_DOWNVOTE: '0' } }))
  expect((await flow($, h, 'perfekt')).feedback).toBe(undefined)
})
test('switch: a server feedback_upvote is persisted and wins over the downvote switch', async ($, on) => {
  const resp = JSON.parse(S8); resp.feedback_upvote = true
  const h = host(on, { ...base({ env: { ACE_FEEDBACK_DOWNVOTE: '0' } }), search: () => ({ stdout: JSON.stringify(resp) }) })
  expect((await flow($, h, 'perfekt')).feedback).toEqual(UPVOTE)
})
test('switch: a server feedback_upvote false turns the upvote off although the downvote is on', async ($, on) => {
  const off = JSON.parse(S8); off.feedback_upvote = false
  const h = host(on, { ...base(), search: () => ({ stdout: JSON.stringify(off) }) })
  expect((await flow($, h, 'perfekt')).feedback).toBe(undefined)
})

test('one feedback per task: an upvote, then a rejection of the same task -> only the upvote', async ($, on) => {
  const h = host(on, base({ model: () => ans('neutral', 0.9) }))
  const { a } = st8a()
  await mainTask($, h)
  await done($, 'applied ' + a)
  await submit($, 'perfekt')
  await submit($, 'das ist falsch')
  await settle(h)
  expect(h.rows().filter((x: any) => x.event === 'rejection_check' && x.matched === 'das ist falsch').pop().failed).toBe('task_downvoted')
  await mainTask($, h)
  await done($, 'second')
  expect(h.trace(h.learns()[1]!).feedback).toEqual(UPVOTE)
})
test('one feedback per task: a downvote, then an approval of the same task -> only the downvote', async ($, on) => {
  const h = host(on, base({ model: () => ans('neutral', 0.9) }))
  const { a } = st8a()
  await mainTask($, h)
  await done($, 'applied ' + a)
  await submit($, 'das ist falsch')
  await submit($, 'perfekt')
  await settle(h)
  expect(upOf(h, 'perfekt').failed).toBe('task_voted')
  await mainTask($, h)
  await done($, 'second')
  expect(h.trace(h.learns()[1]!).feedback?.kind).toBe('downvote')
})
test('headless: the phrase upvotes', async ($, on) => {
  const h = host(on, base())
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  expect((await flow($, h, 'perfekt')).feedback).toEqual(UPVOTE)
})
test('only the next main trace WITH tool work carries it; a pending downvote of another task wins and the upvote waits', async ($, on) => {
  const h = host(on, base())
  const { a } = st8a()
  await mainTask($, h)
  await done($, 'applied ' + a)
  await submit($, 'perfekt')
  await mainTask($, h, [])                          // no substantial work: no trace, the upvote stays pending
  await done($, 'talk')
  h.put(`${SDIR}/pending-downvote.json`, JSON.stringify({ applied_log_ids: [999], at: h.now() / 1000 }))
  await mainTask($, h)
  await done($, 'x')
  expect(h.trace(h.learns()[1]!).feedback).toEqual({ kind: 'downvote', applied_log_ids: [999] })
  await mainTask($, h)
  await done($, 'y')
  expect(h.trace(h.learns()[2]!).feedback).toEqual(UPVOTE)
})

test('precision fixture (unit): every POS is a phrase upvote, NO NEG is; NEG outnumbers POS', () => {
  expect([POS.length, NEG.length]).toEqual([33, 82])
  for (const t of POS) expect([t, upvoteProbe(t).matched !== null]).toEqual([t, true])
  for (const t of NEG) expect([t, upvoteProbe(t).matched]).toEqual([t, null])
  expect(upvoteProbe('perfekt, jetzt noch die doku').blocked).toBe('perfekt')
  expect(upvoteProbe('x'.repeat(301)).tooLong).toBe(true)
})
// The whole pipeline (gates, switch, probe, pending file, trace) per fixture case, with a model that answers 'approve' at 1.0:
// POS -> exactly the phrase upvote, NEG -> never an upvote (a NEG with a rejection phrase may downvote). Target 100 / 100 / 0.
for (const [label, set] of [['POS', POS], ['NEG', NEG]] as const)
  for (const text of set)
    test(`pipeline ${label}: ${JSON.stringify(text).slice(0, 50)}`, async ($, on) => {
      const h = host(on, base({ model: APPROVE }))
      const fb = (await flow($, h, text)).feedback
      if (label === 'POS') expect(fb).toEqual(UPVOTE)
      else expect(fb?.kind === 'upvote').toBe(false)
      if (label === 'NEG' && REJECTION_PHRASES.some(p => text.toLowerCase().includes(p))) expect(fb === undefined || fb.kind === 'downvote').toBe(true)
    })

test('buildTrace: upvote shape is {kind, applied_log_ids, detect_source: phrase} only (no model_conf); a downvote wins', () => {
  const t = (o: any) => buildTrace({ userPrompt: 'p', answer: 'a', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools: [], ...o }).trace.feedback
  expect(t({ upvote: [7], upvoteDetect: { detect_source: 'phrase' } })).toEqual({ kind: 'upvote', applied_log_ids: [7], detect_source: 'phrase' })
  expect(t({ upvote: [7], upvoteDetect: { detect_source: 'model', model_conf: 0.95 } })).toEqual({ kind: 'upvote', applied_log_ids: [7] })  // a stale model pending file
  expect(t({ upvote: [], upvoteDetect: { detect_source: 'phrase' } })).toBe(undefined)
  expect(t({ downvote: [1], upvote: [7] })).toEqual({ kind: 'downvote', applied_log_ids: [1] })
})
