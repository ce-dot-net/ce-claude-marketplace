// 8.2.0 /ace:ace-bootstrap backfill phase, wired through the host: dormant without the flag, honest preview, send after confirm.
import { expect, test } from 'claude-code/testing'
import { CWD, HOME, PROOT, ROOT, cliOf, host } from './helpers.ts'

const start = ($: any) => $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
const run = async ($: any, args = '') => (await $.command.run({ command: 'ace:ace-bootstrap', args })).text as string
const FLAG = `${ROOT}/bootstrap-backfill.json`, ENGINE = `${PROOT}/engine/backfill.js`
const flagOn = (at = 1_800_000_000) => JSON.stringify({ on: true, at })
const JSONL = [
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:00Z', message: { role: 'user', content: 'please fix the crash in the parser module when the input is empty' } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:05Z', message: { role: 'assistant', content: [{ type: 'tool_use', id: 't1', name: 'Edit', input: { file_path: '/proj/src/a.ts', old_string: 'a', new_string: 'b' } }] } },
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:06Z', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't1', content: 'ok' }] } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:07Z', message: { role: 'assistant', content: [{ type: 'tool_use', id: 't2', name: 'Bash', input: { command: 'pytest -q' } }] } },
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:08Z', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't2', content: 'ok' }] } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:09Z', message: { role: 'assistant', content: [{ type: 'text', text: 'done' }] } },
].map(x => JSON.stringify(x)).join('\n')
const GITLOG = '\x1eaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\x002026-10-02T10:00:00+00:00\x00fix: crash when the config file is empty\x00\x00\nsrc/p.ts\n'
const MERGES = '\x1ebbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\x002026-10-03T10:00:00+00:00\x00Merge pull request #5 from o/b\x00Add the retry queue for failed uploads\x00'
const git = (argv: string[]) => argv.includes('ls-files') ? 'a.ts\n' : argv.includes('rev-list') ? '50\n' : argv.includes('--no-merges') ? GITLOG : argv.includes('--merges') ? MERGES : undefined
const cli = (a: string[]) => a[0] === 'bootstrap' ? { stdout: JSON.stringify({ success: true, patternsExtracted: 3, patternsAfterDedup: 3 }) } : a[0] === 'status' ? { stdout: '{"playbook":{"total_patterns":1}}' } : undefined
// the backfill runs as a chain of $.clock.after ticks: move the mocked clock 60 s at a time until the run marker is cleared
const idle = async ($: any, h: any) => { for (let i = 0; i < 500; i++) { await h.clock.advance(60_000); if (!h.marker()) return } throw new Error('backfill still running') }
const bf = (h: any) => h.runs.filter((r: any) => r.argv[1] === ENGINE)
const base = (extra: Record<string, string> = {}) => ({ [ENGINE]: '//', [`${HOME}/.claude/projects/-proj/s1.jsonl`]: JSONL, ...extra })

test('flag absent: one-line preview, no pending backfill, no engine call even with --approved', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base(), backfill: () => ({ status: 202, body: {} }) })
  await start($)
  const t = await run($)
  expect(t).toContain('Backfill: Server unterstützt es noch nicht')
  expect(t).not.toContain('verlassen den Rechner')
  expect(h.pending().backfill).toBe(undefined)
  await run($, '--approved')
  expect(bf(h).length).toBe(0)
})

test('flag stale (8 days): off', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn(1_800_000_000 - 8 * 86400) }) })
  await start($)
  expect(await run($)).toContain('Server unterstützt es noch nicht')
  expect(h.pending().backfill).toBe(undefined)
})

test('flag false: off', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: JSON.stringify({ on: false, at: 1_800_000_000 }) }) })
  await start($)
  expect(await run($)).toContain('Server unterstützt es noch nicht')
  expect(h.pending().backfill).toBe(undefined)
})

test('flag on: preview counts, default cap 100, duration, data-leaves sentence; nothing is sent before the confirm', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => ({ status: 200, body: null }) })
  await start($)
  const t = await run($)
  expect(t).toContain('2 Git-Aufgaben')
  expect(t).toContain('3 Aufgaben werden gesendet (Limit 100')
  expect(t).toContain('verlassen den Rechner')
  expect(h.pending().backfill).toEqual({ days: 90, limit: 100 })
  expect(bf(h).length).toBe(0)
})

