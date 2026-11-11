// 8.2.0 backfill orchestration with every I/O faked (post, get, sleep, now, ledger store): flow, stops, polling, ledger writes.
import { expect, test } from 'claude-code/testing'
import { buildItems, DEFAULT_LIMIT, DEFAULT_SOURCES, MAX_LIMIT, POLL_MS, POLL_RETRY_MS, previewLines, runBackfill, parseLimit, parseBackfillFlags, stepBackfill, newRun, runActive, startLine, RUN_TTL_MS, type Deps } from '../lib/backfill_run.ts'
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

const ALL = ['session', 'git', 'merge'] as const   // the explicit all-sources set (8.2.1: also the default)
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

test('duplicates-only 202 (accepted 0): no poll, the keys are ledgered sent (no slot next run), counted in one line', async () => {
  const f = fake({ posts: [acc('j', 0, 3)], gets: [] })
  const r = await runBackfill(items(3), f.d)
  expect(f.log.some(x => x.startsWith('get:'))).toBe(false)
  for (const n of [1, 2, 3]) expect(statusOf(f.ledger(), K(n))).toBe('sent')
  expect(r.lines).toContain('3 Aufgaben waren dem Server bereits bekannt.')
})
test('mixed batch (202 accepted 2, duplicates 1): the key missing from the finished job is ledgered sent and counted', async () => {
  const f = fake({ posts: [acc('j', 2, 1)], gets: [ok(200, jobBody([K(1), K(2)]))] })
  const r = await runBackfill(items(3), f.d)
  expect(statusOf(f.ledger(), K(3))).toBe('sent')
  expect(r.report.sent).toBe(2)
  expect(r.lines[0]).toContain('Backfill fertig: 2 gesendet')
  expect(r.lines).toContain('1 Aufgaben waren dem Server bereits bekannt.')
})
test('duplicates over several batches (mixed + duplicates-only) add up to ONE line with the real number; a rerun posts nothing', async () => {
  const all = items(25)
  const f = fake({ posts: [acc('j1', 14, 6), acc('j2', 0, 5)], gets: [ok(200, jobBody(all.slice(0, 14).map(i => i.idempotency_key)))] })
  const r = await runBackfill(all, f.d)
  expect(r.report.sent).toBe(14)
  expect(r.lines.filter(x => x.includes('bereits bekannt'))).toEqual(['11 Aufgaben waren dem Server bereits bekannt.'])
  const g = fake({ posts: [], ledger: f.ledger() })
  await runBackfill(all, g.d)
  expect(g.posted.length).toBe(0)
})
test('a job polled several times before finishing counts its duplicates once', async () => {
  const f = fake({ posts: [acc('j', 1, 1)], gets: [ok(200, { state: 'processing', items: [] }), ok(200, jobBody([K(1)]))] })
  const r = await runBackfill(items(2), f.d)
  expect(r.lines).toContain('1 Aufgaben waren dem Server bereits bekannt.')
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
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:07Z', message: { role: 'assistant', content: [{ type: 'tool_use', id: 't2', name: 'Bash', input: { command: 'pytest -q' } }] } },
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:08Z', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't2', content: 'ok' }] } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:09Z', message: { role: 'assistant', content: [{ type: 'text', text: 'done' }] } },
].map(x => JSON.stringify(x)).join('\n')
const GITLOG = '\x1eaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\x002026-10-02T10:00:00+00:00\x00fix: crash when the config file is empty\x00\x00\nsrc/p.ts\n'
const MERGES = '\x1ebbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\x002026-10-03T10:00:00+00:00\x00Merge pull request #5 from o/b\x00Add the retry queue for failed uploads\x00'

test('buildItems: sessions + git + merges counted, ledger-held skipped, capped by limit, mixed kinds shaped', () => {
  const sess = [{ text: sessionJsonl('please fix the crash in the parser module when the input is empty') }]
  const b = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger(), sources: ALL })
  expect(b.sessionTasks).toBe(1)
  expect(b.gitTasks).toBe(2)
  expect(b.skipped).toBe(0)
  expect(b.items.length).toBe(3)
  expect(b.items.every(i => /^bootstrap:[0-9a-f]{32}$/.test(i.idempotency_key))).toBe(true)
  const l = emptyLedger(); add(l, b.items[0].idempotency_key, 'sent', 1)
  const b2 = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: l, sources: ALL })
  expect(b2.skipped).toBe(1)
  expect(b2.items.length).toBe(2)
  expect(buildItems({ projectId: 'prj_t', sessions: [], gitLog: GITLOG, mergeLog: MERGES, limit: 1, ledger: emptyLedger() }).items.length).toBe(1)
  expect(buildItems({ projectId: 'prj_t', sessions: [], gitLog: '', mergeLog: '', limit: 100, ledger: emptyLedger() }).items.length).toBe(0)
})

