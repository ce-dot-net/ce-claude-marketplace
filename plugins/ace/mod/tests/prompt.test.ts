// ACE mod suite, prompt.submit: search, pin, render, state, cohorts, notices, mid-turn prompts, slash commands, malformed input. Harness: ./helpers.ts.
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

// ---------- prompt.submit: search, pin, render, state ----------


test('prompt.submit: one pinned search with a fresh uuid4 task pin per human prompt, full render golden', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const r: any = await submit($)
  expect(h.searches().length).toBe(1)
  const s = h.searches()[0]!
  expect(s.argv.slice(0, 5)).toEqual(['ace-cli', 'search', '--stdin', '--json', '--pin-session'])
  expect(UUID4.test(h.pin(s)!)).toBe(true)
  expect(h.flag(s.argv, '--session-id')).toBe(h.pin(s))
  expect(s.argv.includes('--top-k')).toBe(false)
  expect(s.stdin).toBe(HUMAN)
  expect(s.env!.ACE_PROJECT_ID).toBe(PRJ)
  expect(s.env!.ACE_ORG_ID).toBe('org_t')
  expect(s.timeoutMs! <= 25000).toBe(true)
  expect(r.context.length).toBe(1)
  expect(r.context[0]).toBe(G.full_main_8)
  expect(S8).toContain('zz_extra')  // the fixture's unknown top-level field ...
  expect(r.context[0]).not.toContain('zz_extra')  // ... never reaches the model (allow-list)
  await submit($, HUMAN + ' again please')
  expect(h.pin(h.searches()[1]!)).not.toBe(h.pin(s))
  const row = h.rows().find((x: any) => x.event === 'search')!
  expect(row.hook).toBe('UserPromptSubmit')
  expect(row.session_id).toBe(SID)
  expect(row.patterns_returned).toBe(8)
  expect(row.patterns_injected).toBe(8)
  expect(row.render_cohort).toBe('full')
  expect(row.task_session_id).toBe(h.pin(s))
  expect(row.source).toBe('mod')
  expect(/Z$/.test(row.timestamp)).toBe(true)
})

test('prompt.submit renders ALL 100 patterns, and the edge-case fixture byte-exactly', async ($, on) => {
  let out = S100
  const h = host(on, { search: () => ({ stdout: out }) })
  const r: any = await submit($)
  expect(r.context[0].startsWith('<ace-patterns shown="100" of="100" agent-type="main">\n{')).toBe(true)
  expect(bodyOf(r.context[0]).similar_patterns.length).toBe(100)
  out = SEDGE
  h.files.delete(`${SDIR}/full-injected.json`)  // a new conversation for the dedupe (§31): the edge render byte-exactly
  const r2: any = await submit($, HUMAN + ' edge')
  expect(r2.context[0]).toBe(G.full_main_edge)
  expect(h.searches().length).toBe(2)
})

test('state: patterns-used-main.json is byte-identical to the Python writer (shared fixture state_main_8)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  const tsid = h.pin(h.searches()[0]!)!
  const text = h.files.get(`${SDIR}/patterns-used-main.json`)!
  expect(text.split(tsid).join('__TSID__')).toBe(G.state_main_8)
})

test('state: user_prompt <= 4000, rendered_context <= 10000 and a complete envelope, F-080 ids of the injected set', async ($, on) => {
  const h = host(on)
  const long = HUMAN + ' ' + 'x'.repeat(5000)
  await submit($, long)
  const st = h.state()!
  expect(st.user_prompt).toBe(long.slice(0, 4000))
  expect(st.hook_event_name).toBe('UserPromptSubmit')
  expect(st.retrieval_id).toBe(JSON.parse(S100).retrieval_id)
  expect(st.task_session_id).toBe(h.pin(h.searches()[0]!))
  expect(st.pattern_ids.length).toBe(98)
  expect(Object.keys(st.retrieval_log_ids).length).toBe(84)
  expect(Object.values(st.retrieval_log_ids).every((v: any) => Number.isInteger(v))).toBe(true)
  const rc: string = st.rendered_context
  expect(rc.length <= 10000).toBe(true)
  expect(rc.startsWith('<ace-patterns shown="')).toBe(true)
  expect(rc.endsWith('\n</ace-patterns>')).toBe(true)
  expect(bodyOf(rc).similar_patterns.length).toBe(shownOf(rc))
})

test('prompt.submit writes domains.json (domains_summary) for the domain shift', async ($, on) => {
  const h = host(on)
  await submit($)
  expect(JSON.parse(h.files.get(`${PDIR}/domains.json`)!)).toEqual(JSON.parse(S100).domains_summary)
})

