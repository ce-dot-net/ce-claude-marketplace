// ACE mod suite, 8.4.1: trace.evidence_source = why applied_log_ids is what it is, on every trace (like applied_log_ids):
// 'none' | 'self_eval' (Haiku ACE_USED only) | 'token' (H2 only) | 'both' | 'control_arm' (render_variant control wins).
// Only the mod chain sends it; Python-chain traces lack it (the server reads a missing field as unknown).
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import G from './fixtures/golden.ts'
import { buildTrace } from '../lib/trace.ts'
import { toItem } from '../lib/backfill_send.ts'
import { RENDER_CONTROL_PCT_FILE } from '../lib/cohort.ts'
import { ROOT, done, host, mainTask, settle, spawn, submit } from './helpers.ts'

const st8 = JSON.parse(G.state_main_8), [A, B] = Object.keys(st8.retrieval_log_ids)
const review = (ids: string) => () => ({ isAnswered: true, text: `ACE_REVIEW: 70% | 4m saved | ok\nACE_USED: ${ids}`, usage: {} })
async function traceOf($: any, on: any, o: any, answer?: string) {
  const h = host(on, { search: () => ({ stdout: S8 }), ...o })
  await mainTask($, h)
  await done($, answer)
  await settle(h)
  return h.trace(h.learns()[0]!)
}

test('evidence_source none: nothing used (self-eval failed, no token hit)', async ($, on) => {
  const t = await traceOf($, on, { selfEval: true })
  expect([t.evidence_source, t.applied_log_ids]).toEqual(['none', []])
})
test('evidence_source token: H2 only (id in the answer, self-eval failed)', async ($, on) => {
  const t = await traceOf($, on, { selfEval: true }, 'applied ' + A)
  expect(t.evidence_source).toBe('token')
  expect(t.applied_log_ids.length).toBe(1)
})
test('evidence_source self_eval: Haiku ACE_USED only', async ($, on) => {
  const t = await traceOf($, on, { selfEval: true, model: review(B) })
  expect([t.evidence_source, t.used_ids_tokens]).toEqual(['self_eval', 0])
})
test('evidence_source both: Haiku and H2', async ($, on) => {
  const t = await traceOf($, on, { selfEval: true, model: review(`${A}, ${B}`) }, 'applied ' + A)
  expect(t.evidence_source).toBe('both')
})
test('evidence_source control_arm: the control arm injected nothing; precedence over the (empty) evidence', async ($, on) => {
  const ctrl = { [`${ROOT}/${RENDER_CONTROL_PCT_FILE}`]: JSON.stringify({ pct: 100, at: 1_800_000_000 }) }
  const t = await traceOf($, on, { files: ctrl }, 'applied everything from the patterns ' + A)
  expect([t.render_variant, t.evidence_source, t.applied_log_ids]).toEqual(['control', 'control_arm', []])
})
test('evidence_source none: a fork trace (no own search, [] ids)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  await spawn($, 'fork this context and fix the parser module now', { fork: true, subagentType: 'fork' })
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'fork done', 'agent-1')
  const t = h.trace(h.learns()[0]!)
  expect([t.applied_log_ids, t.evidence_source]).toEqual([[], 'none'])
})
test('evidence_source travels unchanged into the ACE_TRACE_SINK file', async ($, on) => {
  const SINK = '/home/u/sink'
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: 'file:' + SINK } })
  await mainTask($, h)
  await done($, 'applied ' + A)
  const f = [...h.files.keys()].find(k => k.startsWith(SINK + '/'))!
  expect(JSON.parse(h.files.get(f)!).evidence_source).toBe('token')
})

const base = { userPrompt: 'x', tools: [], answer: '', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 't', effort: 'normal' }
test('buildTrace: evidence_source defaults to none, never omitted; control wins; mapping model->self_eval, tokens->token', () => {
  expect(buildTrace(base).trace.evidence_source).toBe('none')
  for (const [src, want] of [['none', 'none'], ['model', 'self_eval'], ['tokens', 'token'], ['both', 'both']] as const)
    expect(buildTrace({ ...base, evidenceSource: src }).trace.evidence_source).toBe(want)
  expect(buildTrace({ ...base, evidenceSource: 'both', renderVariant: 'control' }).trace.evidence_source).toBe('control_arm')
  expect(buildTrace({ ...base, evidenceSource: 'tokens', renderVariant: 'budget' }).trace.evidence_source).toBe('token')
})
test('buildTrace: the ACE_TRACE_FULL_STEPS=0 (8.3.0) shape carries evidence_source too', () => {
  expect(buildTrace({ ...base, evidenceSource: 'model', fullSteps: false }).trace.evidence_source).toBe('self_eval')
})
test('backfill items: evidence_source none (ids cleared), session and git alike', () => {
  const key = 'bootstrap:' + 'a'.repeat(32)
  const git = toItem({ key, task: 'Fix crash', steps: ['src/p.ts'], endMs: 1_800_000_000_000, success: true }, 'git')!
  const ses = toItem({ key, endMs: 1_800_000_000_000, trace: { ...buildTrace({ ...base, evidenceSource: 'both' }).trace } }, 'session')!
  expect([git.trace.evidence_source, ses.trace.evidence_source]).toEqual(['none', 'none'])
})
