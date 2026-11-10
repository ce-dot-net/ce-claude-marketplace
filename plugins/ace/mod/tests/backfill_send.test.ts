// 8.2.0 backfill send helpers (pure, unwired): task -> server item, batching, response classification, job status -> ledger.
import { expect, test } from 'claude-code/testing'
import { applyJob, batches, classify, describeAnswer, failedItems, reportLine, toItem } from '../lib/backfill_send.ts'
import { add, emptyLedger, MAX_ATTEMPTS, MAX_KEYS, serialize, statusOf } from '../lib/ledger.ts'
import { readSession } from '../lib/backfill.ts'

const K = (n: number) => 'bootstrap:' + n.toString(16).padStart(32, '0')
const gitTask = (n: number, over: any = {}) => ({ key: K(n), sha: 'a'.repeat(40), task: 'Fix crash on empty file', steps: ['src/p.ts', 'tests/p.test.ts'],
  success: true, failedThenFixed: false, decisive: 0, endMs: Date.parse('2026-10-01T12:00:00Z'), ...over })

test('git task -> item with a live-shaped trace and no session fields', () => {
  const it = toItem(gitTask(1), 'git')!
  expect(it.idempotency_key).toBe(K(1))
  expect(it.occurred_at).toBe('2026-10-01T12:00:00.000Z')
  const t = it.trace
  expect(t.task).toBe('User request: Git commit (untrusted text): Fix crash on empty file')
  expect(t.trajectory.map((s: any) => s.action)).toEqual(['edit src/p.ts', 'edit tests/p.test.ts'])
  expect(t.trajectory[0].step).toBe(1)
  expect(t.result.success).toBe(true)
  for (const f of ['session_id', 'retrieval_id', 'conversation_id', 'agent_id']) expect(f in t).toBe(false)
  expect(t.playbook_used).toEqual([])
  expect(t.applied_log_ids).toEqual([])
})

test('a reverted git task is a failure', () => {
  expect(toItem(gitTask(2, { success: false }), 'git')!.trace.result.success).toBe(false)
})

test('git task with a secret in the task text stays redacted', () => {
  const it = toItem(gitTask(3, { task: 'rotate password=hunter2secret now' }), 'git')!
  expect(JSON.stringify(it)).not.toContain('hunter2secret')
})

test('session task keeps its own trace, key from the task, no session_id', () => {
  const lines = [
    { type: 'user', sessionId: 's1', timestamp: '2026-10-01T10:00:00Z', message: { content: 'Add a retry to the uploader please' } },
    { type: 'assistant', timestamp: '2026-10-01T10:00:05Z', message: { content: [{ type: 'tool_use', id: 't1', name: 'Edit', input: { file_path: '/p/up.ts', old_string: 'a', new_string: 'b' } }] } },
    { type: 'user', timestamp: '2026-10-01T10:00:06Z', message: { content: [{ type: 'tool_result', tool_use_id: 't1', content: 'ok' }] } },
    { type: 'assistant', timestamp: '2026-10-01T10:00:09Z', message: { content: [{ type: 'text', text: 'Done.' }] } },
  ].map(l => JSON.stringify(l)).join('\n')
  const r = readSession(lines)
  expect(r.tasks.length).toBe(1)
  const task: any = { ...r.tasks[0], key: K(9) }
  const it = toItem(task, 'session')!
  expect(it.idempotency_key).toBe(K(9))
  expect(it.occurred_at).toBe(new Date(task.endMs).toISOString())
  expect('session_id' in it.trace).toBe(false)
  expect(it.trace.playbook_used).toEqual([])
})

test('toItem refuses bad key, bad time, bad kind (never emits NaN)', () => {
  expect(toItem(gitTask(1, { key: 'nope' }), 'git')).toBe(null)
  expect(toItem(gitTask(1, { key: undefined }), 'git')).toBe(null)
  expect(toItem(gitTask(1, { endMs: NaN }), 'git')).toBe(null)
  expect(toItem(gitTask(1, { endMs: 9e18 }), 'git')).toBe(null)
  expect(toItem(gitTask(1, { endMs: 0 }), 'git')).toBe(null)
  expect(toItem(gitTask(1), 'other' as any)).toBe(null)
  expect(toItem(null as any, 'git')).toBe(null)
})

const item = (n: number, pad = 0) => ({ idempotency_key: K(n), occurred_at: '2026-10-01T12:00:00.000Z', trace: { task: 'x'.repeat(pad) } })

