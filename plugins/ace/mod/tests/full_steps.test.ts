// Full steps (no per-step summaries as the only content, no 50-step cap); one hard byte cap against MiB monsters.
import { expect } from 'claude-code/testing'
import { test } from './t.ts'
import S8 from './fixtures/search_8.ts'
import { HUMAN, SDIR, done, host, mainTask, submit } from './helpers.ts'
import { PRIVATE_APPEND_SH, PRIVATE_WRITE_SH, SINK_WRITE_SH } from '../lib/sh.ts'
import { TOOLS_FILE_MAX, parseToolRecs } from '../io/state.ts'
import { switchOff, switchOn } from '../lib/switches.ts'
import { updateGate } from '../lib/update.ts'
import { pyDumps } from '../lib/pyjson.ts'
import { mergeState } from '../lib/state.ts'
import { serverFullSteps, storedFullSteps, storedUpvote } from '../lib/cohort.ts'
import { TEXT_HARD_CAP_CHARS, TRACE_HARD_CAP_BYTES, TRACE_HARD_CAP_MAX, buildTrace, hardCapBytes, textCapChars, toolRec, trimPayloads, utf8Len, summarizeResult } from '../lib/trace.ts'
import { redact } from '../lib/redact.ts'

const T = (tools: any[], hardCap?: number) => buildTrace({ userPrompt: 'fix it', answer: 'a', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools, hardCap } as any)
const steps = (t: any) => t.trajectory.filter((s: any) => !s._truncation_marker)

test('full steps: the real tool input and output reach the step (Bash stdout 30k, Edit strings, Read content), labels stay', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const old = 'o'.repeat(5000), neu = 'n'.repeat(7000)
  await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: old, new_string: neu }, { tool: 'Bash', command: 'big' }, { tool: 'Read', file_path: '/proj/r.py' }])
  await done($)
  const t = h.trace(h.learns()[0]!)
  const [e, b, r] = t.trajectory
  expect([e.action, b.action, r.action]).toEqual(['Edited x.py', 'big :: big', 'Read r.py'])
  expect([e.tool_input.old_string, e.tool_input.new_string]).toEqual([old, neu])
  expect(e.tool_input.tool).toBe(undefined)                 // the event's own keys are no tool input
  expect(b.tool_response.stdout).toBe('y'.repeat(30000))   // not cut to 60/100 chars
  expect(r.tool_response).toBe('     1\ta\n     2\tb')   // Read: the line-numbered text the model saw
  expect(t.metadata).toBe(undefined)
})

test('no 50-step cap: 120 steps all reach the trace, no marker, not truncated', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 119; i++) tools.push({ tool: 'Bash', command: 'echo ' + i })
  await mainTask($, h, tools)
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect(t.trajectory.length).toBe(120)
  expect(t.trajectory.some((s: any) => s._truncation_marker)).toBe(false)
  expect(t.metadata).toBe(undefined)
})

test('no record cap before the trace: 1100 tool calls are all kept (MAX_TOOL_RECS gone)', { timeoutMs: 60_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 1099; i++) tools.push({ tool: 'Bash', command: 'echo ' + i })
  await mainTask($, h, tools)
  await done($)
  expect(h.trace(h.learns()[0]!).trajectory.length).toBe(1100)
})  // 1100 hook round trips: slow under the parallel full suite (timeoutMs above)

test('redaction covers the FULL length of input and output (secret after 1 MB, nested keys, long command); labels unchanged', () => {
  const tok = 'ghp_' + 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6'
  const filler = 'lorem ipsum\n'.repeat(90_000)  // > 1 MB
  const rec = toolRec('Bash', { command: 'x '.repeat(300) + `curl -H "Authorization: Bearer ${tok}" https://h` },
    { stdout: filler + `password=hunter2 and ${tok}\nAuthorization: Bearer abc.def`, stderr: '', interrupted: false, env: { API_KEY: 'plainvalue', nested: [{ token: 'deepsecret' }] } }, false, undefined, 0, 1)
  const s = pyDumps(T([rec]).trace)
  for (const leak of [tok, 'hunter2', 'abc.def', 'plainvalue', 'deepsecret']) expect([leak, s.includes(leak)]).toEqual([leak, false])
  expect(s.includes('lorem ipsum')).toBe(true)
  // the redaction rules themselves are unchanged
  expect(redact('curl -H "Authorization: Bearer abc"')).toBe('curl -H "Authorization: [redacted]')
  expect(redact('x Bearer abc def\nnext')).toBe('x Bearer [redacted]\nnext')
  expect(redact('mysql -u root -p hunter2')).toBe('mysql -u root -p [redacted]')
  expect(redact('--password=s3cret rest')).toBe('--password=[redacted]')
})

test('hard cap: parsing (default 4 MiB, junk keeps the default)', () => {
  expect(TRACE_HARD_CAP_BYTES).toBe(4 * 1024 * 1024)
  expect(hardCapBytes(undefined)).toBe(TRACE_HARD_CAP_BYTES)
  expect(hardCapBytes('junk')).toBe(TRACE_HARD_CAP_BYTES)
  expect(hardCapBytes('-5')).toBe(TRACE_HARD_CAP_BYTES)
  expect(hardCapBytes('8388608')).toBe(TRACE_HARD_CAP_MAX)  // round 8 I3: clamped below the queue MAX_FILE
})

