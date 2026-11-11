// ACE mod suite, turn.complete: the learn, the trivial-task filter. Harness: ./helpers.ts.
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

// ---------- turn.complete: learn ----------

test('item D/H1: Haiku self-eval (not blocking the turn) writes the review and its whitelisted ACE_USED ids join the learn', async ($, on) => {
  const st8 = JSON.parse(G.state_main_8), [a, b] = Object.keys(st8.retrieval_log_ids)
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true,
    model: () => ({ isAnswered: true, text: `ACE_REVIEW: 70% | 4m saved | helped\nACE_USED: ${b}, ctx-9999999999-zzzz`, usage: {} }) })
  await mainTask($, h)
  const r: any = await done($, 'finished the change')
  expect(r.text).toBe('finished the change')  // item 3: the line waits for the dispatch
  await settle(h)
  const req = h.modelCalls[0]
  expect([req.model, req.effort, req.timeoutMs]).toEqual(['haiku', 'low', 15000])
  expect(req.prompt.includes(`${b}: `)).toBe(true)          // injected patterns as id: content lines
  expect(req.prompt.includes('pytest :: pytest -q')).toBe(true)  // the task's tool calls
  expect(req.prompt.includes('finished the change')).toBe(true)
  expect(req.prompt.length <= 2000 + 4000 + 6000 + 4000 + 1500).toBe(true)
  expect(JSON.parse(h.files.get(`${CWD}/.claude/data/logs/ace-review-result.json`)!)).toEqual({ quality_pct: 70, time_saved: '4m' })
  const t = h.trace(h.learns()[0]!)
  expect(t.applied_log_ids).toEqual([st8.retrieval_log_ids[b]])  // the non-injected id is dropped
  expect([t.used_ids_model, t.used_ids_tokens]).toEqual([1, 0])  // per-source counters in the trace itself
  const row = execRow(h)
  expect([row.used_ids_count, row.used_source]).toEqual([1, 'model'])
  expect([row.used_ids_model, row.used_ids_tokens]).toEqual([1, 0])  // item 2: per-source counts for the server team
  const disp = h.rows().find((x: any) => x.event === 'learn_dispatched')!
  expect([disp.used_ids_model, disp.used_ids_tokens]).toEqual([1, 0])
  expect(h.files.has(EVAL_REQ)).toBe(false)  // no HTML-comment self-eval request while the mod is active
})

test('server 5.15.8: more than 20 used ids -> 20 applied_log_ids, Haiku ids first (injected order), then token ids', async ($, on) => {
  let model: string[] = []
  const h = host(on, { search: () => ({ stdout: S100 }), selfEval: true,
    model: () => ({ isAnswered: true, text: `ACE_REVIEW: 70% | 4m saved | ok\nACE_USED: ${model.join(', ')}`, usage: {} }) })
  await submit($)
  const st = h.state()!, rlog = st.retrieval_log_ids, ids: string[] = st.pattern_ids.filter((id: string) => id in rlog)
  model = ids.slice(30, 40).reverse()  // 10 Haiku ids, named out of order
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($, 'used ' + ids.slice(0, 15).join(' '))  // 15 token ids (by id in the answer)
  await settle(h)
  const want = [...ids.slice(30, 40), ...ids.slice(0, 10)].map(id => rlog[id])
  expect(h.trace(h.learns()[0]!).applied_log_ids).toEqual(want)
  const row = execRow(h)
  expect([row.used_ids_count, row.used_ids_capped]).toEqual([25, true])
})

test('server 5.15.8: 20 or fewer used ids are sent as before, no used_ids_capped field', async ($, on) => {
  const st8 = JSON.parse(G.state_main_8), [a] = Object.keys(st8.retrieval_log_ids)
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($, 'applied ' + a)
  expect(h.trace(h.learns()[0]!).applied_log_ids).toEqual([st8.retrieval_log_ids[a]])
  expect('used_ids_capped' in execRow(h)).toBe(false)
})

