// ACE mod suite, server-supplied A/B CONTROL share (search response render_control_pct): env > file (< 7 days) > 0 (off),
// bucket boundary, control+compact > 100 rule, 200-id parity vectors (shared with Python), control label + render_control_pct on the trace.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import V from './fixtures/control_pct_vectors.ts'
import { RENDER_CONTROL_PCT_FILE, appliedControlPct, normalizeVariant, renderCohort, serverControlPct, sha256Hex, storedControlPct, traceVariant } from '../lib/cohort.ts'
import { buildTrace } from '../lib/trace.ts'
import { FULL_PCT, HUMAN, ROOT, SID, done, host, mainTask, submit } from './helpers.ts'

const CTRL = `${ROOT}/${RENDER_CONTROL_PCT_FILE}`
const NOW = 1_800_000_000_000  // the host clock
const fresh = (pct: number, ageDays = 0) => JSON.stringify({ pct, at: Math.floor(NOW / 1000) - ageDays * 86400 })
const bucket = (id: string) => parseInt(sha256Hex('render:' + id).slice(0, 8), 16) % 100
const withCtrl = (pct: unknown) => { const o = JSON.parse(S8); o.render_control_pct = pct; return JSON.stringify(o) }
const sidWith = (pred: (b: number) => boolean) => { for (let i = 0; i < 10000; i++) if (pred(bucket('cc-' + i))) return 'cc-' + i; throw new Error('no sid') }

test('render_control_pct: only a top-level integer 0-100 counts; the stored value expires after 7 days', async () => {
  for (const v of [0, 50, 100]) expect(serverControlPct({ render_control_pct: v })).toBe(v)
  for (const v of [-1, 101, '0', 12.5, true, null, [0]]) expect(serverControlPct({ render_control_pct: v })).toBe(undefined)
  expect(serverControlPct(null)).toBe(undefined)
  expect(storedControlPct(fresh(30, 6), NOW)).toBe(30)
  expect(storedControlPct(fresh(30, 8), NOW)).toBe(undefined)
  for (const t of [undefined, 'x', '[]', '{"pct": 200, "at": 1800000000}', '{"pct": 5}', '{"pct": true, "at": 1800000000}']) expect(storedControlPct(t, NOW)).toBe(undefined)
})

test('bucket boundary: bucket < pct is control, bucket == pct is not; no id is never control', async () => {
  const env = { ACE_AB_CONTROL_PCT: '40', ACE_RENDER_FULL_PCT: '0' }
  expect(renderCohort(sidWith(b => b === 39), env)).toBe('control')
  expect(renderCohort(sidWith(b => b === 40), env)).toBe('budget')
  expect(renderCohort(undefined, { ACE_AB_CONTROL_PCT: '100' })).toBe('budget')
  expect(renderCohort('', { ACE_AB_CONTROL_PCT: '100' })).toBe('budget')
})

test('control + compact > 100: both 0 (rule unchanged); the full share is capped to the rest', async () => {
  const ids = Array.from({ length: 300 }, (_, i) => 'cc-' + i)
  const over = { ACE_AB_CONTROL_PCT: '60', ACE_AB_COMPACT_PCT: '50', ACE_RENDER_FULL_PCT: '0' }
  expect(ids.every(i => renderCohort(i, over) === 'budget')).toBe(true)
  expect(appliedControlPct(over)).toBe(0)
  expect(appliedControlPct({ ACE_AB_CONTROL_PCT: '60', ACE_AB_COMPACT_PCT: '40' })).toBe(60)
  const capped = { ACE_AB_CONTROL_PCT: '80', ACE_RENDER_FULL_PCT: '100' }
  expect(new Set(ids.map(i => renderCohort(i, capped)))).toEqual(new Set(['control', 'full']))
  expect(appliedControlPct({})).toBe(0)
  expect(appliedControlPct({ ACE_AB_CONTROL_PCT: 'abc' })).toBe(0)
})

test('200-id parity vectors (tests-fixtures/control-pct, same file the Python chain reads): arms for every config, share from env', async () => {
  const v: any = V
  expect(v.ids.length).toBe(200)
  for (const c of v.configs) {
    const raw = c.raw ?? c
    const env = { ACE_AB_CONTROL_PCT: String(raw.ctrl), ACE_AB_COMPACT_PCT: String(raw.comp), ACE_RENDER_FULL_PCT: String(raw.full) }
    expect(v.ids.map((i: string) => renderCohort(i, env))).toEqual(c.arms)
  }
})

test('trace label: control is a label now (compact is not); a missing stored label falls back to the control arm', async () => {
  expect(normalizeVariant(' Control ')).toBe('control')
  expect([normalizeVariant('compact'), normalizeVariant('full'), normalizeVariant('budget')]).toEqual([undefined, 'full', 'budget'])
  expect(traceVariant(undefined, 'conv-1', { ACE_AB_CONTROL_PCT: '100', ACE_RENDER_FULL_PCT: '0' })).toBe('control')
})