test('hard cap: under the cap nothing changes; over it the LONGEST outputs go first, marker with counters, size <= cap', () => {
  const r = (n: number, failed = false) => toolRec('Bash', { command: 'echo ' + n }, { stdout: 'z'.repeat(n), stderr: '', interrupted: false, ...(failed ? { exitCode: 2 } : {}) }, false, undefined, 0, 1)
  const tools = [r(1000), r(50_000), r(9000), r(30_000)]
  expect(T(tools).cap).toBe(undefined)
  const { trace, cap } = T(tools, 25_000)
  const st = steps(trace)
  expect(st.map((s: any) => typeof s.tool_response === 'string' ? s.tool_response : 'full')).toEqual(['full', '<truncated: 50050 bytes>', 'full', '<truncated: 30050 bytes>'])
  expect(trace.trajectory[0]).toMatchObject({ _truncation_marker: true, original_length: 4, kept: 4, outputs_truncated: 2, steps_dropped: 0 })
  expect(trace.metadata.trace_truncated).toBe(true)
  expect(pyDumps(trace).length).toBeLessThanOrEqual(25_000)
  expect(cap).toEqual({ bytes_before: expect.any(Number), bytes_after: pyDumps(trace).length, steps: 4 })
  expect(cap!.bytes_before).toBeGreaterThan(90_000)
})

test('hard cap: then OLDER non-failed steps are dropped; failed steps always stay; kept_indices names them', () => {
  const ok = (i: number) => toolRec('Bash', { command: 'echo ' + i + ' ' + 'p'.repeat(400) }, { stdout: 'ok', stderr: '', interrupted: false }, false, undefined, i, i + 1)
  const bad = toolRec('Bash', { command: 'npm run build' }, { stdout: '', stderr: 'e', interrupted: false, exitCode: 2 }, false, undefined, 0, 1)
  const tools = [bad, ...Array.from({ length: 40 }, (_, i) => ok(i))]
  const { trace } = T(tools, 8000)
  const m = trace.trajectory[0]
  expect(m._truncation_marker).toBe(true)
  expect(m.steps_dropped).toBeGreaterThan(0)
  expect(m.kept).toBe(41 - m.steps_dropped)
  expect(m.kept_indices[0]).toBe(0)                        // the failed first step survives
  expect(steps(trace)[0].action.startsWith('npm run :: npm run build')).toBe(true)
  expect(steps(trace).at(-1).step).toBe(41)                // the newest step survives
  expect(pyDumps(trace).length).toBeLessThanOrEqual(8000)
})

test('hard cap via env + one text-free trace_cap_hit row (bytes_before/bytes_after/steps)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_HARD_CAP_BYTES: '20000' } })
  await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Bash', command: 'big' }])
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect(t.trajectory[0]._truncation_marker).toBe(true)
  expect(steps(t)[1].tool_response).toMatch(/^<truncated: \d+ bytes>$/)
  const row = h.rows().find((x: any) => x.event === 'trace_cap_hit')
  expect(row).toMatchObject({ bytes_after: expect.any(Number), steps: 2, source: 'mod' })
  expect(row.bytes_before).toBeGreaterThan(30000)
  expect(row.bytes_after).toBeLessThanOrEqual(20000)
  expect(JSON.stringify(row).includes('yyyy')).toBe(false)
})

// ---- result.summary: the whole (redacted) answer, no 2000/4000 cut; one hard cap with marker + count ----
test('summary: a 10000-char answer arrives complete; redaction covers the whole text (secret at char 9000)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tok = 'ghp_' + 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6'
  const answer = 'a'.repeat(9000) + ' ' + tok + ' ' + 'b'.repeat(1000 - tok.length - 2)
  await mainTask($, h)
  await done($, answer)
  const sum = h.trace(h.learns()[0]!).result.summary
  expect(sum.includes(tok)).toBe(false)
  expect(sum.startsWith('a'.repeat(9000) + ' [redacted]')).toBe(true)
  expect(sum.endsWith('b'.repeat(500))).toBe(true)
  expect(h.rows().some((x: any) => x.event === 'text_cap_hit')).toBe(false)
})
test('summary: over the hard cap -> head kept + <truncated: N chars> marker, one text-free summary_cap_hit row', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TEXT_HARD_CAP_CHARS: '5000' } })
  await mainTask($, h)
  await done($, 'q'.repeat(8000))
  const sum = h.trace(h.learns()[0]!).result.summary
  expect(sum).toBe('q'.repeat(5000) + '<truncated: 8000 chars>')
  const row = h.rows().find((x: any) => x.event === 'text_cap_hit')
  expect(row).toMatchObject({ field: 'summary', chars_before: 8000, chars_after: sum.length, source: 'mod' })
  expect(JSON.stringify(row).includes('qqqq')).toBe(false)
})
test('text cap parsing: default TEXT_HARD_CAP_CHARS, junk keeps it', () => {
  expect(textCapChars(undefined)).toBe(TEXT_HARD_CAP_CHARS)
  expect(textCapChars('x')).toBe(TEXT_HARD_CAP_CHARS)
  expect(textCapChars('0')).toBe(TEXT_HARD_CAP_CHARS)
  expect(textCapChars('1234')).toBe(1234)
  expect(TEXT_HARD_CAP_CHARS).toBe(200_000)
})

