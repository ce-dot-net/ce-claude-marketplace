// 8.2.0 /ace:ace-bootstrap backfill phase, wired through the host: dormant without the flag, honest preview, send after confirm.
import { expect, test } from 'claude-code/testing'
import { CWD, HOME, PROOT, ROOT, host } from './helpers.ts'

const start = ($: any) => $.session.start({ cwd: CWD, surface: null, isInteractive: false } as any)
const run = async ($: any, args = '') => (await $.command.run({ command: 'ace:ace-bootstrap', args })).text as string
const FLAG = `${ROOT}/bootstrap-backfill.json`, ENGINE = `${PROOT}/engine/backfill.js`
const flagOn = (at = 1_800_000_000) => JSON.stringify({ on: true, at })
const JSONL = [
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:00Z', message: { role: 'user', content: 'please fix the crash in the parser module when the input is empty' } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:05Z', message: { role: 'assistant', content: [{ type: 'tool_use', id: 't1', name: 'Edit', input: { file_path: '/proj/src/a.ts', old_string: 'a', new_string: 'b' } }] } },
  { type: 'user', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:06Z', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: 't1', content: 'ok' }] } },
  { type: 'assistant', sessionId: 'sess-a', timestamp: '2026-10-01T10:00:09Z', message: { role: 'assistant', content: [{ type: 'text', text: 'done' }] } },
].map(x => JSON.stringify(x)).join('\n')
const GITLOG = '\x1eaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\x002026-10-02T10:00:00+00:00\x00fix: crash when the config file is empty\x00\x00\nsrc/p.ts\n'
const MERGES = '\x1ebbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\x002026-10-03T10:00:00+00:00\x00Merge pull request #5 from o/b\x00Add the retry queue for failed uploads\x00'
const git = (argv: string[]) => argv.includes('ls-files') ? 'a.ts\n' : argv.includes('rev-list') ? '50\n' : argv.includes('--no-merges') ? GITLOG : argv.includes('--merges') ? MERGES : undefined
const cli = (a: string[]) => a[0] === 'bootstrap' ? { stdout: JSON.stringify({ success: true, patternsExtracted: 3, patternsAfterDedup: 3 }) } : a[0] === 'status' ? { stdout: '{"playbook":{"total_patterns":1}}' } : undefined
const bf = (h: any) => h.runs.filter((r: any) => r.argv[1] === ENGINE)
const base = (extra: Record<string, string> = {}) => ({ [ENGINE]: '//', [`${HOME}/.claude/projects/-proj/s1.jsonl`]: JSONL, ...extra })

test('flag absent: one-line preview, no pending backfill, no engine call even with --approved', async ($, on) => {
  const h = host(on, { cli, git, files: base(), backfill: () => ({ status: 202, body: {} }) })
  await start($)
  const t = await run($)
  expect(t).toContain('Backfill: Server unterstützt es noch nicht')
  expect(t).not.toContain('verlassen den Rechner')
  expect(h.pending().backfill).toBe(undefined)
  await run($, '--approved')
  expect(bf(h).length).toBe(0)
})

test('flag stale (8 days): off', async ($, on) => {
  const h = host(on, { cli, git, files: base({ [FLAG]: flagOn(1_800_000_000 - 8 * 86400) }) })
  await start($)
  expect(await run($)).toContain('Server unterstützt es noch nicht')
  expect(h.pending().backfill).toBe(undefined)
})

test('flag false: off', async ($, on) => {
  const h = host(on, { cli, git, files: base({ [FLAG]: JSON.stringify({ on: false, at: 1_800_000_000 }) }) })
  await start($)
  expect(await run($)).toContain('Server unterstützt es noch nicht')
  expect(h.pending().backfill).toBe(undefined)
})

test('flag on: preview counts, default cap 100, duration, data-leaves sentence; nothing is sent before the confirm', async ($, on) => {
  const h = host(on, { cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => ({ status: 200, body: null }) })
  await start($)
  const t = await run($)
  expect(t).toContain('1 Session-Aufgaben, 2 Git-Aufgaben')
  expect(t).toContain('3 Aufgaben werden gesendet (Limit 100')
  expect(t).toContain('verlassen den Rechner')
  expect(h.pending().backfill).toEqual({ days: 90, limit: 100 })
  expect(bf(h).length).toBe(0)
})

