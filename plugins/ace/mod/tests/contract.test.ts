// ACE mod suite, §31 final client contract (render_variant, conversation_id, used-only applied ids, dedupe). Harness: ./helpers.ts.
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

// ---------- §31 final client contract (render_variant, conversation_id, used-only applied ids, dedupe) ----------


test('§31 default env (50/50): sess-1 lands in the budget half (bucket 66), labelled budget, <= 9,500 chars', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S100 }), defaultArm: true })
  const r: any = await submit($)
  expect(h.state()!.render_variant).toBe('budget')
  expect(r.context[0].length <= 9500).toBe(true)
})

test('item H2: used = id in the answer, or >= 2 distinctive tokens in THIS task\'s tool inputs (shared fixture, Python parity)', async () => {
  for (const c of USED_CASES as any[]) expect([c.name, usedPatternIds(c.ids, c.contents, c.message, toolHaystack(c.tool_inputs))]).toEqual([c.name, c.expected])
})

test('item H2: applied_log_ids = the evidenced ids (tool tokens or id literal), for full too; the answer text alone is no evidence', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const st8 = JSON.parse(G.state_main_8)
  const [a, b] = Object.keys(st8.retrieval_log_ids)
  const unique = 'Run `npm ci --ignore-scripts` after touching plugin-local/cli.js so the binding builds.'
  await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Bash', command: 'npm ci --ignore-scripts' }])
  const path = `${SDIR}/patterns-used-main.json`, st = JSON.parse(h.files.get(path)!)  // the fixture contents share a filler
  st.pattern_contents[b] = unique
  h.put(path, JSON.stringify(st))
  await done($, `Following ${a}; and ${unique.slice(10, 55)} was applied.`)
  const L = h.learns()[0]!, t = h.trace(L)
  expect(t.render_variant).toBe('full')
  expect(t.applied_log_ids).toEqual([st8.retrieval_log_ids[a], st8.retrieval_log_ids[b]])
  expect(h.flag(h.learnArgv(L), '--applied-log-ids')).toBe(`${st8.retrieval_log_ids[a]},${st8.retrieval_log_ids[b]}`)
  expect(t.playbook_used).toEqual(st8.pattern_ids)
  expect(t.retrieval_id).toBe(st8.retrieval_id)
  expect(JSON.stringify(t).includes('npm ci --ignore-scripts')).toBe(true)  // the action summary, as before
  expect(t.trajectory.every((x: any) => x.hay === undefined)).toBe(true)
})

test('§31 a 39-char fragment or an unrelated answer credits nothing', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const st8 = JSON.parse(G.state_main_8)
  await mainTask($, h)
  await done($, 'x ' + st8.pattern_contents[Object.keys(st8.retrieval_log_ids)[0]].slice(-39) + ' y')
  const L = h.learns()[0]!
  expect(h.learnArgv(L).includes('--applied-log-ids')).toBe(false)
  expect(h.trace(L).applied_log_ids).toEqual([])  // server contract: [] when nothing was used
})

test('§31 compact/control are no server label: the trace falls back to the conversation arm (this host pins full)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  const path = `${SDIR}/patterns-used-main.json`
  h.put(path, h.files.get(path)!.replace('"render_variant": "full"', '"render_variant": " COMPACT "'))
  await done($)
  expect(h.trace(h.learns()[0]!).render_variant).toBe('full')
})

test('§31 nothing rendered (search failed): no label in state, the trace carries the conversation arm (server request)', async ($, on) => {
  const h = host(on, { search: () => ({ exitCode: 1, stderr: 'boom' }) })
  await mainTask($, h)
  expect(h.state()!.render_variant).toBeUndefined()
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect(t.render_variant).toBe('full')
  expect(t.conversation_id).toBe(SID)
})

test('§31 dedupe under full: later prompts inject only new ids; a compaction (record removed) injects all again', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const r1: any = await submit($)
  expect(shownOf(r1.context[0])).toBe(8)
  const r2: any = await submit($, HUMAN + ' again')
  expect(shownOf(r2.context[0])).toBe(2)  // only the two the fixture gives no valid id (never tracked, never credited)
  expect(h.state()!.pattern_ids).toEqual([])
  expect(h.state()!.render_variant).toBe('full')
  h.files.delete(`${SDIR}/full-injected.json`)  // what the SessionStart compact hook does
  const r3: any = await submit($, HUMAN + ' after compact')
  expect(shownOf(r3.context[0])).toBe(8)
})

