// 8.4.3: server-side follow-up judging (locked contract v1). The server advertises `followup_judging` in the /patterns/search answer:
// the string "shadow" -> the client sends trace.followup AND keeps its own vote path; boolean true -> trace.followup, no client vote;
// anything else (absent, false, "true", 1, object, stale > 7 days) -> off, byte-identical to 8.4.2 (vote_golden.test.ts).
// trace.followup = { text (redacted human part, <= 600 + marker), target_retrieval_id (UUID of the PREVIOUS main task), applied_log_ids: int[], ts: ISO-8601 Z }.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import GOLDEN from './fixtures/vote_golden_842.ts'
import { CWD, HOME, PRJ, PROOT, ROOT, SDIR, done, host, mainTask, spawn, st8a, submit } from './helpers.ts'
import { FOLLOWUP_FILE, NEUTRAL, SCENARIOS, T0S, ans, snapshot } from './vote_scenarios.ts'
import { FOLLOWUP_LINE_LIVE, FOLLOWUP_LINE_SHADOW, flushRejections } from '../handlers/prompt.ts'
import { followupFileFor, serverFollowup, storedFollowup, sha256Hex } from '../lib/cohort.ts'
import { FOLLOWUP_TEXT_MAX, buildTrace, followupField } from '../lib/trace.ts'
import { HUMAN_MARK, humanPart } from '../lib/humanpart.ts'
import { REJECTION_SYSTEM } from '../lib/rejection.ts'

const T0 = T0S * 1000
// the stored switch: per org/project (review M1); a real search answer always rewrites it, so the tests' answers carry the key too
const ON = (mode: string, at = T0S, project = PRJ, org = 'org_t') => ({ [FOLLOWUP_FILE]: JSON.stringify({ mode, at, org, project }) })
const KEY: Record<string, unknown> = { live: true, shadow: 'shadow' }
const ridN = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
// every search answers with its own retrieval_id: the rejected task and the carrying task differ (as in production)
const rotating = (extra: (o: any) => void = () => {}) => { let n = 0; return () => { const o = JSON.parse(S8); o.retrieval_id = ridN(++n); extra(o); return { stdout: JSON.stringify(o) } } }
const base = (o: any = {}) => ({ defaultArm: true, mockClock: true,
  search: o.search ?? rotating(r => { if (o.mode in KEY) r.followup_judging = KEY[o.mode]; o.extra?.(r) }), env: { ACE_FEEDBACK_DOWNVOTE: '1', ...(o.env ?? {}) },
  files: { ...(o.mode ? ON(o.mode) : {}), ...(o.files ?? {}) }, ...(o.model ? { model: o.model } : {}), ...(o.selfEval ? { selfEval: true } : {}) })
const settle = async (h: any) => { await h.clock.advance(1); await flushRejections(); for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 1)) }
const PF = `${SDIR}/pending-followup.json`
const lmaRid = (h: any) => JSON.parse(h.files.get(`${SDIR}/last-main-applied.json`) ?? '{}').retrieval_id
const TF = `${SDIR}/followup-target.json`   // review S1: the follow-up target has its own file, written only with the final record
const tfRid = (h: any) => h.files.has(TF) ? JSON.parse(h.files.get(TF)!).target_retrieval_id : undefined
const rejCalls = (h: any, text: string) => h.modelCalls.filter((c: any) => c.system === REJECTION_SYSTEM && String(c.prompt).includes('<user_message>\n' + text + '\n'))
const fuRows = (h: any) => h.rows().filter((x: any) => x.event === 'followup_check')
// the previous task (evidenced ids unless prev = 'done'), the reply, the next main task: its trace carries the followup
async function flow($: any, h: any, reply: string, prev = 'applied ' + st8a().a) {
  await mainTask($, h); await done($, prev); await settle(h)
  const target = tfRid(h)
  await submit($, reply); await settle(h)
  const pending = h.files.get(PF)
  await mainTask($, h); await done($, 'did something else'); await settle(h)
  return { target, pending, trace: h.learns().length > 1 ? h.trace(h.learns()[h.learns().length - 1]!) : undefined }
}