test('--limit N is parsed (and kept out of the CLI argv); bad values are refused', async ($, on) => {
  const h = host(on, { cli, git, files: base({ [FLAG]: flagOn() }) })
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
  const h = host(on, { cli, git, files: base({ [FLAG]: flagOn() }), backfill: (cmd, argv, stdin) => {
    if (cmd === 'post') { last = JSON.parse(stdin!); return { status: 202, body: { job_id: 'j1', accepted: last.items.length, duplicates: 0, status_url: '/u' } } }
    return { status: 200, body: jobItems(last) } } })
  await start($)
  const t = await run($, '--approved')
  expect(t).toContain('Bootstrap fertig')
  expect(t).toContain('Backfill fertig: 3 gesendet')
  expect(t).not.toContain('{')
  const post = bf(h)[0]
  expect(post.argv.slice(2, 4)).toEqual(['post', '--org'])
  expect(post.argv).toContain('prj_t')
  expect(post.argv.join(' ')).not.toMatch(/token|Authorization/i)
  expect(last.source).toBe('bootstrap')
  expect(last.items.length).toBe(3)
  const n = bf(h).length
  const t2 = await run($, '--approved')
  expect(bf(h).length).toBe(n)        // everything is in the ledger now
  expect(t2).toContain('0 Aufgaben')
})

test('approved with 429: stops, stores the resume time, the next run says so without calling the engine', async ($, on) => {
  const h = host(on, { cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => ({ status: 429, body: { limit: 100, current: 100 } }) })
  await start($)
  const t = await run($, '--approved')
  expect(t).toContain('Kontingent')
  const n = bf(h).length
  expect(n).toBe(1)
  expect(await run($, '--approved')).toContain('Kontingent')
  expect(bf(h).length).toBe(n)
})

const stopCase = (a: any, word: string) => async ($: any, on: any) => {
  const h = host(on, { cli, git, files: base({ [FLAG]: flagOn() }), backfill: () => a })
  await start($)
  const t = await run($, '--approved')
  expect(t).toContain('Bootstrap fertig')
  expect(t).toContain(word)
  expect(bf(h).length).toBe(1)
}
test('approved with engine exit 3: Gate line, the bootstrap result stays', stopCase({ exit: 3 }, 'Gate'))
test('approved with 401: login line, the bootstrap result stays', stopCase({ status: 401, body: {} }, 'angemeldet'))

test('a ledger file with a bad signature starts empty (never crashes); the key file is created 0600-style via the private write', async ($, on) => {
  const h = host(on, { cli, git, files: base({ [FLAG]: flagOn(), [`${ROOT}/projects/prj_t/backfill-ledger.tsv`]: 'v1\tgarbage\n\x00' }), backfill: () => ({ status: 429, body: {} }) })
  await start($)
  await run($, '--approved')
  expect(bf(h).length).toBe(1)
  expect(h.files.get(`${ROOT}/backfill.key`)?.length ?? 0).toBeGreaterThanOrEqual(32)
})

const flagFromSearch = (v: any, expected: boolean) => async ($: any, on: any) => {
  const resp = JSON.stringify({ similar_patterns: [], retrieval_id: 'r', ...(v === undefined ? {} : { bootstrap_backfill: v }) })
  host(on, { cli, git, files: base(), search: () => ({ stdout: resp }) })
  await start($)
  await $.prompt.submit({ text: 'please fix the domain shift hook so it injects patterns when reading plugin files', wait: false, origin: { kind: 'composer' } } as any)
  expect((await run($)).includes('Aufgaben werden gesendet')).toBe(expected)
}
test('search response bootstrap_backfill:true switches it on', flagFromSearch(true, true))
test('search response bootstrap_backfill:false stays off', flagFromSearch(false, false))
test('search response bootstrap_backfill:"yes" (non-boolean) stays off', flagFromSearch('yes', false))
test('search response without bootstrap_backfill stays off', flagFromSearch(undefined, false))