// 8.2.1 hybrid: sessions (decisive > 0) used to outrank every git task; now each source with candidates gets its share
const SESS3 = [{ text: ['fix the crash in the parser module when the input is empty', 'add a retry to the upload queue in the client module', 'rename the config loader and update all its callers']
  .map(p => sessionJsonl(p)).join('\n') }]
test('buildItems hybrid: sessions cannot starve git/merge; limit 3 takes one of each source', () => {
  const b = buildItems({ projectId: 'prj_t', sessions: SESS3, gitLog: GITLOG, mergeLog: MERGES, limit: 3, ledger: emptyLedger(), sources: ALL })
  expect(b.sessionTasks).toBe(3)
  expect(Object.values(b.sources).sort()).toEqual(['git', 'merge', 'session'])
  const two = buildItems({ projectId: 'prj_t', sessions: SESS3, gitLog: GITLOG, mergeLog: MERGES, limit: 2, ledger: emptyLedger(), sources: ALL })
  expect(Object.values(two.sources)).toContain('git')
  expect(Object.values(two.sources)).toContain('session')
  // git+merge have 2 candidates in all: the rest of the limit goes to the sessions
  const five = buildItems({ projectId: 'prj_t', sessions: SESS3, gitLog: GITLOG, mergeLog: MERGES, limit: 5, ledger: emptyLedger(), sources: ALL })
  expect(Object.values(five.sources).filter(x => x === 'session').length).toBe(3)
  expect(five.items.length).toBe(5)
})
test('buildItems default sources (no --sources) = session, git, merge', () => {
  const b = buildItems({ projectId: 'prj_t', sessions: SESS3, gitLog: GITLOG, mergeLog: MERGES, limit: 3, ledger: emptyLedger() })
  expect(DEFAULT_SOURCES).toEqual(['session', 'git', 'merge'])
  expect(b.sessionTasks).toBe(3)
  expect(new Set(Object.values(b.sources))).toEqual(new Set(['session', 'git', 'merge']))
})

test('previewLines: counts, cap, duration (about 5 items a minute), data-leaves sentence; flag off says so in one line', () => {
  const b = { items: items(100), sessionTasks: 60, gitTasks: 70, skipped: 4 }
  const on = previewLines(b, { flag: true, limit: 100, sources: ALL }).join('\n')
  for (const x of ['60', '70', '4', '100', 'Dauer: etwa 20 Minuten', '5 Aufgaben pro Minute', 'verlassen den Rechner']) expect(on).toContain(x)
  expect(on).not.toContain('70 s')
  expect(previewLines({ ...b, items: items(7) }, { flag: true, limit: 100, sources: ALL }).join('\n')).toContain('etwa 2 Minuten')
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
  expect(startLine(100)).toBe('Backfill gestartet: 100 Aufgaben, läuft im Hintergrund (ca. 20 Min). Ergebnis folgt als Meldung.')
})