// ---- task: the whole (redacted) user request, no 2000 cut (and no 4000 cut in the task state before it) ----
const LONG = (n: number) => 'please refactor the parser module ' + 'w'.repeat(n)
test('task: a 9000-char prompt reaches trace.task complete (state keeps it whole), redacted', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tok = 'ghp_' + 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6'
  const prompt = LONG(9000) + ' ' + tok
  await submit($, prompt)
  await $.turn.start({ text: prompt, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($)
  const task = h.trace(h.learns()[0]!).task
  expect(task).toBe('User request: ' + LONG(9000) + ' [redacted]')
})
test('task: over the hard cap -> head + <truncated: N chars>, one text_cap_hit row (field task)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TEXT_HARD_CAP_CHARS: '5000' } })
  const prompt = LONG(7000)
  await submit($, prompt)
  await $.turn.start({ text: prompt, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($)
  const n = [...prompt].length
  expect(h.trace(h.learns()[0]!).task).toBe('User request: ' + prompt.slice(0, 5000) + `<truncated: ${n} chars>`)
  expect(h.rows().find((x: any) => x.event === 'text_cap_hit' && x.field === 'task')).toMatchObject({ chars_before: n, source: 'mod' })
})

// ---- hot path: tool records are APPENDED (one JSONL line per call, 0600), never the whole list rewritten per call ----
const TOOLS = `${SDIR}/mod-tools-main.jsonl`  // Round 10 / L2: new format, new name (8.3.0 reads mod-tools-main.json)
const TOOLS_830 = `${SDIR}/mod-tools-main.json`
test('append-only tool records: 200 calls -> 200 appends of ONE record each, no full rewrite; trace keeps all, in order', { timeoutMs: 60_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 1; i < 200; i++) tools.push({ tool: 'Bash', command: 'echo ' + i })
  await mainTask($, h, tools)
  const app = h.runs.filter((r: any) => r.argv[0] === '/bin/sh' && r.argv[2] === PRIVATE_APPEND_SH && r.argv[4] === TOOLS)
  const full = h.runs.filter((r: any) => r.argv[0] === '/bin/sh' && r.argv[2] === PRIVATE_WRITE_SH && r.argv[4] === TOOLS)
  expect([app.length, full.length]).toEqual([200, 0])
  expect(Math.max(...app.map((r: any) => r.stdin.length))).toBeLessThan(2000)   // one record, not the growing list
  await done($)
  const st = h.trace(h.learns()[0]!).trajectory
  expect(st.length).toBe(200)
  expect(st.slice(1).map((s: any) => s.tool_input.command)).toEqual(tools.slice(1).map(t => t.command))
})
test('append-only tool records: an old JSON-array file (8.3.0) is still read, new records follow it; a torn last line is skipped', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  const old = [toolRec('Edit', { file_path: '/proj/a.py' }, { filePath: '/proj/a.py' }, false, undefined, 0, 1), toolRec('Bash', { command: 'pytest -q' }, { stdout: 'ok', stderr: '', interrupted: false }, false, undefined, 1, 2)]
  h.put(TOOLS_830, JSON.stringify(old) + '\n{"tool": "Bash", "act')   // the 8.3.0 array (8.3.0 file name) + a torn line
  await $.tool.call({ tool: 'Write', file_path: '/proj/b.py', content: 'z' } as any)
  await done($)
  expect(h.trace(h.learns()[0]!).trajectory.map((s: any) => s.tool)).toEqual(['Edit', 'Bash', 'Write'])
})
test('parseToolRecs: array line, JSONL lines, blanks and junk', () => {
  expect(parseToolRecs('[{"tool":"A"},{"tool":"B"}]\n{"tool":"C"}\n\n{bad\n{"tool":"D"}\n').map((r: any) => r.tool)).toEqual(['A', 'B', 'C', 'D'])
  expect(parseToolRecs('')).toEqual([])
})


// ---- ACE_TRACE_SINK=file:<dir>: the finished trace (the POST /traces body) goes to a file, NOTHING is sent ----
const SINK = '/home/u/sink'
const launches = (h: any) => h.runs.filter((r: any) => r.argv.some((a: any) => typeof a === 'string' && (a.endsWith('learn.js') || a === 'learn' || a.includes('subprocess.Popen'))))
test('sink: the trace lands in <dir>/ace-trace-<idempotency-key>.json, no launcher / engine / ace-cli / queue run, one trace_sinked row; search unaffected', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: 'file:' + SINK } })
  await mainTask($, h)
  await done($)
  expect(launches(h).length).toBe(0)                                 // 0 HTTP: nothing that could send is started
  expect(h.runs.some((r: any) => r.argv.some((a: any) => String(a).includes('ace_trace_queue')) && !r.argv.includes('--auth-held'))).toBe(false)
  expect(h.searches().length).toBe(1)                                // search is read-only and stays
  const f = [...h.files.keys()].filter(k => k.startsWith(SINK + '/'))
  expect(f.length).toBe(1)
  expect(/\/ace-trace-[0-9a-f-]{36}\.json$/.test(f[0]!)).toBe(true)
  const body = JSON.parse(h.files.get(f[0]!)!)
  expect([body.task.startsWith('User request: '), body.trajectory.length, body.retrieval_id, Array.isArray(body.applied_log_ids)]).toEqual([true, 2, JSON.parse(S8).retrieval_id, true])
  expect(body.trajectory[1].tool_input.command).toBe('pytest -q')
  const row = h.rows().find((x: any) => x.event === 'trace_sinked')
  expect(row).toMatchObject({ path: f[0], bytes: h.files.get(f[0]!)!.length, steps: 2, source: 'mod' })
  expect(JSON.stringify(row).includes('pytest')).toBe(false)
  expect([...h.files.keys()].some(k => /learn-inflight-main\.lock$/.test(k))).toBe(false)  // the learn lock is released
  // F9: the sink write never chmods an existing dir (SINK_WRITE_SH, not PRIVATE_WRITE_SH; real-fs test: tests/test_python_sink_round5.py)
  expect(h.runs.filter((r: any) => r.argv[4] === f[0]).map((r: any) => r.argv[2])).toEqual([SINK_WRITE_SH])
})
test('sink: a set but invalid value (no file:<absolute dir>) still sends nothing (fail closed) and logs why', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: 'http://evil' } })
  await mainTask($, h)
  await done($)
  expect(launches(h).length).toBe(0)
  expect(h.rows().find((x: any) => x.event === 'trace_sinked')).toMatchObject({ error: 'invalid_sink', path: null })
})
test('no sink: unchanged, the detached learn is launched', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await done($)
  expect(h.learns().length).toBe(1)
  expect(h.rows().some((x: any) => x.event === 'trace_sinked')).toBe(false)
})