test('item 3: with the self-eval on, "learning sent" shows only once the learn went out: no turn.complete text, ONE log line with the review parts (none at 0% or without a review)', async ($, on) => {
  const cases: [string, string][] = [['ACE_REVIEW: 70% | 4m saved | helped', 'ACE · learning sent · 70% · ~4m saved'],
    ['ACE_REVIEW: 55% | n/a | meh', 'ACE · learning sent · 55%'], ['ACE_REVIEW: 0% | 0m saved | none', 'ACE · learning sent'], ['no review here', 'ACE · learning sent']]
  let text = ''
  let release: () => void = () => {}
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true, defaultArm: true,  // budget arm: no dedupe across tasks
    model: () => new Promise(r => { release = () => r({ isAnswered: true, text, usage: {} }) }) })
  for (const [i, [t, want]] of cases.entries()) {
    text = t
    const from = h.logs.length
    await mainTask($, h)
    const r: any = await done($)
    expect(r.text).toBe('done')  // the hook returned before the model answered: no line yet
    expect(h.learns().length).toBe(i)
    expect(h.logs.slice(from).some((l: string) => l.startsWith('ACE · learning sent'))).toBe(false)
    release()
    await settle(h, i + 1)
    for (let k = 0; k < 50 && h.logs.length === from; k++) await new Promise(r => setTimeout(r, 5))
    expect(h.logs.slice(from).filter((l: string) => /^ACE · (learning|review)/.test(l))).toEqual([want])
  }
})

test('item 3: a model error still sends the learn, then logs the line without review parts', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true, model: () => { throw new Error('boom') } })
  await mainTask($, h)
  const r: any = await done($)
  expect(r.text).toBe('done')
  await settle(h)
  for (let k = 0; k < 50 && !h.logs.length; k++) await new Promise(r => setTimeout(r, 5))
  expect(h.learns().length).toBe(1)
  expect(h.logs.filter((l: string) => /^ACE · (learning|review)/.test(l))).toEqual(['ACE · learning sent'])
})

test('item 3: ACE_SELF_EVAL=0 keeps the turn.complete line', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true, env: { ACE_SELF_EVAL: '0' } })
  await mainTask($, h)
  const r: any = await done($, 'ACE_REVIEW: 80% | 5m saved | ok')
  expect(r.text).toBe('ACE · learning sent · 80% · ~5m saved')
  expect(h.logs.some((l: string) => l.startsWith('ACE · learning sent'))).toBe(false)
})

test('item D/H1: a failed or timed-out model call falls back to the token evidence (H2); the learn still goes out', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true })  // default fake: api-error
  await mainTask($, h)
  await done($)
  await settle(h)
  expect(h.learns().length).toBe(1)
  expect(h.trace(h.learns()[0]!).applied_log_ids).toEqual([])
  expect(execRow(h).used_source).toBe('none')
  expect([h.trace(h.learns()[0]!).used_ids_model, h.trace(h.learns()[0]!).used_ids_tokens]).toEqual([0, 0])
})

test('item D: ACE_SELF_EVAL=0 makes no model call (the learn goes out at once)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true, env: { ACE_SELF_EVAL: '0' } })
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(1)
  expect(h.modelCalls.length).toBe(0)
})

test('item 1a: a non-interactive session (-p, SDK) skips the Haiku wait: the learn goes out at once with H2 only', async ($, on) => {
  const st8 = JSON.parse(G.state_main_8), [a] = Object.keys(st8.retrieval_log_ids)
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true, model: () => new Promise(() => {}) })
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  await mainTask($, h)
  await done($, 'applied ' + a)
  expect(h.learns().length).toBe(1)
  expect(h.modelCalls.length).toBe(0)
  expect(h.trace(h.learns()[0]!).applied_log_ids).toEqual([st8.retrieval_log_ids[a]])
  expect(execRow(h).used_source).toBe('tokens')
  expect([execRow(h).used_ids_model, execRow(h).used_ids_tokens]).toEqual([0, 1])
})

