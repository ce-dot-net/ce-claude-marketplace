// 8.2.0 backfill orchestration with every I/O faked (post, get, sleep, now, ledger store): flow, stops, polling, ledger writes.
import { expect, test } from 'claude-code/testing'
import { buildItems, DEFAULT_LIMIT, MAX_LIMIT, previewLines, runBackfill, parseLimit, parseBackfillFlags, stepBackfill, newRun, runActive, startLine, RUN_TTL_MS, type Deps } from '../lib/backfill_run.ts'
import { emptyLedger, add, parse, serialize, statusOf, type Ledger } from '../lib/ledger.ts'

const K = (n: number) => 'bootstrap:' + n.toString(16).padStart(32, '0')
const item = (n: number) => ({ idempotency_key: K(n), occurred_at: '2026-10-01T12:00:00.000Z', trace: { task: 't' + n } })
const items = (n: number) => Array.from({ length: n }, (_, i) => item(i + 1))
const ok = (status: number, body: any = null) => ({ exit: 0, status, body })
const jobBody = (keys: string[], state = 'finished') => ({ state, items: keys.map(k => ({ idempotency_key: k, state: 'done', patterns_created: 1, failed_chunks: 0 })), patterns_created: keys.length, failed_chunks: 0 })

function fake(o: { posts?: any[], gets?: any[], ledger?: Ledger } = {}) {
  const log: string[] = [], posted: any[] = [], saves: Ledger[] = [], resumes: number[] = []
  let ledger = o.ledger ?? emptyLedger(), pi = 0, gi = 0
  const d: Deps = {
    post: async (b: any) => { log.push('post'); posted.push(b); return o.posts![Math.min(pi++, o.posts!.length - 1)] },
    get: async (job: string) => { log.push('get:' + job); return o.gets![Math.min(gi++, o.gets!.length - 1)] },
    sleep: async (ms: number) => { log.push('sleep:' + ms) }, now: () => 1_800_000_000_000,
    loadLedger: async () => ledger, saveLedger: async (l: Ledger) => { saves.push(structuredClone(l)); ledger = l; log.push('save') },
    setResume: async (ms: number) => { resumes.push(ms) },
  }
  return { d, log, posted, saves, resumes, ledger: () => ledger }
}
const acc = (job: string, accepted: number, dup = 0) => ok(202, { job_id: job, accepted, duplicates: dup, status_url: '/x' })

test('zero items: nothing is posted', async () => {
  const f = fake({ posts: [] })
  const r = await runBackfill([], f.d)
  expect(f.posted.length).toBe(0)
  expect(r.lines.join('\n')).toContain('0')
})

test('happy path: 2 batches go one after the other, each polled to finished, ledger saved after every result', async () => {
  const all = items(25)
  const f = fake({ posts: [acc('j1', 20), acc('j2', 5)], gets: [ok(200, jobBody(all.slice(0, 20).map(i => i.idempotency_key))), ok(200, jobBody(all.slice(20).map(i => i.idempotency_key)))] })
  const r = await runBackfill(all, f.d)
  expect(f.posted.map(b => [b.source, b.items.length])).toEqual([['bootstrap', 20], ['bootstrap', 5]])
  expect(f.log.filter(x => x !== 'save' && !x.startsWith('sleep'))).toEqual(['post', 'get:j1', 'post', 'get:j2'])
  expect(f.log.indexOf('save')).toBeLessThan(f.log.indexOf('post', 1))
  expect(statusOf(f.ledger(), K(1))).toBe('sent')
  expect(statusOf(f.ledger(), K(25))).toBe('sent')
  expect(r.report.sent).toBe(25)
  expect(r.report.finished).toBe(true)
  expect(r.lines.join('\n')).toContain('Backfill fertig: 25 gesendet')
})