// ---- opt-out ACE_TRACE_FULL_STEPS=0: steps as in 8.3.0 (action/result summaries only), nothing full recorded or sent ----
// Decision: no 50-step cap in this mode either (summaries are <= ~700 bytes a step; the hard byte cap still bounds the trace).
for (const v of ['0'])
  test('opt-out ACE_TRACE_FULL_STEPS=' + v + ': no tool_input / tool_response in the trace, none persisted in the tool records', async ($, on) => {
    const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_FULL_STEPS: v } })
    await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'OLDSTR', new_string: 'NEWSTR' }, { tool: 'Bash', command: 'big' }])
    const recs = parseToolRecs(h.files.get(TOOLS) ?? '')  // (`hay`, <= 2000 chars of input for the used check, stays local as in 8.3.0)
    expect([recs.length, recs.some((r: any) => 'input' in r || 'output' in r), (h.files.get(TOOLS) ?? '').includes('y'.repeat(100))]).toEqual([2, false, false])  // the 8.3.0 result summary keeps <= 60
    await done($)
    const t = h.trace(h.learns()[0]!)
    expect(t.trajectory.map((s: any) => Object.keys(s).sort())).toEqual([0, 1].map(() => ['action', 'duration_ms', 'end_ms', 'result', 'start_ms', 'step', 'tool']))
    expect([t.trajectory[0].action, t.trajectory[1].result]).toEqual(['Edited x.py', 'y'.repeat(60) + '...'])
  })
for (const env of [{}, { ACE_TRACE_FULL_STEPS: '1' }, { ACE_TRACE_FULL_STEPS: 'yes' }])
  test('full steps stay ON by default / for any other value: ' + JSON.stringify(env), async ($, on) => {
    const h = host(on, { search: () => ({ stdout: S8 }), env })
    await mainTask($, h)
    await done($)
    expect(h.trace(h.learns()[0]!).trajectory[1].tool_input.command).toBe('pytest -q')
  })
test('buildTrace fullSteps:false drops the payloads even of records that carry them (a toggle mid-task)', () => {
  const r = toolRec('Bash', { command: 'ls' }, { stdout: 'a', stderr: '', interrupted: false }, false, undefined, 0, 1)
  const t = buildTrace({ userPrompt: 'p', answer: 'a', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools: [r], fullSteps: false } as any).trace
  expect(['tool_input' in t.trajectory[0], 'tool_response' in t.trajectory[0]]).toEqual([false, false])
})

// ---- round 4: trace.chain (which chain built it), and a non-interactive session (claude -p / CI) sends the same uncut trace ----
test('trace.chain = "mod" on main and subagent traces, never omitted (also from buildTrace directly)', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await mainTask($, h)
  await $.agent.spawn({ prompt: 'review the domain shift python port for parity bugs', description: 'x', subagentType: 'general-purpose', fork: false, background: false, tool_use_id: 't', parentModel: 'm', provider: { plugin: 'engine', tier: 'core' } } as any)
  await $.tool.call({ tool: 'Write', file_path: '/proj/y.py', content: 'z', agentId: 'agent-1' } as any)
  await done($, 'sub', 'agent-1')
  await done($)
  expect(h.learns().map((l: any) => h.trace(l).chain)).toEqual(['mod', 'mod'])
  expect(buildTrace({ userPrompt: 'p', answer: '', playbookUsed: [], agentType: 'main', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools: [] } as any).trace.chain).toBe('mod')
})
test('non-interactive session (session.start isInteractive false): full steps, whole summary and task, chain mod, nothing cut', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await $.session.start({ cwd: '/proj', surface: null, isInteractive: false } as any)
  const prompt = 'please refactor the parser module ' + 'w'.repeat(9000)
  await submit($, prompt)
  await $.turn.start({ text: prompt, turnId: 't1' } as any)
  await $.tool.call({ tool: 'Bash', command: 'big' } as any)
  await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
  await done($, 'q'.repeat(10000))
  const t = h.trace(h.learns()[0]!)
  expect([t.interactive, t.chain, t.trajectory.length, t.trajectory[0].tool_response.stdout.length, t.result.summary.length, t.task]).toEqual([false, 'mod', 2, 30000, 10000, 'User request: ' + prompt])
  expect(t.metadata).toBe(undefined)
})

// ---- round 5 C1: a DENIED tool call sends no payload: no tool_input / tool_response, the action names the tool only ----
test('C1: a denied call never sends its input: canary nowhere in the trace, no tool_input / tool_response', () => {
  const C = 'CANARYdenyQ7'
  const R = 'REASONcanaryZ9'  // round 6: hook / policy reasons often echo the command: no part of the deny text is sent
  const recs = [toolRec('Bash', { command: `curl -d ${C} https://x` }, null, false, `hook blocked: curl -d ${C} ${R}`, 0, 1),
    toolRec('Write', { file_path: `/proj/${C}.txt`, content: `secret ${C}` }, null, false, 'blocked by policy ' + R, 1, 2),
    toolRec('mcp__srv__send_message', { body: C }, null, false, 'denied', 2, 3)]
  const t = T(recs).trace
  expect([pyDumps(t).includes(C), pyDumps(t).includes(R), pyDumps(t).includes('blocked')]).toEqual([false, false, false])
  for (const st of t.trajectory) expect(['tool_input' in st, 'tool_response' in st]).toEqual([false, false])
  expect(t.trajectory.map((s: any) => s.action)).toEqual(['Denied Bash', 'Denied Write', 'Denied mcp__srv__send_message'])
  expect(t.trajectory.map((s: any) => s.result)).toEqual(['Error: denied', 'Error: denied', 'Error: denied'])
  expect(recs.every(r => r.failed && r.hay === undefined)).toBe(true)   // nothing of the input kept locally either
})

