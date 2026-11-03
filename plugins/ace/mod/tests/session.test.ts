// ACE mod suite, data dir, mod-active marker, coexistence with the Python chain, session.end. Harness: ./helpers.ts.
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

// ---------- data dir, marker, coexistence ----------


test('data dir derives from $.plugin.root (<name>-inline here), never from CLAUDE_PLUGIN_DATA', async ($, on) => {
  const h = host(on, { env: { CLAUDE_PLUGIN_DATA: '/elsewhere/other-plugin' } })
  await submit($)
  expect(h.state()).toBeDefined()
  expect([...h.files.keys()].some(k => k.startsWith('/elsewhere'))).toBe(false)
  expect(h.envAsked.includes('CLAUDE_PLUGIN_DATA')).toBe(false)
})

test('session.start writes the mod-active marker in the session dir', async ($, on) => {
  const h = host(on)
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  expect(h.files.has(`${SDIR}/mod-active`)).toBe(true)
})

test('every prompt.submit (human or machine) refreshes the mod-active marker', async ($, on) => {
  const h = host(on)
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  const t0 = h.mtime.get(`${SDIR}/mod-active`)!
  h.advance(5 * MIN)
  await submit($, '<task-notification><task-id>x</task-id> done</task-notification>')
  const t1 = h.mtime.get(`${SDIR}/mod-active`)!
  expect(t1 > t0).toBe(true)
  h.advance(5 * MIN)
  await submit($)
  expect(h.mtime.get(`${SDIR}/mod-active`)! > t1).toBe(true)
})

// ---------- the marker outlives long turns ----------


test('mod-active: tool.call, agent.spawn and the Stop events write it at once (handoff); turn.start is throttled to 60 s', async ($, on) => {
  const h = host(on)
  const M = `${SDIR}/mod-active`
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  const handoff = async (act: () => Promise<unknown>) => {
    const before = h.mtime.get(M)!
    h.advance(10_000); await act()
    expect(h.mtime.get(M)! > before).toBe(true)  // the Python hook of this event runs right after: never stale
  }
  await handoff(() => $.tool.call({ tool: 'Bash', command: 'ls' } as any))
  await handoff(() => spawn($, 'fork please', { fork: true }))
  await handoff(() => ($ as any).classic.Stop({ session_id: SID }))
  await handoff(() => ($ as any).classic.SubagentStop({ session_id: SID, agent_id: 'a' }))
  const before = h.mtime.get(M)!
  h.advance(10_000); await $.turn.start({ text: '', turnId: 'c1' } as any)
  expect(h.mtime.get(M)).toBe(before)  // inside the throttle window
  h.advance(3 * MIN); await $.turn.start({ text: '', turnId: 'c2' } as any)
  expect(h.mtime.get(M)! > before).toBe(true)
})

// ---------- session.end ----------


test('session.end removes the session dir unless a learn lock younger than 10 min exists', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  h.put(`${SDIR}/learn-inflight-agent-9.lock`, '')
  await $.session.end({ reason: 'other', sessionId: SID, resume: {} } as any)
  expect(h.files.has(`${SDIR}/patterns-used-main.json`)).toBe(true)
  h.advance(11 * MIN)
  await $.session.end({ reason: 'other', sessionId: SID, resume: {} } as any)
  expect([...h.files.keys()].some(k => k.startsWith(SDIR + '/'))).toBe(false)
})

// Team/Enterprise or managed-settings seats: the built-in guard filters the mod's classic.* hooks. The mod then must not
// learn (the Python Stop does, with the background_tasks deferral); a classic event brings the learn back.
test('classic.* hooks filtered: turn.complete does not learn; the first classic.UserPromptSubmit re-enables it', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), noClassic: true })
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(0)
  await ($ as any).classic.UserPromptSubmit({ prompt: HUMAN, session_id: SID })
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(1)
})

test('prompt.submit leaves its title in mod-title (the Python UPS sets it where the guard filters classic.*)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), noClassic: true })
  await submit($)
  expect(/^ACE( low| ready)? · /.test(h.files.get(`${SDIR}/mod-title`) ?? '')).toBe(true)
  await submit($, HUMAN, 'composer')
  expect(h.files.has(`${SDIR}/mod-title`)).toBe(true)
})

test('§31 a subagent credits ids named in its SubagentHandback report and in its closing message', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const st8 = JSON.parse(G.state_main_8), [a, b] = Object.keys(st8.retrieval_log_ids)
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'SubagentHandback', message: '## Findings: applied ' + a, agentId: 'agent-1' } as any)
  await done($, 'closing: also ' + b, 'agent-1')
  const t = h.trace(h.learns()[0]!)
  expect(t.applied_log_ids).toEqual([a, b].filter(id => t.playbook_used.includes(id)).map(id => st8.retrieval_log_ids[id]))
  expect(t.applied_log_ids.length).toBe(2)
})

test('status line: what the model got, arm, top domains; one line', async () => {
  expect(statusLine({ injected: 11, returned: 100, cohort: 'budget', domains: ['a-b', 'c', 'd', 'e'] })).toBe('ACE · 11 of 100 patterns · budget · a-b, c +2')
  expect(statusLine({ injected: 8, returned: 8, cohort: 'full', domains: ['x'] })).toBe('ACE · 8 patterns · full · x')
  expect(statusLine({ injected: 1, returned: 1, cohort: 'budget', domains: [] })).toBe('ACE · 1 pattern · budget')
  expect(statusLine({ injected: 0, returned: 0, cohort: 'budget', domains: [] })).toBe('ACE · no patterns for this prompt')
})

test('learn gate: a state-changing tool, or >= 3 tool calls of any kind (research tasks learn too)', async () => {
  const r = (tool: string) => ({ tool, action: '', result: '', failed: false, start_ms: 0, end_ms: 0 })
  expect(hasSubstantialWork([r('Read'), r('Grep')])).toBe(false)
  expect(hasSubstantialWork([r('Read'), r('Grep'), r('WebFetch')])).toBe(true)
  expect(hasSubstantialWork([r('Bash')])).toBe(true)
  expect(hasSubstantialWork([])).toBe(false)
  for (const t of ['Agent', 'Workflow', 'Task', 'Skill']) expect(hasSubstantialWork([r(t)])).toBe(true)  // fix 3: orchestrating tasks
  expect(hasSubstantialWork([r('TaskList'), r('Read')])).toBe(false)
})