test('item 3: full arm re-inject copy = budget render of the FULL response, independent of the dedupe', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  expect(h.state()!.rendered_context).toBe(G.budget_main_8)
  const r2: any = await submit($, HUMAN + ' again')  // all tracked ids already seen: almost nothing injected
  expect(shownOf(r2.context[0])).toBe(2)
  expect(h.state()!.rendered_context).toBe(G.budget_main_8)
  expect(G.budget_main_8.length <= 9500).toBe(true)
  expect(shownOf(G.budget_main_8)).toBe(8)
})

test('item A: after a main compaction prompt.compose carries the task patterns as section ace:patterns until the next prompt', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  const before: any = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] } as any)
  expect((before.sections ?? []).some((x: any) => x.id === 'ace:patterns')).toBe(false)
  await $.session.compact({ trigger: 'auto', messages: [{ role: 'user', text: 'hi', toolUses: [] }] } as any)
  expect(h.files.has(`${SDIR}/mod-compact`)).toBe(true)  // the Python SessionStart(compact) re-inject steps aside
  expect(h.files.has(`${SDIR}/full-injected.json`)).toBe(false)  // §31 dedupe starts over, as the Python hook does
  const after: any = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] } as any)
  const sec = after.sections.find((x: any) => x.id === 'ace:patterns')
  expect(sec.scope).toBe('session')
  expect(sec.text).toBe(G.budget_main_8)
  await submit($, HUMAN + ' next')
  const later: any = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] } as any)
  expect((later.sections ?? []).some((x: any) => x.id === 'ace:patterns')).toBe(false)
  expect(h.files.has(`${SDIR}/mod-compact`)).toBe(false)
})

test('fix 1: mod-compact exists BEFORE next() (the Python SessionStart(compact) inside it stays silent); a skipped or failed compaction removes it', async ($, on) => {
  const MARK = `${SDIR}/mod-compact`, seen: boolean[] = []
  let answer: any = { messages: [{ role: 'user', text: 'summary', toolUses: [] }] }
  const h = host(on, { search: () => ({ stdout: S8 }), compact: files => { seen.push(files.has(MARK)); if (answer === 'throw') throw new Error('compact failed'); return answer } })
  await mainTask($, h)
  const msg = { trigger: 'auto', messages: [{ role: 'user', text: 'hi', toolUses: [] }] }
  await $.session.compact(msg as any)
  expect(seen).toEqual([true])
  expect(h.files.has(MARK)).toBe(true)
  await submit($, HUMAN + ' next')
  answer = { skip: 'nothing to compact' }
  await $.session.compact(msg as any)
  expect(seen[1]).toBe(true)
  expect(h.files.has(MARK)).toBe(false)  // no compaction happened: a later real one must not be silenced
  answer = 'throw'
  let threw = false
  try { await $.session.compact(msg as any) } catch { threw = true }
  expect(threw).toBe(true)
  expect(h.files.has(MARK)).toBe(false)
  const after: any = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] } as any)
  expect((after.sections ?? []).some((x: any) => x.id === 'ace:patterns')).toBe(false)
})

test('item A: a finished task still survives compaction (rendered-main.txt); subagent and precompute compactions do nothing', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  await $.session.compact({ trigger: 'precompute', messages: [{ role: 'user', text: 'hi', toolUses: [] }] } as any)
  await $.session.compact({ trigger: 'auto', messages: [{ role: 'user', text: 'hi', toolUses: [] }], agentId: 'agent-1' } as any)
  expect(h.files.has(`${SDIR}/mod-compact`)).toBe(false)
  await $.session.compact({ trigger: 'manual', messages: [{ role: 'user', text: 'hi', toolUses: [] }] } as any)
  const after: any = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] } as any)
  expect(after.sections.find((x: any) => x.id === 'ace:patterns').text).toBe(G.budget_main_8)
})

test('§31 budget never dedupes (it re-ranks the top-N every prompt)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), defaultArm: true })
  await submit($)
  const r2: any = await submit($, HUMAN + ' again')
  expect(shownOf(r2.context[0])).toBe(8)
  expect(h.files.has(`${SDIR}/full-injected.json`)).toBe(false)
})

test('§31 a subagent trace carries the conversation id (inherited), its own pin', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.turn.start({ text: 'review the domain shift python port for parity bugs', turnId: 'ta', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/y.py', old_string: 'a', new_string: 'b', agentId: 'agent-1' } as any)
  await done($, 'ok', 'agent-1')
  const t = h.trace(h.learns()[0]!)
  expect(t.conversation_id).toBe(SID)
  expect(t.session_id).toBe(h.pin(h.searches()[1]!))
})

test('§28 the arm buckets on the CC session id (bucket 66 here), CONTROL=70: every task gets control', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_AB_CONTROL_PCT: '70' } })
  for (let i = 0; i < 8; i++) {
    await submit($, HUMAN + ' round ' + i)
    expect(h.state()!.render_variant).toBe('control')
  }
  expect(new Set(h.searches().map(h.pin)).size).toBe(8)  // the pin stays per task (§12)
})