test('item 1b: a self-eval still pending at session.end dispatches once with H2 ids; Haiku answering later sends no second learn', async ($, on) => {
  const st8 = JSON.parse(G.state_main_8), [a, b] = Object.keys(st8.retrieval_log_ids)
  let release: () => void = () => {}
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true,
    model: () => new Promise(r => { release = () => r({ isAnswered: true, text: `ACE_USED: ${b}`, usage: {} }) }) })
  await $.session.start({ cwd: CWD, surface: null, isInteractive: true } as any)
  await mainTask($, h)
  await done($, 'applied ' + a)
  expect(h.modelCalls.length).toBe(1)
  expect(h.learns().length).toBe(0)
  await $.session.end({ reason: 'prompt_input_exit', sessionId: SID, resume: {} } as any)
  expect(h.learns().length).toBe(1)
  expect(h.trace(h.learns()[0]!).applied_log_ids).toEqual([st8.retrieval_log_ids[a]])
  release()
  for (let k = 0; k < 20; k++) await new Promise(r => setTimeout(r, 5))
  expect(h.learns().length).toBe(1)
  expect(h.rows().filter((x: any) => x.event === 'learn_dispatched').length).toBe(1)
})

test('item D: subagents never call the model (H2 only)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), selfEval: true })
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'x', 'agent-1')
  expect(h.learns().length).toBe(1)
  expect(h.modelCalls.length).toBe(0)
})

test('item D: a stale eval request is removed at the next prompt and never injected while the mod runs', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), files: { [EVAL_REQ]: JSON.stringify({ patterns_injected: 5, avg_relevance: 50, domains: 2, tools_executed: 3 }) } })
  const r: any = await submit($)
  expect(r.context.some((c: string) => c.startsWith('<!-- ACE Self-Eval'))).toBe(false)
  expect(h.files.has(EVAL_REQ)).toBe(false)
})

test('item 4: main tools seen but none recorded at learn time -> a tools_mismatch row (diagnostic only); none when they match', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h, [{ tool: 'Bash', command: 'ls' }, { tool: 'Bash', command: 'pwd' }, { tool: 'Bash', command: 'id' }])
  // a machine turn completing in between wipes the main tool store (anchor null): the task's learn then sees 0 tools
  await submit($, '<task-notification><task-id>x</task-id> done</task-notification>', 'task-notification')
  await $.turn.start({ text: 'n', turnId: 'tm' } as any)
  await $.turn.complete({ answer: 'n', durationMs: 1, isAborted: false, turnId: 'tm', reason: 'answer' } as any)
  await done($)
  const mm = h.rows().filter((r: any) => r.event === 'tools_mismatch')
  expect(mm.length).toBe(1)
  const { timestamp, ...rest } = mm[0]
  expect(rest).toEqual({ event: 'tools_mismatch', hook: 'Stop', recorded: 0, seen: 3, source: 'mod' })
  expect(h.rows().some((r: any) => r.event === 'learn_skipped' && r.tools === 0)).toBe(true)  // no behaviour change
  await mainTask($, h)  // counter reset with the new task; recorded == seen
  await done($)
  expect(h.rows().filter((r: any) => r.event === 'tools_mismatch').length).toBe(1)
  expect(h.learns().length).toBe(1)
})

test('item 2: learnLine = one line, unknown parts left out', async () => {
  expect(learnLine({ quality_pct: 80, time_saved: '5m' })).toBe('ACE · learning sent · 80% · ~5m saved')
  expect(learnLine({ quality_pct: 70, time_saved: '12 min' })).toBe('ACE · learning sent · 70% · ~12m saved')
  expect(learnLine({ quality_pct: 60, time_saved: '30s' })).toBe('ACE · learning sent · 60%')
  expect(learnLine(null)).toBe('ACE · learning sent')
})

