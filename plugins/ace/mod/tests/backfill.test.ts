// 8.2.0 session reader (pure library, not wired to any send path): a Claude Code transcript JSONL -> one task per real user
// prompt -> the SAME ToolRec / buildTrace / taskOutcome the live learn path uses. Hermetic synthetic transcripts only.
import { expect, test } from 'claude-code/testing'
import { readSession, readSessionLines, selectTasks, taskKey } from '../lib/backfill.ts'

let n = 0
const ts = () => new Date(Date.UTC(2026, 0, 1) + (n += 1000)).toISOString()
const J = (o: any) => JSON.stringify({ sessionId: 'sess-1', timestamp: ts(), isSidechain: false, ...o })
const prompt = (text: unknown, extra: any = {}) => J({ type: 'user', message: { role: 'user', content: text }, ...extra })
const asst = (...blocks: any[]) => J({ type: 'assistant', message: { role: 'assistant', content: blocks } })
const use = (id: string, name: string, input: any) => ({ type: 'tool_use', id, name, input })
const text = (t: string) => ({ type: 'text', text: t })
const ok = (id: string, content: string, toolUseResult: any = { stdout: content, stderr: '', interrupted: false }) =>
  J({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content }] }, toolUseResult })
const fail = (id: string, code: number, err = 'boom') => J({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: `Exit code ${code}\n${err}`, is_error: true }] }, toolUseResult: `Error: Exit code ${code}\n${err}` })
const edit = (id: string, file = '/repo/src/a.ts') => [asst(use(id, 'Edit', { file_path: file, old_string: 'a', new_string: 'b' })), ok(id, 'The file has been updated', { filePath: file })]
const bash = (id: string, cmd: string) => [asst(use(id, 'Bash', { command: cmd })), ok(id, 'ok')]
const doc = (...lines: (string | string[])[]) => lines.flat().join('\n') + '\n'
const FIX = 'please fix the failing parser in src/a.ts so the tests pass again'
const NEXT = 'now add a retry to the upload helper and run the tests once more'

test('one task per real user prompt up to the next one; tool results never split a task; the trace is the live shape', () => {
  const r = readSession(doc(prompt(FIX), edit('t1'), bash('t2', 'pytest -q'), asst(text('Fixed the parser, tests pass.')),
    prompt(NEXT), edit('t3', '/repo/src/up.ts'), bash('t4', 'pytest -q'), asst(text('Retry added.'))))
  expect(r.tasks.length).toBe(2)
  expect(r.tasks.map(t => t.index)).toEqual([0, 1])
  expect(r.tasks.map(t => t.sessionId)).toEqual(['sess-1', 'sess-1'])
  const t = r.tasks[0].trace
  expect(t.task).toBe(`User request: ${FIX}`)
  expect(t.trajectory.map((s: any) => s.tool)).toEqual(['Edit', 'Bash'])
  expect(t.trajectory[0]).toMatchObject({ step: 1, tool: 'Edit', action: expect.any(String), result: 'Success' })
  expect(t.result).toMatchObject({ success: true, failed_steps: 0, output: 'Executed 2 tool calls', summary: 'Fixed the parser, tests pass.' })
  expect(t.playbook_used).toEqual([])
  expect(t.applied_log_ids).toEqual([])
  expect(t.agent_type).toBe('main')
  // never the session, never an unknown server field in the body
  for (const k of ['session_id', 'source', 'agent_id', 'retrieval_id', 'conversation_id', 'occurred_at']) expect(k in t).toBe(false)
  expect(r.tasks[0]).toMatchObject({ success: true, steps: 2, decisive: 2 })
  expect(r.stats).toMatchObject({ prompts: 2, tasks: 2, trivial: 0, noWork: 0, malformed: 0 })
})