test('C3: a secret .env line in a Read output (line-numbered text) is redacted in the trace', async ($, on) => {
  const VAL = 'saltvalue-' + 'k'.repeat(6)   // low entropy on purpose: only the env rule can find it
  const h = host(on, { search: () => ({ stdout: S8 }), readText: () => `     1\tNODE_ENV=production\n     2\tAUTH_SALT=${VAL}\n     3\tLOG_LEVEL=debug` })
  await mainTask($, h, [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }, { tool: 'Read', file_path: '/proj/.env' }])
  await done($)
  const out = h.trace(h.learns()[0]!).trajectory[1].tool_response
  expect([out.includes(VAL), out.includes('     2\tAUTH_SALT=[redacted:env]'), out.includes('NODE_ENV=production')]).toEqual([false, true, true])
})

// ---- round 5 C4: one switch helper: 0 / false / off / no (any case) turn a switch off; off = the COMPLETE 8.3.0 behaviour ----
test('C4: switchOff / switchOn helpers', () => {
  for (const v of ['0', 'false', 'FALSE', ' off ', 'No']) expect([v, switchOff(v)]).toEqual([v, true])
  for (const v of [undefined, '', '1', 'yes', 'true', 'auto']) expect([v, switchOff(v)]).toEqual([v, false])
  for (const v of ['1', 'true', 'ON', ' yes ']) expect([v, switchOn(v)]).toEqual([v, true])
  for (const v of [undefined, '', '0', 'no', 'maybe']) expect([v, switchOn(v)]).toEqual([v, false])
})
for (const v of ['false', 'OFF', 'No'])
  test(`C4: ACE_TRACE_FULL_STEPS=${v} -> 8.3.0 complete: summaries only, task / summary cut at 2000, the 50-step rule`, async ($, on) => {
    const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_FULL_STEPS: v } })
    const prompt = 'please refactor the parser module ' + 'w'.repeat(3000)
    await submit($, prompt)
    await $.turn.start({ text: prompt, turnId: 't1' } as any)
    await $.tool.call({ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' } as any)
    for (let i = 0; i < 59; i++) await $.tool.call({ tool: 'Bash', command: 'echo ' + i } as any)
    await done($, 'q'.repeat(5000))
    const t = h.trace(h.learns()[0]!)
    expect(t.trajectory.some((s: any) => 'tool_input' in s || 'tool_response' in s)).toBe(false)
    expect([t.task.length, t.result.summary.length]).toEqual(['User request: '.length + 2000, 2000])
    expect([t.trajectory[0]._truncation_marker, t.trajectory[0].original_length, t.metadata.trace_truncated]).toEqual([true, 60, true])
  })
test('C4: off keeps the 8.3.0 handback cap of 4000', () => {
  const t = buildTrace({ userPrompt: 'p', answer: 'h'.repeat(9000), playbookUsed: [], agentType: 'x', appliedLogIds: [], nowIso: 'x', effort: 'normal', tools: [], fullSteps: false, legacySummaryCap: 4000 } as any).trace
  expect(t.result.summary.length).toBe(4000)
})
test('C4: ACE_AUTO_UPDATE=off / false / no also turn the update off (shared helper)', () => {
  const t = JSON.stringify({ policy: { min_plugin_version: '9.0.0' }, at: 1_800_000_000 })
  for (const v of ['off', 'False', 'NO']) expect(updateGate({ optOut: switchOff(v), policyText: t, version: '8.1.4', nowMs: 1_800_000_000_000, mode: 'click' })).toMatchObject({ go: false, why: 'opt_out' })
})

// ---- round 5: the server kill switch full_steps (search response, default ON, the server can only switch it OFF) ----
// false -> the next trace takes the opt-out path (8.3.0 steps + text caps); missing keeps the stored value; non-bool keeps it
// on + full_steps_invalid (no value); env 0/false/off/no always wins; a server true never re-enables an env opt-out.
const withFs = (v: unknown) => { const o = JSON.parse(S8); if (v !== undefined) o.full_steps = v; return JSON.stringify(o) }
const FS_FILE = `${SDIR.slice(0, SDIR.indexOf('/projects/'))}/full-steps.json`
async function ksTrace($: any, h: any) {
  await mainTask($, h)
  await done($, 's'.repeat(5000))
  const t = h.trace(h.learns().at(-1)!)
  return { full: 'tool_input' in t.trajectory[1], summary: t.result.summary.length }
}
test('kill switch: full_steps:false from the server -> next trace without tool_input/tool_response and with the 8.3.0 summary cap', async ($, on) => {
  let v: unknown = false
  const h = host(on, { search: () => ({ stdout: withFs(v) }) })
  expect(await ksTrace($, h)).toEqual({ full: false, summary: 2000 })
  expect(JSON.parse(h.files.get(FS_FILE)!).on).toBe(false)
  v = undefined  // missing field: the stored false stays
  expect(await ksTrace($, h)).toEqual({ full: false, summary: 2000 })
  v = true       // the server switches it back on
  expect(await ksTrace($, h)).toEqual({ full: true, summary: 5000 })
})
for (const bad of ['false', 0, null, 'off', [false]])
  test('kill switch: a non-bool full_steps (' + JSON.stringify(bad) + ') keeps full steps on and logs full_steps_invalid without the value', async ($, on) => {
    const h = host(on, { search: () => ({ stdout: withFs(bad) }) })
    expect(await ksTrace($, h)).toEqual({ full: true, summary: 5000 })
    const rows = h.rows().filter((x: any) => x.event === 'full_steps_invalid')
    expect([rows.length, 'value' in rows[0]]).toEqual([1, false])
  })
