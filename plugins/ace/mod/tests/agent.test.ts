// ACE mod suite, agent.spawn: own ACE session per subagent, and the §32 local reuse cache. Harness: ./helpers.ts.
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

// ---------- agent.spawn: §12 own ACE session per subagent ----------


test('agent.spawn: own search, FRESH uuid4 pin per subagent (never the parent pin), parent_task_id, all patterns appended', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  const main = h.pin(h.searches()[0]!)!
  const p1 = 'review the domain shift python port for parity bugs'
  const r1: any = await spawn($, p1)
  const r2: any = await spawn($, 'audit the learn trace builder for missing fields')
  expect(h.searches().length).toBe(3)
  const s1 = h.pin(h.searches()[1]!)!, s2 = h.pin(h.searches()[2]!)!
  expect(UUID4.test(s1) && UUID4.test(s2)).toBe(true)
  expect(s1).not.toBe(main)
  expect(s2).not.toBe(main)
  expect(s1).not.toBe(s2)
  expect(h.flag(h.searches()[1]!.argv, '--session-id')).toBe(s1)  // SubagentStart: the subagent's own task session
  expect(h.searches()[1]!.stdin).toBe(p1)
  expect(h.searches()[1]!.timeoutMs! <= 25000).toBe(true)
  expect(r1.seenPrompt).toBe(p1 + '\n\n' + G.full_sub_8)
  expect(r2.seenPrompt.includes('<ace-patterns-subagent shown="8" of="8"')).toBe(true)
  const st = h.state('agent-1')!
  expect(st.task_session_id).toBe(s1)
  expect(st.parent_task_id).toBe(main)
  expect(st.hook_event_name).toBe('SubagentStart')
  expect(st.user_prompt).toBe(p1)
  expect(h.state('agent-2')!.task_session_id).toBe(s2)
})

test('agent.spawn from a Workflow: real prompt searched and rewritten, workflow run id logged', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const p = 'implement the TS renderer and make the parity harness pass'
  const r: any = await spawn($, p, { workflow: { runId: 'wf_abc', agentIndex: 1 } })
  expect(h.searches().length).toBe(1)
  expect(r.seenPrompt.startsWith(p + '\n\n<ace-patterns-subagent shown="8" of="8"')).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'search' && x.hook === 'SubagentStart')!.workflow).toBe('wf_abc')
})

test('Workflow placeholder: the first turn.start text differs -> fresh pin, no uninjected credit, the real text searched at the first tool call', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, PLACEHOLDER, { workflow: { runId: 'wf_x', agentIndex: 2 } })
  const pinned = h.state('agent-1')!.task_session_id
  await $.turn.start({ text: REAL, turnId: 'w1', agentId: 'agent-1' } as any)
  const st = h.state('agent-1')!
  expect(st.pattern_ids).toEqual([])
  expect(st.retrieval_log_ids).toEqual({})
  expect(st.retrieval_id).toBe(null)
  expect(st.user_prompt).toBe(REAL)
  expect(UUID4.test(st.task_session_id)).toBe(true)
  expect(st.task_session_id).not.toBe(pinned)
  expect(h.rows().some((x: any) => x.event === 'workflow_placeholder' && x.agent_id === 'agent-1')).toBe(true)
  const r: any = await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'agent-1' } as any)
  expect(h.searches().length).toBe(2)
  const late = h.searches()[1]!
  expect(late.stdin).toBe(REAL)
  expect(h.pin(late)).toBe(st.task_session_id)
  expect(r.context[0].startsWith('<ace-patterns-subagent shown="8" of="8"')).toBe(true)
  expect(h.state('agent-1')!.pattern_ids.length > 0).toBe(true)
  expect(h.state('agent-1')!.task_session_id).toBe(st.task_session_id)
  await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'agent-1' } as any)
  expect(h.searches().length).toBe(2)  // once
})