// ---------- the capability: exact-match tri-state ----------
test('serverFollowup: exactly "shadow" -> shadow, exactly true -> live, absent -> undefined (keep stored), anything else -> off', () => {
  expect(serverFollowup({ followup_judging: 'shadow' })).toBe('shadow')
  expect(serverFollowup({ followup_judging: true })).toBe('live')
  expect(serverFollowup({})).toBe(undefined)
  expect(serverFollowup(null)).toBe(undefined)
  for (const v of [false, 'true', 'Shadow', 'live', 1, 0, null, {}, ['shadow'], ' shadow']) expect(serverFollowup({ followup_judging: v })).toBe('off')
})
test('storedFollowup: {mode shadow|live, at, org, project} < 7 days for THIS org/project; anything else off', () => {
  const now = T0, f = (o: any) => JSON.stringify({ org: 'o', project: 'p', ...o })
  expect(storedFollowup(f({ mode: 'shadow', at: T0S - 6 * 86400 }), now, 'o', 'p')).toBe('shadow')
  expect(storedFollowup(f({ mode: 'live', at: T0S }), now, 'o', 'p')).toBe('live')
  expect(storedFollowup(f({ mode: 'live', at: T0S + 60 }), now, 'o', 'p')).toBe('live')            // small clock skew
  for (const t of [f({ mode: 'live', at: T0S - 8 * 86400 }), f({ mode: 'off', at: T0S }), f({ mode: true, at: T0S }), f({ mode: 'LIVE', at: T0S }),
    f({ mode: 'shadow' }), f({ mode: 'shadow', at: String(T0S) }), f({ mode: 'live', at: T0S + 3600 }),               // a future at
    f({ mode: 'live', at: T0S, project: 'other' }), f({ mode: 'live', at: T0S, org: 'other' }), JSON.stringify({ mode: 'live', at: T0S }), 'x', undefined, '[]'])
    expect(storedFollowup(t, now, 'o', 'p')).toBe('off')
})
test('another project\'s stored switch is off here (no followup, vote path as 8.4.2)', async ($, on) => {
  const h = host(on, base({ extra: (r: any) => { r.followup_judging = true } }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  h.put(FOLLOWUP_FILE, ON('live', T0S, 'prj_other')[FOLLOWUP_FILE]!)   // this project's file with another project's content: off
  await submit($, 'das ist falsch'); await settle(h)
  expect([h.files.has(PF), h.files.has(`${SDIR}/pending-downvote.json`)]).toEqual([false, true])
})
test('capture (engine answer): stores {mode, at, org, project}; an invalid or ABSENT key stores off (a withdrawal stops at once)', async ($, on) => {
  let v: unknown = 'shadow'
  const eng = rotating(o => { if (v !== undefined) o.followup_judging = v })
  const h = host(on, { ...base({ files: { [`${PROOT}/engine/search.js`]: '' } }), engine: () => eng() })
  const mode = () => JSON.parse(h.files.get(FOLLOWUP_FILE)!).mode
  await submit($); expect(JSON.parse(h.files.get(FOLLOWUP_FILE)!)).toEqual({ mode: 'shadow', at: Math.floor(h.now() / 1000), org: 'org_t', project: PRJ })
  v = true; await submit($, 'second prompt please'); expect(mode()).toBe('live')
  v = undefined; await submit($, 'third prompt please'); expect(mode()).toBe('off')
  v = true; await submit($, 'fourth prompt please'); expect(mode()).toBe('live')
  v = 'true'; await submit($, 'fifth prompt please'); expect(mode()).toBe('off')
})
test('ace-cli fallback answer without the key keeps the stored mode; another project\'s file is never touched', async ($, on) => {
  const other = `${ROOT}/${followupFileFor('org_t', 'prj_other')}`, otherText = JSON.stringify({ mode: 'live', at: T0S, org: 'org_t', project: 'prj_other' })
  const h = host(on, base({ files: { ...ON('shadow'), [other]: otherText }, search: rotating() }))
  await submit($)
  expect([JSON.parse(h.files.get(FOLLOWUP_FILE)!).mode, h.files.get(other)]).toEqual(['shadow', otherText])
})
test('capture: a local reuse-cache hit (domain shift) never writes the switch', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await submit($)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)   // a real domain-shift search
  const marker = JSON.stringify({ mode: 'shadow', at: T0S, org: 'org_t', project: PRJ })
  h.put(FOLLOWUP_FILE, marker)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)   // the same query: a reuse hit
  expect(h.files.get(FOLLOWUP_FILE)).toBe(marker)
})