test('parseBackfillFlags: --backfill-only, --target-project, --target-org are stripped into fields', () => {
  expect(parseBackfillFlags('')).toEqual({ ok: true, only: false, rest: '' })
  expect(parseBackfillFlags('docs-only --backfill-only')).toEqual({ ok: true, only: true, rest: 'docs-only' })
  expect(parseBackfillFlags('--target-project prj_abc')).toEqual({ ok: true, only: false, project: 'prj_abc', rest: '' })
  expect(parseBackfillFlags('--limit 3 --target-project=prj_abc --target-org org_x_1 --backfill-only'))
    .toEqual({ ok: true, only: true, project: 'prj_abc', org: 'org_x_1', rest: '--limit 3' })
})
test('parseBackfillFlags --sources: comma list of session|git|merge, canonical order, stripped; absent = no field', () => {
  expect(parseBackfillFlags('--backfill-only --sources git,merge --limit 3')).toEqual({ ok: true, only: true, sources: ['git', 'merge'], rest: '--limit 3' })
  expect(parseBackfillFlags('--sources=merge,session')).toEqual({ ok: true, only: false, sources: ['session', 'merge'], rest: '' })
  expect(parseBackfillFlags('--sources git')).toMatchObject({ ok: true, sources: ['git'] })
  expect('sources' in (parseBackfillFlags('--backfill-only') as any)).toBe(false)
})
test('parseBackfillFlags --sources: unknown token, empty list, duplicates, missing value, repeated flag are refused with a German usage line', () => {
  for (const bad of ['--sources', '--sources=', '--sources ""', '--sources x', '--sources git,x', '--sources git,,merge', '--sources git,', '--sources ,git', '--sources git,git', '--sources GIT',
    '--sources git --sources merge', '--sources --backfill-only', '--sources git,merge,session,git']) {
    const r = parseBackfillFlags(bad)
    expect(r.ok).toBe(false)
    if (!r.ok) { expect(r.line).toContain('--sources'); expect(r.line).toContain('session, git, merge') }
  }
})
const HINT = 'Hinweis: Session-Aufgaben waren im Pilot verrauschter als Git (Tool-Rauschen wird gefiltert)'
test('buildItems with sources: a source not listed contributes nothing; previewLines names only chosen sources and the Quellen line', () => {
  const sess = [{ text: sessionJsonl('please fix the crash in the parser module when the input is empty') }]
  const gm = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger(), sources: ['git', 'merge'] })
  expect(gm.sessionTasks).toBe(0)
  expect(gm.items.length).toBe(2)
  const g = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger(), sources: ['git'] })
  expect(Object.values(g.sources)).toEqual(['git'])
  const m = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger(), sources: ['merge'] })
  expect(Object.values(m.sources)).toEqual(['merge'])
  const s1 = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger(), sources: ['session'] })
  expect(s1.gitTasks).toBe(0)
  expect(s1.items.length).toBe(1)
  const t = previewLines(gm, { flag: true, limit: 100, sources: ['git', 'merge'] })
  expect(t[0]).toBe('Quellen: git, merge')
  expect(t.join('\n')).not.toContain('Session-Aufgaben')
  expect(t.join('\n')).toContain('2 Git-Aufgaben (Fix/Revert + Merges)')
  expect(previewLines(s1, { flag: true, limit: 100, sources: ['session'] }).join('\n')).not.toContain('Git-Aufgaben')
  expect(previewLines(m, { flag: true, limit: 100, sources: ['merge'] }).join('\n')).toContain('1 Git-Aufgaben (Merges)')
  expect(previewLines(g, { flag: true, limit: 100, sources: ['git'] }).join('\n')).toContain('1 Git-Aufgaben (Fix/Revert)')
  const d = previewLines(gm, { flag: true, limit: 100 })   // flag absent: the default session,git,merge (8.2.1 hybrid), labelled as such
  expect(d[0]).toBe('Quellen: session, git, merge (Standard)')
  expect(d).toContain(HINT)
  expect(d.join('\n')).not.toContain('experimentell')
  expect(t.join('\n')).not.toContain('Hinweis:')
  expect(buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger() }).sessionTasks).toBe(1)
  const sg = previewLines(s1, { flag: true, limit: 100, sources: ['session', 'git'] })
  expect(sg[0]).toBe('Quellen: session, git')
  expect(sg).toContain(HINT)
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