test('Workflow placeholder: a text seen as a placeholder burns no second search at agent.spawn', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, PLACEHOLDER, { workflow: { runId: 'wf_x', agentIndex: 1 } })
  await $.turn.start({ text: REAL, turnId: 'w1', agentId: 'agent-1' } as any)
  await spawn($, PLACEHOLDER, { workflow: { runId: 'wf_x', agentIndex: 2 } })
  expect(h.searches().length).toBe(1)
  expect(h.state('agent-2')!.task_session_id).toBeDefined()
})

test('Workflow: an empty first turn.start text (the docs allow it) keeps the credit', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'implement the TS renderer and make the parity harness pass', { workflow: { runId: 'wf_x', agentIndex: 1 } })
  const before = h.state('agent-1')!
  await $.turn.start({ text: '', turnId: 'w1', agentId: 'agent-1' } as any)
  expect(h.state('agent-1')!.pattern_ids).toEqual(before.pattern_ids)
  expect(h.state('agent-1')!.task_session_id).toBe(before.task_session_id)
})

test('an agent that starts before next(e) settles keeps its records and merges; a placeholder is still detected', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), early: async (id) => {
    await $.turn.start({ text: REAL, turnId: 'w1', agentId: id } as any)
    await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b', agentId: id } as any)
  } })
  await spawn($, PLACEHOLDER, { workflow: { runId: 'wf_x', agentIndex: 1 } })
  expect(h.state('agent-1')!.user_prompt).toBe(REAL)
  expect(h.state('agent-1')!.pattern_ids).toEqual([])
  expect(h.rows().some((x: any) => x.event === 'workflow_placeholder')).toBe(true)
  await done($, 'ok', 'agent-1')
  expect(h.trace(h.learns()[0]!).trajectory.map((t: any) => t.tool)).toEqual(['Edit'])
})

test('agent.spawn resume with live state / fork: no new search, no second pin', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'review the domain shift python port for parity bugs')
  const pinned = h.state('agent-1')!.task_session_id
  await spawn($, 'continue', { resume: { agentId: 'agent-1' } })
  await spawn($, 'fork this context please now', { fork: true, subagentType: 'fork' })
  expect(h.searches().length).toBe(1)
  expect(h.state('agent-1')!.task_session_id).toBe(pinned)
})

test('§16 P7 fork: own uuid4 pin + state (parent_task_id), no search / inject, search_skipped; it learns with its own pin', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  const main = h.state()!.task_session_id
  const r: any = await spawn($, 'fork this context and fix the parser module now', { fork: true, subagentType: 'fork' })
  expect(h.searches().length).toBe(1)
  expect(r.seenPrompt).toBe('fork this context and fix the parser module now')
  const st = h.state('agent-1')!
  expect(UUID4.test(st.task_session_id)).toBe(true)
  expect(st.task_session_id).not.toBe(main)
  expect(st.parent_task_id).toBe(main)
  expect(h.rows().some((x: any) => x.event === 'search_skipped' && x.reason === 'fork_inherits_context')).toBe(true)
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'fork done', 'agent-1')
  expect(h.trace(h.learns()[0]!).session_id).toBe(st.task_session_id)
})

test('§16 P7 ACE_SUBAGENT_INJECT_FORKS=1 restores the fork search', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_SUBAGENT_INJECT_FORKS: '1' } })
  await spawn($, 'fork this context and fix the parser module now', { fork: true, subagentType: 'fork' })
  expect(h.searches().length).toBe(1)
})

test('§16 P1 subagent summary = the LAST SubagentHandback message (cap 4000), else the closing answer', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'SubagentHandback', message: 'first draft', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'SubagentHandback', message: '## Findings\n' + 'x'.repeat(6000), agentId: 'agent-1' } as any)
  await done($, 'Now qdrant_search.', 'agent-1')
  const sum = h.trace(h.learns()[0]!).result.summary
  expect(sum.startsWith('## Findings')).toBe(true)
  expect(sum.length).toBe(4000)
})