for (const env of ['0', 'OFF', 'no'])
  test('kill switch: env ACE_TRACE_FULL_STEPS=' + env + ' wins over a server true', async ($, on) => {
    const h = host(on, { search: () => ({ stdout: withFs(true) }), env: { ACE_TRACE_FULL_STEPS: env } })
    expect(await ksTrace($, h)).toEqual({ full: false, summary: 2000 })  // the text cap shows the trace path, not only the record drop
  })
for (const text of ['{broken', '{"on":false}', JSON.stringify({ on: false, at: 1 }), '{"on":"no","at":9999999999}'])
  test('kill switch: a broken / stale / non-bool stored file keeps full steps on: ' + text, async ($, on) => {
    const h = host(on, { search: () => ({ stdout: S8 }) })
    h.files.set(FS_FILE, text)
    expect((await ksTrace($, h)).full).toBe(true)
  })
test('kill switch: storedFullSteps / serverFullSteps', () => {
  expect([storedFullSteps(undefined, 1e12), storedFullSteps(JSON.stringify({ on: false, at: 1e9 }), 1e12), storedFullSteps(JSON.stringify({ on: false, at: 1e9 - 8 * 86400 }), 1e12)]).toEqual([true, false, true])
  expect([serverFullSteps({ full_steps: false }), serverFullSteps({}), serverFullSteps({ full_steps: 'false' })]).toEqual([false, undefined, 'invalid'])
})

// ---- round 5 F13: tool_input is an allowlist of the tool's own input keys (event/meta keys never reach the trace) ----
const META = { tool: 'X', agentId: 'a1', toolUseId: 'toolu_01abc', tool_use_id: 'toolu_01abc', consent: { granted: true }, requestMeta: { k: 'v' }, sessionId: 's' }
test('F13: built-in tools keep only their documented input keys', () => {
  const b = toolRec('Bash', { ...META, tool: 'Bash', command: 'ls', description: 'list', timeout: 5, run_in_background: false }, { stdout: '', stderr: '' }, false, undefined, 0, 1)
  expect(b.input).toEqual({ command: 'ls', description: 'list', timeout: 5, run_in_background: false })
  const e = toolRec('Edit', { ...META, tool: 'Edit', file_path: '/p/x', old_string: 'a', new_string: 'b', replace_all: true, extra: 1 }, {}, false, undefined, 0, 1)
  expect(e.input).toEqual({ file_path: '/p/x', old_string: 'a', new_string: 'b', replace_all: true })
})
test('F13: an MCP / unknown tool keeps its arguments, never the event or request metadata', () => {
  const m = toolRec('mcp__linear__save_comment', { ...META, tool: 'mcp__linear__save_comment', issue: 'LIN-1', body: 'hi' }, {}, false, undefined, 0, 1)
  expect(m.input).toEqual({ issue: 'LIN-1', body: 'hi' })
})

// ---- round 5 F14: the user prompt is redacted when it is written to the task state (not only when the trace is built) ----
test('F14: mergeState redacts a new user_prompt; the stored one is kept as is', () => {
  const key = ['AKIA', 'Q'.repeat(16)].join('')
  const st = mergeState({}, { userPrompt: 'deploy with ' + key + ' now' })
  expect([st.user_prompt.includes(key), st.user_prompt.includes('[redacted')]).toEqual([false, true])
  expect(mergeState(st, { ids: [] }).user_prompt).toBe(st.user_prompt)
})

// ---- round 5 F8: a running byte budget per agent key while recording (2 x ACE_TRACE_HARD_CAP_BYTES): the longest payloads in
// memory become '<truncated: N bytes>' early (capTrace order); every step stays (outcome unchanged); one text-free row per trim.
test('F8: many large steps stay within the in-memory budget; all steps and failures kept; tool_budget_hit logged', { timeoutMs: 60_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_HARD_CAP_BYTES: '20000' } })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 40; i++) tools.push({ tool: 'Write', file_path: '/proj/w' + i + '.py', content: String(i % 10).repeat(3000) })
  await mainTask($, h, tools)
  const rows = h.rows().filter((x: any) => x.event === 'tool_budget_hit')
  expect(rows.length).toBeGreaterThan(0)
  expect(rows.every((r: any) => r.bytes_after <= 40000 && r.bytes_before > 40000 && r.key === 'main' && r.source === 'mod')).toBe(true)
  expect(JSON.stringify(rows).includes('3333')).toBe(false)
  await done($)
  const t = h.trace(h.learns()[0]!)
  expect(t.trajectory.filter((s: any) => !s._truncation_marker).length + (t.trajectory[0]._truncation_marker ? t.trajectory[0].steps_dropped : 0)).toBe(41)
  expect(JSON.stringify(t).includes('<truncated: ')).toBe(true)
})
test('F8: trimPayloads cuts the longest payloads first until under the budget', () => {
  const recs: any[] = [{ tool: 'A', input: 'x'.repeat(100), output: 'y'.repeat(5000) }, { tool: 'B', input: 'z'.repeat(3000), output: 'ok' }]
  const bytes = recs.reduce((n, r) => n + JSON.stringify(r).length, 0)
  const hit = trimPayloads(recs, 4000, bytes)
  expect([recs[0].output, recs[1].input, recs[0].input]).toEqual(['<truncated: 5002 bytes>', 'z'.repeat(3000), 'x'.repeat(100)])
  expect(hit).toMatchObject({ bytes_before: bytes, records: 2, outputs_truncated: 1 })
  expect(hit.bytes_after).toBe(recs.reduce((n, r) => n + JSON.stringify(r).length, 0))
})