test('polling: pending first, sleeps 60 s between polls, stops at finished', async () => {
  const f = fake({ posts: [acc('j', 1)], gets: [ok(200, { state: 'processing', items: [] }), ok(200, { state: 'processing', items: [] }), ok(200, jobBody([K(1)]))] })
  await runBackfill(items(1), f.d)
  expect(f.log.filter(x => x.startsWith('get:')).length).toBe(3)
  expect(f.log.filter(x => x === 'sleep:60000').length).toBe(2)
})

test('duplicates-only 202 (accepted 0): no poll, nothing marked, no error', async () => {
  const f = fake({ posts: [acc('j', 0, 3)], gets: [] })
  const r = await runBackfill(items(3), f.d)
  expect(f.log.some(x => x.startsWith('get:'))).toBe(false)
  expect(r.lines.join('\n')).toContain('bereits')
})

test('404 on the job get: polling stops, treated as submitted, the run goes on', async () => {
  const f = fake({ posts: [acc('j1', 20), acc('j2', 1)], gets: [ok(404, { error: 'gone' }), ok(200, jobBody([K(21)]))] })
  await runBackfill(items(21), f.d)
  expect(f.posted.length).toBe(2)
  expect(f.log.filter(x => x.startsWith('get:')).length).toBe(2)
})

test('429: the run stops, resume time stored, quota line, later batches not sent', async () => {
  const f = fake({ posts: [ok(429, { limit: 100, current: 100 })] })
  const r = await runBackfill(items(25), f.d)
  expect(f.posted.length).toBe(1)
  expect(f.resumes.length).toBe(1)
  expect(f.resumes[0]).toBeGreaterThan(1_800_000_000_000)
  expect(r.lines.join('\n')).toMatch(/Kontingent|Limit/)
})

test('401 and 402 stop: German line, ledger untouched, no poll, no further batch', async () => {
  for (const [st, word] of [[401, 'angemeldet'], [402, 'Abo']] as const) {
    const f = fake({ posts: [ok(st, { error: 'x' })] })
    const r = await runBackfill(items(25), f.d)
    expect(f.posted.length).toBe(1)
    expect(f.saves.length).toBe(0)
    expect(f.ledger().entries.size).toBe(0)
    expect(r.lines.join('\n')).toContain(word)
  }
})

test('503 and other retryable answers: stop, keep the ledger, say retry later', async () => {
  const f = fake({ posts: [ok(503, { error: 'backfill_unavailable' })] })
  const r = await runBackfill(items(25), f.d)
  expect(f.posted.length).toBe(1)
  expect(r.lines.join('\n')).toContain('später')
  const g = fake({ posts: [acc('j', 1)], gets: [ok(503, null)] })
  const r2 = await runBackfill(items(1), g.d)
  expect(r2.lines.join('\n')).toContain('später')
  expect(g.posted.length).toBe(1)
})

test('capability_off (404 on post) stops with the server-not-ready line', async () => {
  const f = fake({ posts: [ok(404, null)] })
  const r = await runBackfill(items(25), f.d)
  expect(f.posted.length).toBe(1)
  expect(r.lines.join('\n')).toContain('unterstützt')
})

test('422 invalid: the batch items count as failed attempts, the run continues', async () => {
  const f = fake({ posts: [ok(422, { detail: 'bad' }), acc('j2', 1)], gets: [ok(200, jobBody([K(21)]))] })
  await runBackfill(items(21), f.d)
  expect(f.posted.length).toBe(2)
  expect(statusOf(f.ledger(), K(1))).toBe('failed')
  expect(statusOf(f.ledger(), K(21))).toBe('sent')
})

test('engine exit 3 (gate): nothing sent, stop; exit 1 (transport): stop, ledger untouched', async () => {
  for (const [exit, word] of [[3, 'Gate'], [1, 'Antwort']] as const) {
    const f = fake({ posts: [{ exit }] })
    const r = await runBackfill(items(25), f.d)
    expect(f.posted.length).toBe(1)
    expect(f.saves.length).toBe(0)
    expect(r.lines.join('\n')).toContain(word)
  }
})

test('exit 2 and unknown exits stop without a ledger write', async () => {
  const f = fake({ posts: [{ exit: 2 }] })
  const r = await runBackfill(items(2), f.d)
  expect(f.saves.length).toBe(0)
  expect(r.lines.length).toBeGreaterThan(0)
})