test('§16 P2 main Stop with a running subagent/workflow defers the learn; the task-notification turn then learns it', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  const tsid = h.state()!.task_session_id
  await ($ as any).classic.Stop({ session_id: SID, background_tasks: [{ type: 'monitor', status: 'running' }, { type: 'subagent', status: 'running' }] })
  await done($, 'waiting for the agent')
  expect(h.learns().length).toBe(0)
  expect(h.state()!.task_session_id).toBe(tsid)
  expect(h.rows().some((x: any) => x.event === 'learn_deferred')).toBe(true)
  await submit($, '<task-notification>agent finished</task-notification>', 'task-notification')
  await $.turn.start({ text: '<task-notification>agent finished</task-notification>', turnId: 't2' } as any)
  await $.tool.call({ tool: 'Bash', command: 'git diff' } as any)
  await ($ as any).classic.Stop({ session_id: SID, background_tasks: [{ type: 'monitor', status: 'running' }] })
  await $.turn.complete({ answer: 'all merged', durationMs: 5, isAborted: false, turnId: 't2', reason: 'answer' } as any)
  expect(h.learns().length).toBe(1)
  const t = h.trace(h.learns()[0]!)
  expect(t.task).toBe('User request: ' + HUMAN)
  expect(t.session_id).toBe(tsid)
  expect(t.result.summary).toBe('all merged')
  expect(t.trajectory.length).toBe(3)
})

test('§16 P2 a monitor/shell alone never defers', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await ($ as any).classic.Stop({ session_id: SID, background_tasks: [{ type: 'monitor', status: 'running' }, { type: 'shell', status: 'running' }] })
  await done($)
  expect(h.learns().length).toBe(1)
})

test('an agent resumed after its learn: fresh pin, resume prompt searched at the first tool call, learned again', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'review the domain shift python port for parity bugs')
  const first = h.state('agent-1')!.task_session_id
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'first', 'agent-1')
  expect(h.learns().length).toBe(1)
  const resume = 'now also cover the workflow spawn path please'
  const r0: any = await spawn($, resume, { resume: { agentId: 'agent-1' } })
  expect(r0.seenPrompt).toBe(resume)  // a rewrite of a resume is not applied: the patterns go out at the first tool call
  const st = h.state('agent-1')!
  expect(UUID4.test(st.task_session_id)).toBe(true)
  expect(st.task_session_id).not.toBe(first)
  expect(st.user_prompt).toBe(resume)
  expect(st.agent_type).toBe('general-purpose')
  const r: any = await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'agent-1' } as any)
  expect(h.searches().length).toBe(2)
  expect(h.searches()[1]!.stdin).toBe(resume)
  expect(r.context[0].includes('ace-patterns-subagent')).toBe(true)
  await done($, 'second', 'agent-1')
  expect(h.learns().length).toBe(2)
  const t = h.trace(h.learns()[1]!)
  expect(t.session_id).toBe(st.task_session_id)
  expect(t.trajectory.map((x: any) => x.tool)).toEqual(['Bash'])
  expect(t.playbook_used.length > 0).toBe(true)
})

test('a resume with an empty prompt: no search but still anchored', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, '', { resume: { agentId: 'agent-7' }, description: 'continue the port work' })
  expect(UUID4.test(h.state('agent-7')!.task_session_id)).toBe(true)
  await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'agent-7' } as any)
  expect(h.searches().length).toBe(0)
  await done($, 'ok', 'agent-7')
  expect(h.learns().length).toBe(1)
})

test('a woken teammate (turn.start only, its state reaped): the message is the new task', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'review the domain shift python port for parity bugs', { isTeammate: true, name: 'scout' })
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'first', 'agent-1')
  const wake = 'scout, please look at the learn trace builder next'
  await $.turn.start({ text: wake, turnId: 'tb', agentId: 'agent-1' } as any)
  expect(h.state('agent-1')!.user_prompt).toBe(wake)
  await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'agent-1' } as any)
  expect(h.searches().length).toBe(2)
  await done($, 'second', 'agent-1')
  expect(h.learns().length).toBe(2)
})