test('batches: at most 20 per batch, order kept', () => {
  const r = batches(Array.from({ length: 45 }, (_, i) => item(i)))
  expect(r.batches.map(b => b.length)).toEqual([20, 20, 5])
  expect(r.skipped).toBe(0)
  expect(r.batches[1][0].idempotency_key).toBe(K(20))
})

test('batches: body stays under 5242880 bytes; an oversize item is skipped and counted', () => {
  const big = 2_000_000
  const r = batches([item(1, big), item(2, big), item(3, big), item(4, 6_000_000), item(5)])
  expect(r.skipped).toBe(1)
  expect(r.batches.flat().some(i => i.idempotency_key === K(4))).toBe(false)
  for (const b of r.batches) expect(new TextEncoder().encode(JSON.stringify({ source: 'bootstrap', items: b })).length <= 5242880).toBe(true)
  expect(r.batches.flat().length).toBe(4)
})

test('batches: multibyte text is measured in bytes', () => {
  const it = { idempotency_key: K(1), occurred_at: '2026-10-01T12:00:00.000Z', trace: { task: '€'.repeat(1_800_000) } }  // 5.4 MB in UTF-8, 1.8M chars
  const r = batches([it])
  expect(r.skipped).toBe(1)
  expect(r.batches.length).toBe(0)
})

test('batches: a duplicate key inside the input is skipped (server would 422 the batch)', () => {
  const r = batches([item(1), item(1), item(2)])
  expect(r.batches.flat().length).toBe(2)
  expect(r.skipped).toBe(1)
})

test('batches: empty and garbage input', () => {
  expect(batches([]).batches).toEqual([])
  expect(batches(null as any)).toEqual({ batches: [], skipped: 0 })
})

const NOW = Date.parse('2026-10-01T15:30:00Z')
test('classify 202', () => {
  const c: any = classify(202, '{"job_id":"j1","accepted":3,"duplicates":1,"status_url":"/traces/backfill/j1"}', NOW)
  expect(c).toMatchObject({ kind: 'accepted', job_id: 'j1', accepted: 3, duplicates: 1 })
})
test('classify 202 without job_id is a retry, not an accept', () => {
  expect(classify(202, '{}', NOW).kind).toBe('retry')
})
test('classify 404 = capability off', () => { expect(classify(404, '{}', NOW).kind).toBe('capability_off') })
test('classify 413 keeps code and limit', () => {
  expect(classify(413, '{"error":"payload_too_large","code":"backfill_batch_too_large","limit":20}', NOW))
    .toMatchObject({ kind: 'too_large', code: 'backfill_batch_too_large', limit: 20 })
})
test('classify 422 = invalid', () => { expect(classify(422, '{"detail":"bad"}', NOW).kind).toBe('invalid') })
test('classify 429 resumes at the next UTC midnight', () => {
  const c: any = classify(429, '{"error":"quota_exceeded","code":"BACKFILL_DAY_LIMIT_REACHED","resource":"backfill_day","current":1000,"limit":1000,"upgrade_url":"u"}', NOW)
  expect(c).toMatchObject({ kind: 'quota', limit: 1000, current: 1000 })
  expect(c.resumeAfter).toBe(Date.parse('2026-10-02T00:00:00Z'))
})
test('classify 429 at exactly midnight resumes a full day later', () => {
  const c: any = classify(429, '{}', Date.parse('2026-10-02T00:00:00Z'))
  expect(c.resumeAfter).toBe(Date.parse('2026-10-03T00:00:00Z'))
})
test('classify 5xx and network failure = retry', () => {
  for (const s of [500, 502, 503, 0, NaN, undefined as any, null as any]) expect(classify(s, '', NOW).kind).toBe('retry')
})
test('classify never throws on garbage', () => {
  for (const b of [undefined, null, 'not json', '[]', '"str"', 7, {}, '{"limit":"x"}', 'null'] as any[])
    for (const s of [202, 404, 413, 422, 429, 500, 401, 418]) expect(() => classify(s, b, NOW)).not.toThrow()
  expect(classify(413, 'garbage', NOW).kind).toBe('too_large')
  expect(classify(429, 'garbage', NOW).kind).toBe('quota')
})
test('classify accepts a parsed object body too', () => {
  expect(classify(202, { job_id: 'j2' } as any, NOW)).toMatchObject({ kind: 'accepted', job_id: 'j2' })
})
test('classify other 4xx (401/403) is invalid with the status kept', () => {
  expect(classify(401, '{}', NOW)).toMatchObject({ kind: 'invalid', status: 401 })
})