test('machine, short, slash-command and /ace prompts never search', async ($, on) => {
  const h = host(on)
  await submit($, '<task-notification><task-id>x</task-id> done</task-notification>')
  await submit($, 'a long enough notification text body', 'task-notification')
  await submit($, '<system-reminder>only a reminder</system-reminder>')
  await submit($, 'ok thanks')
  await submit($, '/ace-status please now')
  expect(h.searches().length).toBe(0)
})

test('disabled.flag (session or project) → no search, no context', async ($, on) => {
  const h = host(on, { files: { [`${SDIR}/disabled.flag`]: '' } })
  const r: any = await submit($)
  expect(h.searches().length).toBe(0)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  h.files.delete(`${SDIR}/disabled.flag`)
  h.put(`${PDIR}/disabled.flag`, '')
  await submit($, HUMAN + ' again')
  expect(h.searches().length).toBe(0)
})

// ---------- §13.1 gaps: 100K guard, pin-drop budget, cohorts ----------


test('100K guard: an oversized render is cut to <= 95,000 chars by dropping tail patterns, logged truncated_for_cap', async ($, on) => {
  const big = JSON.parse(S100)
  big.similar_patterns.forEach((p: any, i: number) => { p.content = 'x'.repeat(1500) + ' #' + i })
  const BIG = JSON.stringify(big)
  const h = host(on, { search: () => ({ stdout: BIG }) })
  const r: any = await submit($)
  const ctx: string = r.context[0]
  expect(ctx.length <= 95000).toBe(true)
  expect(ctx.length > 85000).toBe(true)
  const k = shownOf(ctx)
  expect(k < 100).toBe(true)
  expect(ctx.startsWith(`<ace-patterns shown="${k}" of="100" agent-type="main">\n`)).toBe(true)
  expect(bodyOf(ctx).similar_patterns.map((p: any) => p.content)).toEqual(ranked(BIG).slice(0, k).map((p: any) => p.content))
  const row = h.rows().find((x: any) => x.event === 'search')!
  expect(row.truncated_for_cap).toBe(true)
  expect(row.patterns_injected).toBe(k)
  expect(h.state()!.pattern_ids.every((id: string) => bodyOf(ctx).similar_patterns.some((p: any) => p.id === id))).toBe(true)
})

test('pin-drop: "database is locked" → ONE unpinned re-run, pin_failed logged, pin-backoff touched', async ($, on) => {
  const h = host(on, { search: (argv) => argv.includes('--pin-session') ? LOCKED : { stdout: S8 } })
  const r: any = await submit($)
  expect(h.searches().length).toBe(2)
  expect(h.searches()[1]!.argv.includes('--pin-session')).toBe(false)
  expect(h.flag(h.searches()[1]!.argv, '--session-id')).toBe(h.pin(h.searches()[0]!))  // cli 4.3.1: the retry still stamps the task session
  expect(r.context[0]).toBe(G.full_main_8)
  expect(h.rows().find((x: any) => x.event === 'search')!.pin_failed).toBe(true)
  expect(h.files.has(`${ROOT}/pin-backoff`)).toBe(true)
})

test('pin-backoff younger than 5 min → no pin up front (pin_skipped backoff); older → pinned again', async ($, on) => {
  const h = host(on, { files: { [`${ROOT}/pin-backoff`]: '' } })
  await submit($)
  expect(h.searches().length).toBe(1)
  expect(h.searches()[0]!.argv.includes('--pin-session')).toBe(false)
  expect(h.rows().find((x: any) => x.event === 'search')!.pin_skipped).toBe('backoff')
  expect(h.state()!.task_session_id).toBeDefined()
  expect(h.flag(h.searches()[0]!.argv, '--session-id')).toBe(h.state()!.task_session_id)  // backoff skips the pin, not the stamp
  h.advance(6 * MIN)
  await submit($, HUMAN + ' later')
  expect(h.searches()[1]!.argv.includes('--pin-session')).toBe(true)
})

test('blocking budget <= 25 s: the unpinned retry only gets the time left; none left → no retry', async ($, on) => {
  let spent = 20_000
  const h = host(on, { search: (argv) => argv.includes('--pin-session') ? { ...LOCKED, advanceMs: spent } : { stdout: S8 } })
  await submit($)
  const retry = h.searches()[1]!
  expect(retry.timeoutMs! > 0 && retry.timeoutMs! <= 5_000).toBe(true)
  spent = 25_000
  h.files.delete(`${ROOT}/pin-backoff`)  // the first submit's lock started the backoff; a backoff would skip the pin
  const r: any = await submit($, HUMAN + ' slow')
  expect(h.searches().length).toBe(3)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
})