test('§28 the arm buckets on the CC session id (bucket 66 here), CONTROL=60: every task gets full', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_AB_CONTROL_PCT: '60' } })
  for (let i = 0; i < 8; i++) {
    await submit($, HUMAN + ' round ' + i)
    expect(h.state()!.render_variant).toBe('full')
  }
  expect(new Set(h.searches().map(h.pin)).size).toBe(8)  // the pin stays per task (§12)
})

test('§28 a subagent inherits the conversation arm and stores it', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_AB_CONTROL_PCT: '70' } })
  await submit($)
  await spawn($, 'review the domain shift python port for parity bugs')
  expect(h.state('agent-1')!.render_variant).toBe('control')
  expect(h.state('agent-1')!.task_session_id).not.toBe(h.state()!.task_session_id)
})

test('trace_truncate parity: > 50 steps → truncation marker first + metadata.trace_truncated', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 59; i++) tools.push({ tool: 'Bash', command: 'echo ' + i })
  await mainTask($, h, tools)
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect(t.trajectory[0]._truncation_marker).toBe(true)
  expect(t.trajectory[0].original_length).toBe(60)
  expect(t.metadata.trace_truncated).toBe(true)
})

test('learn launcher carries the execution metrics rows for both outcomes (learning_sent true/false)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  const rowsIn = h.learns()[0]!.argv.flatMap(a => { try { const o = JSON.parse(a); return o && o.event === 'execution' ? [o] : [] } catch { return [] } })
  expect(rowsIn.map((r: any) => r.learning_sent).sort()).toEqual([false, true])
  for (const r of rowsIn) {
    expect(r.hook).toBe('Stop')
    expect(r.session_id).toBe(SID)
    expect(r.patterns_used_count).toBe(JSON.parse(G.state_main_8).pattern_ids.length)
    expect(r.tools_executed).toBe(2)
  }
})

test('v8.0.1 learn launcher carries the learn_retry base row (CC session, conversation, task session, hook) and the cwd for the symlink-safe append', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  const argv = h.learns()[0]!.argv
  const base = argv.flatMap(a => { try { const o = JSON.parse(a); return o && o.event === 'learn_retry' ? [o] : [] } catch { return [] } })
  expect(base).toEqual([{ event: 'learn_retry', hook: 'Stop', session_id: SID, conversation_id: SID,
    task_session_id: h.pin(h.searches()[0]!), agent_id: null, source: 'mod' }])
  expect(argv[argv.findIndex(a => a.includes('"learn_retry"')) + 1]).toBe(CWD)
})

test('learn launcher: gets a 15 s spawn limit; the execution row names the real hook; a failed spawn logs learning_sent false and cleans up', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), learnExit: 1 })
  await mainTask($, h)
  await done($)
  const L = h.learns()[0]!
  expect(L.timeoutMs! >= 15_000).toBe(true)
  const row = h.rows().find((x: any) => x.event === 'execution')!
  expect(row.learning_sent).toBe(false)
  expect(row.hook).toBe('Stop')
  expect(h.files.has(`${SDIR}/learn-inflight-main.lock`)).toBe(false)
})

test('a subagent execution row says SubagentStop', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), learnExit: 1 })
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'x', 'agent-1')
  expect(h.rows().find((x: any) => x.event === 'execution')!.hook).toBe('SubagentStop')
})

test('turn.complete main: no eval request (item D), state reaped, rendered-main.txt kept for the compact re-inject', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  const rendered = h.state()!.rendered_context
  await done($)
  expect(h.files.has(EVAL_REQ)).toBe(false)
  expect(h.files.has(`${SDIR}/patterns-used-main.json`)).toBe(false)
  expect(h.files.get(`${SDIR}/rendered-main.txt`)).toBe(rendered)
})