test('skipped: tool-result-only user lines, machine prompts, meta lines, compact summaries, sidechains; they never start a task', () => {
  const r = readSession(doc(prompt(FIX), edit('t1'),
    prompt('<task-notification><task-id>x</task-id></task-notification>'),
    prompt('<system-reminder>only a reminder</system-reminder>'),
    prompt('<command-name>/compact</command-name>'),
    prompt('meta text that is not a person typing at all', { isMeta: true }),
    prompt('This session is being continued from a previous conversation', { isCompactSummary: true }),
    J({ type: 'user', isSidechain: true, message: { role: 'user', content: 'subagent prompt that does real looking work here' } }),
    J({ type: 'assistant', isSidechain: true, message: { role: 'assistant', content: [use('s1', 'Bash', { command: 'rm -rf x' })] } }),
    J({ type: 'attachment', attachment: { type: 'x' } }), J({ type: 'queue-operation' }), J({ type: 'ai-title' }),
    bash('t2', 'pytest -q'), asst(text('done'))))
  expect(r.tasks.length).toBe(1)
  expect(r.tasks[0].trace.trajectory.map((s: any) => s.tool)).toEqual(['Edit', 'Bash'])  // the sidechain Bash is not in it
  expect(r.stats).toMatchObject({ prompts: 1, tasks: 1 })
  expect(r.stats.sidechain).toBeGreaterThanOrEqual(2)
  expect(r.stats.machine).toBeGreaterThanOrEqual(3)
})

test('a user prompt as content blocks (text + image) is one prompt; a leading system-reminder is stripped', () => {
  const blocks = [{ type: 'text', text: '<system-reminder>ctx</system-reminder>' }, { type: 'text', text: FIX }, { type: 'image', source: {} }]
  const r = readSession(doc(prompt(blocks), edit('t1'), bash('t2', 'pytest -q')))
  expect(r.tasks.length).toBe(1)
  expect(r.tasks[0].trace.task).toBe(`User request: ${FIX}`)
  const r2 = readSession(doc(prompt(`<system-reminder>ctx</system-reminder>\n${FIX}`), edit('t1')))
  expect(r2.tasks[0].trace.task).toBe(`User request: ${FIX}`)
})

test('trivial prompts and tasks without substantial work are skipped and counted; their index still counts', () => {
  const r = readSession(doc(prompt('hi'), asst(text('hello')),
    prompt('/ace:ace-status'), asst(text('x')),
    prompt('list the files in the current folder for me please'), bash('t1', 'ls'),
    prompt('what does this function do in the parser module?'), asst(text('it parses')),
    prompt('explain the architecture of the whole thing to me in detail'), asst(text('long answer with no tool at all')),
    prompt(FIX), edit('t2')))
  expect(r.tasks.length).toBe(1)
  expect(r.tasks[0].index).toBe(5)  // six real prompts, the sixth kept: a stable index whatever gets filtered
  expect(r.stats.prompts).toBe(6)
  expect(r.stats.trivial).toBe(4)
  expect(r.stats.noWork).toBe(1)
})

test('outcome: an unrecovered failed decisive step fails the task, a later ok step of the same key recovers it', () => {
  const failed = readSession(doc(prompt(FIX), asst(use('t1', 'Edit', { file_path: '/repo/src/a.ts', old_string: 'a', new_string: 'b' })),
    J({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't1', content: 'String to replace not found', is_error: true }] }, toolUseResult: 'Error: String to replace not found' }),
    bash('t2', 'pytest -q')))
  expect(failed.tasks[0].success).toBe(false)
  expect(failed.tasks[0].trace.result.success).toBe(false)
  expect(failed.tasks[0].trace.result.failed_steps).toBe(1)
  const recovered = readSession(doc(prompt(FIX),
    asst(use('t1', 'Bash', { command: 'pytest -q' })), fail('t1', 1, 'AssertionError'),
    ...edit('t2'), asst(use('t3', 'Bash', { command: 'pytest -q' })), ok('t3', '5 passed')))
  expect(recovered.tasks[0].success).toBe(true)
  const denied = readSession(doc(prompt(FIX), edit('t0'),
    asst(use('t1', 'Bash', { command: 'git push origin main' })),
    J({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't1', content: "The user doesn't want to proceed with this tool use. The tool use was rejected", is_error: true }] }, toolUseResult: 'rejected' })))
  expect(denied.tasks[0].trace.trajectory[1].result).toMatch(/^Error:/)
})