test('--limit N is parsed (and kept out of the CLI argv); bad values are refused', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  const t = await run($, '--limit 2')
  expect(t).toContain('2 Aufgaben werden gesendet (Limit 2')
  expect(h.pending().backfill.limit).toBe(2)
  expect(h.pending().argv).not.toContain('--limit')
  expect(await run($, '--limit 101')).toContain('--limit')
})

test('approved: the CLI bootstrap runs, then the backfill posts the batch and reports one line; rerun sends nothing', async ($, on) => {
  const jobItems = (b: any) => ({ state: 'finished', items: b.items.map((i: any) => ({ idempotency_key: i.idempotency_key, state: 'done', patterns_created: 1, failed_chunks: 0 })) })
  let last: any
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: (cmd, argv, stdin) => {
    if (cmd === 'post') { last = JSON.parse(stdin!); return { status: 202, body: { job_id: 'j1', accepted: last.items.length, duplicates: 0, status_url: '/u' } } }
    return { status: 200, body: jobItems(last) } } })
  await start($)
  const t = await run($, '--approved')
  expect(t).toContain('Bootstrap fertig')
  expect(t).toContain('Backfill gestartet: 3 Aufgaben')
  expect(t).not.toContain('Backfill fertig')   // returned before the loop finished
  expect(t).not.toContain('{')
  await idle($, h)
  expect(h.logs.join('\n')).toContain('Backfill fertig: 3 gesendet')
  expect(h.toasts.some((x: string) => x.includes('Backfill fertig: 3 gesendet'))).toBe(true)
  const post = bf(h)[0]
  expect(post.argv.slice(2, 4)).toEqual(['post', '--org'])
  expect(post.argv).toContain('prj_t')
  expect(post.argv.join(' ')).not.toMatch(/token|Authorization/i)
  expect(last.source).toBe('bootstrap')
  expect(last.items.length).toBe(3)
  const n = bf(h).length
  const t2 = await run($, '--approved')
  await idle($, h)
  expect(bf(h).length).toBe(n)        // everything is in the ledger now
  expect(t2).toContain('0 Aufgaben')
})

test('8.2.4 approved: the job poll loses the network once (engine exit 1), the detached run waits and finishes; ONE post', async ($, on) => {
  let last: any, gets = 0
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: (cmd, _argv, stdin) => {
    if (cmd === 'post') { last = JSON.parse(stdin!); return { status: 202, body: { job_id: 'j1', accepted: last.items.length, duplicates: 0, status_url: '/u' } } }
    if (++gets === 1) return { exit: 1 }
    return { status: 200, body: { state: 'finished', items: last.items.map((i: any) => ({ idempotency_key: i.idempotency_key, state: 'done', patterns_created: 1, failed_chunks: 0 })) } } } })
  await start($)
  await run($, '--approved')
  await idle($, h)
  expect(gets).toBe(2)
  expect(bf(h).filter((r: any) => r.argv[2] === 'post').length).toBe(1)
  expect(h.logs.join('\n')).toContain('Backfill fertig: 3 gesendet')
  expect(h.logs.join('\n')).not.toContain('gestoppt')
})

test('approved with 429: stops, stores the resume time, the next run says so without calling the engine', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => ({ status: 429, body: { limit: 100, current: 100 } }) })
  await start($)
  const t = await run($, '--approved')
  expect(t).toContain('Backfill gestartet')
  await idle($, h)
  expect(h.logs.join('\n')).toContain('Kontingent')
  expect(h.toasts.join('\n')).toContain('Kontingent')
  const n = bf(h).length
  expect(n).toBe(1)
  expect(await run($, '--approved')).toContain('Kontingent')
  expect(bf(h).length).toBe(n)
})