test('buildTrace: render_control_pct travels with render_variant (0 when off), omitted without it', async () => {
  const a = { userPrompt: 'fix it', answer: 'done', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools: [] }
  const t = buildTrace({ ...a, renderVariant: 'control', renderControlPct: 35 }).trace
  expect([t.render_variant, t.render_control_pct]).toEqual(['control', 35])
  expect(buildTrace({ ...a, renderVariant: 'budget', renderControlPct: 0 }).trace.render_control_pct).toBe(0)
  expect('render_control_pct' in buildTrace(a).trace).toBe(false)
})

// ---------- the share through the hooks: server file, env override, expiry ----------
test('server file: control arm injects NO patterns; search, retrieval and F-080 anchor keep running', async ($, on) => {
  const h = host(on, { files: { [CTRL]: fresh(100) }, search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  expect(h.searches().length).toBe(1)
  expect(h.state()!.render_variant).toBe('control')
  expect(h.state()!.task_session_id).toBe(h.pin(h.searches()[0]!))
  expect(h.state()!.retrieval_id).toBeTruthy()
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('control')
})

const arm = async ($: any, on: any, o: any) => { const h = host(on, { search: () => ({ stdout: S8 }), ...o }); await submit($); return h.state()!.render_variant }
test('server file: sess-1 is bucket 66; pct 67 -> control, pct 66 -> not (boundary)', async ($, on) => {
  expect(bucket(SID)).toBe(66)
  expect(await arm($, on, { files: { [CTRL]: fresh(67) } })).toBe('control')
})
test('server file: pct == bucket is not control', async ($, on) => { expect(await arm($, on, { files: { [CTRL]: fresh(66) } })).toBe('full') })
test('server file: env 0 beats a file of 100', async ($, on) => { expect(await arm($, on, { files: { [CTRL]: fresh(100) }, env: { ACE_AB_CONTROL_PCT: '0' } })).toBe('full') })
test('server file: env 100 beats a file of 0', async ($, on) => { expect(await arm($, on, { files: { [CTRL]: fresh(0) }, env: { ACE_AB_CONTROL_PCT: '100' } })).toBe('control') })
test('server file: a stale (> 7 days) file is off', async ($, on) => { expect(await arm($, on, { files: { [CTRL]: fresh(100, 8) } })).toBe('full') })
test('server file: an invalid file is off', async ($, on) => { expect(await arm($, on, { files: { [CTRL]: '{"pct": 500, "at": 1800000000}' } })).toBe('full') })

test('server share: a response render_control_pct is persisted in its own file; invalid values and a missing field keep it', async ($, on) => {
  let pct: unknown = 40
  const h = host(on, { search: () => ({ stdout: withCtrl(pct) }) })
  await submit($)
  expect(JSON.parse(h.files.get(CTRL)!)).toEqual({ pct: 40, at: Math.floor(h.now() / 1000) })
  expect(h.files.has(FULL_PCT)).toBe(false)
  for (const bad of ['off', -1, 101, true, 12.5]) { pct = bad; await submit($, HUMAN + ' again'); expect(JSON.parse(h.files.get(CTRL)!).pct).toBe(40) }
  pct = undefined; await submit($, HUMAN + ' once more'); expect(JSON.parse(h.files.get(CTRL)!).pct).toBe(40)
  pct = 0; await submit($, HUMAN + ' and zero'); expect(JSON.parse(h.files.get(CTRL)!).pct).toBe(0)
})

async function traceOf($: any, on: any, files: any) {
  const h = host(on, { files, search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  return h.trace(h.learns()[0]!)
}
test('trace: control arm from the server file carries render_variant control + render_control_pct 100', async ($, on) => {
  const t = await traceOf($, on, { [CTRL]: fresh(100) })
  expect([t.render_variant, t.render_control_pct, t.conversation_id]).toEqual(['control', 100, SID])
})
test('trace: a full-arm conversation carries the share applied (10)', async ($, on) => {
  const t = await traceOf($, on, { [CTRL]: fresh(10) })
  expect([t.render_variant, t.render_control_pct]).toEqual(['full', 10])
})
test('trace: render_control_pct is 0 when off', async ($, on) => { expect((await traceOf($, on, {})).render_control_pct).toBe(0) })

test('control trace: render_variant control unchanged, applied_log_ids [], playbook_used [], no used_ids', async ($, on) => {
  const h = host(on, { files: { [CTRL]: fresh(100) }, search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($, 'applied everything from the patterns')
  const L = h.learns()[0]!, t = h.trace(L)
  expect(t.render_variant).toBe('control')
  expect([t.applied_log_ids, t.playbook_used]).toEqual([[], []])
  expect([t.used_ids_model_list, t.used_ids_tokens_list, t.used_ids_model, t.used_ids_tokens]).toEqual([[], [], 0, 0])
  expect(h.learnArgv(L).includes('--applied-log-ids')).toBe(false)
})