// ---------- live ----------
test('live: the next MAIN trace carries trace.followup {text, target_retrieval_id, applied_log_ids, ts}; no client vote, no model call, no vote row', async ($, on) => {
  const h = host(on, base({ mode: 'live', model: ans('reject', 1) }))
  const { target, trace } = await flow($, h, 'das ist falsch, mach das anders')
  expect(trace.followup).toEqual({ text: 'das ist falsch, mach das anders', target_retrieval_id: target, applied_log_ids: [st8a().log], ts: expect.any(String) })
  const ms = Date.parse(trace.followup.ts)
  expect(ms >= T0 && ms < T0 + 60_000).toBe(true)              // when the reply was written (mock clock; ISO-8601 UTC, trailing Z)
  expect(Object.keys(trace.followup)).toEqual(['text', 'target_retrieval_id', 'applied_log_ids', 'ts'])
  expect(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$/.test(trace.followup.ts)).toBe(true)
  expect([target, trace.retrieval_id !== target, trace.feedback]).toEqual([ridN(1), true, undefined])
  expect(rejCalls(h, 'das ist falsch, mach das anders').length).toBe(0)
  expect([h.files.has(`${SDIR}/pending-downvote.json`), h.files.has(PF)]).toEqual([false, false])
  expect(h.rows().some((x: any) => x.event === 'rejection_check' && x.chars === 'das ist falsch, mach das anders'.length)).toBe(false)
  expect(fuRows(h).map((r: any) => r.failed)).toEqual(['no_target', null, 'task_sent'])   // the first prompt (no task yet); the reply; the next prompt to the same task
  const r = fuRows(h)[1]
  expect([r.mode, r.prev_ids, r.sent_chars, r.source]).toEqual(['live', 1, 'das ist falsch, mach das anders'.length, 'mod'])
  expect(JSON.stringify(fuRows(h)).includes('falsch')).toBe(false)
})
test('live: a previous task without evidenced ids still sends the followup with applied_log_ids []', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  const { target, trace } = await flow($, h, 'das passt so nicht', 'done')
  expect([trace.followup.applied_log_ids, trace.followup.target_retrieval_id]).toEqual([[], target])
})
test('live: an upvote phrase is not judged on the client either (followup only)', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  const { trace } = await flow($, h, 'Perfekt, danke!')
  expect([trace.feedback, trace.followup.text]).toEqual([undefined, 'Perfekt, danke!'])
})

