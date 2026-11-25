// ACE mod suite, 8.2.7: the trace carries the used ids per source as lists (ids only, <= 50, injected order) next to
// the counters; applied_log_ids and its cap of 20 are unchanged. Harness: ./helpers.ts.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import S100 from './fixtures/search_100.ts'
import G from './fixtures/golden.ts'
import { buildTrace } from '../lib/trace.ts'
import { done, host, mainTask, settle, submit } from './helpers.ts'

test('8.2.7 lists: Haiku ids (whitelisted) and token ids each in their own list; one id may stand in both', async ($, on) => {
  const st8 = JSON.parse(G.state_main_8), [a, b] = Object.keys(st8.retrieval_log_ids)
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true,
    model: () => ({ isAnswered: true, text: `ACE_REVIEW: 70% | 4m saved | ok\nACE_USED: ${b}, ${a}, ctx-9999999999-zzzz`, usage: {} }) })
  await mainTask($, h)
  await done($, 'applied ' + a)  // a by its id in the answer: token source too
  await settle(h)
  const t = h.trace(h.learns()[0]!), order = st8.pattern_ids.filter((id: string) => id === a || id === b)
  expect(t.used_ids_model_list).toEqual(order)
  expect(t.used_ids_tokens_list).toEqual([a])
  expect([t.used_ids_model, t.used_ids_tokens]).toEqual([2, 1])
})

test('8.2.7 lists: empty lists when nothing was used (never omitted)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true })  // default fake: api-error
  await mainTask($, h)
  await done($)
  await settle(h)
  const t = h.trace(h.learns()[0]!)
  expect([t.used_ids_model_list, t.used_ids_tokens_list, t.applied_log_ids]).toEqual([[], [], []])
})

test('8.2.7 lists: at most 50 ids each, injected order; applied_log_ids still 20', async ($, on) => {
  let model: string[] = []
  const h = host(on, { search: () => ({ stdout: S100 }), selfEval: true,
    model: () => ({ isAnswered: true, text: `ACE_REVIEW: 70% | 4m saved | ok\nACE_USED: ${model.join(', ')}`, usage: {} }) })
  await submit($)
  const st = h.state()!, ids: string[] = st.pattern_ids
  model = [...ids.slice(0, 70)].reverse()
  await $.turn.start({ text: 'go', turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($, 'used ' + ids.slice(10, 70).join(' '))
  await settle(h)
  const t = h.trace(h.learns()[0]!)
  expect(t.used_ids_model_list).toEqual(ids.slice(0, 50))
  expect(t.used_ids_tokens_list).toEqual(ids.slice(10, 60))
  expect(t.applied_log_ids.length).toBe(20)
})

test('8.2.7 buildTrace: lists default to [] and are cut to 50', () => {
  const base = { userPrompt: 'x', tools: [], answer: '', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 't', effort: 'normal' }
  const t0 = buildTrace(base).trace
  expect([t0.used_ids_model_list, t0.used_ids_tokens_list]).toEqual([[], []])
  const many = Array.from({ length: 60 }, (_, k) => `id-${k}`)
  const t1 = buildTrace({ ...base, usedIds: { used_ids_model: 60, used_ids_tokens: 0, used_ids_model_list: many, used_ids_tokens_list: [] } }).trace
  expect(t1.used_ids_model_list).toEqual(many.slice(0, 50))
})