test('item 2: a dispatched main learn shows one line beneath the answer; skips and subagents show none', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  const r: any = await done($, 'ACE_REVIEW: 80% | 5m saved | ok')
  expect(h.learns().length).toBe(1)
  expect(r.text).toBe('ACE · learning sent · 80% · ~5m saved')
  expect(r.text.includes('\n')).toBe(false)
  await mainTask($, h)
  expect(((await done($, 'all done')) as any).text).toBe('ACE · learning sent')
  await mainTask($, h, [{ tool: 'Read', file_path: '/proj/x.py' }])  // no substantial work: skipped
  expect(((await done($, 'looked')) as any).text).toBe('looked')
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  expect(((await done($, 'sub done', 'agent-1')) as any).text).toBe('sub done')
})

test('item 2: classic hooks filtered (the Python Stop learns): the mod shows no line', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), noClassic: true })
  await mainTask($, h)
  expect(((await done($, 'finished')) as any).text).toBe('finished')
  expect(h.learns().length).toBe(0)
})

test('turn.complete main: detached learn (--no-stream, F-080 flags, --timeout 300000), lock taken before the spawn', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_RENDER_FULL_PCT: '0' } })
  const st8 = JSON.parse(G.state_main_8), used = Object.keys(st8.retrieval_log_ids)[1]
  await mainTask($, h)
  await done($, 'followed ' + used)  // §31: only the USED pattern is applied
  expect(h.learns().length).toBe(1)
  const L = h.learns()[0]!, a = h.learnArgv(L)
  expect(a.slice(0, 3)).toEqual(['ace-cli', 'learn', '--transcript'])
  for (const f of ['--json', '--no-stream']) expect(a).toContain(f)
  expect(h.flag(a, '--timeout')).toBe('300000')
  expect(h.flag(a, '--verbosity')).toBe('detailed')
  expect(a.includes('--pin-session')).toBe(false)
  expect(h.flag(a, '--retrieval-id')).toBe(st8.retrieval_id)
  expect(h.flag(a, '--applied-log-ids')).toBe(String(st8.retrieval_log_ids[used]))
  expect(h.flag(a, '--transcript')!.startsWith(`${ROOT}/tmp/`)).toBe(true)
  expect(L.files.has(`${SDIR}/learn-inflight-main.lock`)).toBe(true)
  expect(L.argv[0] === 'ace-cli').toBe(false)  // never the bare learn: always through the detaching launcher
})

test('trace parity with ace_after_task.py: fields, effort from classic.Stop, git context, render_variant', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await ($ as any).classic.Stop({ session_id: SID, stop_hook_active: false, last_assistant_message: 'all done', effort: { level: 'high' } })
  await done($, 'all done')
  const t = h.trace(h.learns()[0]!)
  const tsid = h.pin(h.searches()[0]!)
  expect(t.task).toBe('User request: ' + HUMAN)
  expect(t.trajectory.map((s: any) => [s.step, s.tool])).toEqual([[1, 'Edit'], [2, 'Bash']])
  expect(t.trajectory.every((s: any) => typeof s.action === 'string' && typeof s.result === 'string')).toBe(true)
  expect(t.result.success).toBe(true)
  expect(t.result.output).toBe('Executed 2 tool calls')
  expect(t.result.summary).toBe('all done')
  expect(t.playbook_used).toEqual(JSON.parse(G.state_main_8).pattern_ids)
  expect(/^\d{4}-\d\d-\d\dT.*Z$/.test(t.timestamp)).toBe(true)
  expect(t.agent_type).toBe('main')
  expect(t.session_id).toBe(tsid)
  expect(t.render_variant).toBe('full')
  expect(t.render_path).toBe('mod')  // 8.2.1: which chain rendered
  expect(t.conversation_id).toBe(SID)  // §31: the stable CC session id
  expect(t.retrieval_id).toBe(JSON.parse(S8).retrieval_id)
  expect(t.applied_log_ids).toEqual([])  // §31: 'all done' uses no pattern; the server wants [] not omitted
  expect(t.effort_level).toBe('high')
  expect(t.effort_weight).toBe(1.5)
  expect(t.git.commit_hash).toBe('abc123')
  expect(t.git.branch).toBe('main')
})

// ---------- trivial-task filter ----------


