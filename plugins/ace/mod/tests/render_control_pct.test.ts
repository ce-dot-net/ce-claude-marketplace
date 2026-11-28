// 8.4.3: trace.render_control_pct is the control share that applied WHEN the patterns were rendered (frozen in the task state next to
// render_variant), not the one that applies at learn time. A path without a render keeps no label; a legacy state without the stored
// value falls back to the learn-time value (as in 8.4.2).
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import { SDIR, done, host, mainTask, spawn } from './helpers.ts'

// every search answer carries the current server control share
const answers = (pct: { v: number }) => () => { const o = JSON.parse(S8); o.render_control_pct = pct.v; return { stdout: JSON.stringify(o) } }

test('main task: rendered under control share 0, the server says 30 before the learn -> the trace keeps 0; the state stores it', async ($, on) => {
  const pct = { v: 0 }
  const h = host(on, { defaultArm: true, search: answers(pct) })
  await mainTask($, h)                                                        // rendered at 0
  pct.v = 30                                                                  // a later domain-shift search stores 30
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  expect(h.state()!.render_control_pct).toBe(0)
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect([t.render_variant !== undefined, t.render_control_pct]).toEqual([true, 0])
})
test('main task: the share did not change -> the same value as before (30)', async ($, on) => {
  const h = host(on, { defaultArm: true, search: answers({ v: 30 }) })
  await mainTask($, h); await done($)
  expect(h.trace(h.learns()[0]!).render_control_pct).toBe(30)
})
test('subagent: rendered at spawn under 0, the share changes to 30 before its learn -> its trace keeps 0', async ($, on) => {
  const pct = { v: 0 }
  const h = host(on, { defaultArm: true, search: answers(pct) })
  await mainTask($, h)
  await spawn($, 'a subagent task that is long enough to count as one')   // rendered at 0
  pct.v = 30
  await $.turn.start({ text: 'a subagent task that is long enough to count as one', turnId: 'w1', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)   // a fresh search stores 30
  await $.tool.call({ tool: 'Edit', file_path: '/proj/y.py', old_string: 'a', new_string: 'b', agentId: 'agent-1' } as any)
  expect(h.state('agent-1')!.render_control_pct).toBe(0)
  await done($, 'sub done', 'agent-1')
  expect(h.trace(h.learns()[0]!).render_control_pct).toBe(0)
})
test('a legacy state without render_control_pct -> the learn-time value (8.4.2)', async ($, on) => {
  const h = host(on, { defaultArm: true, search: answers({ v: 30 }) })
  await mainTask($, h)
  const st = h.state()!; delete st.render_control_pct
  h.put(`${SDIR}/patterns-used-main.json`, JSON.stringify(st))
  await done($)
  expect(h.trace(h.learns()[0]!).render_control_pct).toBe(30)
})