// ---- 8.2.0 diagnosis: attempts per verdict, response/item rows, top cause in the final line
const failedJob = (n: number, state: string, error = 'pipeline_failed') => ({ state, items: Array.from({ length: n }, (_, i) => ({ idempotency_key: K(i + 1), state: 'failed', error })) })
test('polls of one unfinished job burn ONE attempt per item, not one per poll (the 5/5/10 ledger bug)', async () => {
  const f = fake({ posts: [acc('j', 3)], gets: [ok(200, failedJob(1, 'processing')), ok(200, failedJob(2, 'processing')), ok(200, failedJob(3, 'processing')), ok(200, failedJob(3, 'processing')), ok(200, failedJob(3, 'finished'))] })
  const r = await runBackfill(items(3), f.d)
  for (const n of [1, 2, 3]) expect(f.ledger().entries.get(K(n))).toMatchObject({ status: 'failed', attempts: 1 })
  expect(r.report.failed).toBe(3)
})
function logged(o: any) {
  const rows: any[] = [], f = fake(o)
  f.d.log = async (r: any) => { rows.push(r) }
  return { ...f, rows }
}
test('a rejected batch logs a backfill_response row (status, code, field names) and the final line names the top cause', async () => {
  const f = logged({ posts: [ok(422, { code: 'payload_invalid', detail: [{ loc: ['body', 'items', 0, 'trace'], msg: 'm', type: 't', input: 'SECRET' }] })] })
  const r = await runBackfill(items(2), f.d)
  const row = f.rows.find(x => x.event === 'backfill_response')
  expect(row).toMatchObject({ event: 'backfill_response', kind: 'invalid', status: 422, code: 'payload_invalid', items: 2, fields: ['body.items.0.trace'] })
  expect(JSON.stringify(f.rows)).not.toContain('SECRET')
  expect(r.lines[0]).toContain('2 fehlgeschlagen (422 payload_invalid ×2)')
})
test('failed job items log one backfill_item row each (once, not per poll) and the top cause is the item error', async () => {
  const f = logged({ posts: [acc('j', 3)], gets: [ok(200, failedJob(3, 'processing', 'pipeline_failed')), ok(200, failedJob(3, 'finished', 'pipeline_failed'))] })
  const r = await runBackfill(items(3), f.d)
  const rows = f.rows.filter(x => x.event === 'backfill_item')
  expect(rows.length).toBe(3)
  expect(rows[0]).toMatchObject({ error: 'pipeline_failed', key: K(1) })
  expect(r.lines[0]).toContain('(item pipeline_failed ×3)')
})
test('engine exit and stderr are logged, truncated', async () => {
  const f = logged({ posts: [{ exit: 7, stderr: 'E'.repeat(500) }] })
  await runBackfill(items(1), f.d)
  const row = f.rows.find(x => x.event === 'backfill_response')
  expect(row).toMatchObject({ exit: 7 })
  expect(row.stderr.length).toBe(200)
})
test('every non-accepted answer logs a row (429, 503, 401); an accepted 202 logs kind accepted', async () => {
  for (const [st, kind] of [[429, 'quota'], [503, 'retry'], [401, 'auth']] as const) {
    const f = logged({ posts: [ok(st, { limit: 1, current: 1 })] })
    await runBackfill(items(1), f.d)
    expect(f.rows.find(x => x.event === 'backfill_response')).toMatchObject({ kind, status: st })
  }
  const g = logged({ posts: [acc('j', 1)], gets: [ok(200, jobBody([K(1)]))] })
  await runBackfill(items(1), g.d)
  expect(g.rows.find(x => x.event === 'backfill_response')).toMatchObject({ kind: 'accepted', status: 202 })
})
test('a failing logger never breaks the run', async () => {
  const f = fake({ posts: [ok(422, { detail: 'bad' })] })
  f.d.log = async () => { throw new Error('disk') }
  const r = await runBackfill(items(1), f.d)
  expect(r.report.failed).toBe(1)
})

// Source per idempotency key (session / git / merge) for a later evaluation: keys and counts only, never task text.
const srcMap = (): Record<string, 'session' | 'git' | 'merge'> => ({ [K(1)]: 'session', [K(2)]: 'session', [K(3)]: 'git', [K(4)]: 'merge' })
test('one backfill_item_sent row per item with its source, then one backfill_batch summary; no task text', async () => {
  const all = items(4), keys = all.map(i => i.idempotency_key)
  const f = logged({ posts: [acc('j', 4)], gets: [ok(200, jobBody(keys))] })
  f.d.sources = srcMap()
  const r = await runBackfill(all, f.d)
  const sent = f.rows.filter(x => x.event === 'backfill_item_sent')
  expect(sent.map(x => [x.key, x.source])).toEqual([[K(1), 'session'], [K(2), 'session'], [K(3), 'git'], [K(4), 'merge']])
  expect(Object.keys(JSON.parse(JSON.stringify(sent[0]))).sort()).toEqual(['event', 'key', 'source'])
  expect(f.rows.filter(x => x.event === 'backfill_batch')).toMatchObject([{ event: 'backfill_batch', total: 4, session: 2, git: 1, merge: 1 }])
  expect(JSON.stringify(f.rows)).not.toContain('"t1"')
  expect(r.lines[0]).toContain('(Session 2, Git 1, Merge 1)')
})
test('without a source map nothing new is logged and the final line is unchanged', async () => {
  const f = logged({ posts: [acc('j', 1)], gets: [ok(200, jobBody([K(1)]))] })
  const r = await runBackfill(items(1), f.d)
  expect(f.rows.some(x => x.event === 'backfill_item_sent' || x.event === 'backfill_batch')).toBe(false)
  expect(r.lines[0]).not.toContain('Session')
})
test('a failing logger never breaks a run that has sources', async () => {
  const f = fake({ posts: [acc('j', 1)], gets: [ok(200, jobBody([K(1)]))] })
  f.d.sources = srcMap(); f.d.log = async () => { throw new Error('disk') }
  const r = await runBackfill(items(1), f.d)
  expect(r.report.sent).toBe(1)
})
test('buildItems returns the source of every selected key', () => {
  const sess = [{ text: sessionJsonl('please fix the crash in the parser module when the input is empty') }]
  const b = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger(), sources: ALL })
  expect(Object.keys(b.sources).sort()).toEqual(b.items.map(i => i.idempotency_key).sort())
  expect(new Set(Object.values(b.sources))).toEqual(new Set(['session', 'git', 'merge']))
})