test('turn.complete subagent: learn with the SUBAGENT pin, parent_task_id, own lock, effort from classic.SubagentStop', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  const main = h.pin(h.searches()[0]!)
  await spawn($, 'review the domain shift python port for parity bugs')
  const sub = h.state('agent-1')!.task_session_id
  await $.turn.start({ text: 'x', turnId: 'ta', agentId: 'agent-1' } as any)
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await ($ as any).classic.SubagentStop({ session_id: SID, agent_id: 'agent-1', effort: { level: 'high' } })
  await done($, 'sub done', 'agent-1')
  const L = h.learns()[0]!
  const t = h.trace(L)
  expect(t.session_id).toBe(sub)
  expect(t.parent_agent_id).toBe(main)  // §16 P3: server field name; parent_task_id stays local
  expect(t.parent_task_id).toBeUndefined()
  expect(t.agent_id).toBe('agent-1')
  expect(t.agent_type).toBe('general-purpose')
  expect(t.result.success).toBe(true)
  expect(t.effort_level).toBe('high')
  expect(t.effort_weight).toBe(1.5)
  expect(L.files.has(`${SDIR}/learn-inflight-agent-1.lock`)).toBe(true)
})

test('an aborted subagent never learns (no outcome to credit): state reaped', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: true, turnId: 'ta', reason: 'aborted', agentId: 'agent-1' } as any)
  expect(h.learns().length).toBe(0)
  expect(h.state('agent-1')).toBeUndefined()
})

for (const reason of ['error', 'refusal', 'aborted']) {
  test(`a main turn ended by ${reason} never learns: state reaped, the render kept, logged`, async ($, on) => {
    const h = host(on, { search: () => ({ stdout: S8 }) })
    await mainTask($, h)
    const rendered = h.state()!.rendered_context
    await $.turn.complete({ answer: '', durationMs: 1, isAborted: reason === 'aborted', turnId: 't1', reason } as any)
    expect(h.learns().length).toBe(0)
    expect(h.state()).toBeUndefined()
    expect(h.files.get(`${SDIR}/rendered-main.txt`)).toBe(rendered)
    expect(h.rows().some((x: any) => x.event === 'learn_skipped' && x.reason === `turn_${reason}`)).toBe(true)
  })
}

test('a subagent turn ended by an API error never learns', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'ta', reason: 'error', agentId: 'agent-1' } as any)
  expect(h.learns().length).toBe(0)
  expect(h.state('agent-1')).toBeUndefined()
})

test('a machine turn and a read-only task never learn', async ($, on) => {
  const h = host(on)
  await submit($, 'a long enough notification text body', 'task-notification')
  await $.turn.start({ text: 'x', turnId: 'm1' } as any)
  await $.tool.call({ tool: 'Bash', command: 'ls' } as any)
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 'm1', reason: 'answer' } as any)
  await submit($)
  await $.turn.start({ text: HUMAN, turnId: 't2' } as any)
  await $.tool.call({ tool: 'Read', file_path: '/proj/README' } as any)
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 't2', reason: 'answer' } as any)
  expect(h.learns().length).toBe(0)
})

test('task state is read from disk: a learn after a module reload uses the persisted patterns-used-main.json', async ($, on) => {
  const TSID = '11111111-2222-4333-8444-555555555555'
  const seeded = G.state_main_8.split('__TSID__').join(TSID)
  const h = host(on, { files: { [`${SDIR}/patterns-used-main.json`]: seeded } })
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($)
  expect(h.searches().length).toBe(0)
  expect(h.learns().length).toBe(1)
  const a = h.learnArgv(h.learns()[0]!)
  expect(h.flag(a, '--retrieval-id')).toBe(JSON.parse(seeded).retrieval_id)
  expect(h.trace(h.learns()[0]!).session_id).toBe(TSID)
})

// A REAL reload: every test registers the module anew, so module memory dies between these two tests.
let afterReload: Record<string, string> = {}
test('reload between tool.call and turn.complete, part 1: everything needed is on disk', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  afterReload = Object.fromEntries(h.files)
})

test('reload between tool.call and turn.complete, part 2: main and subagent still learn their full trajectory', async ($, on) => {
  const h = host(on, { files: afterReload })
  await $.tool.call({ tool: 'Bash', command: 'second half', agentId: 'agent-1' } as any)
  await done($, 'sub', 'agent-1')
  await done($, 'main')  // turn t1 was never heard in this load
  expect(h.learns().length).toBe(2)
  const [sub, main] = h.learns().map(l => h.trace(l))
  expect(sub!.trajectory.map((t: any) => t.tool)).toEqual(['Write', 'Bash'])
  expect(main!.trajectory.map((t: any) => t.tool)).toEqual(['Edit', 'Bash'])
  expect(main!.playbook_used).toEqual(JSON.parse(G.state_main_8).pattern_ids)
})

test('tool records are removed with the task', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  expect([...h.files.keys()].some(k => k.includes('mod-tools-main'))).toBe(true)
  await done($)
  expect([...h.files.keys()].some(k => k.includes('mod-tools-main'))).toBe(false)
})