test('ledger dedupe: a rerun with everything sent posts nothing', async () => {
  const l = emptyLedger()
  for (const i of items(5)) add(l, i.idempotency_key, 'sent', 1)
  const f = fake({ posts: [], ledger: l })
  await runBackfill(items(5), f.d)
  expect(f.posted.length).toBe(0)
})

test('a poll that aborts mid-run keeps what earlier batches wrote', async () => {
  const all = items(21)
  const f = fake({ posts: [acc('j1', 20), acc('j2', 1)], gets: [ok(200, jobBody(all.slice(0, 20).map(i => i.idempotency_key))), ok(503, null)] })
  await runBackfill(all, f.d)
  expect(statusOf(f.ledger(), K(1))).toBe('sent')
  expect(statusOf(f.ledger(), K(21))).toBe(undefined)
})

test('ledger file: corrupt or missing text parses to an empty ledger; a signed one round-trips', () => {
  expect(parse('\x00garbage\n\n', 's').entries.size).toBe(0)
  const l = emptyLedger(); add(l, K(1), 'sent', 5)
  expect(parse(serialize(l, 's'), 's').entries.size).toBe(1)
  expect(parse(serialize(l, 's'), 'other').entries.size).toBe(0)
})

test('limit: default 100, max 100, parse accepts only 1..100', () => {
  expect([DEFAULT_LIMIT, MAX_LIMIT]).toEqual([100, 100])
  expect(parseLimit('')).toEqual({ ok: true, limit: 100, rest: '' })
  expect(parseLimit('docs-only --limit 5')).toEqual({ ok: true, limit: 5, rest: 'docs-only' })
  expect(parseLimit('--limit=7 light')).toEqual({ ok: true, limit: 7, rest: 'light' })
  for (const bad of ['--limit 0', '--limit 101', '--limit abc', '--limit', '--limit 5 --limit 6']) expect([bad, (parseLimit(bad) as any).ok]).toEqual([bad, false])
})

const sessionJsonl = (prompt: string) => [
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:00Z', message: { role: 'user', content: prompt } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:05Z', message: { role: 'assistant', content: [{ type: 'tool_use', id: 't1', name: 'Edit', input: { file_path: '/proj/src/a.ts', old_string: 'a', new_string: 'b' } }] } },
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:06Z', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't1', content: 'ok' }] } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:09Z', message: { role: 'assistant', content: [{ type: 'text', text: 'done' }] } },
].map(x => JSON.stringify(x)).join('\n')
const GITLOG = '\x1eaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\x002026-10-02T10:00:00+00:00\x00fix: crash when the config file is empty\x00\x00\nsrc/p.ts\n'
const MERGES = '\x1ebbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\x002026-10-03T10:00:00+00:00\x00Merge pull request #5 from o/b\x00Add the retry queue for failed uploads\x00'

test('buildItems: sessions + git + merges counted, ledger-held skipped, capped by limit, mixed kinds shaped', () => {
  const sess = [{ text: sessionJsonl('please fix the crash in the parser module when the input is empty') }]
  const b = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger() })
  expect(b.sessionTasks).toBe(1)
  expect(b.gitTasks).toBe(2)
  expect(b.skipped).toBe(0)
  expect(b.items.length).toBe(3)
  expect(b.items.every(i => /^bootstrap:[0-9a-f]{32}$/.test(i.idempotency_key))).toBe(true)
  const l = emptyLedger(); add(l, b.items[0].idempotency_key, 'sent', 1)
  const b2 = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: l })
  expect(b2.skipped).toBe(1)
  expect(b2.items.length).toBe(2)
  expect(buildItems({ projectId: 'prj_t', sessions: [], gitLog: GITLOG, mergeLog: MERGES, limit: 1, ledger: emptyLedger() }).items.length).toBe(1)
  expect(buildItems({ projectId: 'prj_t', sessions: [], gitLog: '', mergeLog: '', limit: 100, ledger: emptyLedger() }).items.length).toBe(0)
})