// ---- 8.2.0 tool-noise filter: counted, shown in the preview, logged ----
const NOISY = (prompt: string) => [
  { type: 'user', sessionId: 'sess-n', timestamp: '2026-10-01T10:00:00Z', message: { role: 'user', content: prompt } },
  ...['r1', 'r2', 'r3'].flatMap((id, i) => [
    { type: 'assistant', sessionId: 'sess-n', timestamp: `2026-10-01T10:00:0${i * 2 + 1}Z`, message: { role: 'assistant', content: [{ type: 'tool_use', id, name: 'Read', input: { file_path: `/p/nope${i}.ts` } }] } },
    { type: 'user', sessionId: 'sess-n', timestamp: `2026-10-01T10:00:0${i * 2 + 2}Z`, message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: 'File does not exist.', is_error: true }] } }]),
  { type: 'assistant', sessionId: 'sess-n', timestamp: '2026-10-01T10:00:09Z', message: { role: 'assistant', content: [{ type: 'text', text: 'not found' }] } },
].map(x => JSON.stringify(x)).join('\n')

test('buildItems: a session task that is only tool noise is not a candidate and is counted in noiseExcluded; git is untouched', () => {
  const sess = [{ text: sessionJsonl('please fix the crash in the parser module when the input is empty') + '\n' + NOISY('please look at the nope module and report what it does') }]
  const b = buildItems({ projectId: 'prj_t', sessions: sess, gitLog: GITLOG, mergeLog: MERGES, limit: 100, ledger: emptyLedger(), sources: ALL })
  expect(b.sessionTasks).toBe(1)
  expect(b.noiseExcluded).toBe(1)
  expect(b.gitTasks).toBe(2)
  expect(b.items.length).toBe(3)
})

test('previewLines: names how many session tasks were set aside as tool noise (total includes them); no noise = the old text', () => {
  const b = { items: items(5), sessionTasks: 121, noiseExcluded: 61, gitTasks: 570, skipped: 0 }
  expect(previewLines(b, { flag: true, limit: 100, sources: ALL })[2]).toBe('Backfill: 182 Session-Aufgaben (davon 61 wegen Tool-Rauschen aussortiert), 570 Git-Aufgaben (Fix/Revert + Merges) im Fenster, 0 schon gesendet (übersprungen)')
  expect(previewLines({ ...b, noiseExcluded: 0 }, { flag: true, limit: 100, sources: ALL })[2]).toContain('121 Session-Aufgaben, 570 Git-Aufgaben')
})

test('backfill_batch carries noise_excluded', async () => {
  const all = items(1)
  const f = logged({ posts: [acc('j', 1)], gets: [ok(200, jobBody([K(1)]))] })
  f.d.sources = { [K(1)]: 'session' }; f.d.noiseExcluded = 7
  await runBackfill(all, f.d)
  expect(f.rows.filter(x => x.event === 'backfill_batch')).toMatchObject([{ event: 'backfill_batch', total: 1, noise_excluded: 7 }])
})