const job = (items: any[], extra: any = {}) => ({ job_id: 'j', state: 'finished', patterns_created: 5, failed_chunks: 1, items, ...extra })
test('applyJob maps item states to the ledger', () => {
  const l = emptyLedger()
  const r = applyJob(l, job([
    { idempotency_key: K(1), state: 'done', patterns_created: 3, failed_chunks: 0 },
    { idempotency_key: K(2), state: 'done', patterns_created: 2, failed_chunks: 1 },
    { idempotency_key: K(3), state: 'skipped', error: 'terminal_prune' },
    { idempotency_key: K(4), state: 'failed', error: 'pipeline_failed' },
    { idempotency_key: K(5), state: 'failed', error: 'expired' },
    { idempotency_key: K(6), state: 'failed', error: 'project_gone' },
    { idempotency_key: K(7), state: 'pending' },
    { idempotency_key: K(8), state: 'processing' },
  ]), 1000)
  expect(statusOf(l, K(1))).toBe('sent')
  expect(statusOf(l, K(2))).toBe('sent')
  expect(statusOf(l, K(3))).toBe('skipped')
  expect(statusOf(l, K(4))).toBe('failed')
  expect(statusOf(l, K(5))).toBe('skipped-failed')
  expect(statusOf(l, K(6))).toBe('skipped-failed')
  expect(statusOf(l, K(7))).toBe(undefined)
  expect(statusOf(l, K(8))).toBe(undefined)
  expect(r).toEqual({ sent: 2, partial: 1, failed: 3, skipped: 1, patternsCreated: 5, failedChunks: 1, finished: true })
})
test('applyJob: repeated failed hits the ledger retry cap', () => {
  const l = emptyLedger()
  for (let i = 0; i < MAX_ATTEMPTS; i++) applyJob(l, job([{ idempotency_key: K(1), state: 'failed', error: 'chunks_failed' }]), 1)
  expect(statusOf(l, K(1))).toBe('skipped-failed')
})
test('applyJob never downgrades sent', () => {
  const l = emptyLedger()
  add(l, K(1), 'sent', 1)
  applyJob(l, job([{ idempotency_key: K(1), state: 'failed', error: 'expired' }]), 2)
  expect(statusOf(l, K(1))).toBe('sent')
})
test('applyJob tolerates garbage, unknown states, bad keys, missing fields', () => {
  const l = emptyLedger()
  for (const j of [null, undefined, 'x', 5, [], {}, { items: 'no' }, { items: [null, 3, {}, { idempotency_key: 'bad', state: 'done' }, { idempotency_key: K(1), state: 'weird' }] }] as any[])
    expect(() => applyJob(l, j, 1)).not.toThrow()
  expect(l.entries.size).toBe(0)
  expect(applyJob(l, {} as any, 1)).toEqual({ sent: 0, partial: 0, failed: 0, skipped: 0, patternsCreated: 0, failedChunks: 0, finished: false })
})
test('applyJob: unfinished job reports finished false; totals fall back to the item sums', () => {
  const r = applyJob(emptyLedger(), { state: 'running', items: [{ idempotency_key: K(1), state: 'done', patterns_created: 4, failed_chunks: 2 }] }, 1)
  expect(r).toMatchObject({ finished: false, sent: 1, partial: 1, patternsCreated: 4, failedChunks: 2 })
})

test('reportLine is one German line', () => {
  const l = reportLine({ sent: 12, partial: 2, failed: 1, skipped: 3, patternsCreated: 34, failedChunks: 2, finished: true })
  expect(l).toBe('Backfill fertig: 12 gesendet (2 teilweise), 1 fehlgeschlagen, 3 übersprungen, 34 Patterns erstellt')
  expect(l.includes('\n')).toBe(false)
  expect(reportLine({ sent: 0, partial: 0, failed: 0, skipped: 0, patternsCreated: 0, failedChunks: 0, finished: false })).toBe('Backfill läuft noch: 0 gesendet')
  expect(() => reportLine(null as any)).not.toThrow()
})

test('ledger cap fits the 4 MiB file limit: a full ledger serializes under 3 MiB', () => {
  expect(MAX_KEYS).toBe(20000)
  const l = emptyLedger()
  for (let i = 0; i < MAX_KEYS; i++) l.entries.set(K(i), { status: 'skipped-failed', atMs: 1_800_000_000_000, attempts: 3 })
  expect(new TextEncoder().encode(serialize(l, 'per-install-secret')).length).toBeLessThan(3 * 1024 * 1024)
})