test('a tool call whose result never arrived (the session ended) is an interrupted last step: the task is not a success', () => {
  const r = readSession(doc(prompt(FIX), edit('t1'), asst(use('t2', 'Bash', { command: 'pytest -q' }))))
  expect(r.tasks.length).toBe(1)
  expect(r.tasks[0].success).toBe(false)
})

test('redaction: secrets in the prompt, the answer and the tool text never reach the trace', () => {
  const r = readSession(doc(prompt(`${FIX} with password=hunter2hunter2 and token ghp_abcdefgh12345678`), edit('t1'),
    asst(use('t2', 'Bash', { command: 'curl -u admin:s3cretpass https://x.test' })), ok('t2', 'api_key=ABCDEF123456 done'),
    asst(text('the key is sk-abcdefgh12345678 ok'))))
  const s = JSON.stringify(r.tasks[0].trace)
  for (const leak of ['hunter2hunter2', 'ghp_abcdefgh12345678', 's3cretpass', 'ABCDEF123456', 'sk-abcdefgh12345678']) expect([leak, s.includes(leak)]).toEqual([leak, false])
})

test('malformed, truncated and foreign lines are counted and skipped; the rest still parses; empty input gives nothing', () => {
  const good = doc(prompt(FIX), edit('t1'))
  const r = readSession('{"type":"user","mess\n' + 'not json at all\n' + '\n' + '[1,2]\n' + '{"type":"user"}\n' + good + '{"type":"assistant","message":{"con')
  expect(r.tasks.length).toBe(1)
  expect(r.stats.malformed).toBe(3)  // the cut line, the garbage, the cut last line ('[1,2]', '{"type":"user"}' and the blank are well-formed but empty)
  expect(readSession('')).toMatchObject({ tasks: [], stats: { prompts: 0, tasks: 0, malformed: 0 } })
  expect(readSession('\n\n').tasks).toEqual([])
  expect(readSession(good.replace(/\n/g, '\r\n')).tasks.length).toBe(1)
})

test('readSessionLines takes any line iterator (streaming) and equals readSession; the session id comes from the lines or the option', () => {
  const t = doc(prompt(FIX), edit('t1'), prompt(NEXT), edit('t2'))
  expect(readSessionLines(t.split('\n'))).toEqual(readSession(t))
  const nosid = t.replace(/"sessionId":"sess-1",/g, '')
  expect(readSession(nosid).tasks[0].sessionId).toBe('')
  expect(readSession(nosid, { sessionId: 'from-file' }).tasks.map(x => x.sessionId)).toEqual(['from-file', 'from-file'])
})

test('big transcripts: a 200 000 line session reads in one pass without trouble', { timeoutMs: 60_000 }, () => {
  const parts: string[] = []
  for (let i = 0; i < 20_000; i++) parts.push(prompt(`${FIX} number ${i}`), ...edit(`e${i}`, `/repo/src/f${i % 50}.ts`), ...bash(`b${i}`, 'pytest -q'), asst(text(`done ${i}`)), J({ type: 'attachment' }), J({ type: 'ai-title' }))
  const r = readSession(parts.join('\n') + '\n')
  expect(r.tasks.length).toBe(20_000)
  expect(r.stats.prompts).toBe(20_000)
})

test('taskKey: bootstrap:<32 hex>, stable, distinct by project, session and prompt index', () => {
  const k = taskKey('prj_a', 'sess-1', 0)
  expect(k).toMatch(/^bootstrap:[0-9a-f]{32}$/)
  expect(taskKey('prj_a', 'sess-1', 0)).toBe(k)
  expect(new Set([k, taskKey('prj_b', 'sess-1', 0), taskKey('prj_a', 'sess-2', 0), taskKey('prj_a', 'sess-1', 1)]).size).toBe(4)
})