const stopCase = (a: any, word: string) => async ($: any, on: any) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => a })
  await start($)
  const t = await run($, '--approved')
  expect(t).toContain('Bootstrap fertig')
  await idle($, h)
  expect(h.logs.join('\n')).toContain(word)
  expect(h.toasts.join('\n')).toContain(word)
  expect(h.marker()).toBe(null)   // marker cleared after an error end too
  expect(bf(h).length).toBe(1)
}
test('approved with engine exit 3: Gate line, the bootstrap result stays', stopCase({ exit: 3 }, 'Gate'))
test('approved with 401: login line, the bootstrap result stays', stopCase({ status: 401, body: {} }, 'angemeldet'))

test('a ledger file with a bad signature starts empty (never crashes); the key file is created 0600-style via the private write', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn(), [`${ROOT}/projects/prj_t/backfill-ledger.tsv`]: 'v1\tgarbage\n\x00' }), backfill: () => ({ status: 429, body: {} }) })
  await start($)
  await run($, '--approved')
  await idle($, h)
  expect(bf(h).length).toBe(1)
  expect(h.files.get(`${ROOT}/backfill.key`)?.length ?? 0).toBeGreaterThanOrEqual(32)
})

const flagFromSearch = (v: any, expected: boolean) => async ($: any, on: any) => {
  const resp = JSON.stringify({ similar_patterns: [], retrieval_id: 'r', ...(v === undefined ? {} : { bootstrap_backfill: v }) })
  host(on, { mockClock: true, cli, git, files: base(), search: () => ({ stdout: resp }) })
  await start($)
  await $.prompt.submit({ text: 'please fix the domain shift hook so it injects patterns when reading plugin files', wait: false, origin: { kind: 'composer' } } as any)
  expect((await run($)).includes('Aufgaben werden gesendet')).toBe(expected)
}
test('search response bootstrap_backfill:true switches it on', flagFromSearch(true, true))
test('search response bootstrap_backfill:false stays off', flagFromSearch(false, false))
test('search response bootstrap_backfill:"yes" (non-boolean) stays off', flagFromSearch('yes', false))
test('search response without bootstrap_backfill stays off', flagFromSearch(undefined, false))

// --- non-blocking run (8.2.0): detached loop, run marker (single flight, TTL), progress status ---
const jobOf = (b: any) => ({ state: 'finished', items: b.items.map((i: any) => ({ idempotency_key: i.idempotency_key, state: 'done', patterns_created: 1, failed_chunks: 0 })) })
const slow = (polls: number, times?: number[], clk?: () => number) => { let last: any, n = 0
  return (cmd: string, _a: string[], stdin?: string) => {
    if (cmd === 'get') times?.push(clk!())
    if (cmd === 'post') { last = JSON.parse(stdin!); return { status: 202, body: { job_id: 'j1', accepted: last.items.length, duplicates: 0, status_url: '/u' } } }
    return n++ < polls ? { status: 200, body: { state: 'processing', items: [] } } : { status: 200, body: jobOf(last) } } }

test('approved returns at once: the start line, the engine call happened only for the post/poll that the detached loop makes later', async ($, on) => {
  const times: number[] = []; let h: any
  h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: slow(3, times, () => h.clock.now()) })
  await start($)
  const t = await run($, '--approved')
  expect(bf(h).length).toBe(0)   // nothing ran inside the command: the first step waits for the timer
  expect(t).toMatch(/Backfill gestartet: 3 Aufgaben, läuft im Hintergrund \(ca\. \d+ Min\)\. Ergebnis folgt als Meldung\./)
  expect(h.marker().startedAt).toBeGreaterThan(0)   // running: the marker is set when the command returns
  await idle($, h)
  expect(times.length).toBe(4)
  for (let i = 1; i < times.length; i++) expect(times[i] - times[i - 1]).toBeGreaterThanOrEqual(60_000)  // never polled faster than every 60 s
  expect(h.runs.some((r: any) => r.argv[0] === 'sleep')).toBe(false)  // a timer, no sleep subprocess
})

test('single flight: a second confirm while a run is active says so and starts nothing', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: slow(2) })
  await start($)
  await run($, '--approved')
  const posts = () => bf(h).filter((r: any) => r.argv[2] === 'post').length
  const t2 = await run($, '--approved')
  expect(t2).toContain('Backfill läuft bereits')
  expect(t2).not.toContain('Backfill gestartet')
  await idle($, h)
  expect(posts()).toBe(1)
})