// ---------- shadow ----------
test('shadow: the followup is sent AND the client vote path runs unchanged (phrase downvote in trace.feedback)', async ($, on) => {
  const h = host(on, base({ mode: 'shadow' }))
  const { target, trace } = await flow($, h, 'das ist falsch')
  expect(trace.feedback).toEqual({ kind: 'downvote', applied_log_ids: [st8a().log], detect_source: 'phrase' })
  expect([trace.followup.text, trace.followup.target_retrieval_id]).toEqual(['das ist falsch', target])
})
test('shadow: model path unchanged too (Haiku asked, downvote with model_conf) plus the followup', async ($, on) => {
  const h = host(on, base({ mode: 'shadow', model: ans('reject', 0.93) }))
  const { trace } = await flow($, h, NEUTRAL)
  expect(rejCalls(h, NEUTRAL).length).toBe(1)
  expect(trace.feedback).toEqual({ kind: 'downvote', applied_log_ids: [st8a().log], detect_source: 'model', model_conf: 0.93 })
  expect(trace.followup.text).toBe(NEUTRAL)
})
// every golden scenario with the shadow switch: everything the 8.4.2 client did is identical, the traces only gain `followup`
const stripFollowup = (snap: any) => JSON.parse(JSON.stringify(snap, (k, v) => k === 'followup' ? undefined : v))
for (const [name, sc] of Object.entries(SCENARIOS))
  test('golden with followup_judging "shadow": ' + name + ' -> 8.4.2 vote behaviour identical (traces gain only followup)', async ($, on) => {
    const { snap } = await snapshot($, on, sc, ON('shadow'), {}, (r: any) => { r.followup_judging = 'shadow' })
    expect(stripFollowup(snap)).toEqual((GOLDEN as any)[name])
  })