test('a task that names a path under plugins/ or /ace- is real work; the commands themselves stay trivial', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const work = async (text: string, turnId: string) => {
    await submit($, text)
    await $.turn.start({ text, turnId } as any)
    await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
    await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId, reason: 'answer' } as any)
  }
  await work('fix the marker in plugins/ace/mod/register.ts', 'a')
  await work('rename the folder /opt/ace-tools/bin in the docs', 'b')
  expect(h.learns().length).toBe(2)
  await work('run /ace-status for this project', 'c')
  await work('please run /plugin install now', 'd')
  expect(h.learns().length).toBe(2)
})

test('8.1.0 fix: a pending mid-turn state without a task_session_id anchors null (never undefined): no learn, no error row', async ($, on) => {
  const h = host(on, { files: { [`${SDIR}/mod-pending-main.json`]: JSON.stringify({ text: HUMAN, state: '{}' }) } })
  await $.turn.start({ text: HUMAN, turnId: 't9' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await $.turn.complete({ answer: 'done', durationMs: 5, isAborted: false, turnId: 't9', reason: 'answer' } as any)
  expect(h.learns().length).toBe(0)
  expect(h.rows().some((r: any) => r.event === 'error')).toBe(false)
})

test('8.1.0: SubagentHandback is matched by name (not in the typed tool table); a non-string or main-agent message is ignored', async ($, on) => {
  const h = host(on)
  await $.tool.call({ tool: 'SubagentHandback', message: { not: 'a string' }, agentId: 'agent-9' } as any)
  await $.tool.call({ tool: 'SubagentHandback', message: 'main never hands back' } as any)
  expect(h.rows().some((r: any) => r.event === 'error')).toBe(false)
})

test('8.1.0 audit: the execution row carries source, agent_id, task_session_id, render_cohort; learn_dispatched counts applied ids', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  await settle(h)
  const ex = execRow(h)
  expect(ex.source).toBe('mod')
  expect('agent_id' in ex && 'render_cohort' in ex).toBe(true)
  expect(ex.task_session_id).toBe(h.state()?.task_session_id ?? ex.task_session_id)
  const d = h.rows().find((r: any) => r.event === 'learn_dispatched')
  expect(typeof d.applied_log_ids_count).toBe('number')
  expect('applied_log_ids' in d).toBe(false)
})

// ---------- 8.2.2: origin fields on the learn trace (mod only) ----------

test('8.2.2: prompt_origin = the FIRST prompt\'s origin.kind (machine ones too), kept; human_prompt_count counts composer/bridge only', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($, '<task-notification>bg done</task-notification>', 'task-notification')  // the first prompt, a machine one
  await submit($, HUMAN, 'sdk')
  await submit($, HUMAN, 'bridge')
  await mainTask($, h)  // composer
  await done($, 'all done')
  const t = h.trace(h.learns()[0]!)
  expect([t.prompt_origin, t.human_prompt_count]).toEqual(['task-notification', 2])
  expect('interactive' in t).toBe(false)  // no session.start seen: unknown, never defaulted
})

test('8.2.2: no origin -> unclassified; count 0 still sent once a prompt was seen; interactive from session.start', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  await $.prompt.submit({ text: HUMAN, wait: false } as any)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await $.tool.call({ tool: 'Bash', command: 'pytest -q' } as any)
  await done($, 'all done')
  await settle(h)
  const t = h.trace(h.learns()[0]!)
  expect([t.prompt_origin, t.human_prompt_count, t.interactive]).toEqual(['unclassified', 0, false])
})

test('8.2.2: a subagent trace carries the conversation\'s origin fields', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await $.session.start({ cwd: CWD, surface: null, isInteractive: true } as any)
  await submit($)
  await spawn($, 'review the domain shift python port for parity bugs')
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'reviewed', 'agent-1')
  const t = h.trace(h.learns()[0]!)
  expect([t.agent_id, t.interactive, t.prompt_origin, t.human_prompt_count]).toEqual(['agent-1', true, 'composer', 1])
})