test('a stale marker (older than 3 h) is ignored; a fresh one blocks', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: slow(0) })
  await start($)
  h.setMarker({ startedAt: h.clock.now() - 4 * 3_600_000, beat: h.clock.now() - 4 * 3_600_000 })
  expect(await run($, '--approved')).toContain('Backfill gestartet')
  await idle($, h)
  h.setMarker({ startedAt: h.clock.now() - 3_600_000, beat: h.clock.now() - 3_600_000 })
  expect(await run($, '--approved')).toContain('Backfill läuft bereits')
})

test('progress: the status line shows done/total while running, and is cleared at the end', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: slow(1) })
  await start($)
  await run($, '--approved')
  await idle($, h)
  expect(h.statuses.some(x => /^Backfill \d+\/3$/.test(String(x)))).toBe(true)
  expect(h.statuses[h.statuses.length - 1]).toBe(undefined)
})

test('a throwing engine ends the run with an error line and clears the marker', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => { throw new Error('boom') } })
  await start($)
  await run($, '--approved')
  await idle($, h)
  expect(h.logs.join('\n')).toMatch(/Backfill/)
  expect(h.marker()).toBe(null)
})

test('session.end / a reload does not block forever: a marker whose last beat is older than 3 h is ignored and cleared at the next session start', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: slow(0) })
  h.setMarker({ startedAt: 1, beat: h.clock.now() - 4 * 3_600_000, total: 3, posted: [], polls: 0, lines: [], report: {} })
  await start($)
  expect(h.marker()).toBe(null)
  expect(bf(h).length).toBe(0)
})

test('session.start with a fresh marker (module reloaded mid-run) plans the next tick and finishes the run', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: slow(1) })
  await start($)
  await run($, '--approved')
  await h.clock.advance(1)             // first step: posts and polls once
  const n = bf(h).length
  expect(n).toBeGreaterThan(0)
  // simulate the reload: the chain is gone, only $.state survives. A second start in the same load must not double the chain.
  await start($)
  await idle($, h)
  expect(h.marker()).toBe(null)
  expect(h.logs.join('\n')).toContain('Backfill fertig: 3 gesendet')
  expect(bf(h).filter((r: any) => r.argv[2] === 'post').length).toBe(1)
})

test('session.start with a fresh marker and no chain in this load (a reload) plans a tick that continues the run', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: slow(0) })
  const t0 = h.clock.now()
  h.setMarker({ startedAt: t0 - 7, beat: t0 - 5, total: 3, posted: [], polls: 0, lines: [], report: { sent: 0, partial: 0, failed: 0, skipped: 0, patternsCreated: 0, failedChunks: 0, finished: false },
    args: { root: CWD, orgId: 'org_t', projectId: 'prj_t', days: 90, limit: 100 } })
  await start($)
  expect(bf(h).length).toBe(0)         // planned, not run yet
  await idle($, h)
  expect(h.logs.join('\n')).toContain('Backfill fertig: 3 gesendet')
})

// --- --backfill-only: no legacy CLI bootstrap at all ---
const cliCalls = (h: any) => h.runs.filter((r: any) => cliOf(r.argv)).map((r: any) => cliOf(r.argv)![0])
// what the commands themselves spawn: the host's own binding lookups (context) and session start are not the command's
const noLegacy = (h: any, before: number) => expect(cliCalls(h).slice(before)).toEqual([])
const warm = async ($: any, h: any) => { await run($, '--limit 0'); return cliCalls(h).length }  // a refused command still resolves the binding once (context/status probes)
const jobFor = (store: { last?: any }) => (cmd: string, _a: string[], stdin?: string) => {
  if (cmd === 'post') { store.last = JSON.parse(stdin!); return { status: 202, body: { job_id: 'j1', accepted: store.last.items.length, duplicates: 0, status_url: '/u' } } }
  return { status: 200, body: jobOf(store.last) }
}
const richCli = (a: string[]) => a[0] === 'status' ? { stdout: '{"playbook":{"total_patterns":150}}' } : cli(a)
const fewCommits = (argv: string[]) => argv.includes('rev-list') ? '5\n' : git(argv)