// ---- round 6 (item 4): $.fs.read stops at 4 MiB, so the tool-record file never grows past TOOLS_FILE_MAX (3 MiB): at the budget
// the trimmed list is rewritten; a reload mid-task (cache gone) still reads every step from the file.
test('F8/4: a task with 6 MB of tool output keeps its record file under 3 MiB and all steps readable after a reload', { timeoutMs: 60_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_HARD_CAP_BYTES: String(64 * 1024 * 1024) } })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 60; i++) tools.push({ tool: 'Write', file_path: '/proj/w' + i + '.py', content: String(i % 10).repeat(100_000) })
  await mainTask($, h, tools)
  const text = h.files.get(TOOLS) ?? ''
  expect(text.length).toBeLessThan(TOOLS_FILE_MAX + 200_000)
  const recs = parseToolRecs(text)
  expect([recs.length, recs[0].tool, recs.at(-1).tool]).toEqual([61, 'Edit', 'Write'])
})

// ---- round 8 W2: at the budget the records are trimmed to ~75 % of it, so the next calls append again (few rewrites) ----
const utf8 = (s: string) => new TextEncoder().encode(s).length
test('W2: 200 calls x 50 KB -> only a few full rewrites of the record file', { timeoutMs: 120_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 199; i++) tools.push({ tool: 'Write', file_path: '/proj/w' + i + '.py', content: String(i % 10).repeat(50_000) })
  await mainTask($, h, tools)
  const rewrites = h.runs.filter((r: any) => r.argv[0] === '/bin/sh' && r.argv[2] === PRIVATE_WRITE_SH && r.argv[4] === TOOLS).length
  expect(rewrites).toBeLessThanOrEqual(15)  // measured: 137 before (trim to the budget), see report
  expect(parseToolRecs(h.files.get(TOOLS) ?? '').length).toBe(200)
})
// ---- round 8 W3: the budget counts UTF-8 bytes ($.fs.read reads 4 MiB of BYTES): CJK output keeps the file under the limit ----
test('W3: CJK tool output: the record file stays under TOOLS_FILE_MAX in UTF-8 bytes', { timeoutMs: 120_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_HARD_CAP_BYTES: String(64 * 1024 * 1024) } })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 60; i++) tools.push({ tool: 'Write', file_path: '/proj/c' + i + '.md', content: '東京大阪'.repeat(10_000) })
  await mainTask($, h, tools)
  const text = h.files.get(TOOLS) ?? ''
  expect(utf8(text)).toBeLessThan(TOOLS_FILE_MAX + 200_000)
  expect(parseToolRecs(text).length).toBe(61)
})
test('W3: utf8Len counts bytes', () => {
  expect([utf8Len('abc'), utf8Len('ä'), utf8Len('東'), utf8Len('😀')]).toEqual([3, 2, 3, 4])
})

// ---- round 8 I3: ACE_TRACE_HARD_CAP_BYTES is clamped below the queue's MAX_FILE (5 MiB) minus room for the entry ----
test('I3: hardCapBytes(20 MiB) is clamped to TRACE_HARD_CAP_MAX; smaller values stay', () => {
  expect([hardCapBytes(String(20 * 1024 * 1024)), hardCapBytes('600'), TRACE_HARD_CAP_MAX]).toEqual([TRACE_HARD_CAP_MAX, 600, 5 * 1024 * 1024 - 256 * 1024])
})

// ---- round 8 I4: the full-steps switch is resolved once per load (not per tool call); toolRec skips the payload work when off ----
test('I4: 40 tool calls read ACE_TRACE_FULL_STEPS once', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 39; i++) tools.push({ tool: 'Bash', command: 'echo ' + i })
  await mainTask($, h, tools)
  expect(h.envAsked.filter((n: string) => n === 'ACE_TRACE_FULL_STEPS').length).toBe(1)
})
test('I4: toolRec(full=false) builds no tool_input / tool_response at all', () => {
  const r = toolRec('Bash', { command: 'ls' }, { stdout: 'a', stderr: '', interrupted: false }, false, undefined, 0, 1, undefined, false)
  expect(['input' in r, 'output' in r, r.action]).toEqual([false, false, 'ls :: ls'])
})