test('a pinned search stuck on the lock is killed at its share of the budget; the unpinned re-run still fits and injects', async ($, on) => {
  const h = host(on, { search: (argv) => argv.includes('--pin-session') ? { killed: true, advanceMs: 15_000 } : { stdout: S8 } })
  const r: any = await submit($)
  const [pinned, retry] = h.searches()
  expect(pinned!.timeoutMs! < 25000).toBe(true)
  expect(retry!.argv.includes('--pin-session')).toBe(false)
  expect(pinned!.timeoutMs! + retry!.timeoutMs! <= 25000).toBe(true)
  expect(r.context[0]).toBe(G.full_main_8)
  expect(h.files.has(`${ROOT}/pin-backoff`)).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'search')!.pin_failed).toBe(true)
})

test('a pinned search killed by a slow server (the unpinned re-run dies too) does NOT suspend pins; pinned latency is logged', async ($, on) => {
  const h = host(on, { search: () => ({ killed: true, advanceMs: 15_000 }) })
  await submit($)
  expect(h.files.has(`${ROOT}/pin-backoff`)).toBe(false)
  const h2 = h.rows().find((x: any) => x.event === 'error')!
  expect(h2.pin_failed).toBe(true)
  expect(h2.pin_ms).toBe(15_000)
})

test('render_cohort ACE_AB_CONTROL_PCT=100 → control: search + state, NO injection', async ($, on) => {
  const h = host(on, { env: { ACE_AB_CONTROL_PCT: '100' } })
  const r: any = await submit($)
  expect(h.searches().length).toBe(1)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  expect(h.state()!.task_session_id).toBe(h.pin(h.searches()[0]!))
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('control')
})

test('render_cohort ACE_AB_COMPACT_PCT=100 → compact one-liners <= 9,500 chars', async ($, on) => {
  const h = host(on, { env: { ACE_AB_COMPACT_PCT: '100' } })
  const r: any = await submit($)
  expect(r.context[0].length <= 9500).toBe(true)
  expect(r.context[0].startsWith('<ace-patterns shown="100" of="100" mode="compact" agent-type="main">\n#')).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('compact')
})

test('render_cohort ACE_RENDER_FULL_PCT=0 → budget-verbatim (render_patterns, <= 9,500 chars)', async ($, on) => {
  const h = host(on, { env: { ACE_RENDER_FULL_PCT: '0' } })
  const r: any = await submit($)
  const ctx: string = r.context[0]
  expect(ctx.length <= 9500).toBe(true)
  expect(shownOf(ctx) < 100).toBe(true)
  expect(ctx.startsWith(`<ace-patterns shown="${shownOf(ctx)}" of="100" agent-type="main">\n{`)).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'search')!.render_cohort).toBe('budget')
})

test('item D: a self-eval request file is removed, the prompt carries only the patterns', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }),
    files: { [EVAL_REQ]: JSON.stringify({ patterns_injected: 100, avg_relevance: 0, domains: 0, tools_executed: 2, success: true }) } })
  const r: any = await submit($)
  expect(r.context).toEqual([G.full_main_8])
  expect(h.files.has(EVAL_REQ)).toBe(false)
})

// ---------- UI parity: systemMessage / sessionTitle ----------


test('notice: ONE transcript line after the prompt on success, an [ACE] error line on failure', async ($, on) => {
  let fail = false
  const h = host(on, { search: () => fail ? { exitCode: 1, stdout: '', stderr: 'boom' } : { stdout: S8 } })
  await submit($)
  expect(h.logs.some(l => /^ACE · 8 patterns · full/.test(l))).toBe(true)
  expect(h.logs.every(l => !l.includes('\n'))).toBe(true)  // $.ui.log is one line
  fail = true
  await submit($, HUMAN + ' fail')
  expect(h.logs.some(l => /^(❌|⚠️|⏱️) \[ACE\]/.test(l))).toBe(true)
})

test('sessionTitle via classic.UserPromptSubmit, only when the session has no title yet', async ($, on) => {
  host(on)
  await submit($)
  const c: any = await ($ as any).classic.UserPromptSubmit({ prompt: HUMAN, session_id: SID })
  expect(/^ACE( low| ready)? · /.test(c.sessionTitle)).toBe(true)
  const c2: any = await ($ as any).classic.UserPromptSubmit({ prompt: HUMAN, session_id: SID, session_title: 'my title' })
  expect(c2.sessionTitle).toBe(undefined)
})