test('--backfill-only preview: no legacy source warning, no playbook/commit warnings, one line that only redacted task data leaves; no ace-cli call at all', async ($, on) => {
  const h = host(on, { mockClock: true, cli: richCli, git: fewCommits, files: base({ [FLAG]: flagOn() }) })
  await start($)
  const n0 = await warm($, h)
  const t = await run($, '--backfill-only --limit 2')
  expect(t).not.toContain('Achtung')
  expect(t).not.toContain('Quellcode-Funktionskörper')
  expect(t).not.toContain('Playbook hat schon')
  expect(t).not.toContain('Commits im Fenster')
  expect(t.split('\n').filter(l => l.includes('Titel, Dateinamen, redigierte Texte')).length).toBe(1)
  expect(t).toContain('nur redigierte Aufgabendaten')
  expect(t).toContain('2 Aufgaben werden gesendet (Limit 2')
  expect(t).toContain('Oder tippen: /ace:ace-bootstrap --backfill-only --limit 2 --approved')
  expect(h.pending().backfill).toEqual({ days: 90, limit: 2, only: true })
  noLegacy(h, n0)
})

test('--backfill-only --approved: only the backfill starts, ace-cli is never spawned, the result is the start line', async ($, on) => {
  const st: { last?: any } = {}
  const h = host(on, { mockClock: true, cli: richCli, git, files: base({ [FLAG]: flagOn() }), backfill: jobFor(st) })
  await start($)
  const n0 = await warm($, h)
  const t = await run($, '--backfill-only --approved')
  expect(t).toContain('Backfill gestartet: 3 Aufgaben')
  expect(t).not.toContain('Bootstrap fertig')
  await idle($, h)
  expect(h.logs.join('\n')).toContain('Backfill fertig: 3 gesendet')
  noLegacy(h, n0)
})

test('--backfill-only with the flag off: one line, nothing to confirm, no pending, --approved sends nothing', async ($, on) => {
  const h = host(on, { mockClock: true, cli: richCli, git, files: base() })
  await start($)
  const n0 = await warm($, h)
  const t = await run($, '--backfill-only')
  expect(t).toBe('Backfill: Server unterstützt es noch nicht')
  expect(h.pending()).toBe(null)
  expect(await run($, '--backfill-only --approved')).toBe('Backfill: Server unterstützt es noch nicht')
  expect(bf(h).length).toBe(0)
  noLegacy(h, n0)
})

test('bad flag values are refused with a German line and store nothing', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  for (const a of ['--target-project nope', '--target-org org_abc', '--target-project prj_abc --target-org bad', '--backfill-only=1'])
    expect(await run($, a)).toContain('--target-project')
  expect(h.pending()).toBe(null)
})

// --- --target-project: another destination, same sessions and git ---
test('target preview: the Ziel line (bound org stays); without --backfill-only the target is refused', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  const t = await run($, '--target-project prj_newtest')
  expect(t).toContain('nur mit --backfill-only')
  expect(h.pending()).toBe(null)
  const t2 = await run($, '--backfill-only --target-project prj_newtest --target-org org_other')
  expect(t2).toContain('Ziel: org_other/prj_newtest (gebunden ist: prj_t)')
  expect(t2).toContain('Oder tippen: /ace:ace-bootstrap --backfill-only --target-project prj_newtest --target-org org_other --approved')
  expect(t2).not.toContain('Bootstrap selbst')
  expect(await run($, '')).not.toContain('Ziel:')
  expect(await run($, '--backfill-only --target-project prj_t')).not.toContain('Ziel:')   // the bound project itself is no change
})