test('classify 202 with accepted 0 (only duplicates): already submitted, never poll (the job id answers 404)', () => {
  const c: any = classify(202, { job_id: 'j1', accepted: 0, duplicates: 3, status_url: '/traces/backfill/j1' }, NOW)
  expect(c.kind).toBe('accepted')
  expect(c.poll).toBe(false)
  const m: any = classify(202, { job_id: 'j2', accepted: 2, duplicates: 1, status_url: '/traces/backfill/j2' }, NOW)
  expect(m.poll).toBe(true)
})

test('classify 503 backfill_unavailable is temporary (retry), not capability off', () => {
  expect(classify(503, '{"error":"backfill_unavailable"}', NOW)).toEqual({ kind: 'retry', status: 503 })
})

test('applyJob: payload_invalid and drain_error are failed items (resubmittable), not skipped-failed', () => {
  const l = emptyLedger()
  const job = { state: 'finished', items: [
    { idempotency_key: K(1), state: 'failed', error: 'payload_invalid' },
    { idempotency_key: K(2), state: 'failed', error: 'drain_error' }] }
  const r = applyJob(l, job, 1)
  expect(r.failed).toBe(2)
  expect(statusOf(l, K(1))).toBe('failed')
  expect(statusOf(l, K(2))).toBe('failed')
})

test('applyJob: reflector_disabled and an unknown error value are failed items (resubmittable)', () => {
  const l = emptyLedger()
  const job = { state: 'finished', items: [
    { idempotency_key: K(1), state: 'failed', error: 'reflector_disabled' },
    { idempotency_key: K(2), state: 'failed', error: 'some_future_error' }] }
  const r = applyJob(l, job, 1)
  expect(r.failed).toBe(2)
  expect(statusOf(l, K(1))).toBe('failed')
  expect(statusOf(l, K(2))).toBe('failed')
})

const SECRET = 'sk_live_ABCDEF0123456789abcdef'
const sessTask = (over: any = {}) => ({ key: K(7), endMs: Date.parse('2026-10-01T12:00:00Z'), trace: {
  task: 'User request: deploy with password=hunter2secret now', trajectory: [
    { step: 1, tool: 'Grep', action: `grep "api_key=${SECRET}" in src`, result: 'ok', start_ms: 1, end_ms: 2, duration_ms: 1 },
    { step: 2, tool: 'Bash', action: 'run tests', result: `failed: token=${SECRET} rejected`, start_ms: 2, end_ms: 3, duration_ms: 1 }],
  result: { success: true, failed_steps: 0, output: 'x', summary: `done, secret: ${SECRET}` } }, ...over })

test('session items go through safeText: secrets in the task, a grep pattern, a result and the summary never reach the item JSON', () => {
  const it = toItem(sessTask(), 'session')!
  const j = JSON.stringify(it)
  expect(j).not.toContain(SECRET)
  expect(j).not.toContain('hunter2secret')
  expect(it.trace.trajectory[1].tool).toBe('Bash')
  expect(it.trace.trajectory[0].step).toBe(1)
  expect(it.trace.task.startsWith('User request: deploy with')).toBe(true)
})

test('session items: redact by default, a secret in result.output or in an unknown nested field never leaves', () => {
  const t = sessTask(); t.trace.result.output = `deploy token=${SECRET} done`
  ;(t.trace as any).extra = { notes: [`password=hunter2secret`], deep: { v: `api_key=${SECRET}` } }
  const j = JSON.stringify(toItem(t, 'session')!)
  expect(j).not.toContain(SECRET)
  expect(j).not.toContain('hunter2secret')
})

test('session items: a fullwidth/folded secret in a step is cut too', () => {
  const t = sessTask(); t.trace.trajectory[0].action = 'grep ｐａｓｓｗｏｒｄ=hunter2secret'
  expect(JSON.stringify(toItem(t, 'session')!)).not.toContain('hunter2secret')
})