// ---- 8.2.4: a transient poll failure (no network, 502/503/504) is retried, bounded; the post is never repeated ----
const NET = { exit: 1, stderr: 'fetch failed (ENOTFOUND)' }
test('poll: ENOTFOUND then recovery: the job finishes, ONE post, the ledger holds the keys sent', async () => {
  const f = fake({ posts: [acc('j', 1)], gets: [NET, ok(200, jobBody([K(1)]))] })
  const r = await runBackfill(items(1), f.d)
  expect(r.stopped).toBe(undefined)
  expect(f.posted.length).toBe(1)
  expect(r.report.sent).toBe(1)
  expect(statusOf(f.ledger(), K(1))).toBe('sent')
  expect(f.log.filter(x => x.startsWith('sleep:'))).toEqual([`sleep:${POLL_RETRY_MS[0]}`])
})

test('poll: 502, 503, 504 are retried too, with a growing wait', async () => {
  const f = fake({ posts: [acc('j', 1)], gets: [ok(502, null), ok(503, null), ok(504, null), ok(200, jobBody([K(1)]))] })
  const r = await runBackfill(items(1), f.d)
  expect(r.stopped).toBe(undefined)
  expect(f.posted.length).toBe(1)
  expect(f.log.filter(x => x.startsWith('sleep:'))).toEqual(POLL_RETRY_MS.slice(0, 3).map(ms => `sleep:${ms}`))
})

test('poll: the retry budget is bounded (a few tries, growing, <= 15 min in all)', () => {
  expect(POLL_RETRY_MS.length).toBeGreaterThanOrEqual(3)
  expect(POLL_RETRY_MS.length).toBeLessThanOrEqual(6)
  for (let i = 1; i < POLL_RETRY_MS.length; i++) expect(POLL_RETRY_MS[i]).toBeGreaterThanOrEqual(POLL_RETRY_MS[i - 1])
  expect(POLL_RETRY_MS.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(15 * 60_000)
})

test('poll: persistent network failure stops after the bounded retries with a clear line; no re-post, ledger untouched', async () => {
  const f = fake({ posts: [acc('j', 1)], gets: [NET] })
  const r = await runBackfill(items(1), f.d)
  expect(f.log.filter(x => x.startsWith('get:')).length).toBe(POLL_RETRY_MS.length + 1)
  expect(f.posted.length).toBe(1)
  expect(f.saves.length).toBe(0)
  expect(statusOf(f.ledger(), K(1))).toBe(undefined)
  expect(r.stopped).toContain('ENOTFOUND')
  expect(r.stopped).toContain('später')
})

test('poll: the retry count starts over after a good answer (each job gets the full budget)', async () => {
  const all = items(21)
  const gets = [...POLL_RETRY_MS.map(() => NET), ok(200, jobBody(all.slice(0, 20).map(i => i.idempotency_key))),
    ...POLL_RETRY_MS.map(() => NET), ok(200, jobBody([K(21)]))]
  const f = fake({ posts: [acc('j1', 20), acc('j2', 1)] })
  let gi = 0
  f.d.get = async (job: string) => { f.log.push('get:' + job); return gets[gi++] }
  const r = await runBackfill(all, f.d)
  expect(r.stopped).toBe(undefined)
  expect(f.posted.length).toBe(2)
  expect(r.report.sent).toBe(21)
})

test('poll: auth answers, 429 and other engine exits still stop at once (no retry)', async () => {
  for (const g of [ok(401, null), ok(402, null), { exit: 3 }, ok(429, { code: 'BACKFILL_DAY_LIMIT_REACHED' })]) {
    const f = fake({ posts: [acc('j', 1)], gets: [g] })
    const r = await runBackfill(items(1), f.d)
    expect(f.log.filter(x => x.startsWith('get:')).length).toBe(1)
    expect(r.stopped).toBeTruthy()
  }
})

test('stepBackfill: a transient poll failure asks for the next step after the retry wait (waitMs); the state stays plain JSON', async () => {
  const f = fake({ posts: [acc('j', 1)], gets: [NET, ok(200, jobBody([K(1)]))] })
  const st = newRun(1, 0)
  expect(await stepBackfill(items(1), st, f.d)).toEqual({ done: false, waitMs: POLL_RETRY_MS[0] })   // post, then the first poll fails
  expect((await stepBackfill(items(1), JSON.parse(JSON.stringify(st)), f.d)).done).toBe(true)
  expect(f.posted.length).toBe(1)
  expect(POLL_MS).toBe(60_000)
})