test('target run: engine gets the target org/project, own ledger (second target and the bound project each send), marker carries the target', async ($, on) => {
  const st: { last?: any } = {}
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: jobFor(st) })
  await start($)
  await run($, '--backfill-only --target-project prj_newtest --approved')
  expect(h.marker().args.projectId).toBe('prj_newtest')
  expect(h.marker().args.orgId).toBe('org_t')
  await idle($, h)
  const post = bf(h)[0]
  expect(post.argv.slice(2)).toEqual(expect.arrayContaining(['post', '--org', 'org_t', '--project', 'prj_newtest']))
  expect(post.argv).not.toContain('prj_t')
  expect(post.env?.ACE_PROJECT_ID).toBe('prj_newtest')
  const keysA = st.last.items.map((i: any) => i.idempotency_key)
  expect(h.files.has(`${ROOT}/projects/prj_newtest/backfill-ledger.tsv`)).toBe(true)
  expect(h.files.has(`${ROOT}/projects/prj_t/backfill-ledger.tsv`)).toBe(false)
  // same target again: all in its ledger. Another target and the bound project: their own ledgers, their own keys.
  expect(await run($, '--backfill-only --target-project prj_newtest --approved')).toContain('0 Aufgaben')
  await run($, '--backfill-only --target-project prj_second --target-org org_o2x --approved'); await idle($, h)
  const keysB = st.last.items.map((i: any) => i.idempotency_key)
  expect(bf(h).at(-2)!.argv).toEqual(expect.arrayContaining(['org_o2x', 'prj_second']))
  expect(keysB.some((k: string) => keysA.includes(k))).toBe(false)
  await run($, '--backfill-only --approved'); await idle($, h)
  expect(st.last.items.length).toBe(3)
  expect(bf(h).at(-1)!.argv).toEqual(expect.arrayContaining(['org_t', 'prj_t']))
  expect(h.files.has(`${ROOT}/projects/prj_t/backfill-ledger.tsv`)).toBe(true)
})

test('default run (no target flags) is unchanged: bound project in the engine args and the ledger', async ($, on) => {
  const st: { last?: any } = {}
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: jobFor(st) })
  await start($)
  await run($, '--approved'); await idle($, h)
  expect(bf(h)[0].argv).toEqual(expect.arrayContaining(['org_t', 'prj_t']))
  expect(h.files.has(`${ROOT}/projects/prj_t/backfill-ledger.tsv`)).toBe(true)
})

test('a rejected batch: a backfill_response row goes to backfill-log.jsonl (no request content) and the toast names the top cause', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => ({ status: 422, body: { code: 'payload_invalid', detail: [{ loc: ['body', 'items', 0, 'trace'], msg: 'm', type: 't', input: 'SECRET-PROMPT' }] } }) })
  await start($)
  await run($, '--approved')
  await idle($, h)
  const row = h.runs.find((r: any) => String(r.stdin ?? '').includes('backfill_response'))
  expect(row?.argv.join(' ')).toContain('backfill-log.jsonl')
  const j = JSON.parse(row!.stdin!)
  expect(j).toMatchObject({ event: 'backfill_response', kind: 'invalid', status: 422, code: 'payload_invalid' })
  expect(row!.stdin).not.toContain('SECRET')
  expect(h.toasts.some((x: string) => x.includes('(422 payload_invalid ×3)'))).toBe(true)
})