// ---------- malformed input never wedges the hooks worker ----------

test('pyLoads rejects malformed JSON, and never spins', () => {
  for (const bad of MALFORMED) {
    let threw = false
    try { pyLoads(bad) } catch { threw = true }
    expect([bad, threw]).toEqual([bad, true])
  }
  expect(pyLoads('{"a": [1, {"b": "c\\"d"}], "e": null}').a[1].b).toBe('c"d')
})

test('a project settings file with a trailing comma: ACE stays out, as Python get_context returns None', async ($, on) => {
  const h = host(on, { files: { [`${CWD}/.claude/settings.json`]: '{"projectId": "prj_t",}' } })
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
  await submit($)
  expect(h.searches().length).toBe(0)
})

test('cut-off ace-cli stdout: search fails cleanly, the task stays anchored', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: '{"similar_patterns": [{"id": "abc' }) })
  const r: any = await submit($)
  expect(r.context === undefined || r.context.length === 0).toBe(true)
  expect(h.rows().find((x: any) => x.event === 'error')!.error).toBe('json_parse_failed')
  expect(h.state()!.task_session_id).toBeDefined()
})

// ---------- prompts into a running turn ----------

test('a prompt typed mid-turn leaves the running task alone: it still learns with its anchor and all its tools', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  const before = h.state()!
  const r: any = await $.prompt.submit({ text: SECOND, wait: false, origin: { kind: 'composer' }, turnId: 't1' } as any)
  expect(r.context.length).toBe(1)  // the new prompt still gets its patterns
  expect(h.state()).toEqual(before)
  await $.tool.call({ tool: 'Bash', command: 'after the prompt' } as any)
  await done($)
  expect(h.learns().length).toBe(1)
  const t = h.trace(h.learns()[0]!)
  expect(t.task).toBe('User request: ' + HUMAN)
  expect(t.session_id).toBe(before.task_session_id)
  expect(t.trajectory.length).toBe(3)
})

test('a mid-turn prompt that then runs as its own turn becomes its own task, with its own pin and credit', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await $.prompt.submit({ text: SECOND, wait: true, origin: { kind: 'composer' }, turnId: 't1' } as any)
  const pin2 = h.pin(h.searches()[1]!)!
  await done($)
  await $.turn.start({ text: SECOND, turnId: 't2' } as any)
  expect(h.state()!.task_session_id).toBe(pin2)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/z.py', old_string: 'a', new_string: 'b' } as any)
  await $.turn.complete({ answer: 'two', durationMs: 1, isAborted: false, turnId: 't2', reason: 'answer' } as any)
  expect(h.learns().length).toBe(2)
  const t = h.trace(h.learns()[1]!)
  expect(t.session_id).toBe(pin2)
  expect(t.task).toBe('User request: ' + SECOND)
  expect(t.trajectory.map((x: any) => x.tool)).toEqual(['Edit'])
})

test('a machine prompt delivered into a running turn does not disturb the human prompt waiting for its turn', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  await $.prompt.submit({ text: '<task-notification>done</task-notification>', wait: false, origin: { kind: 'task-notification' }, turnId: 't0' } as any)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($)
  expect(h.learns().length).toBe(1)
})

// ---------- slash commands ----------

test('a slash command with arguments gets search, context and learn; the arguments are the query', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const args = 'build the login page with oauth support'
  const r: any = await cmd($, 'feature-dev', args)
  expect(h.searches().length).toBe(1)
  expect(h.searches()[0]!.stdin).toBe(args)
  expect(r.context[0]).toBe(G.full_main_8)
  await $.turn.start({ text: 'skill body', turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($)
  expect(h.learns().length).toBe(1)
  expect(h.trace(h.learns()[0]!).task).toBe(`User request: /feature-dev ${args}`)
})

test('ACE commands, commands without arguments and session built-ins stay out', async ($, on) => {
  const h = host(on)
  await cmd($, 'ace:ace-learn', 'capture what we learned about the render')
  await cmd($, 'ace-status', 'for this project and that one')
  await cmd($, 'feature-dev', '')
  await cmd($, 'compact', 'focus on the mod work and the open review')
  await cmd($, 'model', 'claude-sonnet-with-a-long-argument')
  expect(h.searches().length).toBe(0)
})