test('previewLines: counts, cap, duration (70 s per trace), data-leaves sentence; flag off says so in one line', () => {
  const b = { items: items(100), sessionTasks: 60, gitTasks: 70, skipped: 4 }
  const on = previewLines(b, { flag: true, limit: 100 }).join('\n')
  for (const x of ['60', '70', '4', '100', 'Stunden', 'verlassen den Rechner']) expect(on).toContain(x)
  expect(previewLines(b, { flag: false, limit: 100 }).join('\n')).toBe('Backfill: Server unterstützt es noch nicht')
  expect(previewLines({ items: [], sessionTasks: 0, gitTasks: 0, skipped: 0 }, { flag: true, limit: 100 }).join('\n')).toContain('0 Aufgaben')
})

test('stepBackfill: one GET per step, the state is plain JSON between steps (a reload continues from it), never more than one poll per call', async () => {
  const all = items(2)
  const f = fake({ posts: [acc('j', 2)], gets: [ok(200, { state: 'processing', items: [] }), ok(200, { state: 'processing', items: [] }), ok(200, jobBody(all.map(i => i.idempotency_key)))] })
  let st = newRun(2, 1)
  expect((await stepBackfill(all, st, f.d)).done).toBe(false)
  expect(f.log.filter(x => x.startsWith('get:')).length).toBe(1)
  st = JSON.parse(JSON.stringify(st))                 // the marker round trip
  expect((await stepBackfill(all, st, f.d)).done).toBe(false)
  st = JSON.parse(JSON.stringify(st))
  expect(f.log.filter(x => x.startsWith('get:')).length).toBe(2)
  expect((await stepBackfill(all, st, f.d)).done).toBe(true)
  expect(f.posted.length).toBe(1)                     // the resumed steps never re-post the batch
  expect(st.report.sent).toBe(2)
  expect(st.report.finished).toBe(true)
})

test('run marker: active within 3 h of the last beat, stale after; start line has count and minutes', () => {
  expect(runActive({ beat: 1000 }, 1000 + RUN_TTL_MS - 1)).toBe(true)
  expect(runActive({ beat: 1000 }, 1000 + RUN_TTL_MS)).toBe(false)
  expect(runActive(null, 5)).toBe(false)
  expect(runActive({ beat: 'x' }, 5)).toBe(false)
  expect(startLine(100)).toBe('Backfill gestartet: 100 Aufgaben, läuft im Hintergrund (ca. 117 Min). Ergebnis folgt als Meldung.')
})

test('parseBackfillFlags: --backfill-only, --target-project, --target-org are stripped into fields', () => {
  expect(parseBackfillFlags('')).toEqual({ ok: true, only: false, rest: '' })
  expect(parseBackfillFlags('docs-only --backfill-only')).toEqual({ ok: true, only: true, rest: 'docs-only' })
  expect(parseBackfillFlags('--target-project prj_abc')).toEqual({ ok: true, only: false, project: 'prj_abc', rest: '' })
  expect(parseBackfillFlags('--limit 3 --target-project=prj_abc --target-org org_x_1 --backfill-only'))
    .toEqual({ ok: true, only: true, project: 'prj_abc', org: 'org_x_1', rest: '--limit 3' })
})
test('parseBackfillFlags: bad shapes, duplicates, org without project, a value on the switch are refused with a German line', () => {
  for (const bad of ['--target-project', '--target-project x', '--target-project prj_a', '--target-project prj_ab/c', '--target-project prj_abc --target-org', '--target-project prj_abc --target-org prj_abc',
    '--target-project prj_abc --target-org org_a', '--target-org org_abc', '--target-project prj_abc --target-project prj_abd', '--target-project=', '--target-project prj_abc;x', '--backfill-only=1',
    '--target-project --backfill-only', `--target-project prj_${'a'.repeat(65)}`]) {
    const r = parseBackfillFlags(bad)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.line).toContain('--target-project')
  }
})