// --- --sources: which task sources are read, previewed and sent (needs --backfill-only) ---
const sessionsDir = `${HOME}/.claude/projects/-proj`
test('--sources git,merge: no session read at all, no session count, Quellen line, copy-line has the flag, pending carries the sources', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  h.reads.length = 0
  const t = await run($, '--backfill-only --sources git,merge')
  expect(h.reads.filter((p: string) => p.startsWith(sessionsDir))).toEqual([])
  expect(t.split('\n')).toContain('Quellen: git, merge')
  expect(t).not.toContain('Session-Aufgaben')
  expect(t).toContain('2 Git-Aufgaben')
  expect(t).toContain('2 Aufgaben werden gesendet')
  expect(t).toContain('Oder tippen: /ace:ace-bootstrap --backfill-only --sources git,merge --approved')
  expect(h.pending().backfill).toEqual({ days: 90, limit: 100, only: true, sources: ['git', 'merge'] })
})
test('--sources session: no git log call for the commit history, only session counts', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  const n = h.runs.length
  const t = await run($, '--backfill-only --sources session')
  expect(h.runs.slice(n).some((r: any) => r.argv.includes('--no-merges') || r.argv.includes('--merges'))).toBe(false)
  expect(t).toContain('1 Session-Aufgaben')
  expect(t).not.toContain('Git-Aufgaben')
  expect(t).toContain('Quellen: session')
  expect(t).toContain('Hinweis: Session-Aufgaben waren im Pilot verrauschter als Git (Tool-Rauschen wird gefiltert)')
})
test('--sources merge: the fix/revert log is never called, the merge log is', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  const n = h.runs.length
  const t = await run($, '--backfill-only --sources merge')
  const calls = h.runs.slice(n)
  expect(calls.some((r: any) => r.argv.includes('--no-merges'))).toBe(false)
  expect(calls.some((r: any) => r.argv.includes('--merges'))).toBe(true)
  expect(t).toContain('1 Git-Aufgaben (Merges)')
})
test('--sources git,merge --approved: marker carries the sources, run sends only git+merge, resume (reload, rebuilt) keeps them', async ($, on) => {
  const st: { last?: any } = {}
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: jobFor(st) })
  await start($)
  h.reads.length = 0
  await run($, '--backfill-only --sources git,merge --approved')
  expect(h.marker().args.sources).toEqual(['git', 'merge'])
  await idle($, h)
  expect(st.last.items.length).toBe(2)
  expect(h.reads.filter((p: string) => p.startsWith(sessionsDir))).toEqual([])
  expect(h.logs.join('\n')).toContain('Backfill fertig: 2 gesendet')
})
test('default (no --sources) is hybrid: sessions AND git+merge in one run, Quellen (Standard) line, short Hinweis, marker carries the effective sources', async ($, on) => {
  const st: { last?: any } = {}
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: jobFor(st) })
  await start($)
  h.reads.length = 0
  const t = await run($, '--backfill-only')
  expect(h.reads.some((p: string) => p.startsWith(sessionsDir))).toBe(true)
  expect(t.split('\n')).toContain('Quellen: session, git, merge (Standard)')
  expect(t).toContain('Hinweis: Session-Aufgaben waren im Pilot verrauschter als Git (Tool-Rauschen wird gefiltert)')
  expect(t).not.toContain('experimentell')
  expect(t).toContain('1 Session-Aufgaben, 2 Git-Aufgaben')
  expect(h.pending().backfill).toEqual({ days: 90, limit: 100, only: true })
  await run($, '--backfill-only --approved')
  expect(h.marker().args.sources).toEqual(['session', 'git', 'merge'])
  await idle($, h)
  expect(st.last.items.length).toBe(3)
})
test('--sources session,git,merge: all three read and sent, Quellen without (Standard), Hinweis, marker keeps all three', async ($, on) => {
  const st: { last?: any } = {}
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }), backfill: jobFor(st) })
  await start($)
  const t = await run($, '--backfill-only --sources session,git,merge')
  expect(t.split('\n')).toContain('Quellen: session, git, merge')
  expect(t.split('\n')).toContain('Hinweis: Session-Aufgaben waren im Pilot verrauschter als Git (Tool-Rauschen wird gefiltert)')
  expect(t).toContain('1 Session-Aufgaben, 2 Git-Aufgaben')
  await run($, '--backfill-only --sources session,git,merge --approved')
  expect(h.marker().args.sources).toEqual(['session', 'git', 'merge'])
  await idle($, h)
  expect(st.last.items.length).toBe(3)
})
test('bad --sources values: German usage line, nothing stored', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  for (const a of ['--backfill-only --sources', '--backfill-only --sources x', '--backfill-only --sources git,git', '--backfill-only --sources ""', '--backfill-only --sources git,,merge'])
    expect(await run($, a)).toContain('--sources')
  expect(h.pending()).toBe(null)
})
test('--sources without --backfill-only is refused (the legacy bootstrap never runs), as is --target-project; nothing stored, no ace-cli bootstrap', async ($, on) => {
  const h = host(on, { mockClock: true, cli, git, files: base({ [FLAG]: flagOn() }) })
  await start($)
  const n0 = await warm($, h)
  for (const a of ['--sources git', '--sources git,merge --approved', '--target-project prj_abc', '--target-project prj_abc --target-org org_xyz --approved', '--limit 5 --sources session'])
    expect(await run($, a)).toContain('nur mit --backfill-only')
  expect(h.pending()).toBe(null)
  noLegacy(h, n0)
})