// ---- round 9 N5: payloads first, then the oldest records' hay; nothing left to cut -> append without rewrite, logged ONCE per task ----
test('N5: a budget the summaries alone exceed -> hay trimmed, then plain appends, one tool_budget_exhausted row', { timeoutMs: 60_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_HARD_CAP_BYTES: '1000' } })   // budget 2000 bytes
  const tools: any[] = [{ tool: 'Edit', file_path: '/proj/x.py', old_string: 'a', new_string: 'b' }]
  for (let i = 0; i < 39; i++) tools.push({ tool: 'Bash', command: 'echo some words to keep ' + i })
  await mainTask($, h, tools)
  const rewrites = h.runs.filter((r: any) => r.argv[0] === '/bin/sh' && r.argv[2] === PRIVATE_WRITE_SH && r.argv[4] === TOOLS).length
  const exhausted = h.rows().filter((x: any) => x.event === 'tool_budget_exhausted')
  expect(rewrites).toBeLessThanOrEqual(3)
  expect([exhausted.length, exhausted[0].key, JSON.stringify(exhausted).includes('some words')]).toEqual([1, 'main', false])
  const recs = parseToolRecs(h.files.get(TOOLS) ?? '')
  expect(recs.length).toBe(40)
  expect(recs.slice(0, 5).every((r: any) => r.hay === undefined)).toBe(true)   // the oldest records lost their hay first
})
test('N5: trimPayloads cuts the oldest hay after the payloads', () => {
  const recs: any[] = [{ tool: 'A', hay: 'h'.repeat(500), output: 'y'.repeat(100) }, { tool: 'B', hay: 'g'.repeat(500) }]
  const bytes = recs.reduce((n, r) => n + JSON.stringify(r).length + 1, 0)
  const hit = trimPayloads(recs, bytes - 550, bytes)  // the payload (~80) + the first hay (~509) suffice
  expect([recs[0].hay, typeof recs[1].hay, recs[0].output.startsWith('<truncated')]).toEqual([undefined, 'string', true])
  expect(hit.hay_dropped).toBe(1)
})

// ---- Round 10 / M2: summarizeResult redacts nested values before it stringifies (MCP answers) ----
test('Round 10 / M2: nested error / data values carry no secret into the result summary', () => {
  const tok = ['gh', 'p_', 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'].join('')
  expect(summarizeResult('mcp__x__y', { data: { items: [{ note: 'bad ' + tok }] } }).includes(tok)).toBe(false)
  expect(summarizeResult('mcp__x__y', { result: { password: 'hunter22xx' } }).includes('hunter22xx')).toBe(false)
})

// ---- Round 10 / L2: an 8.3.0 session (same session id) wrote mod-tools-main.json: still read, and both names are cleaned up ----
test('L2: records of the 8.3.0 file name come first, new ones follow in .jsonl; a cleared task removes both files', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }) })
  await submit($)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  h.put(TOOLS_830, JSON.stringify([toolRec('Edit', { file_path: '/proj/a.py' }, { filePath: '/proj/a.py' }, false, undefined, 0, 1)]))
  await $.tool.call({ tool: 'Write', file_path: '/proj/b.py', content: 'z' } as any)
  expect([h.files.has(TOOLS), JSON.parse(h.files.get(TOOLS_830)!).length]).toEqual([true, 1])
  await done($)
  expect(h.trace(h.learns()[0]!).trajectory.map((s: any) => s.tool)).toEqual(['Edit', 'Write'])
  expect([h.files.has(TOOLS), h.files.has(TOOLS_830)]).toEqual([false, false])
})

// ---- Round 10 / T2: the stored upvote gate goes stale after 7 days; without one the upvote follows the downvote gate ----
test('Round 10 / T2: storedUpvote: stale (8 d) or missing at -> undefined (the downvote gate decides); fresh -> its value', () => {
  const now = 1_800_000_000_000
  expect([storedUpvote(JSON.stringify({ on: true, at: now / 1000 - 8 * 86400 }), now), storedUpvote(JSON.stringify({ on: false }), now),
    storedUpvote(JSON.stringify({ on: true, at: now / 1000 - 3600 }), now), storedUpvote(JSON.stringify({ on: false, at: now / 1000 - 3600 }), now)])
    .toEqual([undefined, undefined, true, false])
})

// ---- Round 10 / T4: the mod sink fails closed on the same invalid values as the Python chain, and on a failed write ----
for (const bad of ['http://evil', 'file:relative/dir', 'file:', '/abs/without/scheme'])
  test('Round 10 / T4: sink value ' + JSON.stringify(bad) + ' -> nothing sent, invalid_sink, no file', async ($, on) => {
    const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: bad } })
    await mainTask($, h)
    await done($)
    expect([launches(h).length, h.rows().find((x: any) => x.event === 'trace_sinked')?.error, [...h.files.keys()].some(k => k.includes('ace-trace-'))]).toEqual([0, 'invalid_sink', false])
  })
test('Round 10 / T4: a failed sink write sends nothing and logs write_failed', async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_SINK: 'file:' + SINK }, sinkFail: true })
  await mainTask($, h)
  await done($)
  expect([launches(h).length, h.rows().find((x: any) => x.event === 'trace_sinked')?.error]).toEqual([0, 'write_failed'])
})

// ---- Round 11 / I2: the budget rewrite carries the 8.3.0 records into .jsonl, so the old .json goes (a reload would read them twice) ----
test('Round 11 / I2: after a budget rewrite the 8.3.0 file is gone and every record is on disk exactly once', { timeoutMs: 60_000 }, async ($, on) => {
  const h = host(on, { search: () => ({ stdout: S8 }), env: { ACE_TRACE_HARD_CAP_BYTES: '20000' } })
  await submit($)
  await $.turn.start({ text: HUMAN, turnId: 't1' } as any)
  h.put(TOOLS_830, JSON.stringify([toolRec('Edit', { file_path: '/proj/old.py' }, { filePath: '/proj/old.py' }, false, undefined, 0, 1)]))
  for (let i = 0; i < 20; i++) await $.tool.call({ tool: 'Write', file_path: '/proj/w' + i + '.py', content: String(i % 10).repeat(3000) } as any)
  expect(h.rows().some((x: any) => x.event === 'tool_budget_hit')).toBe(true)
  expect(h.files.has(TOOLS_830)).toBe(false)
  const recs = parseToolRecs(h.files.get(TOOLS) ?? '')
  expect([recs.length, recs.filter((r: any) => r.tool === 'Edit').length]).toEqual([21, 1])
})