test('a turn.start that lands while the spawn state is still being written is not a woken teammate: 1 search, 1 tsid, ids kept', async ($, on) => {
  let racing: Promise<unknown> | undefined, fired = false
  const h = host(on, { search: () => ({ stdout: S8 }), beforeWrite: async (path) => {
    if (fired || !path.endsWith('patterns-used-agent-1.json')) return
    fired = true
    racing = Promise.resolve($.turn.start({ text: 'review the domain shift python port for parity bugs', turnId: 'r1', agentId: 'agent-1' } as any))
    await new Promise(r => setTimeout(r, 20))  // the turn.start runs to its state read before the write lands
  } })
  await spawn($, 'review the domain shift python port for parity bugs')
  await racing
  expect(h.searches().length).toBe(1)
  const st = h.state('agent-1')!
  expect(st.task_session_id).toBe(h.pin(h.searches()[0]!)!)
  const want = JSON.parse(S8).similar_patterns.map((p: any) => p.id).filter((id: any) => /^[\w-]+$/.test(id ?? ''))
  expect(want.length > 0 && [...st.pattern_ids].sort().join()).toBe([...want].sort().join())
  await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'agent-1' } as any)
  expect(h.searches().length).toBe(1)  // no late search queued
})

// ---------- DESIGN §32: hybrid local reuse (domain-shift + agent.spawn) ----------

test('§32 domain shift: a different agent with the same query is served from the cache (no spawn), cache_hit logged', async ($, on) => {
  const h = host(on)
  await submit($)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  const r: any = await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)
  expect(dsSearches(h).length).toBe(1)
  expect(r.context[r.context.length - 1].startsWith('<ace-patterns-domain-shift domain="ace-cli">')).toBe(true)
  expect(h.rows().filter((x: any) => x.event === 'domain_shift').map((x: any) => x.cache_hit)).toEqual([false, true])
})

test('§32 domain shift: the same agent never gets the same entry twice (server again)', async ($, on) => {
  const h = host(on)
  await submit($)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  h.files.delete(`${SDIR}/domain-last-main.txt`)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  expect(dsSearches(h).length).toBe(2)
})

test('§32 domain shift: a stale (> 15 min) entry goes to the server', async ($, on) => {
  const h = host(on)
  await submit($)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  h.advance(16 * MIN)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)
  expect(dsSearches(h).length).toBe(2)
})

test('§32 domain shift: an empty server result is never cached or served', async ($, on) => {
  const h = host(on, { search: (argv) => ({ stdout: argv.includes('--top-k') ? JSON.stringify({ similar_patterns: [], count: 0 }) : S100 }) })
  await submit($)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)
  expect(dsSearches(h).length).toBe(2)
})

test('§32 domain shift: a different query goes to the server; ACE_LOCAL_REUSE=subagent turns domain reuse off', async ($, on) => {
  const h = host(on, { env: { ACE_LOCAL_REUSE: 'subagent' } })
  await submit($)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md' } as any)
  await $.tool.call({ tool: 'Read', file_path: '/proj/ace-cli/notes.md', agentId: 'agent-1' } as any)
  expect(dsSearches(h).length).toBe(2)
})

test('§32 agent.spawn: the same task text for a new agent is served from the cache, keeping the cached retrieval_id', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const p1 = 'review the domain shift python port for parity bugs'
  await spawn($, p1)
  const r2: any = await spawn($, p1)
  expect(h.searches().length).toBe(1)
  expect(r2.seenPrompt).toBe(p1 + '\n\n' + G.full_sub_8)
  expect(h.state('agent-2')!.retrieval_id).toBe(JSON.parse(S8).retrieval_id)
  expect(h.rows().filter((x: any) => x.hook === 'SubagentStart').map((x: any) => x.cache_hit)).toEqual([false, true])
})

test('§32 agent.spawn: ACE_LOCAL_REUSE=domain and a different task text both go to the server', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_LOCAL_REUSE: 'domain' } })
  await spawn($, 'review the domain shift python port for parity bugs')
  await spawn($, 'review the domain shift python port for parity bugs')
  expect(h.searches().length).toBe(2)
})

test('§32 agent.spawn: a different task text is a different key (server)', async ($, on) => {
  const h2 = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'audit the learn trace builder for missing fields')
  await spawn($, 'audit the learn trace builder for other things')
  expect(h2.searches().length).toBe(2)
})