// ---------- the text ----------
test('text: redacted first (secrets and personal data), then the human part', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  const key = 'sk-' + 'ant-api03-' + 'Zq9Xw2Lm'.repeat(4)
  const { trace } = await flow($, h, `das stimmt nicht, schreib an max.mustermann@firma.de, IBAN DE89370400440532013000, key ${key} bitte`)
  for (const secret of ['max.mustermann@firma.de', 'DE89370400440532013000', 'Zq9Xw2Lm']) expect(trace.followup.text.includes(secret)).toBe(false)
  expect(trace.followup.text.startsWith('das stimmt nicht')).toBe(true)
})
test('text: > 600 code points -> head 300 + marker + tail 300 (<= 605 <= 640); code blocks and logs are not sent', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  const reply = 'Größe '.repeat(80) + '\n```\nsecret_code()\n```\n' + 'ende '.repeat(80)
  const { trace } = await flow($, h, reply)
  expect(trace.followup.text).toBe(humanPart(reply))
  expect(trace.followup.text.includes(HUMAN_MARK)).toBe(true)
  expect(trace.followup.text.includes('secret_code')).toBe(false)
  expect([...trace.followup.text].length <= 605 && [...HUMAN_MARK].length <= 40).toBe(true)
})
test('text: a prompt whose human part is empty sends NO followup (the server would drop it); a text-free row says empty_human', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  await submit($, '```\nconst a = 1\nconst b = 2\n```'); await settle(h)
  expect([h.files.has(PF), fuRows(h).pop().failed]).toEqual([false, 'empty_human'])
})
test('builder guards: empty / over 640 code points / non-UUID target / non-int ids -> no followup field at all', () => {
  const ok = { text: 'x', target_retrieval_id: ridN(7), applied_log_ids: [1], ts: '2027-01-15T08:00:00.000Z' }
  expect(followupField(ok)).toEqual(ok)
  expect(FOLLOWUP_TEXT_MAX).toBe(640)
  for (const bad of [{ text: '' }, { text: '   ' }, { text: 'a'.repeat(641) }, { target_retrieval_id: 'nope' }, { target_retrieval_id: null }, { applied_log_ids: [1.5] },
    { applied_log_ids: null }, { ts: 1800000000 }, { ts: 'yesterday' }])
    expect(followupField({ ...ok, ...bad } as any)).toBe(undefined)
  expect(followupField({ ...ok, text: '😀'.repeat(640) })).toEqual({ ...ok, text: '😀'.repeat(640) })   // code points, as Python len
  const b = (followup: any) => buildTrace({ userPrompt: 'p', tools: [], answer: '', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', followup }).trace
  expect([b(ok).followup, 'followup' in b(undefined), 'followup' in b({ ...ok, text: '' })]).toEqual([ok, false, false])
})

// ---------- gates: nothing leaves the machine ----------
// review S3: in live the client never votes, also when a follow-up gate failed (ACE_REJECTION_MODEL=0 and headless get no feedback signal)
test('live + ACE_REJECTION_MODEL=0: no follow-up text leaves the machine AND no client vote', async ($, on) => {
  const h = host(on, base({ mode: 'live', env: { ACE_REJECTION_MODEL: '0' } }))
  const { trace } = await flow($, h, 'das ist falsch')
  expect([trace.followup, trace.feedback]).toEqual([undefined, undefined])
  expect([h.files.has(PF), h.files.has(`${SDIR}/pending-downvote.json`)]).toEqual([false, false])
})
test('shadow + ACE_REJECTION_MODEL=0: no followup, the client phrase vote as in 8.4.2', async ($, on) => {
  const h = host(on, base({ mode: 'shadow', env: { ACE_REJECTION_MODEL: '0' } }))
  const { trace } = await flow($, h, 'das ist falsch')
  expect([trace.followup, trace.feedback]).toEqual([undefined, { kind: 'downvote', applied_log_ids: [st8a().log], detect_source: 'phrase' }])
})
test('headless (isInteractive false): no followup', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  const { pending, trace } = await flow($, h, 'das ist falsch')
  expect([pending, trace.followup]).toEqual([undefined, undefined])
})
test('machine prompts (task notification) and mid-turn prompts: no followup', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  await submit($, 'das ist falsch', 'task-notification'); await settle(h)
  await $.prompt.submit({ text: 'das ist falsch', wait: false, origin: { kind: 'composer' }, turnId: 't1' } as any); await settle(h)
  expect(h.files.has(PF)).toBe(false)
})
test('subagent learns never take the pending followup; the next MAIN learn does', async ($, on) => {
  const target = ridN(42)
  const h = host(on, base({ mode: 'live', files: { [PF]: JSON.stringify({ text: 'nein', target_retrieval_id: target, applied_log_ids: [], ts: new Date(T0).toISOString(), target_at: T0S }) } }))
  await mainTask($, h)
  await spawn($, 'a subagent task that is long enough to count as one')
  await $.turn.start({ text: 'a subagent task that is long enough to count as one', turnId: 'w1', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/y.py', old_string: 'a', new_string: 'b', agentId: 'agent-1' } as any)
  await done($, 'sub done', 'agent-1'); await settle(h)
  expect(h.learns().length).toBe(1)                              // the subagent learn went out
  expect(h.files.has(PF)).toBe(true)
  await done($, 'main done'); await settle(h)
  const traces = h.learns().map((r: any) => h.trace(r))
  expect(traces.filter((t: any) => t.followup).map((t: any) => [t.agent_type, t.followup.target_retrieval_id])).toEqual([['main', target]])
})
test('no valid UUID retrieval_id on the previous task -> no followup (live: no client vote either)', async ($, on) => {
  const h = host(on, base({ mode: 'live', extra: (r: any) => { r.retrieval_id = 'not-a-uuid' } }))
  const { trace } = await flow($, h, 'das ist falsch')
  expect([trace.followup, trace.feedback]).toEqual([undefined, undefined])
})
// review S1: the target is the task the reply reacts to, or nothing
test('an aborted task, then a reply -> no followup (the target file went with the turn)', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  expect(tfRid(h)).toBe(ridN(1))
  await mainTask($, h)
  await $.turn.complete({ answer: 'stopped', durationMs: 5, isAborted: true, turnId: 't1', reason: 'answer' } as any); await settle(h)
  expect(tfRid(h)).toBe(undefined)
  h.files.delete(PF)   // the aborted / deferred task's own prompt was a reply to the task before: that follow-up is fine
  await submit($, 'das ist falsch'); await settle(h)
  expect(h.files.has(PF)).toBe(false)
})
test('a deferred Stop (running subagent), then a reply -> no followup', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  await mainTask($, h)
  await ($ as any).classic.Stop({ session_id: 'sess-1', background_tasks: [{ type: 'subagent', status: 'running' }] })
  await done($, 'waiting for the agent'); await settle(h)
  expect(h.rows().some((x: any) => x.event === 'learn_deferred')).toBe(true)
  expect(tfRid(h)).toBe(undefined)
  h.files.delete(PF)   // the aborted / deferred task's own prompt was a reply to the task before: that follow-up is fine
  await submit($, 'das ist falsch'); await settle(h)
  expect(h.files.has(PF)).toBe(false)
})
test('no previous record / older than 6 h -> no followup', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await submit($, 'das ist falsch'); await settle(h)
  expect(h.files.has(PF)).toBe(false)
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  await h.clock.advance(6 * 3600 * 1000)
  await submit($, 'das ist falsch'); await settle(h)
  expect(h.files.has(PF)).toBe(false)
})
test('one followup per previous task: a second reply to the same task sends nothing more (row task_sent)', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  await submit($, 'das ist falsch'); await settle(h)
  const first = h.files.get(PF)
  await submit($, 'wirklich falsch, nochmal'); await settle(h)
  expect([h.files.get(PF), fuRows(h).pop().failed]).toEqual([first, 'task_sent'])
})