const mk = (i: number, success: boolean, decisive: number, endMs: number): any => ({ sessionId: 's', index: i, success, decisive, steps: decisive + 1, startMs: endMs - 1, endMs, prompt: 'p', trace: {} })
test('selectTasks: never more than n; successful first, then more decisive steps, then the newest', () => {
  const ts = [mk(0, true, 1, 100), mk(1, false, 9, 900), mk(2, true, 5, 200), mk(3, true, 5, 300), mk(4, true, 1, 400), mk(5, true, 0, 500)]
  expect(selectTasks(ts, 3).map(t => t.index)).toEqual([3, 2, 4])
  expect(selectTasks(ts, 100).map(t => t.index)).toEqual([3, 2, 4, 0, 5, 1])
  expect(selectTasks(ts, 0)).toEqual([])
  expect(selectTasks(ts, -1)).toEqual([])
  expect(selectTasks(ts, Number.NaN)).toEqual([])
  expect(selectTasks([], 5)).toEqual([])
  expect(ts.map(t => t.index)).toEqual([0, 1, 2, 3, 4, 5])  // the input is not reordered
})

// ---- 8.2.0 tool-noise filter ----
const rsn = (t: string) => readSession(t, { denoise: true })
const readMissing = (id: string, file = '/repo/nope.ts') => [asst(use(id, 'Read', { file_path: file })),
  J({ type: 'user', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: 'File does not exist.', is_error: true }] }, toolUseResult: 'Error: File does not exist.' })]
const grepEmpty = (id: string) => [asst(use(id, 'Grep', { pattern: 'zzz' })), ok(id, 'No matches found', { filenames: [] })]

test('noise steps are dropped from the trace, steps renumbered 1..n, failed_steps and success recomputed from what is left', () => {
  const r = rsn(doc(prompt(FIX), readMissing('n1'), edit('t1'), grepEmpty('n2'), bash('t2', 'pytest -q'), asst(text('done'))))
  expect(r.tasks.length).toBe(1)
  const t = r.tasks[0]
  expect(t.trace.trajectory.map((s: any) => [s.step, s.tool])).toEqual([[1, 'Edit'], [2, 'Bash']])
  expect(t.trace.result).toMatchObject({ success: true, failed_steps: 0, output: 'Executed 2 tool calls' })
  expect(t).toMatchObject({ steps: 2, decisive: 2, success: true })
  expect(r.stats).toMatchObject({ tasks: 1, noise: 0, noiseDropped: 2 })
})

test('a task left with fewer than 2 steps, or without a state-changing step, is excluded as noise (counted, not a candidate)', () => {
  const onlyLookups = doc(prompt(FIX), readMissing('a1'), grepEmpty('a2'), readMissing('a3'), asst(text('nothing found')))
  const oneEdit = doc(prompt(NEXT), readMissing('b1'), edit('b2'), asst(text('ok')))
  const r = rsn(onlyLookups + oneEdit)
  expect(r.tasks.length).toBe(0)
  expect(r.stats).toMatchObject({ prompts: 2, tasks: 0, noise: 2, noWork: 0 })
})

test('a task whose remaining steps still fail (success false) is excluded as noise', () => {
  const bad = [asst(use('c1', 'Bash', { command: 'npm run build' })), fail('c1', 2, 'error TS2304')]
  const r = rsn(doc(prompt(FIX), edit('c0'), bad, asst(text('could not build'))))
  expect(r.tasks.length).toBe(0)
  expect(r.stats.noise).toBe(1)
})

test('a clean task (no noise) is untouched; a trivial or no-work task keeps its old counter (no double count)', () => {
  const r = rsn(doc(prompt('hi'), asst(text('hello')), prompt(FIX), edit('d1'), bash('d2', 'pytest -q'), asst(text('ok'))))
  expect(r.stats).toMatchObject({ trivial: 1, tasks: 1, noise: 0, noiseDropped: 0 })
})

test('redaction still applies to what is kept (the filter runs before buildTrace)', () => {
  const r = rsn(doc(prompt(FIX), readMissing('e1'), edit('e2'), bash('e3', 'echo password=hunter2abc'), asst(text('ok'))))
  expect(JSON.stringify(r.tasks[0].trace)).not.toContain('hunter2abc')
})