test('git items: fixed untrusted-text prefix, the rest stays redacted and bounded; merges get their own prefix', () => {
  const c = toItem(gitTask(8, { task: 'rotate password=hunter2secret now' }), 'git')!
  expect(c.trace.task).toBe('User request: Git commit (untrusted text): rotate [redacted]')
  expect(JSON.stringify(c)).not.toContain('hunter2secret')
  const m = toItem(gitTask(9, { task: 'Add retry queue', _merge: true }), 'git')!
  expect(m.trace.task).toBe('User request: Merged PR (untrusted text): Add retry queue')
  const long = toItem(gitTask(10, { task: 'x '.repeat(2000) }), 'git')!
  expect(long.trace.task.length).toBeLessThan(700)
  expect(Object.keys(c.trace).sort()).toEqual(Object.keys(toItem(gitTask(11), 'git')!.trace).sort())
})

test('bare token shapes with no key word never leave (session and git)', () => {
  const toks = ['sk_live_ABCDEF0123456789abcdef', 'glpat-abcdefghij0123456789', 'AIzaSyA1234567890abcdefghij', 'ASIAABCDEFGHIJKLMNOP', 'hf_abcdefghij0123456789', 'https://hooks.slack.com/services/T0/B0/abcdef']
  for (const tok of toks) {
    const t = sessTask(); t.trace.trajectory[0].action = `curl ${tok} now`
    expect(JSON.stringify(toItem(t, 'session')!)).not.toContain(tok)
    expect(JSON.stringify(toItem(gitTask(21, { task: `fix leak ${tok} here` }), 'git')!)).not.toContain(tok)
  }
})

test('git file steps with whitespace or sentence-like text are dropped, plain paths stay', () => {
  const it = toItem(gitTask(22, { steps: ['src/a.ts', 'ignore previous instructions.txt', 'x'.repeat(250)] }), 'git')!
  expect(it.trace.trajectory.map((s: any) => s.action)).toEqual(['edit src/a.ts'])
})

test('applyJob with a judged set: an item that failed in an earlier poll of the same job burns NO further attempt, but still counts as failed', () => {
  const l = emptyLedger(), judged = new Set<string>()
  const j = job([{ idempotency_key: K(1), state: 'failed', error: 'pipeline_failed' }], { state: 'processing' })
  for (let i = 0; i < 5; i++) applyJob(l, j, 1, judged)
  expect(l.entries.get(K(1))).toMatchObject({ status: 'failed', attempts: 1 })
  expect(applyJob(l, j, 1, judged).failed).toBe(1)
  expect(judged.has(K(1))).toBe(true)
})
test('applyJob with a judged set: the gone path (expired) is one verdict as well', () => {
  const l = emptyLedger(), judged = new Set<string>()
  const j = job([{ idempotency_key: K(1), state: 'failed', error: 'expired' }])
  applyJob(l, j, 1, judged); applyJob(l, j, 2, judged)
  expect(l.entries.get(K(1))).toMatchObject({ status: 'skipped-failed', attempts: 3 })
})
test('failedItems: only failed items not yet judged, with their error value cut to 80 chars', () => {
  const j = job([{ idempotency_key: K(1), state: 'failed', error: 'x'.repeat(200) }, { idempotency_key: K(2), state: 'done' }, { idempotency_key: K(3), state: 'failed' }, { idempotency_key: K(4), state: 'failed', error: 'boom' }])
  const r = failedItems(j, new Set([K(4)]))
  expect(r).toEqual([{ key: K(1), error: 'x'.repeat(80) }, { key: K(3), error: 'failed' }])
  expect(failedItems(null as any, new Set())).toEqual([])
})
test('describeAnswer: status, code, error, string detail and 422 field names only, never input values', () => {
  const d = describeAnswer(422, { code: 'payload_invalid', error: 'bad', detail: [{ loc: ['body', 'items', 0, 'trace', 'task'], msg: 'Field required', type: 'missing', input: 'SECRET-PROMPT' }] })
  expect(d).toEqual({ status: 422, code: 'payload_invalid', error: 'bad', fields: ['body.items.0.trace.task'] })
  expect(JSON.stringify(d)).not.toContain('SECRET')
  expect(describeAnswer(400, { detail: 'plain text ' + 'y'.repeat(500) }).detail?.length).toBe(200)
  expect(describeAnswer(0, 'garbage')).toEqual({ status: 0 })
})
test('classify 422 detail names the fields, never the input values', () => {
  const c: any = classify(422, { detail: [{ loc: ['body', 'items', 0, 'occurred_at'], msg: 'x', type: 'value_error', input: 'SECRET-PROMPT' }] }, NOW)
  expect(c.detail).toContain('body.items.0.occurred_at')
  expect(c.detail).not.toContain('SECRET')
})