// review S3: a text-free followup_check row also when a gate stops the follow-up (only while the mode is not off)
for (const [name, setup, failed] of [
  ['headless', async ($: any) => { await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any) }, 'headless'],
  ['ACE_REJECTION_MODEL=0', null, 'model_off'],
] as [string, any, string][])
  test('followup_check failed ' + failed + ' (' + name + ')', async ($, on) => {
    const h = host(on, base({ mode: 'live', env: failed === 'model_off' ? { ACE_REJECTION_MODEL: '0' } : {} }))
    if (setup) await setup($)
    await flow($, h, 'das ist falsch')
    expect(fuRows(h).map((r: any) => r.failed).every((f: string) => f === failed)).toBe(true)
    expect(fuRows(h).length > 0).toBe(true)
  })
test('followup_check failed no_target / stale_target / no_uuid', async ($, on) => {
  const h = host(on, base({ mode: 'live' }))
  await submit($, 'das ist falsch'); await settle(h)                                   // no target file
  expect(fuRows(h).pop().failed).toBe('no_target')
  h.put(TF, JSON.stringify({ target_retrieval_id: ridN(9), applied_log_ids: [], task_session_id: 't', at: T0S - 6 * 3600 }))
  await submit($, 'das ist falsch'); await settle(h)
  expect(fuRows(h).pop().failed).toBe('stale_target')
  h.put(TF, JSON.stringify({ target_retrieval_id: 'nope', applied_log_ids: [], task_session_id: 't2', at: T0S }))
  await submit($, 'das ist falsch'); await settle(h)
  expect(fuRows(h).pop().failed).toBe('no_uuid')
  expect(JSON.stringify(fuRows(h)).includes('falsch')).toBe(false)
})
test('mode off: no followup_check rows at all', async ($, on) => {
  const h = host(on, base())
  await flow($, h, 'das ist falsch')
  expect(fuRows(h).length).toBe(0)
})
// review S7: with the mode off no target file is written and no rm is spawned for it
test('mode off: the follow-up target file is never written nor removed (no extra process per turn)', async ($, on) => {
  const h = host(on, base())
  await flow($, h, 'das ist falsch')
  expect(h.files.has(TF)).toBe(false)
  expect(h.runs.some((r: any) => r.argv.some((a: string) => typeof a === 'string' && a.includes('followup-target.json')))).toBe(false)
})
test('mode on: the target file is written with the final record and removed at the next human turn end', async ($, on) => {
  const h = host(on, base({ mode: 'shadow' }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  expect(tfRid(h)).toBe(ridN(1))
})

// review (round 6): queueFollowup never throws; a write failure is logged (write_failed) and the shadow vote path still runs
test('shadow: writing the pending follow-up fails -> followup_check write_failed, the client vote still goes out as in 8.4.2', async ($, on) => {
  const h = host(on, { ...base({ mode: 'shadow' }), beforeWrite: (p: string) => p.endsWith('/pending-followup.json') ? Promise.reject(new Error('disk full')) : Promise.resolve() })
  const { trace } = await flow($, h, 'das ist falsch')
  expect(trace.feedback).toEqual({ kind: 'downvote', applied_log_ids: [st8a().log], detect_source: 'phrase' })
  expect(fuRows(h).some((r: any) => r.failed === 'write_failed')).toBe(true)
  expect(JSON.stringify(fuRows(h)).includes('falsch')).toBe(false)
})
test('live: writing the pending follow-up fails -> write_failed, still no client vote', async ($, on) => {
  const h = host(on, { ...base({ mode: 'live' }), beforeWrite: (p: string) => p.endsWith('/pending-followup.json') ? Promise.reject(new Error('disk full')) : Promise.resolve() })
  const { trace } = await flow($, h, 'das ist falsch')
  expect([trace.feedback, trace.followup, fuRows(h).some((r: any) => r.failed === 'write_failed')]).toEqual([undefined, undefined, true])
})

// ---------- take time ----------
const pendingAt = (ts: string, target = ridN(42), targetAt = T0S) => ({ [PF]: JSON.stringify({ text: 'nein', target_retrieval_id: target, applied_log_ids: [3], ts, target_at: targetAt }) })
async function nextTrace($: any, h: any) { await mainTask($, h); await done($, 'x'); await settle(h); return h.trace(h.learns()[0]!) }
test('take: a valid pending followup goes out once and is consumed', async ($, on) => {
  const h = host(on, base({ mode: 'live', files: { ...pendingAt(new Date(T0).toISOString()) } }))
  expect((await nextTrace($, h)).followup).toEqual({ text: 'nein', target_retrieval_id: ridN(42), applied_log_ids: [3], ts: new Date(T0).toISOString() })
  expect(h.files.has(PF)).toBe(false)
})
test('take: older than 6 h -> dropped (consumed)', async ($, on) => {
  const h = host(on, base({ mode: 'live', files: { ...pendingAt(new Date(T0 - 6 * 3600 * 1000).toISOString()) } }))
  expect([(await nextTrace($, h)).followup, h.files.has(PF)]).toEqual([undefined, false])
})
test('take: the target task is 6 h old by now (target_at) -> dropped (consumed)', async ($, on) => {
  const h = host(on, base({ mode: 'live', files: { ...pendingAt(new Date(T0).toISOString(), ridN(42), T0S - 6 * 3600) } }))
  expect([(await nextTrace($, h)).followup, h.files.has(PF)]).toEqual([undefined, false])
})
// review M2: the privacy gates again at take time (a resumed / headless session, or the off switch set since)
test('take: ACE_REJECTION_MODEL=0 since -> the pending followup is removed, nothing sent', async ($, on) => {
  const h = host(on, base({ mode: 'live', env: { ACE_REJECTION_MODEL: '0' }, files: { ...pendingAt(new Date(T0).toISOString()) } }))
  expect([(await nextTrace($, h)).followup, h.files.has(PF)]).toEqual([undefined, false])
})
test('take: a headless (resumed -p) session -> the pending followup is removed, nothing sent', async ($, on) => {
  const h = host(on, base({ mode: 'live', files: { ...pendingAt(new Date(T0).toISOString()) } }))
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  expect([(await nextTrace($, h)).followup, h.files.has(PF)]).toEqual([undefined, false])
})
test('take: the server withdrew the flag since -> dropped (consumed)', async ($, on) => {
  const h = host(on, base({ mode: 'off', files: { ...pendingAt(new Date(T0).toISOString()) } }))
  expect([(await nextTrace($, h)).followup, h.files.has(PF)]).toEqual([undefined, false])
})
test('take: a followup whose target is the carrying trace\'s own retrieval_id stays pending', async ($, on) => {
  const h = host(on, base({ mode: 'live', files: { ...pendingAt(new Date(T0).toISOString(), ridN(1)) } }))
  const t = await nextTrace($, h)
  expect([t.retrieval_id, t.followup, h.files.has(PF)]).toEqual([ridN(1), undefined, true])
})
test('held login (8.4.1): a parked learn does not consume the followup; nothing parked carries it', async ($, on) => {
  const CFG = `${HOME}/.config/ace/config.json`
  const h = host(on, base({ mode: 'live', files: { [CFG]: '{}', ...pendingAt(new Date(T0).toISOString()) } }))
  h.put(`${ROOT}/auth-rejected`, sha256Hex('{}'))
  await mainTask($, h); await done($, 'x'); await settle(h)
  expect(h.files.has(PF)).toBe(true)
  expect(h.enqueued.length > 0 && h.enqueued.every((q: any) => !('followup' in JSON.parse(q.body)))).toBe(true)
})
test('self-eval window: no follow-up target before the real record, so a reply in the window sends no followup', async ($, on) => {
  let release = () => {}
  const gate = new Promise<void>(r => { release = r })
  const h = host(on, { ...base({ mode: 'live' }), selfEval: true, model: (req: any) => req.system ? { isAnswered: false, reason: 'api-error' } : gate.then(() => ({ isAnswered: true, text: '{"used": []}' })) })
  await mainTask($, h); await done($, 'applied ' + st8a().a)
  expect([lmaRid(h), tfRid(h)]).toEqual([ridN(1), undefined])   // the vote record names the task (unresolved votes); the follow-up target is not there yet
  await submit($, 'das ist falsch'); await settle(h)
  expect(h.files.has(PF)).toBe(false)
  release(); await settle(h); await settle(h)
  expect([lmaRid(h), tfRid(h)]).toEqual([ridN(1), ridN(1)])
})
test('ACE_TRACE_SINK: the sinked trace carries trace.followup unchanged', async ($, on) => {
  const h = host(on, base({ mode: 'live', env: { ACE_TRACE_SINK: 'file:/home/u/sink' } }))
  await mainTask($, h); await done($, 'applied ' + st8a().a); await settle(h)
  await submit($, 'das ist falsch'); await settle(h)
  await mainTask($, h); await done($, 'did something else'); await settle(h)
  const fu = [...h.files.keys()].filter(k => k.startsWith('/home/u/sink/')).map(k => JSON.parse(h.files.get(k)!).followup).filter(Boolean)
  expect(fu.map((f: any) => [f.text, f.target_retrieval_id, f.applied_log_ids])).toEqual([['das ist falsch', ridN(1), [st8a().log]]])
})

// ---------- the notice ----------
for (const [mode, line] of [['live', () => FOLLOWUP_LINE_LIVE], ['shadow', () => FOLLOWUP_LINE_SHADOW]] as [string, () => string][])
  test('notice: once per conversation while the mode is ' + mode, async ($, on) => {
    const h = host(on, base({ mode }))
    await submit($); await submit($, 'second prompt please')
    expect(h.logs.filter((l: string) => l === line()).length).toBe(1)
    expect(line().startsWith('ACE: Follow-up-Text (geschwärzt, rund 600 Zeichen) geht zur Bewertung an den Server')).toBe(true)
  })
test('notice: none when off or with ACE_REJECTION_MODEL=0', async ($, on) => {
  const h = host(on, base({ mode: 'live', env: { ACE_REJECTION_MODEL: '0' } }))
  await submit($)
  expect(h.logs.some((l: string) => l.includes('Follow-up'))).toBe(false)
})
test('notice: none when the switch is off', async ($, on) => {
  const h = host(on, base({ mode: 'off' }))
  await submit($)
  expect(h.logs.some((l: string) => l.includes('Follow-up'))).toBe(false)
})
